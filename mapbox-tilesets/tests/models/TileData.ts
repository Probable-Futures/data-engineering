import { VectorTile } from "@mapbox/vector-tile";
import * as turf from "@turf/turf";
import tilebelt from "@mapbox/tilebelt";

import { Feature, FeatureMap } from "../types";
import Data from "./Data";
import { TILE, tilePointToLonLat } from "../utils";
import { TileService } from "../services";

class Tileset extends Data {
  vt: VectorTile;
  latFeaturesMap: FeatureMap = {};

  constructor(vt: VectorTile) {
    super();
    this.vt = vt;
  }

  parseVtFeatures() {
    const featuresMap: FeatureMap = {};
    const layerIds = Object.keys(this.vt.layers);
    const bbox = tilebelt.tileToBBOX([TILE.x, TILE.y, TILE.z]);

    layerIds.forEach((layerId) => {
      const layer = this.vt.layers[layerId];
      for (let i = 0; i < layer.length; i++) {
        const feature = layer.feature(i);
        if (!feature.bbox) {
          continue;
        }
        const poly = turf.bboxPolygon(feature.bbox());
        const centroid = turf.centroid(poly);
        const [x, y] = centroid.geometry.coordinates;
        const [lon, lat] = tilePointToLonLat(layer.extent, TILE.z, TILE.x, TILE.y, x, y);

        // set the boundaries of the tileset, so they can be used to select which points to parse from the csv file.
        if (TileService.isPointInBbox({ lon, lat }, bbox)) {
          const finalFeature = {
            lon,
            lat,
            ...feature.properties,
          } as Feature;

          if (featuresMap[lat]) {
            featuresMap[lat].push(finalFeature);
          } else {
            featuresMap[lat] = [finalFeature];
          }
        }
      }
    });

    this.createFeaturesMap(featuresMap);
  }
}

export default Tileset;
