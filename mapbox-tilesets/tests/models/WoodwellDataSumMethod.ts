import { parse } from "csv-parse";
import tilebelt from "@mapbox/tilebelt";

import { COLUMNS_INDEXES_IN_CSV, CSV_FILE_PATH } from "../utils";
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
              const lonStr = lon.toFixed(1).toString();
              const latStr = lat.toFixed(1).toString();
              const finalFeature = {
                lon: lonStr,
                lat: latStr,
                data_baseline_mid: Math.floor(row[COLUMNS_INDEXES_IN_CSV.data_baseline_mid]),
                data_1c_mid: Math.floor(row[COLUMNS_INDEXES_IN_CSV.data_1c_mid]),
                data_1_5c_mid: Math.floor(row[COLUMNS_INDEXES_IN_CSV.data_1_5c_mid]),
                data_2c_mid: Math.floor(row[COLUMNS_INDEXES_IN_CSV.data_2c_mid]),
                data_2_5c_mid: Math.floor(row[COLUMNS_INDEXES_IN_CSV.data_2_5c_mid]),
                data_3c_mid: Math.floor(row[COLUMNS_INDEXES_IN_CSV.data_3c_mid]),
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
}

export default WoodwellDataSumMethod;
