import mbxClient from "@mapbox/mapbox-sdk/lib/client";
import mbxTilesets from "@mapbox/mapbox-sdk/services/tilesets";
import mbxStyles from "@mapbox/mapbox-sdk/services/styles";
import { S3Client, GetObjectCommand } from "@aws-sdk/client-s3";

const eastRecipeTemplate = require("./templates/east.recipe.json");
const westRecipeTemplate = require("./templates/west.recipe.json");
const worldRecipeTemplate = require("./templates/world.recipe.json");
const debug = require("debug")("createTilesets");
const env = require("dotenv").config();

if (env.error && process.env["APP_ENV"] === "local") {
  throw env.error;
}

import {
  formatName,
  datasetFile,
  createTilesetId,
  createTilesetIds,
  createTilesetSourceId,
  setLayersSource,
  sanitizeTilesetName,
  injectStyle,
  wait,
  poll,
  randomBetween,
  parseDataset,
} from "./utils";
import { Recipe, ParsedDataset } from "./types";
import { DATASETS, MethodUsedForMid } from "./configs";
import {
  HIRES_RUNGS,
  PyramidVariant,
  pyramidFileId,
  pyramidDatasetId,
  pyramidSubdir,
  setRungLayers,
  hiResCompositeUrl,
} from "./hires";

const baseClient = mbxClient({ accessToken: process.env["MAPBOX_ACCESS_TOKEN"] });
const geoJSONS3Bucket = process.env["S3_BUCKET_NAME"];
const appEnv = process.env["APP_ENV"];

console.log("App Environment:", appEnv);

const stylesService = mbxStyles(baseClient);
const tilesetsService = mbxTilesets(baseClient);

const mapboxUser = "probablefutures";
const isTilesetPrivate = false;

const debugTilesets = debug.extend("tilesets");

const debugMTSUpload = debugTilesets.extend("upload");
async function uploadTilesetGeoJSONSource(
  datasetId: string,
  datasetVersion: string,
  // Subfolder of data/mapbox/mts (and of the S3 prefix) holding the file. Only the comparison
  // maps use one; it is kept out of `datasetId` because that also becomes the tileset source id,
  // which Mapbox rejects if it contains a slash.
  subdir = "",
) {
  debugMTSUpload("input %i", datasetId);
  let fileStream;

  if (appEnv === "local") {
    fileStream = datasetFile(datasetId, subdir);
  } else {
    const prefix = subdir ? `${subdir}/` : "";
    const key = `climate-data-geojson/v${datasetVersion}/${prefix}${datasetId}.geojsonld`;
    const s3Client = new S3Client({});

    try {
      const { Body } = await s3Client.send(
        new GetObjectCommand({
          Bucket: geoJSONS3Bucket,
          Key: key,
        }),
      );
      if (!Body) {
        throw Error("File does not exist");
      }
      fileStream = Body;
    } catch (error) {
      console.error("Error fetching file from S3:", error);
      throw new Error(`Could not fetch file from S3: ${geoJSONS3Bucket}/${key}`);
    }
  }
  const { body, statusCode } = await tilesetsService
    .createTilesetSource({
      id: createTilesetSourceId(datasetId),
      file: fileStream,
      ownerId: mapboxUser,
    })
    .send();
  debugMTSUpload("response %O", { body, statusCode });
  return body;
}

type RecipeResponse = { body: any; recipe: Recipe };
const debugMTSValidate = debugTilesets.extend("validate");
async function createRecipe(source: string, { version, layers }): Promise<RecipeResponse> {
  debugMTSValidate("input %O", { source, version, layers });
  const recipe = { layers: setLayersSource({ layers, source }), version };
  const { body, statusCode } = await tilesetsService.validateRecipe({ recipe }).send();
  debugMTSValidate("response %O", { body, statusCode });
  return { body, recipe };
}

