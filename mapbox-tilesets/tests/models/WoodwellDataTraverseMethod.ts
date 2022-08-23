import { parse } from "csv-parse";
import tilebelt from "@mapbox/tilebelt";

import { woodwellDatasetDir, DATASET, CSV_DATA_START_INDEX } from "../utils";
import { Feature, FeatureMap } from "../types";
import { FileService, TileService } from "../services";
import Data from "./Data";

const filePath = `${woodwellDatasetDir}/woodwell.${DATASET.id}.csv`;

class WoodwellDataTraverseMethod extends Data {
  constructor(tileConf: number[]) {
    super();
    this.tileConf = tileConf;
  }

  async streamAndBuildLatMap() {
    const featuresMap: FeatureMap = {};
    const bbox = tilebelt.tileToBBOX([this.tileConf[1], this.tileConf[2], this.tileConf[0]]);
    return await new Promise((resolve, reject) => {
      FileService.parseCsvStream({
        path: filePath,
        parse: parse({ delimiter: ",", from_line: CSV_DATA_START_INDEX + 1 }),
        eventHandlers: {
          data: async (row) => {
            const coordinates = row[CSV_DATA_START_INDEX].replace("(", "")
              .replace(")", "")
              .split(",")
              .map((coordinate: string) => parseFloat(coordinate));
            const [lon, lat] = coordinates as number[];
            // skip coordinates outside the tileset bbox
            if (TileService.isPointInBbox({ lon, lat }, bbox)) {
              const lonStr = lon.toFixed(1).toString();
              const latStr = lat.toFixed(1).toString();
              const finalFeature = {
                lon: lonStr,
                lat: latStr,
                data_baseline_mid: Math.floor(row[CSV_DATA_START_INDEX + 2]),
                data_1c_mid: Math.floor(row[CSV_DATA_START_INDEX + 5]),
                data_1_5c_mid: Math.floor(row[CSV_DATA_START_INDEX + 8]),
                data_2c_mid: Math.floor(row[CSV_DATA_START_INDEX + 11]),
                data_2_5c_mid: Math.floor(row[CSV_DATA_START_INDEX + 14]),
                data_3c_mid: Math.floor(row[CSV_DATA_START_INDEX + 17]),
              } as Feature;
              if (featuresMap[latStr]) {
                featuresMap[latStr].push(finalFeature);
              } else {
                featuresMap[latStr] = [finalFeature];
              }
            }
          },
          end: () => {
            this.createFeaturesMap(featuresMap);
            resolve(this.latFeaturesMap);
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

export default WoodwellDataTraverseMethod;
