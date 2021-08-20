import path from "path";
import {
  RecipeLayers,
  ModelGrid,
  ModelSource,
  Model,
  Category,
  ParsedDataset,
  DatasetToken,
  Unit,
} from "./types";

const styleTemplate = require("./templates/style.json");

export function formatName({ name, model }: Pick<ParsedDataset, "name" | "model">) {
  return `${name} -- ${model.source}`;
}

export const datasetFile = (datasetId: string | number): string =>
  path.resolve(__dirname, "../data/mapbox/mts", `${datasetId}.geojsonld`);

export const unixTimestamp = () => ~~(Date.now() / 1000);

export function createTilesetIds(
  datasetId: string,
  user = "probablefutures",
): { eastId: string; westId: string } {
  return {
    eastId: `${user}.${datasetId}-east`,
    westId: `${user}.${datasetId}-west`,
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

export function injectStyle({ name, tilesetEastId, tilesetWestId }) {
  let { sources, ...rest } = styleTemplate;
  sources.composite.url = `mapbox://${tilesetEastId},mapbox.mapbox-streets-v8,${tilesetWestId},mapbox.mapbox-terrain-v2`;
  return {
    ...rest,
    name,
    sources,
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
      return Category.Heat;
    case 2:
      return Category.Cold;
    case 3:
      return Category.Humidity;
    case 4:
      return Category.Drought;
    case 5:
      return Category.Precipitation;
    case 6:
      return Category.Fire;
    case 7:
      return Category.Storm;
    default:
      throw Error(`No category for id ${categoryId}`);
  }
}

function tokenizeDatasetId({
  id,
  name,
  unit,
}: {
  id: string;
  name: string;
  unit: Unit;
}): DatasetToken {
  if (id.length !== 5) {
    throw new Error(`Expected dataset Id to have 5 digits. Received ${id.length} instead`);
  }

  return Array.from(id).reduce(
    (token, digit, index) => {
      token[datasetIdIndexKey(index)] += digit;
      return token;
    },
    { name, id, model: "", category: "", dataset: "", unit },
  );
}

function decodeDatasetToken({ model, category, ...rest }: DatasetToken): ParsedDataset {
  return {
    model: decodeModelId(model),
    category: decodeCategoryId(category),
    ...rest,
  };
}

export function parseDataset({
  id,
  name,
  unit,
}: {
  id: number;
  name: string;
  unit: Unit;
}): ParsedDataset {
  return decodeDatasetToken(tokenizeDatasetId({ id: id.toString(), name, unit }));
}
