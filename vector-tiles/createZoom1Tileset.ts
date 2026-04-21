import mbxClient from "@mapbox/mapbox-sdk/lib/client";
import mbxTilesets from "@mapbox/mapbox-sdk/services/tilesets";
import mbxStyles from "@mapbox/mapbox-sdk/services/styles";
import { S3Client, GetObjectCommand } from "@aws-sdk/client-s3";

const zoom1RecipeTemplate = require("./templates/zoom1.recipe.json");
const debug = require("debug")("createZoom1Tileset");
const env = require("dotenv").config();

if (env.error && process.env["APP_ENV"] === "local") {
  throw env.error;
}

import {
  formatName,
  datasetZoom1File,
  createZoom1TilesetId,
  createTilesetSourceId,
  setLayersSource,
  injectStyle,
  wait,
  poll,
  randomBetween,
  parseDataset,
} from "./utils";
import { Recipe, ParsedDataset, ModelGrid } from "./types";
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
async function uploadZoom1Source(datasetId: string, datasetVersion: string) {
  debugMTSUpload("input %i-zoom1", datasetId);
  let fileStream;

  if (appEnv === "local") {
    fileStream = datasetZoom1File(datasetId);
  } else {
    const key = `climate-data-geojson/v${datasetVersion}/${datasetId}-zoom1.geojsonld`;
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
      id: createTilesetSourceId(`${datasetId}-zoom1`),
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
  debugMTSCreate("response %O", { body, statusCode });
  return body;
}

const debugMTSPublish = debugTilesets.extend("publish");
async function publishTileset(tilesetId: string) {
  debugMTSPublish("input %O", { tilesetId });
  const { body, statusCode } = await tilesetsService.publishTileset({ tilesetId }).send();
  debugMTSPublish("response %O", { body, statusCode });
  return body;
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

const debugStyles = debug.extend("styles");
async function createStyle({ id, name, version, map }: ParsedDataset) {
  debugStyles("input %O", { id, name });
  if (!version) {
    throw Error(`Please set a version for dataset ${id} in the configs.ts file.`);
  }
  const tilesetId = createZoom1TilesetId(id, version);
  const style = injectStyle({
    tilesetId,
    name: formatName({ name, version }),
    map,
  });
  debugStyles("%O", { id: tilesetId, style });
  const { body, statusCode } = await stylesService.createStyle({ style }).send();
  debugStyles("response %O", { body, statusCode });
  return body;
}

export async function processZoom1Dataset(dataset: ParsedDataset): Promise<void> {
  if (dataset.model.grid !== ModelGrid.RCM) return;

  console.log(`${dataset.id}: Uploading zoom-1 GeoJSON tileset source...\n`);
  const { id: zoom1SourceId } = await uploadZoom1Source(dataset.id, dataset.version);

  console.log(`${dataset.id}: Validating zoom-1 recipe...\n`);
  const zoom1Recipe = await createRecipe(zoom1SourceId, zoom1RecipeTemplate);

  console.log(`${dataset.id}: Creating zoom-1 tileset...\n`);
  const zoom1TilesetId = createZoom1TilesetId(dataset.id, dataset.version);
  await createTileset({
    tilesetId: zoom1TilesetId,
    name: formatName({ name: `${dataset.id} - Zoom1`, model: dataset.model, version: dataset.version }),
    recipe: zoom1Recipe.recipe,
  });

  await wait(5000);

  console.log(`${dataset.id}: Publishing zoom-1 tileset...\n`);
  const { jobId } = await publishTileset(zoom1TilesetId);

  console.log(`${dataset.id}: Waiting on zoom-1 tileset job to finish...\n`);
  const retryAfter = randomBetween(2000, 5000);
  await waitForTilesetJob({ jobId, tilesetId: zoom1TilesetId, retryAfter });

  console.log(`${dataset.id}: Creating zoom-1 map style...\n`);
  await createStyle(dataset);

  console.log(`${dataset.id}: Zoom-1 tileset finished!\n`);
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

    console.log("\nCreating zoom-1 tilesets for %O \n", datasets);

    for (const dataset of datasets) {
      await processZoom1Dataset(dataset);
    }

    console.log("Finished zoom-1 tileset creation");
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
