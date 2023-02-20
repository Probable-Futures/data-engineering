import { DATASET, FETCH, VALIDATION_METHOD } from "./utils";
import { TileService, FileService } from "./services";
import WoodwellDataSumMethod from "./models/WoodwellDataSumMethod";
import WoodwellDataQueryMethod from "./models/WoodwellDataQueryMethod";
import TileData from "./models/TileData";

export const start = async () => {
  if (FETCH) {
    console.log("\nFetching and writing tilesets...");
    for (let i = 0; i < DATASET.directions.length; i++) {
      const direction = DATASET.directions[i];
      const tiles = DATASET[direction + "Tiles"];
      for (let j = 0; j < tiles.length; j++) {
        const tileConf = tiles[j];
        await TileService.fetchAndWriteTile(
          { x: tileConf[1], y: tileConf[2], z: tileConf[0] },
          direction,
        );
      }
    }
  }
  if (VALIDATION_METHOD === "using-vtquery") {
    try {
      for (let i = 0; i < DATASET.directions.length; i++) {
        const direction = DATASET.directions[i];
        const tiles = DATASET[direction + "Tiles"];
        for (let i = 0; i < tiles.length; i++) {
          const tileConf = tiles[i];
          const logMessage = `${DATASET.id}-${direction}-${tileConf[0]}-${tileConf[1]}-${tileConf[2]}`;
          console.log(`\n${logMessage}: Reading tileset...\n`);
          const woodwellData = new WoodwellDataQueryMethod(tileConf, direction);
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
      }
      process.exit(0);
    } catch (e) {
      console.error(e);
      process.exit(1);
    }
  } else {
    try {
      for (let i = 0; i < DATASET.directions.length; i++) {
        const direction = DATASET.directions[i];
        const tiles = DATASET[direction + "Tiles"];
        for (let i = 0; i < tiles.length; i++) {
          const tileConf = tiles[i];
          const logMessage = `${DATASET.id}-${direction}-${tileConf[0]}-${tileConf[1]}-${tileConf[2]}`;
          console.log(`\n${logMessage}: Reading tileset...\n`);
          const vt = FileService.readFileAsVectorTile(
            {
              x: tileConf[1],
              y: tileConf[2],
              z: tileConf[0],
            },
            direction,
          );

          console.log(`${logMessage}: Reading the CSV file...\n`);
          const woodwellData = new WoodwellDataSumMethod(tileConf);
          await woodwellData.streamAndBuildLatMap();
          const wdAvgByLat = woodwellData.getAverageDataPerLatitude();

          console.log(`${logMessage}: Parsing tile data...\n`);
          const tile = new TileData(vt, tileConf);
          tile.parseVtFeatures();
          const tdAvgByLat = tile.getAverageDataPerLatitude();

          const { total, errors } = TileService.compareAndValidate(tdAvgByLat, wdAvgByLat);

          console.log(
            `${logMessage}: Validation finished! Parsed all data points in the specified tileset at a total of ${total} latitudes.\n`,
          );
          console.log(
            `${logMessage}: All points at ${total - errors.length} latitudes are valid.\n`,
          );
          if (errors.length) {
            console.log("Validation failed at the following latitudes: ", errors.join(", "));
            console.warn(
              "\nFeel free to set the VALIDATION_METHOD to `using-vtquery` in the configs.ts file in order to check the failed rows/coordinates.\n",
            );
          }
          console.log("\t-----------------------------------------------\t");
        }
      }
      process.exit(0);
    } catch (e) {
      console.error(e);
      process.exit(1);
    }
  }
};