function appendMeanOrMedianToRecipe(recipeTemplate, methodUsedForMid?: MethodUsedForMid) {
  const additionalOutput =
    methodUsedForMid === "mean"
      ? [
          "data_baseline_median",
          "data_1c_median",
          "data_1_5c_median",
          "data_2c_median",
          "data_2_5c_median",
          "data_3c_median",
        ]
      : [
          "data_baseline_mean",
          "data_1c_mean",
          "data_1_5c_mean",
          "data_2c_mean",
          "data_2_5c_mean",
          "data_3c_mean",
        ];
  Object.values(recipeTemplate.layers).forEach((layer: any) => {
    const allowedOutput = layer.features.attributes.allowed_output;
    additionalOutput.forEach((val) => {
      if (!allowedOutput.includes(val)) {
        allowedOutput.push(val);
      }
    });
  });
  return recipeTemplate;
}

async function createRecipes(
  tilesetSourceId: string,
): Promise<{ east: RecipeResponse; west: RecipeResponse }> {
  const [east, west] = await Promise.all([
    createRecipe(tilesetSourceId, eastRecipeTemplate),
    createRecipe(tilesetSourceId, westRecipeTemplate),
  ]);
  return { east, west };
}

const debugMTSCreate = debugTilesets.extend("create");
async function createTileset({
  name,
  recipe,
  tilesetId,
}: {
  name: string;
  recipe: Recipe;
  tilesetId: string;
}) {
  debugMTSCreate("input %O", { name, tilesetId });
  const { body, statusCode } = await tilesetsService
    .createTileset({ name: sanitizeTilesetName(name), recipe, tilesetId, private: isTilesetPrivate })
    .send();
  debugMTSCreate("createTileset:response %O", { body, statusCode });
  return body;
}

async function createTilesets({
  dataset: { id, model, version },
  east,
  west,
  suffix = "",
}: {
  dataset: ParsedDataset;
  east: RecipeResponse;
  west: RecipeResponse;
  suffix?: string;
}) {
  const { eastId, westId } = createTilesetIds(id, version, suffix);
  await Promise.all([
    createTileset({
      tilesetId: eastId,
      name: formatName({ name: `${id} - East`, model, version, suffix }),
      recipe: east.recipe,
    }),
    createTileset({
      tilesetId: westId,
      name: formatName({ name: `${id} - West`, model, version, suffix }),
      recipe: west.recipe,
    }),
  ]);
}

const debugMTSPublish = debugTilesets.extend("publish");
async function publishTileset(tilesetId: string) {
  debugMTSPublish("publishTileset:input %O", { tilesetId });
  const { body, statusCode } = await tilesetsService.publishTileset({ tilesetId }).send();
  debugMTSPublish("publishTileset:response %O", { body, statusCode });
  return body;
}

async function publishTilesets(datasetId: string, version: string, suffix = "") {
  const { eastId, westId } = createTilesetIds(datasetId, version, suffix);
  const [{ jobId: eastJobId }, { jobId: westJobId }] = await Promise.all([
    publishTileset(eastId),
    publishTileset(westId),
  ]);
  return { eastJobId, westJobId };
}

function retryJobStatus(tilesetId: string): ({ statusCode, body }: any) => boolean {
  return ({ statusCode, body }) => {
    debugMTSJobs("retryJobStatus:input %O", { statusCode, body, tilesetId });
    if (statusCode >= 200 && statusCode < 300) {
      const { stage } = body;
      switch (stage) {
        case "queued":
          debugMTSJobs("retryJobStatus:queued %s", tilesetId);
          return true;
        case "processing":
          debugMTSJobs("retryJobStatus:processing %s", tilesetId);
          return true;
        case "failed":
          debugMTSJobs("retryJobStatus:failed %s", tilesetId);
          console.error("failed: %s", tilesetId);
          return false;
        case "success":
          debugMTSJobs("retryJobStatus:success %s", tilesetId);
          return false;
        default:
          console.error("!default case! %s", tilesetId);
          return false;
      }
    }
    return false;
  };
}

