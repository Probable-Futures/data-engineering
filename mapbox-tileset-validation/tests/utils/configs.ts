import * as path from "path";

import { DatasetUnit, ValidationMethod } from "../types";

/**
 * Choose one of the below methods:
 *
 * 1- using-vtquery: Vtquery is used to get the closest features from a longitude/latitude in a set of vector tile buffers. This way of validation is slow since it works by searching for each point in the tileset and then getting the features at this point.
 *
 * 2- using-checksums: This is a much faster way for validation, and it does not rely on vtquery. It works by parsing through all features in all layers in the vector tile.
 *
 */
const woodwellDatasetDir = path.resolve(__dirname, "../../woodwellDatasets");

export const VALIDATION_METHOD: ValidationMethod = "using-checksums";

/**
 * Specify the tileset Id. Currently, each dataset is created into two tilesets: east and west tileset.
 * When choosing the TILES to inspect in the TILES array below, make sure that the tiles fall in the
 * specified tileset.
 * For example: [3, 4, 3] is a tile inside the east tileset
 * [4, 3, 5] is a tile inside the west tileset
 */

export const TILESET_ID = "probablefutures.40206-west-v3";

export const CSV_FILE_PATH = `${woodwellDatasetDir}/woodwell.40206.csv`;

// each element in the TILES array shoud be of the order: z, x, y
export const TILES = [
  //east
  // [3, 4, 3],
  // [5, 22, 9],
  // [5, 15, 14],
  // [2, 2, 1],
  //west
  [4, 3, 5],
  [4, 3, 6],
  [3, 2, 4],
  // [3, 2, 3],
  // [3, 2, 4],
];

export const DATASET_UNIT: DatasetUnit = "°C";

// Check the CSV file and update the index of each column here. Index starts from 0.

// using mean
export const COLUMNS_INDEXES_IN_CSV = {
  lon: 0, // if lon and lat are in the same column set them both to the same index of that column.
  lat: 1,
  data_baseline_low: 3,
  data_baseline_mid: 2,
  data_baseline_high: 5,
  data_1c_low: 7,
  data_1c_mid: 6,
  data_1c_high: 9,
  data_1_5c_low: 11,
  data_1_5c_mid: 10,
  data_1_5c_high: 13,
  data_2c_low: 15,
  data_2c_mid: 14,
  data_2c_high: 17,
  data_2_5c_low: 19,
  data_2_5c_mid: 18,
  data_2_5c_high: 21,
  data_3c_low: 23,
  data_3c_mid: 22,
  data_3c_high: 25,
};

// data using median
// export const COLUMNS_INDEXES_IN_CSV = {
//   lon: 0, // if lon and lat are in the same column set them both to the same index of that column.
//   lat: 1,
//   data_baseline_low: 3,
//   data_baseline_mid: 4,
//   data_baseline_high: 5,
//   data_1c_low: 7,
//   data_1c_mid: 8,
//   data_1c_high: 9,
//   data_1_5c_low: 11,
//   data_1_5c_mid: 12,
//   data_1_5c_high: 13,
//   data_2c_low: 15,
//   data_2c_mid: 16,
//   data_2c_high: 17,
//   data_2_5c_low: 19,
//   data_2_5c_mid: 20,
//   data_2_5c_high: 21,
//   data_3c_low: 23,
//   data_3c_mid: 24,
//   data_3c_high: 25,
// };

// only mid
// export const COLUMNS_INDEXES_IN_CSV = {
//   lon: 0, // if lon and lat are in the same column set them both to the same index of that column.
//   lat: 1,
//   data_1c_mid: 2,
//   data_1_5c_mid: 3,
//   data_2c_mid: 4,
//   data_2_5c_mid: 5,
//   data_3c_mid: 6,
// };

// mean and 50th percentiles only
// export const COLUMNS_INDEXES_IN_CSV = {
//   lon: 0, // if lon and lat are in the same column set them both to the same index of that column.
//   lat: 1,
//   data_1c_mid: 4,
//   data_1_5c_mid: 6,
//   data_2c_mid: 8,
//   data_2_5c_mid: 10,
//   data_3c_mid: 12,
// };
