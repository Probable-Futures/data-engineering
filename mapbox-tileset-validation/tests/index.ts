import * as fs from "fs";

import { logProgress, TILES, TILESET_ID, VALIDATION_METHOD } from "./utils";
import { TileService, FileService } from "./services";
import WoodwellDataSumMethod from "./models/WoodwellDataSumMethod";
import WoodwellDataQueryMethod from "./models/WoodwellDataQueryMethod";
import TileData from "./models/TileData";

const fetchFileIfDoesNotExist = async ({ x, y, z }: { x: number; y: number; z: number }) => {
  const path = FileService.stdTileFilename({ x, y, z });
  const fileAlreadyExists = fs.existsSync(path);
  if (!fileAlreadyExists) {
    logProgress("\nFetching and writing tiles...");
    await TileService.fetchAndWriteTile({ x, y, z });
  }
};

export const start = async () => {
  // fetch tilesets if they are not fetched before.
  for (let j = 0; j < TILES.length; j++) {
    const tileConf = TILES[j];
    await fetchFileIfDoesNotExist({ x: tileConf[1], y: tileConf[2], z: tileConf[0] });
  }

  if (VALIDATION_METHOD === "using-vtquery") {
    try {
      for (let i = 0; i < TILES.length; i++) {
        const tileConf = TILES[i];
        const logMessage = `${TILESET_ID}-${tileConf[0]}-${tileConf[1]}-${tileConf[2]}`;
        console.log(`\n${logMessage}: Reading tileset...\n`);
        const woodwellData = new WoodwellDataQueryMethod(tileConf);
        console.log(`${logMessage}: Reading the CSV file...\n`);
        await woodwellData.streamAndVtQueryFile();
        console.log(
          `\n${logMessage}: Validation is finished!\n\nParsed ${
            woodwellData.processedRows
          } data points in the specified tileset.\n\n${
            woodwellData.processedRows - woodwellData.unmatchedRows.length
          } out of ${woodwellData.processedRows} are valid points.\n`,
        );
        console.log("\t-----------------------------------------------\t");
      }
      process.exit(0);
    } catch (e) {
      console.error(e);
      process.exit(1);
    }
  } else {
    try {
      for (let i = 0; i < TILES.length; i++) {
        const tileConf = TILES[i];
        const logMessage = `${TILESET_ID}-${tileConf[0]}-${tileConf[1]}-${tileConf[2]}`;
        console.log(`\n${logMessage}: Reading tileset...\n`);
        const vt = FileService.readFileAsVectorTile({
          x: tileConf[1],
          y: tileConf[2],
          z: tileConf[0],
        });

        console.log(`${logMessage}: Reading the CSV file...\n`);
        const woodwellData = new WoodwellDataSumMethod(tileConf);
        await woodwellData.streamAndBuildLatMap();
        const wdAvgByLat = woodwellData.getAverageDataPerLatitude();

        console.log(`${logMessage}: Parsing tile data...\n`);
        const tile = new TileData(
          vt,
          tileConf,
          woodwellData.getAllLongitudesCoveredForEachLatitude(),
        );
        tile.parseVtFeatures();
        const tdAvgByLat = tile.getAverageDataPerLatitude();

        const { total, errors } = TileService.compareAndValidate(tdAvgByLat, wdAvgByLat);

        console.log(
          `${logMessage}: Validation finished! Parsed all data points in the specified tileset at a total of ${total} latitudes.\n`,
        );
        console.log(`${logMessage}: All points at ${total - errors.length} latitudes are valid.\n`);
        if (errors.length) {
          console.log("Validation failed at the following latitudes: ", errors.join(", "));
          console.warn(
            "\nFeel free to set the VALIDATION_METHOD to `using-vtquery` in the configs.ts file in order to check the failed rows/coordinates.\n",
          );
        }
        console.log("\t-----------------------------------------------\t");
      }
      process.exit(0);
    } catch (e) {
      console.error(e);
      process.exit(1);
    }
  }
};
