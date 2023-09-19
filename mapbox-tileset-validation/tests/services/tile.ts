import fetch from "node-fetch";
import mbxTilesets from "@mapbox/mapbox-sdk/services/tilesets";
import mbxClient from "@mapbox/mapbox-sdk/lib/client";
import * as fs from "fs";

import { ACCESS_TOKEN, ORGANIZATION, TILESET_ID } from "../utils";
import { stdTileFilename } from "./file";
import { AvergageDataByLat, Point } from "../types";

const baseClient = mbxClient({ accessToken: ACCESS_TOKEN });
const tilesetsService = mbxTilesets(baseClient);

export const fetchTilesetList = async () => {
  const tilesetList = await tilesetsService.listTilesets({ ownerId: ORGANIZATION }).send();
  return tilesetList.body;
};

export const fetchAndWriteTile = async ({ x, y, z }: { x: number; y: number; z: number }) => {
  const res = await fetch(
    `https://api.mapbox.com/v4/${TILESET_ID}/${z}/${x}/${y}.mvt?access_token=${ACCESS_TOKEN}`,
  );
  const fileStream = fs.createWriteStream(stdTileFilename({ x, y, z }));

  return new Promise((resolve, reject) => {
    res.body.pipe(fileStream);
    res.body.on("error", reject);
    fileStream.on("finish", resolve);
  });
};

export const compareAndValidate = (
  tdAvgByLat: AvergageDataByLat[],
  wdAvgByLat: AvergageDataByLat[],
) => {
  const errors = [];
  let total = 0;
  for (let i = 0; i < tdAvgByLat.length; i++) {
    const tileDataAtLat = tdAvgByLat[i];
    const woodwellDataAtLat = wdAvgByLat.find((wd) => wd.lat === tileDataAtLat.lat);
    if (woodwellDataAtLat) {
      total++;
      if (
        tileDataAtLat.data_1c_mid_average !== woodwellDataAtLat.data_1c_mid_average ||
        tileDataAtLat.data_1_5c_mid_average !== woodwellDataAtLat.data_1_5c_mid_average ||
        tileDataAtLat.data_2c_mid_average !== woodwellDataAtLat.data_2c_mid_average ||
        tileDataAtLat.data_2_5c_mid_average !== woodwellDataAtLat.data_2_5c_mid_average ||
        tileDataAtLat.data_3c_mid_average !== woodwellDataAtLat.data_3c_mid_average
      ) {
        errors.push(tileDataAtLat.lat);
      }
    }
  }

  return { total, errors };
};

export const isPointInBbox = (point: Point, bbox: number[]) => {
  const { lon, lat } = point;
  if (lon >= bbox[0] && lon <= bbox[2] && lat >= bbox[1] && lat <= bbox[3]) {
    return true;
  }
  return false;
};
