import * as path from "path";

export const ACCESS_TOKEN = process.env.MAPBOX_ACCESS_TOKEN;

export const ORGANIZATION = "probablefutures";

export const tilesetDir = path.resolve(__dirname, "../../tiles");

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

export const dataAttributeNames = [
  "data_baseline_low",
  "data_baseline_mid",
  "data_baseline_high",
  "data_1c_low",
  "data_1c_mid",
  "data_1c_high",
  "data_1_5c_low",
  "data_1_5c_mid",
  "data_1_5c_high",
  "data_2c_low",
  "data_2c_mid",
  "data_2c_high",
  "data_2_5c_low",
  "data_2_5c_mid",
  "data_2_5c_high",
  "data_3c_low",
  "data_3c_mid",
  "data_3c_high",
];
