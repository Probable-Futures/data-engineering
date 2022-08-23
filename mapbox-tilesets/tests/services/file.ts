import { VectorTile } from "@mapbox/vector-tile";
import * as fs from "fs";

import { tilesetDir, tilesetId } from "../utils";

const Protobuf = require("pbf");

export const stdTileFilename = (
  { x, y, z }: { x: number; y: number; z: number },
  direction: string,
) => {
  return `${tilesetDir}/${tilesetId(direction)}-${z}-${x}-${y}.mvt`;
};

export const readFileAsVectorTile = (
  { x, y, z }: { x: number; y: number; z: number },
  direction: string,
) => {
  const buf = fs.readFileSync(stdTileFilename({ x, y, z }, direction));
  return new VectorTile(new Protobuf(buf));
};

export const readFile = ({ x, y, z }: { x: number; y: number; z: number }, direction: string) => {
  return fs.readFileSync(stdTileFilename({ x, y, z }, direction));
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
