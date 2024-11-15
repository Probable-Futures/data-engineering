import { parse } from "csv-parse";
import tilebelt from "@mapbox/tilebelt";

import { COLUMNS_INDEXES_IN_CSV, CSV_FILE_PATH, parseValueV3 } from "../utils";
import { Feature, FeatureMap } from "../types";
import { FileService, TileService } from "../services";
import Data from "./Data";

class WoodwellDataSumMethod extends Data {
  constructor(tileConf: number[]) {
    super();
    this.tileConf = tileConf;
  }

  async streamAndBuildLatMap() {
    const allFeaturesGroupedByLatitude: FeatureMap = {};
    const bbox = tilebelt.tileToBBOX([this.tileConf[1], this.tileConf[2], this.tileConf[0]]);
    return await new Promise((resolve, reject) => {
      FileService.parseCsvStream({
        path: CSV_FILE_PATH,
        parse: parse({ delimiter: ",", from_line: 2 }), // start from row 2 to skip the header.
        eventHandlers: {
          data: async (row) => {
            const coordinates = FileService.parseCoordinateValue(row);
            const [lon, lat] = coordinates as number[];
            // skip coordinates outside the tileset bbox
            if (TileService.isPointInBbox({ lon, lat }, bbox)) {
              const lonStr = (lon + 0).toFixed(1); // +0 incase we have lon = -0 so it becomes 0
              const latStr = lat.toFixed(1);
              const finalFeature = {
                lon: lonStr,
                lat: latStr,
                data_1c_mid: parseValueV3(row[COLUMNS_INDEXES_IN_CSV.data_1c_mid]),
                data_1_5c_mid: parseValueV3(row[COLUMNS_INDEXES_IN_CSV.data_1_5c_mid]),
                data_2c_mid: parseValueV3(row[COLUMNS_INDEXES_IN_CSV.data_2c_mid]),
                data_2_5c_mid: parseValueV3(row[COLUMNS_INDEXES_IN_CSV.data_2_5c_mid]),
                data_3c_mid: parseValueV3(row[COLUMNS_INDEXES_IN_CSV.data_3c_mid]),
              } as Feature;
              if (allFeaturesGroupedByLatitude[latStr]) {
                allFeaturesGroupedByLatitude[latStr].push(finalFeature);
              } else {
                allFeaturesGroupedByLatitude[latStr] = [finalFeature];
              }
            }
          },
          end: () => {
            this.sortAndSetFeaturesMap(allFeaturesGroupedByLatitude);
            resolve(this.allFeaturesSortedAndGroupedByLatitude);
          },
          error: (error) => {
            console.log(error.message);
            reject(error);
          },
        },
      });
    });
  }

  getAllLongitudesCoveredForEachLatitude() {
    return Object.keys(this.allFeaturesSortedAndGroupedByLatitude).reduce((prev, cur) => {
      prev[cur] = this.allFeaturesSortedAndGroupedByLatitude[cur].map((lats) => lats.lon);
      return prev;
    }, {} as Record<string, string[]>);
  }
}

export default WoodwellDataSumMethod;
