import mbxClient from "@mapbox/mapbox-sdk/lib/client";
import mbxTilesets from "@mapbox/mapbox-sdk/services/tilesets";

const eastRecipeTemplate = require("./templates/east.recipe.json");
const westRecipeTemplate = require("./templates/west.recipe.json");
const zoom1RecipeTemplate = require("./templates/zoom1.recipe.json");
const debug = require("debug")("createTilesets");
const env = require("dotenv").config();

if (env.error) {
  throw env.error;
}

import {
  formatName,
  datasetFile,
  datasetZoom1File,
  createTilesetIds,
  createZoom1TilesetId,
  createTilesetSourceId,
  setLayersSource,
  wait,
  poll,
  randomBetween,
  parseDataset,
} from "./utils";

import { Unit, Recipe, ParsedDataset, ModelGrid } from "./types";
import { DATASETS } from "./configs";

const baseClient = mbxClient({ accessToken: process.env["MAPBOX_ACCESS_TOKEN"] });
const tilesetsService = mbxTilesets(baseClient);

const mapboxUser = "probablefutures";

const debugTilesets = debug.extend("tilesets");

const debugMTSUpload = debugTilesets.extend("upload");
async function uploadTilesetGeoJSONSource(datasetId: string, zoom1 = false) {
  const suffix = zoom1 ? "-zoom1" : "";
  debugMTSUpload("input %i%s", datasetId, suffix);
  const file = zoom1 ? datasetZoom1File(datasetId) : datasetFile(datasetId);
  const { body, statusCode } = await tilesetsService
    .createTilesetSource({
      id: createTilesetSourceId(`${datasetId}${suffix}`),
      file,
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

const debugMTSUpdate = debugTilesets.extend("update");
async function updateTileset({
  name,
  recipe,
  tilesetId,
}: {
  name: string;
  recipe: Recipe;
  tilesetId: string;
}) {
  debugMTSUpdate("input %O", { name, tilesetId });
  const { body, statusCode } = await tilesetsService.updateRecipe({ recipe, tilesetId }).send();
  debugMTSUpdate("updateTileset:response %O", { body, statusCode });
  return body;
}

async function updateTilesets({
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
    updateTileset({
      tilesetId: eastId,
      name: formatName({ name: `${id} - East`, model, version }),
      recipe: east.recipe,
    }),
    updateTileset({
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

async function processDataset(dataset: ParsedDataset) {
  console.log(`${dataset.id}: Starting tileset update...\n`);

  // Stagger requests to avoid rate limiting
  // await wait(randomBetween(500, 5000));

  console.log(`${dataset.id}: Uploading GeoJSON tileset source...\n`);
  const { id: sourceId } = await uploadTilesetGeoJSONSource(dataset.id);

  console.log(`${dataset.id}: Validating recipes...\n`);
  console.log("");

  const recipes = await createRecipes(sourceId);

  console.log(`${dataset.id}: Updating tilesets...\n`);

  if (recipes.east && recipes.west) {
    const { east, west } = recipes;
    await updateTilesets({ dataset, east, west });
  }

  // Update zoom-1 tileset for RCM datasets
  if (dataset.model.grid === ModelGrid.RCM) {
    console.log(`${dataset.id}: Uploading zoom-1 GeoJSON tileset source...\n`);
    const { id: zoom1SourceId } = await uploadTilesetGeoJSONSource(dataset.id, true);

    console.log(`${dataset.id}: Validating zoom-1 recipe...\n`);
    const zoom1Recipe = await createRecipe(zoom1SourceId, zoom1RecipeTemplate);

    console.log(`${dataset.id}: Updating zoom-1 tileset...\n`);
    const zoom1TilesetId = createZoom1TilesetId(dataset.id, dataset.version);
    await updateTileset({
      tilesetId: zoom1TilesetId,
      name: formatName({ name: `${dataset.id} - Zoom1`, model: dataset.model, version: dataset.version }),
      recipe: zoom1Recipe.recipe,
    });
  }

  // Sometimes we try to publish a tileset to quickly after it's created
  // and mapbox hasn't had time to tell all it's serves and dbs about it.
  // So we wait for 5 seconds to give them time to catch up
  await wait(5000);

  console.log(`${dataset.id}: Publishing tilesets...\n`);
  const jobIds = await publishTilesets(dataset.id, dataset.version);

  // Publish zoom-1 tileset
  let zoom1JobId: string | undefined;
  if (dataset.model.grid === ModelGrid.RCM) {
    console.log(`${dataset.id}: Publishing zoom-1 tileset...\n`);
    const zoom1TilesetId = createZoom1TilesetId(dataset.id, dataset.version);
    const { jobId } = await publishTileset(zoom1TilesetId);
    zoom1JobId = jobId;
  }

  console.log(`${dataset.id}: Waiting on tileset jobs to finish...\n`);
  if (jobIds.eastJobId && jobIds.westJobId) {
    const { eastJobId, westJobId } = jobIds;
    const retryAfter = randomBetween(2000, 5000);
    const jobPromises: Promise<any>[] = [
      waitForTilesetJobs({
        retryAfter,
        datasetId: dataset.id,
        eastJobId,
        westJobId,
        version: dataset.version,
      }),
    ];

    if (zoom1JobId) {
      jobPromises.push(
        waitForTilesetJob({
          jobId: zoom1JobId,
          tilesetId: createZoom1TilesetId(dataset.id, dataset.version),
          retryAfter: retryAfter + 40,
        }),
      );
    }

    await Promise.all(jobPromises);
  }
}

const datasets = DATASETS.map((dataset) => parseDataset(dataset)).filter(
  ({ id }) => id === "40601",
);

async function processSerial(ds: ParsedDataset[]) {
  for await (const dataset of datasets) {
    await processDataset(dataset);
  }
}

(async function () {
  try {
    console.log("\nUpdating tilesets for %O \n", datasets);

    await processSerial(datasets);

    console.log("Finished updating tileset");
  } catch (error) {
    console.error("\n=+=+===+=+=+=+=+=+=FAILED=+=+===+=+=+=+=+=+=\n");
    console.error("%O", error);

    process.exit(1);
  } finally {
    process.exit(0);
  }
})();
