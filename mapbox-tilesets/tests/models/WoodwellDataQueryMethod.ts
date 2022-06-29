import { parse } from "csv-parse";
import { promisify } from "util";
import tilebelt from "@mapbox/tilebelt";
import vtquery from "@mapbox/vtquery";

import { woodwellDatasetDir, DATASET, TILE, LAYERS, logProgress } from "../utils";
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

  constructor() {
    this.tiles = [
      {
        buffer: FileService.readFile(),
        z: TILE.z,
        x: TILE.x,
        y: TILE.y,
      },
    ];
    this.options = {
      radius: 0,
      limit: 5,
      geometry: "polygon",
      dedupe: true,
      layers: LAYERS,
    };
  }

  private async process(allrows: any[]) {
    for (let i = 0; i < allrows.length; i++) {
      const row = allrows[i];
      const [lon, lat] = this.parseCoordinate(row[1]);
      const result = await vtqueryPromise(this.tiles, [lon, lat], this.options);
      this.processedRows++;
      logProgress(`Validating points: ${this.processedRows} / ${allrows.length}`);

      if (result.features?.length) {
        const props = result.features[0].properties;
        for (let i = 0; i < dataAttributeNames.length; i++) {
          const originalData = parseInt(row[i + 2]);
          if (originalData !== props[dataAttributeNames[i]]) {
            this.unmatchedRows.push(row);
            console.log("\nFailed to validate row: ");
            console.table(row);
            break;
          }
        }
      }
    }
    process.stdout.write("\n");
  }

  async streamAndVtQueryFile() {
    let stream = null;
    const bbox = tilebelt.tileToBBOX([TILE.x, TILE.y, TILE.z]);
    console.log("Reading the CSV file...");
    const result = await new Promise<Array<any>>((resolve, reject) => {
      const allrows = [];
      stream = FileService.parseCsvStream({
        path: this.filePath,
        parse: parse({ delimiter: ",", from_line: 2 }),
        eventHandlers: {
          data: async (row) => {
            const [lon, lat] = this.parseCoordinate(row[1]);
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
          close: () => {
            stream.destroy();
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
