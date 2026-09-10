/**
 * Hi-res resolution pyramid (see "The resolution pyramid" in docs/hi-res-map-pipeline.md).
 *
 * The new 0.1° data overflows low-zoom tiles. We fix it by serving coarser precomputed rungs
 * at low zoom: native 0.1° at z4-5, 0.2° at z2-3, 0.8° at z0-1. Each rung is its own
 * tileset built from its own `.geojsonld` (produced by `hires-maps pyramid`), but every rung
 * KEEPS THE SAME LAYER KEYS. Because the tilesets share source-layer names and cover disjoint
 * zoom ranges, compositing them all in one style makes Mapbox serve the right rung per zoom —
 * so the map style needs no per-rung layers.
 *
 * A pyramid is a response to feature density, not a requirement. Use `rungsFor(variant)` rather
 * than HIRES_RUNGS directly: the ERA5 variant is sparse enough to publish as a single native rung
 * (see ERA5_RUNGS), and compositing one tileset works exactly the same way as compositing three.
 */

import { RecipeLayers } from "./types";

export interface HiResRung {
  suffix: string; // geojsonld/tileset id suffix ("" for native 0.1°)
  minzoom: number;
  maxzoom: number;
  label: string;
}

// Rung order matters only for readability; zoom bands are disjoint and cover 0..5.
//
// Why z0-1 share one rung: a tileset pinned to `minzoom: 1, maxzoom: 1` (the old `-p04` rung)
// fails Mapbox's post-publish metadata validation — "center zoom value must be greater than or
// equal to minzoom 1", because the center zoom it derives sits below that minzoom. Letting the
// coarsest rung start at zoom 0 avoids the problem, and 0.8° cells are ~2px at z1 so the visual
// difference from 0.4° is imperceptible. `hires-maps pyramid` no longer generates a `-p04` file.
export const HIRES_RUNGS: HiResRung[] = [
  { suffix: "", minzoom: 4, maxzoom: 5, label: "0.1" }, // native, from hires-maps build
  { suffix: "-p02", minzoom: 2, maxzoom: 3, label: "0.2" }, // 0.2°
  { suffix: "-p08", minzoom: 0, maxzoom: 1, label: "0.8" }, // 0.8°, covers z0 and z1
];

/**
 * ERA5 needs no pyramid: **one rung at its native 0.25°, covering z2-z5.**
 *
 * The pyramid exists because the 0.1° grid overflows the 2500 KB per-layer-per-tile ceiling at low
 * zoom — measured at 8183 KB for the worst z2 tile. ERA5 is 3.7x sparser (593K features against
 * 2.21M), which puts its worst z2 tile at an estimated ~1665 KB, inside the limit. Two things make
 * that estimate conservative: our layers are already latitude bands, so per-layer counts run below
 * whole-tile arithmetic, and ERA5 features carry 6 properties against the hi-res 18.
 *
 * z2 rather than z0 is not a compromise — every production recipe pins `minzoom: 2` and the app's
 * MIN_ZOOM is 2.2, so z0-1 has never been served. Serving z0-1 was a hi-res-only decision, and it
 * is what forced the coarse rungs there.
 *
 * NOTE: this is right for the raw ERA5 maps and is also right for the ERA5-vs-v3 comparison on the
 * 0.2° grid (~2044 KB at z2), which is why ERA5V3_RUNGS below has the same single rung. It is NOT
 * right for ERA5-vs-v4 on the 0.1° grid: that lands back near 8183 KB, so `rungsFor` gives it
 * HIRES_RUNGS instead. Question resolved; see docs/era5-and-gcm-maps.md for the workings.
 */
export const ERA5_RUNGS: HiResRung[] = [
  // The native grid, and the only rung. maxzoom 5 because clients overzoom past it.
  { suffix: "", minzoom: 2, maxzoom: 5, label: "0.25" },
];

/**
 * ERA5 used as the yardstick rather than as a map in its own right: **`v3 - ERA5` on the live
 * 0.2° grid**, so "how wrong is what we publish today". Same single rung as V3ABS_RUNGS — same
 * grid, same ~425k cells — and the note on ERA5_RUNGS above already sizes it at ~2044 KB for the
 * worst z2 tile, inside the 2500 KB ceiling.
 *
 * Unlike `era5`, this one IS a signed difference, so it takes the diverging `diffMap` ramp.
 */
export const ERA5V3_RUNGS: HiResRung[] = [
  // The live grid, and the only rung.
  { suffix: "", minzoom: 2, maxzoom: 5, label: "0.2" },
];

