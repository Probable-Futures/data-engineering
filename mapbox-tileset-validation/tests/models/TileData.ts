import { VectorTile } from "@mapbox/vector-tile";
import * as turf from "@turf/turf";
import tilebelt from "@mapbox/tilebelt";

import { Feature, FeatureMap } from "../types";
import Data from "./Data";
import { tilePointToLonLat } from "../utils";
import { TileService } from "../services";

class Tileset extends Data {
  vt: VectorTile;
  latFeaturesMap: FeatureMap = {};
  longitudesToCoverInThisTile: Record<string, string[]>;

  constructor(
    vt: VectorTile,
    tileConf: number[],
    longitudesToCoverInThisTile: Record<string, string[]>,
  ) {
    super();
    this.vt = vt;
    this.tileConf = tileConf;
    this.longitudesToCoverInThisTile = longitudesToCoverInThisTile;
  }

  parseVtFeatures() {
    const allFeaturesGroupedByLatitude: FeatureMap = {};
    const layerIds = Object.keys(this.vt.layers);
    const bbox = tilebelt.tileToBBOX([this.tileConf[1], this.tileConf[2], this.tileConf[0]]);

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
        const [lon, lat] = tilePointToLonLat(
          layer.extent,
          this.tileConf[0],
          this.tileConf[1],
          this.tileConf[2],
          x,
          y,
        );

        // set the boundaries of the tileset, so they can be used to select which points to parse from the csv file.
        if (TileService.isPointInBbox({ lon, lat }, bbox)) {
          const finalFeature = {
            lon: (parseFloat(lon) + 0).toFixed(1), // +0 incase we have lon = -0 so it becomes 0
            lat,
            ...feature.properties,
          } as Feature;

          if (allFeaturesGroupedByLatitude[lat]) {
            allFeaturesGroupedByLatitude[lat].push(finalFeature);
          } else {
            allFeaturesGroupedByLatitude[lat] = [finalFeature];
          }
        }
      }
    });

    this.sortAndSetFeaturesMap(allFeaturesGroupedByLatitude, this.longitudesToCoverInThisTile);
  }
}

export default Tileset;
