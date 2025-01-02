import { start } from "./dist/createTilesets.js";

export const handler = async (event, _context, callback) => {
  try {
    const { datasetId } = event;

    if (!datasetId) {
      const response = {
        message: "error",
        body: "Missing datasetId",
      };
      callback(null, response);
      return response;
    }

    await start([String(datasetId)]);

    callback(null, { message: "success", body: "Tileset creation completed successfully!" });
  } catch (error) {
    console.error("Error:", error);
    callback(null, { message: "error", body: "An error occurred during tileset creation." });
  }
};