/**
 * Which pyramid a build refers to. They differ only in what the values mean and which grid they sit
 * on, so they differ only by this infix in every id.
 *
 *  - `hires`  — the new data itself          (`hires-maps pyramid`      -> `{id}-hires*.geojsonld`)
 *  - `diff`   — the new data minus the live map (`hires-maps diff-pyramid` -> `{id}-diff*.geojsonld`)
 *  - `era5`   — the ERA5 observations themselves (`hires-maps era5-map`  -> `{id}-era5.geojsonld`)
 *  - `era5v3` — the LIVE data minus ERA5  (`era5-diff --reference v3` -> `{id}-era5v3.geojsonld`)
 *  - `era5v4` — the NEW data minus ERA5   (`era5-diff --reference v4` -> `{id}-era5v4*.geojsonld`)
 *
 * The two ERA5 comparisons are the pair that answers the migration question: `era5v3` measures how
 * wrong today's map is, `era5v4` whether the new one is closer to reality. Note the asymmetry in
 * rung count that follows from their grids — `era5v3` is one file, `era5v4` is three.
 *
 * Keeping the dataset `id` itself untouched matters: `tokenizeDatasetId` in utils.ts requires a
 * 5-digit id and would reject anything like `40105-diff`.
 *
 * Tileset-id length is fine at these spellings: the longest is `40105-era5v4-p08-east-v4` at 24
 * characters against Mapbox's 32, so there is no need for a shortened `e5v4` infix.
 */
export type PyramidVariant = "hires" | "diff" | "era5" | "era5v3" | "era5v4" | "abs" | "v3abs";

/**
 * The change indicators republished as ABSOLUTE maps. Five of them (40601, 40607, 40613, 40614,
 * 40616) have an ERA5 counterpart to sit beside — and ERA5 is absolute, because deriving a change
 * from two windows of a single observed record measures weather variability as much as climate.
 * 40703 and 40704 have no ERA5 partner and are republished for completeness.
 *
 *  - `abs`   — v4 at 0.1°, so it needs the full pyramid like any other 0.1° build
 *  - `v3abs` — v3 at 0.2°, ~425k cells: the resolution production has always served at z2-5 as a
 *              single tileset, so there is nothing to coarsen. Same single rung as ERA5.
 */
export const V3ABS_RUNGS: HiResRung[] = [
  // The live grid, and the only rung.
  { suffix: "", minzoom: 2, maxzoom: 5, label: "0.2" },
];

/**
 * Comparison-map builds live in their own folder (`hires-maps` writes them there — see
 * DIFF_MAPS_DIR in its config.py), a sibling of the `old-geojson/` folder holding the live maps they
 * are differenced against. ERA5 builds get their own sibling folder. Hi-res builds stay directly in
 * data/mapbox/mts.
 */
export const DIFF_SUBDIR = "diff-geojson";
export const ERA5_SUBDIR = "era5-geojson";

/** Subfolder of data/mapbox/mts holding this variant's `.geojsonld` files ("" = the folder itself). */
export const pyramidSubdir = (variant: PyramidVariant = "hires"): string => {
  if (variant === "diff") return DIFF_SUBDIR;
  if (variant === "era5" || variant === "era5v3" || variant === "era5v4") return ERA5_SUBDIR;
  return "";
};

/** The rungs this variant publishes. The 0.1° variants need the pyramid; the coarser ones do not. */
export const rungsFor = (variant: PyramidVariant = "hires"): HiResRung[] => {
  if (variant === "era5") return ERA5_RUNGS;
  if (variant === "era5v3") return ERA5V3_RUNGS;
  if (variant === "v3abs") return V3ABS_RUNGS;
  // era5v4 is native 0.1° like `hires`, `diff` and `abs`, so it wants the full pyramid. Stated
  // explicitly rather than left to the fall-through: with an if-chain the compiler cannot tell you
  // whether a new variant was considered here or forgotten.
  if (variant === "era5v4") return HIRES_RUNGS;
  return HIRES_RUNGS;
};

/** GeoJSON file id (within `pyramidSubdir(variant)`) for one rung of one variant. */
export const pyramidFileId = (
  datasetId: string,
  rung: HiResRung,
  variant: PyramidVariant = "hires",
): string => `${datasetId}-${variant}${rung.suffix}`;

/** Dataset id used to mint this rung's tileset ids (keeps production ids untouched). */
export const pyramidDatasetId = (
  datasetId: string,
  rung: HiResRung,
  variant: PyramidVariant = "hires",
): string => `${datasetId}-${variant}${rung.suffix}`;

/**
 * Point every layer at this rung's source and pin it to the rung's zoom band, keeping the
 * layer keys (source-layer names) identical across rungs.
 */
export function setRungLayers(
  layers: RecipeLayers,
  source: string,
  rung: HiResRung,
): RecipeLayers {
  return Object.fromEntries(
    Object.entries(layers).map(([name, layer]) => [
      name,
      { ...layer, source, minzoom: rung.minzoom, maxzoom: rung.maxzoom },
    ]),
  ) as RecipeLayers;
}

/** Composite URL listing every rung tileset (east then west) plus the Mapbox base layers. */
export function hiResCompositeUrl(eastIds: string[], westIds: string[]): string {
  return `mapbox://${eastIds.join(",")},mapbox.mapbox-streets-v8,${westIds.join(
    ",",
  )},mapbox.mapbox-terrain-v2`;
}
