import mbxClient from "@mapbox/mapbox-sdk/lib/client";
import mbxTilesets from "@mapbox/mapbox-sdk/services/tilesets";
import mbxStyles from "@mapbox/mapbox-sdk/services/styles";

const eastRecipeTemplate = require("./templates/east.recipe.json");
const westRecipeTemplate = require("./templates/west.recipe.json");
const worldRecipeTemplate = require("./templates/world.recipe.json");
const debug = require("debug")("createTilesets");
const env = require("dotenv").config();

if (env.error) {
  throw env.error;
}

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
import { Unit, Recipe, ParsedDataset } from "./types";
import { pgPool } from "./database";
import { DATASET_VERSIONS } from "./configs";

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
  const datasetVersion = DATASET_VERSIONS[id];
  if (!datasetVersion) {
    throw Error(`Please set a version for dataset ${id} in the configs.ts file.`);
  }
  let style;
  if (model.grid === "GCM") {
    const tilesetId = createTilesetId(id);
    style = injectStyle({
      tilesetId,
      name: `${formatName({ name, model })} -- v${datasetVersion}`,
    });
    debugStyles("%O", { id: tilesetId, style });
  } else {
    const { eastId, westId } = createTilesetIds(id);
    style = injectStyle({
      tilesetEastId: eastId,
      tilesetWestId: westId,
      name: `${formatName({ name, model })} -- v${DATASET_VERSIONS[id]}`,
    });
    debugStyles("%O", { eastId, westId, style });
  }
  const { body, statusCode } = await stylesService.createStyle({ style }).send();
  debugStyles("response %O", { body, statusCode });
  return body;
}

async function saveMap(dataset: ParsedDataset, mapStyleId: string) {
  try {
    await pgPool.query(`delete from pf_public.pf_maps where dataset_id = ${dataset.id}`);
    await pgPool.query(`
      insert into pf_public.pf_maps (
        dataset_id,
        map_style_id,
        name, 
        description,
        stops,
        bin_hex_colors, 
        status,
        "order", 
        is_diff)
      values (
        ${dataset.id}, 
        '${mapStyleId}', 
        '${dataset.map?.name}', 
        '${dataset.map?.description}',
        '{${dataset.map?.stops}}',
        '{${dataset.map?.binHexColors}}', 
        '${dataset.map?.status}',
        ${dataset.map?.order}, 
        ${dataset.map?.isDiff}
      )`);
    console.log("Map Info was successfully save into the database.");
  } catch (e) {
    console.log(
      `Failed to insert into pf_public.pf_maps. You can do that manually: use map_style_id= ${mapStyleId}`,
    );
  }
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
      name: formatName({ name: dataset.id, model: dataset.model }),
      recipe: recipes.recipe,
    });
  }

  // Sometimes we try to publish a tileset to quickly after it's created
  // and mapbox hasn't had time to tell all it's serves and dbs about it.
  // So we wait for 5 seconds to give them time to catch up
  await wait(5000);

  console.log(`${dataset.id}: Publishing tilesets...\n`);
  let jobIds;
  if (dataset.model.grid === "GCM") {
    jobIds = await publishTileset(createTilesetId(dataset.id));
  } else {
    jobIds = await publishTilesets(dataset.id);
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

  if (dataset.map && body.id) {
    await saveMap(dataset, body.id);
  }

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
  // { id: 20101, name: "Average Temperature", unit: Unit.Temperature },
  // { id: 20103, name: "10 hottest days", unit: Unit.Temperature },
  // { id: 20104, name: "Days above 32°C (90°F)", unit: Unit.Days },
  // { id: 20201, name: "Days above 35°C (95°F)", unit: Unit.Days },
  // { id: 20202, name: "Frost nights", unit: Unit.Days },
  // { id: 20203, name: "Nights above 20°C (68°F)", unit: Unit.Days },
  // { id: 20204, name: "Nights above 25°C (77°F)", unit: Unit.Days },
  // { id: 20205, name: "Freezing days", unit: Unit.Days },
  // { id: 40101, name: "Average Temperature", unit: Unit.Temperature },
  // { id: 40102, name: "Average daytime temperature", unit: Unit.Temperature },
  // { id: 40103, name: "10 hottest days", unit: Unit.Temperature },
  // { id: 40104, name: "Days above 32°C (90°F)", unit: Unit.Days },
  // { id: 40105, name: "Days above 35°C (95°F)", unit: Unit.Days },
  // { id: 40106, name: "Days above 38°C (100°F)", unit: Unit.Days },
  // { id: 40201, name: "Average nighttime temperature", unit: Unit.Days },
  // { id: 40202, name: "Frost nights", unit: Unit.Days },
  // { id: 40203, name: "Nights above 20°C (68°F)", unit: Unit.Days },
  // { id: 40204, name: "Nights above 25°C (77°F)", unit: Unit.Days },
  // { id: 40205, name: "Freezing days", unit: Unit.Days },
  // { id: 40301, name: "Days above 26°C wet-bulb", unit: Unit.Days },
  // { id: 40302, name: "Days above 28°C wet-bulb", unit: Unit.Days },
  // { id: 40303, name: "Days above 30°C wet-bulb", unit: Unit.Days },
  // { id: 40304, name: "Days above 32°C wet-bulb", unit: Unit.Days },
  // { id: 40305, name: "10 hottest wet-bulb days", unit: Unit.Temperature },
  // { id: 40601, name: "Change in total annual precipitation", unit: Unit.Millimeters },
  // { id: 40607, name: "Change in dry hot days", unit: Unit.Days },
  // { id: 40612, name: 'Change in frequency of "1-in-100 year" storm', unit: Unit.Frequency },
  // { id: 40613, name: 'Change in precipitation "1-in-100 year" storm', unit: Unit.Millimeters },
  // { id: 40614, name: "Change in snowy days", unit: Unit.Days },
  // { id: 40616, name: "Change in wettest 90 days", unit: Unit.Millimeters },
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