const debugMTSJobs = debugTilesets.extend("jobs");
async function waitForTilesetJob({ jobId, tilesetId, retryAfter }) {
  debugMTSJobs("input %O", { jobId, tilesetId, retryAfter });
  const { status, body } = await poll(
    () => tilesetsService.tilesetJob({ jobId, tilesetId }).send(),
    retryJobStatus(tilesetId),
    retryAfter,
  );
  debugMTSJobs("response %O", { status, body });
  return body;
}

async function waitForTilesetJobs({
  eastJobId,
  westJobId,
  datasetId,
  retryAfter,
  version,
  suffix = "",
}) {
  const { eastId, westId } = createTilesetIds(datasetId, version, suffix);
  const [eastJob, westJob] = await Promise.all([
    waitForTilesetJob({ jobId: eastJobId, tilesetId: eastId, retryAfter }),
    waitForTilesetJob({ jobId: westJobId, tilesetId: westId, retryAfter: retryAfter + 20 }),
  ]);
  return { eastJob, westJob };
}

const debugStyles = debug.extend("styles");
async function createStyle({ id, name, model, version, map }: ParsedDataset, suffix = "") {
  debugStyles("input %O", { id, name });
  if (!version) {
    throw Error(`Please set a version for dataset ${id} in the configs.ts file.`);
  }
  let style;
  if (model.grid === "GCM") {
    const tilesetId = createTilesetId(id, suffix);
    style = injectStyle({
      tilesetId,
      name: formatName({ name, version, suffix }),
    });
    debugStyles("%O", { id: tilesetId, style });
  } else {
    const { eastId, westId } = createTilesetIds(id, version, suffix);
    style = injectStyle({
      tilesetEastId: eastId,
      tilesetWestId: westId,
      name: formatName({ name, version, suffix }),
      map,
    });
    debugStyles("%O", { eastId, westId, style });
  }
  const { body, statusCode } = await stylesService.createStyle({ style }).send();
  debugStyles("response %O", { body, statusCode });
  return body;
}

async function processDataset(dataset: ParsedDataset, suffix = "") {
  console.log(`${dataset.id}: Starting tileset creation...\n`);

  // Stagger requests to avoid rate limiting
  // await wait(randomBetween(500, 5000));

  console.log(`${dataset.id}: Uploading GeoJSON tileset source...\n`);
  const { id: sourceId } = await uploadTilesetGeoJSONSource(dataset.id, dataset.version);

  console.log(`${dataset.id}: Validating recipes...\n`);
  console.log("");

  let recipes;
  if (dataset.model.grid === "GCM") {
    recipes = await createRecipe(sourceId, worldRecipeTemplate);
  } else {
    recipes = await createRecipes(sourceId);
  }

  console.log(`${dataset.id}: Creating tilesets...\n`);

  if (recipes.east && recipes.west) {
    const { east, west } = recipes;
    await createTilesets({ dataset, east, west, suffix });
  } else {
    await createTileset({
      tilesetId: createTilesetId(dataset.id, suffix),
      name: formatName({
        name: dataset.id,
        model: dataset.model,
        version: dataset.version,
        suffix,
      }),
      recipe: recipes.recipe,
    });
  }

  // Sometimes we try to publish a tileset too quickly after it's created
  // and mapbox hasn't had time to tell all it's servers and dbs about it.
  // So we wait for 5 seconds to give them time to catch up
  await wait(5000);

  console.log(`${dataset.id}: Publishing tilesets...\n`);
  let jobIds;
  if (dataset.model.grid === "GCM") {
    jobIds = await publishTileset(createTilesetId(dataset.id, suffix));
  } else {
    jobIds = await publishTilesets(dataset.id, dataset.version, suffix);
  }

  console.log(`${dataset.id}: Waiting on tileset jobs to finish...\n`);
  const retryAfter = randomBetween(2000, 5000);

  if (jobIds.eastJobId && jobIds.westJobId) {
    const { eastJobId, westJobId } = jobIds;
    await waitForTilesetJobs({
      retryAfter,
      datasetId: dataset.id,
      eastJobId,
      westJobId,
      version: dataset.version,
      suffix,
    });
  } else {
    await waitForTilesetJob({
      jobId: jobIds.jobId,
      tilesetId: createTilesetId(dataset.id, suffix),
      retryAfter,
    });
  }

  console.log(`${dataset.id}: Creating map style...\n`);
  await createStyle(dataset, suffix);

  console.log(`${dataset.id}: Finished!\n`);
}

