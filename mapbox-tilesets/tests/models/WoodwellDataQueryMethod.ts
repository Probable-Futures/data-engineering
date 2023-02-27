import { parse } from "csv-parse";
import { promisify } from "util";
import tilebelt from "@mapbox/tilebelt";
import vtquery from "@mapbox/vtquery";

import {
  LAYERS,
  logProgress,
  COLUMNS_INDEXES_IN_CSV,
  dataAttributeNames,
  CSV_FILE_PATH,
  parseValue,
} from "../utils";
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
  private options: VTOption = {};
  private tiles: VT[] = [];
  processedRows = 0;
  unmatchedRows: any[] = [];
  tileConf: number[];

  constructor(tileConf: number[]) {
    this.tileConf = tileConf;
    this.tiles = [
      {
        buffer: FileService.readFile({ x: tileConf[1], y: tileConf[2], z: tileConf[0] }),
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
      const [lon, lat] = FileService.parseCoordinateValue(row);
      const result = await vtqueryPromise(this.tiles, [lon, lat], this.options);
      this.processedRows++;
      logProgress(`Validating points: ${this.processedRows} / ${allrows.length}`);

      if (result.features?.length) {
        const props = result.features[0].properties;
        for (let j = 0; j < dataAttributeNames.length; j++) {
          const dataAttributeIndexInCsv: number = COLUMNS_INDEXES_IN_CSV[dataAttributeNames[j]];
          const originalData: string = row[dataAttributeIndexInCsv];
          const tileData = props[dataAttributeNames[j]];
          if (parseValue(originalData) !== tileData) {
            this.unmatchedRows.push(row);
            console.log(
              "\nFailed to validate.\n",
              "CSV Row: ",
              row,
              "\n",
              "Tileset Features: ",
              result.features,
              "\n",
            );
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
        path: CSV_FILE_PATH,
        parse: parse({ delimiter: ",", from_line: 2 }),
        eventHandlers: {
          data: async (row) => {
            const [lon, lat] = FileService.parseCoordinateValue(row);
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
}

export default WoodwellDataQueryMethod;
