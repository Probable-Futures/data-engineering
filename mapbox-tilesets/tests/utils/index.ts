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
