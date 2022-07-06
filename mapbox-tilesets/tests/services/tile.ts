import fetch from "node-fetch";
import mbxTilesets from "@mapbox/mapbox-sdk/services/tilesets";
import mbxClient from "@mapbox/mapbox-sdk/lib/client";
import * as fs from "fs";

import { ACCESS_TOKEN, ORGANIZATION, tilesetId, x, y, z } from "../utils";
import { stdTileFilename } from "./file";
import { AvergageDataByLat, Point } from "../types";

const baseClient = mbxClient({ accessToken: ACCESS_TOKEN });
const tilesetsService = mbxTilesets(baseClient);

const fetchTilesetList = async () => {
  const tilesetList = await tilesetsService.listTilesets({ ownerId: ORGANIZATION }).send();
  return tilesetList.body;
};

const fetchAndWriteTile = async () => {
  const res = await fetch(
    `https://api.mapbox.com/v4/${tilesetId}/${z}/${x}/${y}.mvt?access_token=${ACCESS_TOKEN}`,
  );
  const fileStream = fs.createWriteStream(stdTileFilename());

  return new Promise((resolve, reject) => {
    res.body.pipe(fileStream);
    res.body.on("error", reject);
    fileStream.on("finish", resolve);
  });
};

export const fetchAndWriteTilesets = async () => {
  console.log("Fetching tileset list...");
  const tilesetList = await fetchTilesetList();
  if (!tilesetList || !tilesetList.length) {
    return;
  }

  for (const [index, tileset] of tilesetList.entries()) {
    // get dataset id from tileset.id
    const datasetIdMatches = tileset.id.matchAll(/probablefutures.(.*?)-/g);
    const datasetId = Array.from(datasetIdMatches, (x: any) => x[1]);
    // we only need to validate datasets where datasetId >= 40000
    if (datasetId && datasetId[0]) {
      const id = parseInt(datasetId[0]);
      if (id < 40000) {
        continue;
      }
    }
    // skip test or draft datasets
    if (tileset.id.includes("test") || tileset.id.includes("draft")) {
      continue;
    }
    if (tileset.id.includes(tilesetId)) {
      await fetchAndWriteTile();
      console.log(`${tileset.id}: Fetching and writing tile...`);
    }
  }
};

export const compareAndValidate = (
  tdAvgByLat: AvergageDataByLat[],
  wdAvgByLat: AvergageDataByLat[],
) => {
  const errors = [];
  let total = 0;
  for (let i = 0; i < tdAvgByLat.length; i++) {
    const lat = tdAvgByLat[i].lat;
    const woodwellDataAtLat = wdAvgByLat.find((wd) => wd.lat === lat);
    if (woodwellDataAtLat) {
      total++;
      if (
        tdAvgByLat[i].data_baseline_mid_average !== woodwellDataAtLat.data_baseline_mid_average ||
        tdAvgByLat[i].data_1c_mid_average !== woodwellDataAtLat.data_1c_mid_average ||
        tdAvgByLat[i].data_1_5c_mid_average !== woodwellDataAtLat.data_1_5c_mid_average ||
        tdAvgByLat[i].data_2c_mid_average !== woodwellDataAtLat.data_2c_mid_average ||
        tdAvgByLat[i].data_2_5c_mid_average !== woodwellDataAtLat.data_2_5c_mid_average ||
        tdAvgByLat[i].data_3c_mid_average !== woodwellDataAtLat.data_3c_mid_average
      ) {
        errors.push(lat);
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
