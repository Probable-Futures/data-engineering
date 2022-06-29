import { FETCH, TILE, VALIDATION_METHOD } from "./utils";
import { TileService, FileService } from "./services";
import WoodwellDataTraverseMethod from "./models/WoodwellDataTraverseMethod";
import WoodwellDataQueryMethod from "./models/WoodwellDataQueryMethod";
import TileData from "./models/TileData";

export const start = async () => {
  if (FETCH) {
    await TileService.fetchAndWriteTilesets();
  }

  console.log(`Configs: "Zoom" = ${TILE.z}, "X" = ${TILE.x}, "Y" = ${TILE.y}`);
  if (VALIDATION_METHOD === "using-vtquery") {
    try {
      const woodwellData = new WoodwellDataQueryMethod();
      await woodwellData.streamAndVtQueryFile();
      console.log(
        `Finished! The program parsed ${
          woodwellData.processedRows
        } data points in the specified tileset.\n${
          woodwellData.processedRows - woodwellData.unmatchedRows.length
        } out of ${woodwellData.processedRows} are valid points.`,
      );
      process.exit(0);
    } catch (e) {
      console.error(e);
      process.exit(1);
    }
  } else {
    try {
      const vt = FileService.readFileAsVectorTile();

      const tile = new TileData(vt);
      tile.parseVtFeatures();
      const tdAvgByLat = tile.getAverageDataPerLatitude();

      const woodwellData = new WoodwellDataTraverseMethod();
      await woodwellData.streamAndBuildLatMap();
      const wdAvgByLat = woodwellData.getAverageDataPerLatitude();

      console.log("Validating Data...");
      const { total, errors } = TileService.compareAndValidate(tdAvgByLat, wdAvgByLat);

      console.log(
        `Finished! The program parsed all data points in the specified tileset at a total of ${total} latitudes.\nAll points at ${
          total - errors.length
        } latitudes are valid.`,
      );
      if (errors.length) {
        console.log("Validation failed at the following latitudes: ", errors.join(", "));
        console.warn(
          "Feel free to set the VALIDATION_METHOD to `using-vtquery` in the configs.ts file in order to check the failed rows/coordinates.",
        );
      }
      process.exit(0);
    } catch (e) {
      console.error(e);
      process.exit(1);
    }
  }
};