// Hi-res path: build the resolution pyramid (docs §8). Uploads one source per rung, creates
// an east+west tileset per rung (same layer keys, disjoint zoom bands), publishes them, and
// creates ONE style compositing all rungs. Requires the `<id>-hires[-pNN].geojsonld` files
// from `hires-maps pyramid <slug>`. Publishes under a `-hires` id namespace — production
// tilesets are never touched.
// Mapbox signals "this tileset id is taken" inconsistently: observed as a 400 whose message is
// "<id> already exists" (and documented as 409 elsewhere). Match on both.
function isAlreadyExists(err: any): boolean {
  const message = err?.body?.message ?? err?.message ?? "";
  return err?.statusCode === 409 || /already exists/i.test(message);
}

// Idempotent: re-running a build reuses an existing tileset instead of failing — we update its
// recipe (pointing it at the freshly uploaded source) and publish as usual.
async function createOrUpdateTileset(args: { name: string; recipe: Recipe; tilesetId: string }) {
  try {
    return await createTileset(args);
  } catch (err: any) {
    if (isAlreadyExists(err)) {
      console.log(`  ${args.tilesetId} exists — updating its recipe instead\n`);
      const { body } = await tilesetsService
        .updateRecipe({ tilesetId: args.tilesetId, recipe: args.recipe })
        .send();
      return body;
    }
    throw err;
  }
}

// Publishing is heavily rate limited (429) — 8 tilesets fired back-to-back trips it. Publish one
// at a time, with a gap between calls and exponential backoff when we do get limited.
const PUBLISH_GAP_MS = 8000;
async function publishTilesetThrottled(tilesetId: string, attempts = 6) {
  for (let attempt = 0; ; attempt++) {
    try {
      return await publishTileset(tilesetId);
    } catch (err: any) {
      if (err?.statusCode !== 429 || attempt >= attempts - 1) throw err;
      const backoff = 20000 * 2 ** attempt; // 20s, 40s, 80s, ...
      console.log(
        `  rate limited publishing ${tilesetId} — retrying in ${backoff / 1000}s ` +
          `(attempt ${attempt + 2}/${attempts})\n`,
      );
      await wait(backoff);
    }
  }
}

