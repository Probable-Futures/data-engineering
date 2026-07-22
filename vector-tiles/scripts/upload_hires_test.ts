/**
 * Standalone script to upload synthetic 0.1° test data to Mapbox
 * with split latitude bands to reduce feature dropping at low zoom levels.
 *
 * Splits each original layer in half (by latitude), producing:
 *   - East 1: 18 layers (eu_af regions split)
 *   - East 2: 16 layers (as_oc regions split)
 *   - West:   14 layers (na_sa regions split)
 *
 * Usage:
 *   cd vector-tiles
 *   npx ts-node scripts/upload_hires_test.ts [existing-source-id]
 *
 * Example with existing source:
 *   npx ts-node scripts/upload_hires_test.ts mapbox://tileset-source/probablefutures/40105-hires-test-1776330146
python3 vector-tiles/scripts/generate_hires_test.py
cd vector-tiles
npx ts-node scripts/upload_hires_test.ts

npx ts-node scripts/upload_hires_test.ts "mapbox://tileset-source/probablefutures/40105-hires-test-1776330146"   

 */

import path from "path";
import mbxClient from "@mapbox/mapbox-sdk/lib/client";
import mbxTilesets from "@mapbox/mapbox-sdk/services/tilesets";

const env = require("dotenv").config({ path: path.resolve(__dirname, "..", ".env") });
if (env.error) {
  throw env.error;
}

const eastRecipeTemplate = require("../templates/east.recipe.json");
const westRecipeTemplate = require("../templates/west.recipe.json");

const baseClient = mbxClient({ accessToken: process.env["MAPBOX_ACCESS_TOKEN"] });
const tilesetsService = mbxTilesets(baseClient);

const mapboxUser = "probablefutures";
const testDatasetId = "40105-hires-test";
const testVersion = "v2";
const inputFile = path.resolve(
  __dirname,
  "..",
  "..",
  "data",
  "mapbox",
  "mts",
  "40105-hires-test.geojsonld",
);

/**
 * Split a layer's bbox in half by latitude, creating two sub-layers.
 * Preserves all other layer config (minzoom, maxzoom, attributes, tiles, etc).
 */
function splitLayer(name: string, layer: any): [string, any][] {
  const [lonMin, latMin, lonMax, latMax] = layer.features.bbox;
  const midLat = Math.round(((latMin + latMax) / 2) * 10) / 10;

  const lower = {
    ...layer,
    features: { ...layer.features, bbox: [lonMin, latMin, lonMax, midLat] },
  };
  const upper = {
    ...layer,
    features: { ...layer.features, bbox: [lonMin, midLat, lonMax, latMax] },
  };

  return [
    [`${name}_a`, lower],
    [`${name}_b`, upper],
  ];
}

/** Split all layers in a template, set the source, and return layer entries. */
function splitTemplateLayers(template: any, source: string): [string, any][] {
  const splitLayers: [string, any][] = [];
  for (const [name, layer] of Object.entries(template.layers)) {
    splitLayers.push(...splitLayer(name, layer));
  }
  return splitLayers.map(([name, layer]) => [name, { ...layer, source }]);
}

async function wait(ms = 1000) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function uploadSource() {
  console.log(`Uploading tileset source from: ${inputFile}`);
  console.log("This may take a few minutes for an 830 MB file...\n");

  const sourceId = `${testDatasetId}-${Math.floor(Date.now() / 1000)}`;
  const { body, statusCode } = await tilesetsService
    .createTilesetSource({
      id: sourceId,
      file: inputFile,
      ownerId: mapboxUser,
    })
    .send();

  console.log(`Source uploaded: ${body.id} (status: ${statusCode})`);
  console.log(`  Files: ${body.files}, Size: ${(body.file_size / 1024 / 1024).toFixed(1)} MB\n`);
  return body.id;
}

async function validateRecipe(recipe: any, label: string) {
  const { body } = await tilesetsService.validateRecipe({ recipe }).send();
  if (!body.valid) {
    console.error(`Recipe validation failed for ${label}:`, body);
    throw new Error(`Invalid recipe for ${label}`);
  }
  console.log(`  ${label}: valid (${Object.keys(recipe.layers).length} layers)`);
  return recipe;
}

async function createTileset(tilesetId: string, name: string, recipe: any) {
  try {
    const { body, statusCode } = await tilesetsService
      .createTileset({ name, recipe, tilesetId, private: false })
      .send();
    console.log(`  Created tileset: ${tilesetId} (status: ${statusCode})`);
    return body;
  } catch (err: any) {
    if (err.statusCode === 409) {
      console.log(`  Tileset ${tilesetId} already exists, updating recipe...`);
      const { body } = await tilesetsService.updateRecipe({ tilesetId, recipe }).send();
      return body;
    }
    throw err;
  }
}

