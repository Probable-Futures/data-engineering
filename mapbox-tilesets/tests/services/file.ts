import { VectorTile } from "@mapbox/vector-tile";
import * as fs from "fs";

import { tilesetDir, tilesetId, z, x, y } from "../utils";

const Protobuf = require("pbf");

export const stdTileFilename = () => {
  return `${tilesetDir}/${tilesetId}-${z}-${x}-${y}.mvt`;
};

export const readFileAsVectorTile = () => {
  const buf = fs.readFileSync(stdTileFilename());
  return new VectorTile(new Protobuf(buf));
};

export const readFile = () => {
  return fs.readFileSync(stdTileFilename());
};

const noop = (): void => {};

export const parseCsvStream = ({
  path,
  parse,
  eventHandlers: { data = noop, error = noop, end = noop, close = noop },
}: {
  path: string;
  parse: any;
  eventHandlers: {
    data?: (row: any) => void;
    error?: (e?: Error) => void;
    end?: (rowCount: number) => void;
    close?: () => void;
  };
}) => {
  try {
    return fs
      .createReadStream(path)
      .pipe(parse)
      .on("error", error)
      .on("data", data)
      .on("end", end)
      .on("close", close);
  } catch (err) {
    console.error("failed to create parserStream");
    console.error(err);
    throw err;
  }
};
