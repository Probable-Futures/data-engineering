import { DATASET_UNIT } from "./configs";

export * from "./configs";
export * from "./constants";

/**
 * Returns the lat and lon coordinates from a tile point given x and y
 *
 * https://github.com/mapbox/vtquery/blob/master/src/util.hpp#L58
 */
export const tilePointToLonLat = (
  extent: number,
  z: number,
  x: number,
  y: number,
  featureX: number,
  featureY: number,
) => {
  const z2 = 1 << z;
  const ex = extent;
  const size = ex * z2;
  const x0 = ex * x;
  const y0 = ex * y;

  const y2 = 180.0 - ((featureY + y0) * 360.0) / size;
  const x1 = ((featureX + x0) * 360.0) / size - 180.0;
  const y1 = (360.0 / Math.PI) * Math.atan(Math.exp((y2 * Math.PI) / 180.0)) - 90.0;

  return [x1.toFixed(1), y1.toFixed(1)];
};

export const logProgress = (msg: string) => {
  process.stdout.clearLine(0);
  process.stdout.cursorTo(0);
  process.stdout.write(msg);
};

/**
 * This function accepts one string param repersenting the value at a specific point.
 *
 * When we import the data from netcdf into SQL, we format the netcdf data and round it based on the unit. Check /netcdfs/import/pfimport.py#L73
 * After that, we call the floor method when creating the recipes for the tilesets. Check https://github.com/Probable-Futures/data-engineering/blob/4dfb5266bd3e8dfa9de918ad7843f8fbd72ef8f8/vector-tiles/templates/east.recipe.json#L12
 *
 * Therefore, before validating the original data against map data, we need to take this transformation into consideration and the do the comparison.
 */
export const parseValueV1 = (value: string) => {
  switch (DATASET_UNIT) {
    case "days":
      return Math.floor(parseInt(value));
    case "°C":
    case "likelihood":
    case "%":
      return Math.floor(parseFloat(parseFloat(value).toFixed(1)));
    default:
      return Math.floor(parseFloat(value));
  }
};

/**
 * In V3 maps, the data science team provides all data as integers, except the z-score data is provided as float with 1 precision
 * @param value
 * @returns
 */
export const parseValueV3 = (value: string) => {
  switch (DATASET_UNIT) {
    case "z-score":
      return parseFloat(parseFloat(value).toFixed(1));
    default:
      return parseInt(value);
  }
};
