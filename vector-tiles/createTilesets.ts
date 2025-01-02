import mbxClient from "@mapbox/mapbox-sdk/lib/client";
import mbxTilesets from "@mapbox/mapbox-sdk/services/tilesets";
import mbxStyles from "@mapbox/mapbox-sdk/services/styles";
import { S3Client, GetObjectCommand } from "@aws-sdk/client-s3";

const eastRecipeTemplate = require("./templates/east.recipe.json");
const westRecipeTemplate = require("./templates/west.recipe.json");
const worldRecipeTemplate = require("./templates/world.recipe.json");
const debug = require("debug")("createTilesets");
// const env = require("dotenv").config();

// if (env.error) {
//   throw env.error;
// }

import {
  formatName,
  datasetFile,
  createTilesetId,
  createTilesetIds,
  createTilesetSourceId,
  setLayersSource,
  injectStyle,
  wait,
  poll,
  randomBetween,
  parseDataset,
} from "./utils";
import { Recipe, ParsedDataset } from "./types";
import { DATASETS } from "./configs";

const baseClient = mbxClient({ accessToken: process.env["MAPBOX_ACCESS_TOKEN"] });
const geoJSONS3Bucket = process.env["S3_BUCKET_NAME"];
const appEnv = process.env["APP_ENV"];

const stylesService = mbxStyles(baseClient);
const tilesetsService = mbxTilesets(baseClient);

const mapboxUser = "probablefutures";
const isTilesetPrivate = false;

const debugTilesets = debug.extend("tilesets");

const debugMTSUpload = debugTilesets.extend("upload");
async function uploadTilesetGeoJSONSource(datasetId: string) {
  debugMTSUpload("input %i", datasetId);
  let fileStream;

  if (appEnv === "local") {
    fileStream = datasetFile(datasetId);
  } else {
    const key = `climate-data-geojson/${datasetId}.geojsonld`;
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
    .createTileset({ name, recipe, tilesetId, private: isTilesetPrivate })
    .send();
  debugMTSCreate("createTileset:response %O", { body, statusCode });
  return body;
}

async function createTilesets({
  dataset: { id, model, version },
  east,
  west,
}: {
  dataset: ParsedDataset;
  east: RecipeResponse;
  west: RecipeResponse;
}) {
  const { eastId, westId } = createTilesetIds(id, version);
  await Promise.all([
    createTileset({
      tilesetId: eastId,
      name: formatName({ name: `${id} - East`, model, version }),
      recipe: east.recipe,
    }),
    createTileset({
      tilesetId: westId,
      name: formatName({ name: `${id} - West`, model, version }),
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

async function publishTilesets(datasetId: string, version: string) {
  const { eastId, westId } = createTilesetIds(datasetId, version);
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

async function waitForTilesetJobs({ eastJobId, westJobId, datasetId, retryAfter, version }) {
  const { eastId, westId } = createTilesetIds(datasetId, version);
  const [eastJob, westJob] = await Promise.all([
    waitForTilesetJob({ jobId: eastJobId, tilesetId: eastId, retryAfter }),
    waitForTilesetJob({ jobId: westJobId, tilesetId: westId, retryAfter: retryAfter + 20 }),
  ]);
  return { eastJob, westJob };
}

const debugStyles = debug.extend("styles");
async function createStyle({ id, name, model, version, map }: ParsedDataset) {
  debugStyles("input %O", { id, name });
  if (!version) {
    throw Error(`Please set a version for dataset ${id} in the configs.ts file.`);
  }
  let style;
  if (model.grid === "GCM") {
    const tilesetId = createTilesetId(id);
    style = injectStyle({
      tilesetId,
      name: formatName({ name, version }),
    });
    debugStyles("%O", { id: tilesetId, style });
  } else {
    const { eastId, westId } = createTilesetIds(id, version);
    style = injectStyle({
      tilesetEastId: eastId,
      tilesetWestId: westId,
      name: formatName({ name, version }),
      map,
    });
    debugStyles("%O", { eastId, westId, style });
  }
  const { body, statusCode } = await stylesService.createStyle({ style }).send();
  debugStyles("response %O", { body, statusCode });
  return body;
}

async function processDataset(dataset: ParsedDataset) {
  console.log(`${dataset.id}: Starting tileset creation...\n`);

  // Stagger requests to avoid rate limiting
  // await wait(randomBetween(500, 5000));

  console.log(`${dataset.id}: Uploading GeoJSON tileset source...\n`);
  const { id: sourceId } = await uploadTilesetGeoJSONSource(dataset.id);

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
    await createTilesets({ dataset, east, west });
  } else {
    await createTileset({
      tilesetId: createTilesetId(dataset.id),
      name: formatName({ name: dataset.id, model: dataset.model, version: dataset.version }),
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
    jobIds = await publishTileset(createTilesetId(dataset.id));
  } else {
    jobIds = await publishTilesets(dataset.id, dataset.version);
  }

  console.log(`${dataset.id}: Waiting on tileset jobs to finish...\n`);
  if (jobIds.eastJobId && jobIds.westJobId) {
    const { eastJobId, westJobId } = jobIds;
    await waitForTilesetJobs({
      // Using a random retry time here to prevent rate limiting when these
      // requests are run in parallel.
      retryAfter: randomBetween(2000, 5000),
      datasetId: dataset.id,
      eastJobId,
      westJobId,
      version: dataset.version,
    });
  } else {
    await waitForTilesetJob({
      jobId: jobIds.jobId,
      tilesetId: createTilesetId(dataset.id),
      retryAfter: randomBetween(2000, 5000),
    });
  }

  console.log(`${dataset.id}: Creating map style...\n`);
  const body = await createStyle(dataset);

  console.log(`${dataset.id}: Finished!\n`);
}

async function processSerial(datasets: ParsedDataset[]) {
  for await (const dataset of datasets) {
    await processDataset(dataset);
  }
}

// TODO: Parallelize and ride rate limit
async function processParallel(datasets: ParsedDataset[]) {
  await Promise.all(datasets.map(processDataset));
}

export async function start(datasetIds: string[], version?: string): Promise<void> {
  try {
    if (datasetIds.length === 0) {
      console.log("\nNo datasets provided. Please pass dataset IDs as arguments.\n");
      return;
    }

    const datasets = DATASETS.map((dataset) => parseDataset(dataset, version)).filter(({ id }) =>
      datasetIds.includes(id),
    );

    console.log("\nCreating tilesets for %O \n", datasets);

    await processSerial(datasets);
    // await processParallel(datasets);

    console.log("Finished tileset creation");
  } catch (error) {
    console.error("\n=+=+===+=+=+=+=+=+=FAILED=+=+===+=+=+=+=+=+=\n");
    console.error("%O", error);
    throw error;
  }
}

// Allow running as a standalone script
if (require.main === module) {
  const datasetIds = process.argv.slice(2);
  start(datasetIds)
    .then(() => process.exit(0))
    .catch(() => process.exit(1));
}