// `idSuffix` is the caller-supplied --suffix, appended to every tileset id and to the style name
// so a re-run can publish a fresh set instead of colliding with an existing one.
// `publishOnly` skips the (slow, ~1.5 GB) source upload and tileset creation and just re-publishes
// the existing tilesets + creates the style — the cheap way to recover from a mid-run failure.
// `variant` picks which pyramid to publish: the new data (`hires`) or the new-minus-live comparison
// map (`diff`). The two are identical pipelines over different `.geojsonld` files; only the ids,
// the style name and the colour ramp differ.
async function processHiResDataset(
  dataset: ParsedDataset,
  idSuffix = "",
  publishOnly = false,
  variant: PyramidVariant = "hires",
) {
  const { id, version, model } = dataset;
  if (model.grid === "GCM") {
    throw Error(`--hi-res currently supports RCM (east/west) datasets; ${id} is GCM.`);
  }
  // Comparison maps are signed around zero, so they need the diverging ramp, not the climate one.
  const map = variant === "diff" ? dataset.diffMap : dataset.map;
  if (variant === "diff" && !map) {
    throw Error(
      `${id}: --diff needs a \`diffMap\` palette in configs.ts (diverging stops + colours).`,
    );
  }
  const label = variant === "diff" ? "diff" : "hi-res";
  const rungIds = (rung: (typeof HIRES_RUNGS)[number]) =>
    createTilesetIds(pyramidDatasetId(id, rung, variant), version, idSuffix);

  if (publishOnly) {
    console.log(`${id}: [${label}] --publish-only: skipping source upload + tileset creation\n`);
  } else {
    console.log(`${id}: [${label}] uploading ${HIRES_RUNGS.length} rung sources...\n`);
    const sourceByRung: Record<string, string> = {};
    for (const rung of HIRES_RUNGS) {
      const { id: sourceId } = await uploadTilesetGeoJSONSource(
        pyramidFileId(id, rung, variant),
        version,
        pyramidSubdir(variant),
      );
      sourceByRung[rung.suffix] = sourceId;
    }

    console.log(`${id}: [${label}] validating + creating ${HIRES_RUNGS.length * 2} tilesets...\n`);
    for (const rung of HIRES_RUNGS) {
      const source = sourceByRung[rung.suffix];
      const { eastId, westId } = rungIds(rung);
      const eastRecipe: Recipe = {
        version: eastRecipeTemplate.version,
        layers: setRungLayers(eastRecipeTemplate.layers, source, rung),
      };
      const westRecipe: Recipe = {
        version: westRecipeTemplate.version,
        layers: setRungLayers(westRecipeTemplate.layers, source, rung),
      };
      await Promise.all([
        tilesetsService.validateRecipe({ recipe: eastRecipe }).send(),
        tilesetsService.validateRecipe({ recipe: westRecipe }).send(),
      ]);
      await createOrUpdateTileset({
        tilesetId: eastId,
        name: formatName({
          name: `${id} ${label} ${rung.label}° East`,
          model,
          version,
          suffix: idSuffix,
        }),
        recipe: eastRecipe,
      });
      await createOrUpdateTileset({
        tilesetId: westId,
        name: formatName({
          name: `${id} ${label} ${rung.label}° West`,
          model,
          version,
          suffix: idSuffix,
        }),
        recipe: westRecipe,
      });
    }

    await wait(5000);
  }

  const allIds = HIRES_RUNGS.flatMap((rung) => {
    const { eastId, westId } = rungIds(rung);
    return [eastId, westId];
  });

  console.log(`${id}: [${label}] publishing ${allIds.length} tilesets (throttled)...\n`);
  const retryAfter = randomBetween(2000, 5000);
  const jobs: Array<{ jobId: string; tilesetId: string }> = [];
  for (const [i, tilesetId] of allIds.entries()) {
    if (i > 0) await wait(PUBLISH_GAP_MS);
    const { jobId } = await publishTilesetThrottled(tilesetId);
    console.log(`  published ${i + 1}/${allIds.length}: ${tilesetId}\n`);
    jobs.push({ jobId, tilesetId });
  }
  console.log(`${id}: [${label}] waiting on ${jobs.length} tileset jobs...\n`);
  await Promise.all(
    jobs.map((job, i) => waitForTilesetJob({ ...job, retryAfter: retryAfter + i * 10 })),
  );

  console.log(`${id}: [${label}] creating composited style...\n`);
  const eastIds = HIRES_RUNGS.map((r) => rungIds(r).eastId);
  const westIds = HIRES_RUNGS.map((r) => rungIds(r).westId);
  const style = injectStyle({
    tilesetEastId: eastIds[0],
    tilesetWestId: westIds[0],
    name: formatName({ name: `${id} ${label}`, version, suffix: idSuffix }),
    map,
  });
  // Composite every rung so Mapbox serves the right resolution at each zoom.
  (style.sources as any).composite.url = hiResCompositeUrl(eastIds, westIds);
  const { body } = await stylesService.createStyle({ style }).send();
  console.log(`  style id: ${body.id}  (put this in datasets.ts mapStyleId)\n`);

  console.log(`${id}: [${label}] finished!\n`);
}

