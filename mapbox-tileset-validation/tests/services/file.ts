import { VectorTile } from "@mapbox/vector-tile";
import * as fs from "fs";

import { COLUMNS_INDEXES_IN_CSV, tilesetDir, TILESET_ID } from "../utils";

const Protobuf = require("pbf");

export const stdTileFilename = ({ x, y, z }: { x: number; y: number; z: number }) => {
  return `${tilesetDir}/${TILESET_ID}-${z}-${x}-${y}.mvt`;
};

export const readFileAsVectorTile = ({ x, y, z }: { x: number; y: number; z: number }) => {
  const buf = fs.readFileSync(stdTileFilename({ x, y, z }));
  return new VectorTile(new Protobuf(buf));
};

export const readFile = ({ x, y, z }: { x: number; y: number; z: number }) => {
  return fs.readFileSync(stdTileFilename({ x, y, z }));
};

const noop = (): void => {};

export const parseCsvStream = ({
  path,
  parse,
  eventHandlers: { data = noop, error = noop, end = noop },
}: {
  path: string;
  parse: any;
  eventHandlers: {
    data?: (row: any) => void;
    error?: (e?: Error) => void;
    end?: (rowCount: number) => void;
  };
}): fs.ReadStream => {
  try {
    return fs.createReadStream(path).pipe(parse).on("error", error).on("data", data).on("end", end);
  } catch (err) {
    console.error("failed to create parserStream");
    console.error(err);
    throw err;
  }
};

/**
 * @param row
 * Returns an array of two numbers lon and lat. It handles two major cases:
 * 1- Both lat and lon are in the same column in the csv files
 * 2- lat and lon exists in two different columns
 */
export const parseCoordinateValue = (row: string[]) => {
  // if the lat and lon are combined in the same column
  // expecting something like (-68,-56.8)
  if (COLUMNS_INDEXES_IN_CSV.lon === COLUMNS_INDEXES_IN_CSV.lat) {
    return row[COLUMNS_INDEXES_IN_CSV.lon]
      .replace("(", "")
      .replace(")", "")
      .split(",")
      .map((coordinate: string) => parseFloat(coordinate));
  } else {
    return [
      parseFloat(row[COLUMNS_INDEXES_IN_CSV.lon]),
      parseFloat(row[COLUMNS_INDEXES_IN_CSV.lat]),
    ];
  }
};
