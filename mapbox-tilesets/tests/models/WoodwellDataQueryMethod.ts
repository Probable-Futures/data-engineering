import { parse } from "csv-parse";
import { promisify } from "util";
import tilebelt from "@mapbox/tilebelt";
import vtquery from "@mapbox/vtquery";

import { woodwellDatasetDir, DATASET, LAYERS, logProgress, CSV_DATA_START_INDEX } from "../utils";
import { dataAttributeNames } from "../types";
import { FileService, TileService } from "../services";

const vtqueryPromise = promisify(vtquery);

type VT = {
  buffer: Buffer;
  z: number;
  x: number;
  y: number;
};

type VTOption = {
  radius?: number;
  limit?: number;
  geometry?: string;
  layers?: string[];
  dedupe?: boolean;
  "basic-filters"?: any[];
  direct_hit_polygon?: boolean;
};

class WoodwellDataQueryMethod {
  private filePath: string = `${woodwellDatasetDir}/woodwell.${DATASET.id}.csv`;
  private options: VTOption = {};
  private tiles: VT[] = [];
  processedRows = 0;
  unmatchedRows: any[] = [];
  tileConf: number[];

  constructor(tileConf: number[], direction: string) {
    this.tileConf = tileConf;
    this.tiles = [
      {
        buffer: FileService.readFile({ x: tileConf[1], y: tileConf[2], z: tileConf[0] }, direction),
        z: tileConf[0],
        x: tileConf[1],
        y: tileConf[2],
      },
    ];
    this.options = {
      radius: 0.0,
      limit: 5,
      geometry: "polygon",
      dedupe: true,
      direct_hit_polygon: true,
      layers: LAYERS,
    };
  }

  private async process(allrows: any[]) {
    for (let i = 0; i < allrows.length; i++) {
      const row = allrows[i];
      const [lon, lat] = this.parseCoordinate(row[CSV_DATA_START_INDEX]);
      const result = await vtqueryPromise(this.tiles, [lon, lat], this.options);
      this.processedRows++;
      logProgress(`Validating points: ${this.processedRows} / ${allrows.length}`);

      if (result.features?.length) {
        const props = result.features[0].properties;
        for (let j = 0; j < dataAttributeNames.length; j++) {
          const originalData = Math.floor(row[j + 1 + CSV_DATA_START_INDEX]); // we use floor because that how we set data in mapbox.
          const tileData = props[dataAttributeNames[j]];
          if (originalData !== tileData) {
            this.unmatchedRows.push(row);
            console.log("\nFailed to validate row: ", dataAttributeNames[j]);
            console.log("original data: ", originalData, " ≠ ", "tile data: ", tileData);
            break;
          }
        }
      }
    }
    process.stdout.write("\n");
  }

  async streamAndVtQueryFile() {
    const bbox = tilebelt.tileToBBOX([this.tileConf[1], this.tileConf[2], this.tileConf[0]]);
    const result = await new Promise<Array<any>>((resolve, reject) => {
      const allrows = [];
      FileService.parseCsvStream({
        path: this.filePath,
        parse: parse({ delimiter: ",", from_line: CSV_DATA_START_INDEX + 1 }),
        eventHandlers: {
          data: async (row) => {
            const [lon, lat] = this.parseCoordinate(row[CSV_DATA_START_INDEX]);
            // skip coordinates outside the tileset bbox
            if (TileService.isPointInBbox({ lon, lat }, bbox)) {
              allrows.push(row);
            }
          },
          end: () => {
            resolve(allrows);
          },
          error: (error) => {
            console.log(error.message);
            reject(error);
          },
        },
      });
    });
    await this.process(result);
  }

  private parseCoordinate = (coordinate: string) => {
    const result = coordinate
      .replace("(", "")
      .replace(")", "")
      .split(",")
      .map((coordinate: string) => parseFloat(coordinate));

    return result;
  };
}

export default WoodwellDataQueryMethod;