async function publishAndWait(tilesetId: string) {
  const { body } = await tilesetsService.publishTileset({ tilesetId }).send();
  const { jobId } = body;
  console.log(`  Published ${tilesetId}, jobId: ${jobId}`);

  let attempts = 0;
  while (attempts < 120) {
    await wait(5000);
    const { body: jobStatus } = await tilesetsService.tilesetJob({ jobId, tilesetId }).send();

    const { stage } = jobStatus;
    if (stage === "success") {
      console.log(`  ${tilesetId}: SUCCESS`);
      return jobStatus;
    } else if (stage === "failed") {
      console.error(`  ${tilesetId}: FAILED`, jobStatus);
      throw new Error(`Tileset job failed for ${tilesetId}`);
    }
    attempts++;
    if (attempts % 6 === 0) {
      console.log(`  ${tilesetId}: ${stage}... (${attempts * 5}s elapsed)`);
    }
  }
  throw new Error(`Timed out waiting for ${tilesetId}`);
}

async function main() {
  console.log("=== 0.1° Resolution Test — Split Latitude Bands ===\n");

  // Step 1: Get source
  let sourceId: string;
  if (process.argv[2]) {
    sourceId = process.argv[2];
    console.log(`Reusing existing source: ${sourceId}\n`);
  } else {
    sourceId = await uploadSource();
  }

  // Step 2: Split layers and build recipes
  console.log("Splitting layers and building recipes...");

  const eastSplitLayers = splitTemplateLayers(eastRecipeTemplate, sourceId);
  const westSplitLayers = splitTemplateLayers(westRecipeTemplate, sourceId);

  // East has 34 split layers — group by region into 2 tilesets
  const euAfLayers = Object.fromEntries(
    eastSplitLayers.filter(([n]) => n.startsWith("region_eu_af")),
  );
  const asOcLayers = Object.fromEntries(
    eastSplitLayers.filter(([n]) => n.startsWith("region_as_oc")),
  );

  const east1Recipe = { version: 1, layers: euAfLayers };
  const east2Recipe = { version: 1, layers: asOcLayers };
  const westRecipe = { version: 1, layers: Object.fromEntries(westSplitLayers) };

  console.log(`  East 1 (eu_af): ${Object.keys(euAfLayers).length} layers`);
  console.log(`  East 2 (as_oc): ${Object.keys(asOcLayers).length} layers`);
  console.log(`  West   (na_sa): ${Object.keys(westRecipe.layers).length} layers\n`);

  // Step 3: Validate
  console.log("Validating recipes...");
  await validateRecipe(east1Recipe, "East-1 (eu_af)");
  await validateRecipe(east2Recipe, "East-2 (as_oc)");
  await validateRecipe(westRecipe, "West");
  console.log();

  // Step 4: Create tilesets
  const east1Id = `${mapboxUser}.${testDatasetId}-east1-${testVersion}`;
  const east2Id = `${mapboxUser}.${testDatasetId}-east2-${testVersion}`;
  const westId = `${mapboxUser}.${testDatasetId}-west-${testVersion}`;

  console.log("Creating tilesets...");
  await createTileset(east1Id, `40105 Hi-Res Test - EU AF - ${testVersion}`, east1Recipe);
  await createTileset(east2Id, `40105 Hi-Res Test - AS OC - ${testVersion}`, east2Recipe);
  await createTileset(westId, `40105 Hi-Res Test - West - ${testVersion}`, westRecipe);
  console.log();

  console.log("Waiting 5s for Mapbox to propagate...\n");
  await wait(5000);

  // Step 5: Publish and wait (staggered to avoid rate limiting)
  console.log("Publishing tilesets...");
  await publishAndWait(east1Id);
  await wait(2000);
  await publishAndWait(east2Id);
  await wait(2000);
  await publishAndWait(westId);

  console.log("\n=== Done! ===");
  console.log(`\nInspect in Mapbox Studio:`);
  console.log(`  East 1 (eu_af): https://studio.mapbox.com/tilesets/${east1Id}/`);
  console.log(`  East 2 (as_oc): https://studio.mapbox.com/tilesets/${east2Id}/`);
  console.log(`  West:           https://studio.mapbox.com/tilesets/${westId}/`);
}

main().catch((err) => {
  console.error("\nFailed:", err);
  process.exit(1);
});