async function processSerial(
  datasets: ParsedDataset[],
  hiRes: boolean,
  suffix: string,
  publishOnly = false,
  variant: PyramidVariant = "hires",
) {
  for await (const dataset of datasets) {
    await (hiRes
      ? processHiResDataset(dataset, suffix, publishOnly, variant)
      : processDataset(dataset, suffix));
  }
}

// TODO: Parallelize and ride rate limit
async function processParallel(datasets: ParsedDataset[], suffix = "") {
  await Promise.all(datasets.map((dataset) => processDataset(dataset, suffix)));
}

export async function start(
  datasetIds: string[],
  version?: string,
  hiRes = false,
  /** Appended to every tileset id and to the style name (the --suffix CLI arg). */
  suffix = "",
  /** Hi-res only: skip upload + create, just publish existing tilesets (--publish-only). */
  publishOnly = false,
  /** Which pyramid to publish: the new data ("hires") or the comparison map ("diff"). */
  variant: PyramidVariant = "hires",
): Promise<void> {
  try {
    if (datasetIds.length === 0) {
      console.log("\nNo datasets provided. Please pass dataset IDs as arguments.\n");
      return;
    }

    const datasets = DATASETS.map((dataset) => parseDataset(dataset, version)).filter(({ id }) =>
      datasetIds.includes(id),
    );

    console.log(
      "\nCreating %s tilesets%s for %O \n",
      hiRes ? (variant === "diff" ? "comparison (diff)" : "hi-res") : "standard",
      suffix ? ` (suffix "${suffix}")` : "",
      datasets,
    );

    await processSerial(datasets, hiRes, suffix, publishOnly, variant);
    // await processParallel(datasets, suffix);

    console.log("Finished tileset creation");
  } catch (error) {
    console.error("\n=+=+===+=+=+=+=+=+=FAILED=+=+===+=+=+=+=+=+=\n");
    console.error("%O", error);
    throw error;
  }
}

// Allow running as a standalone script. NOTE: via npm you must pass `--` first, otherwise npm
// swallows the flags:  npm run create-tilesets -- 40105 --hi-res --suffix=-3
//
//   ts-node createTilesets.ts 40105                                    # standard
//   ts-node createTilesets.ts 40105 --hi-res                           # resolution pyramid
//   ts-node createTilesets.ts 40105 --hi-res --suffix=-3               # fresh ids + style name
//   ts-node createTilesets.ts 40105 --hi-res --suffix=-3 --publish-only  # resume after a failure
//   ts-node createTilesets.ts 40105 --diff                             # comparison map (new - live)
//
// --diff publishes the comparison pyramid (`{id}-diff*.geojsonld` from `hires-maps diff-pyramid`)
// with the diverging red/blue ramp from the config's `diffMap`. It implies --hi-res: a comparison
// map is the same three rungs over the same 0.1° grid.
//
// --suffix is appended to every tileset id AND to the style name. Use it to publish a new set
// without colliding with tilesets you already created (Mapbox rejects duplicate ids).
// Re-running the same suffix is safe: an existing tileset has its recipe updated instead.
// --publish-only skips the slow source upload + tileset creation and just publishes what exists.
if (require.main === module) {
  const args = process.argv.slice(2);
  const isDiff = args.includes("--diff");
  const hiRes = args.includes("--hi-res") || isDiff; // a comparison map is always a pyramid
  const publishOnly = args.includes("--publish-only");
  const suffixArg = args.find((a) => a.startsWith("--suffix"));
  const suffix = suffixArg ? (suffixArg.split("=")[1] ?? "") : "";
  const datasetIds = args.filter((a) => !a.startsWith("--"));
  start(datasetIds, undefined, hiRes, suffix, publishOnly, isDiff ? "diff" : "hires")
    .then(() => process.exit(0))
    .catch(() => process.exit(1));
}
