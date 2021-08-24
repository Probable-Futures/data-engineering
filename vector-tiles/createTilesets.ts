import mbxClient from "@mapbox/mapbox-sdk/lib/client";
import mbxTilesets from "@mapbox/mapbox-sdk/services/tilesets";
import mbxStyles from "@mapbox/mapbox-sdk/services/styles";

const eastRecipeTemplate = require("./templates/east.recipe.json");
const westRecipeTemplate = require("./templates/west.recipe.json");
const debug = require("debug")("createTilesets");

import {
  formatName,
  datasetFile,
  createTilesetIds,
  createTilesetSourceId,
  setLayersSource,
  injectStyle,
  wait,
  poll,
  randomBetween,
  parseDataset,
} from "./utils";

import { Unit, Recipe, ParsedDataset } from "./types";

const baseClient = mbxClient({ accessToken: process.env["MAPBOX_ACCESS_TOKEN"] });
const stylesService = mbxStyles(baseClient);
const tilesetsService = mbxTilesets(baseClient);

const mapboxUser = "probablefutures";

const debugTilesets = debug.extend("tilesets");

const debugMTSUpload = debugTilesets.extend("upload");
async function uploadTilesetGeoJSONSource(datasetId: string) {
  debugMTSUpload("input %i", datasetId);
  const { body, statusCode } = await tilesetsService
    .createTilesetSource({
      id: createTilesetSourceId(datasetId),
      file: datasetFile(datasetId),
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
    .createTileset({ name, recipe, tilesetId })
    .send();
  debugMTSCreate("createTileset:response %O", { body, statusCode });
  return body;
}

async function createTilesets({
  dataset: { id, model },
  east,
  west,
}: {
  dataset: ParsedDataset;
  east: RecipeResponse;
  west: RecipeResponse;
}) {
  const { eastId, westId } = createTilesetIds(id);
  await Promise.all([
    createTileset({
      tilesetId: eastId,
      name: formatName({ name: `${id} - East`, model }),
      recipe: east.recipe,
    }),
    createTileset({
      tilesetId: westId,
      name: formatName({ name: `${id} - West`, model }),
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

async function publishTilesets(datasetId: string) {
  const { eastId, westId } = createTilesetIds(datasetId);
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

async function waitForTilesetJobs({ eastJobId, westJobId, datasetId, retryAfter }) {
  const { eastId, westId } = createTilesetIds(datasetId);
  const [eastJob, westJob] = await Promise.all([
    waitForTilesetJob({ jobId: eastJobId, tilesetId: eastId, retryAfter }),
    waitForTilesetJob({ jobId: westJobId, tilesetId: westId, retryAfter: retryAfter + 20 }),
  ]);
  return { eastJob, westJob };
}

const debugStyles = debug.extend("styles");
async function createStyle({ id, name, model }: ParsedDataset) {
  debugStyles("input %O", { id, name });
  const { eastId, westId } = createTilesetIds(id);
  const style = injectStyle({
    tilesetEastId: eastId,
    tilesetWestId: westId,
    name: formatName({ name, model }),
  });
  debugStyles("%O", { eastId, westId, style });
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
  const { east, west } = await createRecipes(sourceId);

  console.log(`${dataset.id}: Creating tilesets...\n`);
  await createTilesets({ dataset, east, west });

  // Sometimes we try to publish a tileset to quickly after it's created
  // and mapbox hasn't had time to tell all it's serves and dbs about it.
  // So we wait for 5 seconds to give them time to catch up
  await wait(5000);

  console.log(`${dataset.id}: Publishing tilesets...\n`);
  const { eastJobId, westJobId } = await publishTilesets(dataset.id);

  console.log(`${dataset.id}: Waiting on tileset jobs to finish...\n`);
  await waitForTilesetJobs({
    // Using a random retry time here to prevent rate limiting when these
    // requests are run in parallel.
    retryAfter: randomBetween(2000, 5000),
    datasetId: dataset.id,
    eastJobId,
    westJobId,
  });

  console.log(`${dataset.id}: Creating map style...\n`);
  await createStyle(dataset);

  console.log(`${dataset.id}: Finished!\n`);
}

const datasets = [
  // { id: 10101, name: "Human niche", unit: Unit.Class },
  // { id: 10102, name: "Average Temperature", unit: Unit.Temperature },
  // { id: 10103, name: "Maximum Temperature", unit: Unit.Temperature },
  // { id: 10104, name: "10 hottest days", unit: Unit.Temperature },
  // { id: 10105, name: "Days above 32°C (90°f)", unit: Unit.Days },
  // { id: 10106, name: "Days above 35°C (95°f)", unit: Unit.Days },
  // { id: 10107, name: "Days above 38°C (100°f)", unit: Unit.Days },
  // { id: 10108, name: "Hot days", unit: Unit.Days },
  // { id: 10201, name: "Minimum Temperature", unit: Unit.Temperature },
  // { id: 10202, name: "Frost nights", unit: Unit.Days },
  // { id: 10203, name: "Nights above 20°C (68°F)", unit: Unit.Days },
  // { id: 10204, name: "Nights above 25°C (77°F)", unit: Unit.Days },
  // { id: 10205, name: "Freezing days", unit: Unit.Days },
  // { id: 10206, name: "Days above 15°C (59°F)", unit: Unit.Days },
  // { id: 10301, name: "Likelihood of surpassing 30°c wet-bulb", unit: Unit.Days },
  // { id: 10302, name: "Days above 26°C wet-bulb", unit: Unit.Days },
  // { id: 10303, name: "Days above 28°C wet-bulb", unit: Unit.Days },
  // { id: 10304, name: "Days above 30°C wet-bulb", unit: Unit.Days },
  // { id: 10305, name: "Days above 32°C wet-bulb", unit: Unit.Days },
  // { id: 10306, name: "10 hottest wet-bulb days", unit: Unit.Temperature },
  // { id: 10307, name: "Hot wet-bulb days", unit: Unit.Days },

  { id: 20101, name: "Average Temperature", unit: Unit.Temperature },
  { id: 20103, name: "10 hottest days", unit: Unit.Temperature },
  { id: 20104, name: "Days above 32°C (90°F)", unit: Unit.Days },
  { id: 20201, name: "Days above 35°C (95°F)", unit: Unit.Days },
  { id: 20202, name: "Frost nights", unit: Unit.Days },
  { id: 20203, name: "Nights above 20°C (68°F)", unit: Unit.Days },
  { id: 20204, name: "Nights above 25°C (77°F)", unit: Unit.Days },
  { id: 20205, name: "Freezing days", unit: Unit.Days },

  // { id: 40101, name: "Average Temperature", unit: Unit.Temperature },
  // { id: 40102, name: "Average daytime temperature", unit: Unit.Temperature },
  // { id: 40104, name: "Days above 32°C (90°F)", unit: Unit.Days },
  // { id: 40105, name: "Days above 35°C (95°F)", unit: Unit.Days },
  // { id: 40106, name: "Days above 38°C (100°F)", unit: Unit.Days },
  // { id: 40202, name: "Frost nights", unit: Unit.Days },
  // { id: 40204, name: "Nights above 25°C (77°F)", unit: Unit.Days },
  // { id: 40205, name: "Freezing days", unit: Unit.Days },
  // { id: 40301, name: "Days above 26°C wet-bulb", unit: Unit.Days },
  // { id: 40302, name: "Days above 28°C wet-bulb", unit: Unit.Days },
  // { id: 40303, name: "Days above 30°C wet-bulb", unit: Unit.Days },
  // { id: 40304, name: "Days above 32°C wet-bulb", unit: Unit.Days },
].map(parseDataset);

async function processSerial(ds: ParsedDataset[]) {
  for await (const dataset of datasets) {
    await processDataset(dataset);
  }
}

// TODO: Parallelize and ride rate limit
async function processParallel(ds: ParsedDataset[]) {
  await Promise.all(datasets.map(processDataset));
}

(async function () {
  try {
    console.log("\nCreating tilesets for %O \n", datasets);

    await processSerial(datasets);
    // await processParallel(datasets);

    console.log("Finished tileset creation");
  } catch (error) {
    console.error("\n=+=+===+=+=+=+=+=+=FAILED=+=+===+=+=+=+=+=+=\n");
    console.error("%O", error);

    process.exit(1);
  } finally {
    process.exit(0);
  }
})();