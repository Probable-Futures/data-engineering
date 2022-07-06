import * as path from "path";
import { TILE, DATASET } from "./configs";

export const ACCESS_TOKEN = process.env.MAPBOX_ACCESS_TOKEN;

export const ORGANIZATION = "probablefutures";

export const tilesetDir = path.resolve(__dirname, "../../tiles");

export const woodwellDatasetDir = path.resolve(__dirname, "../../woodwellDatasets");

export const LAYERS = [
  "region_eu_af_6",
  "region_eu_af_7",
  "region_eu_af_8",
  "region_eu_af_9",
  "region_as_oc_1",
  "region_as_oc_2",
  "region_as_oc_3",
  "region_as_oc_4",
  "region_as_oc_5",
  "region_as_oc_6",
  "region_as_oc_7",
  "region_as_oc_8",
  "region_eu_af_1",
  "region_eu_af_2",
  "region_eu_af_3",
  "region_eu_af_4",
  "region_eu_af_5",
  "region_na_sa_1",
  "region_na_sa_2",
  "region_na_sa_3",
  "region_na_sa_4",
  "region_na_sa_5",
  "region_na_sa_6",
  "region_na_sa_7",
];

export const tilesetId = `${DATASET.org}.${DATASET.id}-${DATASET.direction}-v${DATASET.version}`;
export const { x, y, z } = TILE;
