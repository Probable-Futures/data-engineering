import path from "path";
import { BARREN_LAND_VALUE, DATA_LAYER_ID_PREFIX, ERROR_VALUE } from "./configs";

import {
  RecipeLayers,
  ModelGrid,
  ModelSource,
  Model,
  Category,
  ParsedDataset,
  DatasetToken,
  Unit,
  Map,
} from "./types";

const styleTemplate = require("./templates/style.json");
const gcmStyleTemplate = require("./templates/gcm.style.json");

export function formatName({
  name,
  model,
  version,
}: {
  name: string;
  model?: Model;
  version: string;
}) {
  if (model) {
    return `${name} -- ${model.source} -- v${version}`;
  }
  return `${name} -- v${version}`;
}

export const datasetFile = (datasetId: string | number): string =>
  path.resolve(__dirname, "../data/mapbox/mts", `${datasetId}.geojsonld`);

export const unixTimestamp = () => ~~(Date.now() / 1000);

export function createTilesetId(datasetId: string, user = "probablefutures"): string {
  return `${user}.${datasetId}`;
}

export function createTilesetIds(
  datasetId: string,
  version: string,
  user = "probablefutures",
): { eastId: string; westId: string } {
  if (!version) {
    throw Error(`Please set a version for dataset ${datasetId} in the configs.ts file.`);
  }
  return {
    eastId: `${user}.${datasetId}-east-v${version}`,
    westId: `${user}.${datasetId}-west-v${version}`,
  };
}

export function createTilesetSourceId(datasetId: string): string {
  return `${datasetId}-${unixTimestamp()}`;
}

export function setLayersSource({ layers, source }: { layers: RecipeLayers; source: string }) {
  // @ts-ignore
  return Object.fromEntries(
    Object.entries(layers).map(([name, recipe]) => [name, { ...recipe, source }]),
  );
}

export function injectStyle({
  name,
  tilesetEastId,
  tilesetWestId,
  tilesetId,
  map,
}: {
  name: string;
  tilesetEastId?: string;
  tilesetWestId?: string;
  tilesetId?: string;
  map?: Map;
}) {
  let { sources, layers, ...rest } = tilesetId ? gcmStyleTemplate : styleTemplate;
  if (tilesetEastId && tilesetWestId) {
    sources.composite.url = `mapbox://${tilesetEastId},mapbox.mapbox-streets-v8,${tilesetWestId},mapbox.mapbox-terrain-v2`;
  } else {
    sources.composite.url = `mapbox://${tilesetId},mapbox.mapbox-streets-v8,mapbox.mapbox-terrain-v2`;
  }
  if (map && map.binHexColors && map.stops) {
    for (let layer of layers) {
      if (layer.id.includes(DATA_LAYER_ID_PREFIX)) {
        layer.paint["fill-color"] = getFillColorExpresion(map.binHexColors, map.stops);
      }
    }
  }
  return {
    ...rest,
    name,
    sources,
    layers,
  };
}

export async function wait(ms = 1000) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export async function poll(fn, fnCondition, ms) {
  let result = await fn();
  while (fnCondition(result)) {
    await wait(ms);
    result = await fn();
  }
  return result;
}

export function randomBetween(min: number, max: number) {
  min = Math.ceil(min);
  max = Math.floor(max);
  return Math.floor(Math.random() * (max - min + 1) + min); //The maximum is inclusive and the minimum is inclusive
}

function datasetIdIndexKey(index: number): "model" | "category" | "dataset" {
  switch (index) {
    case 0:
      return "model";
    case 1:
    case 2:
      return "category";
    case 3:
    case 4:
      return "dataset";
    default:
      throw Error(`Datasets Ids are 5 digits. No key for ${index}.`);
  }
}

function decodeModelId(modelId: string): Model {
  switch (Number(modelId)) {
    case 1:
      return { grid: ModelGrid.GCM, source: ModelSource.CMIP5 };
    case 2:
      return { grid: ModelGrid.RCM, source: ModelSource.REMO };
    case 3:
      return { grid: ModelGrid.RCM, source: ModelSource.RegCM };
    case 4:
      return { grid: ModelGrid.RCM, source: ModelSource.Ensemble };
    default:
      throw Error(`No model for id ${modelId}`);
  }
}

function decodeCategoryId(categoryId: string): Category {
  switch (Number(categoryId)) {
    case 1:
    case 4:
      return Category.Heat;
    case 2:
      return Category.Cold;
    case 3:
      return Category.Humidity;
    case 6:
      return Category.Precipitation;
    case 7:
      return Category.Drought;
    case 9:
      return Category.Other;
    default:
      throw Error(`No category for id ${categoryId}`);
  }
}

function tokenizeDatasetId({
  id,
  name,
  unit,
  version,
}: {
  id: string;
  name: string;
  unit: Unit;
  version: string;
}): DatasetToken {
  if (id.length !== 5) {
    throw new Error(`Expected dataset Id to have 5 digits. Received ${id.length} instead`);
  }

  return Array.from(id).reduce(
    (token, digit, index) => {
      token[datasetIdIndexKey(index)] += digit;
      return token;
    },
    {
      name,
      id,
      model: "",
      category: "",
      subCategory: "",
      parentCategory: "",
      dataset: "",
      unit,
      version,
    },
  );
}

function decodeDatasetToken({ model, category, ...rest }: DatasetToken): ParsedDataset {
  return {
    model: decodeModelId(model),
    category: decodeCategoryId(category),
    ...rest,
  };
}

export function parseDataset(
  {
    id,
    name,
    unit,
    map,
    version,
  }: {
    id: number;
    name: string;
    unit: Unit;
    version: string;
    map?: Map;
  },
  overrideVersion?: string,
): ParsedDataset {
  const decodeResult = decodeDatasetToken(
    tokenizeDatasetId({ id: id.toString(), name, unit, version: overrideVersion ?? version }),
  );
  return { ...decodeResult, map };
}

export const getFillColorExpresion = (colors: string[], bins: number[]) => {
  const startIndex = 5;
  const additionalBins = colors
    .slice(startIndex)
    .map((_, index) => [bins[startIndex + index - 1], colors[startIndex + index]]);

  return [
    "step",
    ["get", "data_1c_mid"],
    // color the areas with error values the same as the ocean color
    "#f5f5f5",
    ERROR_VALUE + 1,
    "#e6e6e6",
    BARREN_LAND_VALUE + 1,
    colors[0],
    bins[0],
    colors[1],
    bins[1],
    colors[2],
    bins[2],
    colors[3],
    bins[3],
    colors[4],
    ...additionalBins.flat(),
  ];
};
