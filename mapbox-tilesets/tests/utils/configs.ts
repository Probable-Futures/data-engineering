import { ValidationMethod } from "../types";

export const FETCH = false;

/**
 * Choose one of the below methods:
 *
 * 1- using-vtquery: Vtquery is used to get the closest features from a longitude/latitude in a set of vector tile buffers. This way of validation is slow since it works by searching for each point in the tileset and then getting the features at this point.
 *
 * 2- using-checksums: This is a much faster way for validation, and it does not rely on vtquery. It works by parsing through all features in all layers in the vector tile.
 *
 */
export const VALIDATION_METHOD: ValidationMethod = "using-checksums";

export const DATASET = {
  id: 40601,
  org: "probablefutures",
  directions: ["east", "west"], // every dataset is created into two tilesets east and west.
  version: "1",
  // set xyz of the tileset to validate in the east and west tiles
  // shoud be of the order: z, x, y
  eastTiles: [
    [3, 4, 3],
    [5, 15, 14],
  ],
  westTiles: [
    [3, 2, 3],
    [4, 5, 8],
  ],
};

// This the index where the lon/lat followed by the data attribute columns start
export const CSV_DATA_START_INDEX = 1;
