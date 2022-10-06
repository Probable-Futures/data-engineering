import { ValidationMethod } from "../types";

export const FETCH = true;

export const VALIDATION_METHOD: ValidationMethod = "using-vtquery";

export const DATASET = {
  id: 40703,
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
