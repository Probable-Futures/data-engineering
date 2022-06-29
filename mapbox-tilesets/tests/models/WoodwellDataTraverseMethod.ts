import { parse } from "csv-parse";
import tilebelt from "@mapbox/tilebelt";

import { woodwellDatasetDir, DATASET, TILE } from "../utils";
import { Feature, FeatureMap } from "../types";
import { FileService, TileService } from "../services";
import Data from "./Data";

const filePath = `${woodwellDatasetDir}/woodwell.${DATASET.id}.csv`;

class WoodwellDataTraverseMethod extends Data {
  constructor() {
    super();
  }

  async streamAndBuildLatMap() {
    const featuresMap: FeatureMap = {};
    const bbox = tilebelt.tileToBBOX([TILE.x, TILE.y, TILE.z]);
    console.log("Reading the CSV file...");
    await new Promise((resolve, reject) => {
      FileService.parseCsvStream({
        path: filePath,
        parse: parse({ delimiter: ",", from_line: 2 }),
        eventHandlers: {
          data: async (row) => {
            const coordinates = row[1]
              .replace("(", "")
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
                data_baseline_mean: parseFloat(row[3]),
                data_1c_mean: parseFloat(row[6]),
                data_1_5c_mean: parseFloat(row[9]),
                data_2c_mean: parseFloat(row[12]),
                data_2_5c_mean: parseFloat(row[15]),
                data_3c_mean: parseFloat(row[18]),
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
