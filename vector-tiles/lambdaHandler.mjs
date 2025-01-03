import { start } from "./dist/createTilesets.js";

export const handler = async (event, _context, callback) => {
  try {
    const { datasetId, datasetVersion } = event;
    const response = { message: "success", body: "Tileset creation completed successfully!" };

    if (!datasetId) {
      response.message = "error";
      response.body = "Missing datasetId";
    } else if (!datasetVersion) {
      response.message = "error";
      response.body = "Missing datasetVersion";
    }

    if (response.message === "error") {
      callback(null, response);
      return response;
    }

    await start([String(datasetId)], String(datasetVersion));

    callback(null, response);
  } catch (error) {
    console.error("Error:", error);
    callback(null, { message: "error", body: "An error occurred during tileset creation." });
  }
};
