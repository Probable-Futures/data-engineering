/**
 * Hi-res resolution pyramid (see docs/warming-levels-data-and-next-steps.md §8).
 *
 * The new 0.1° data overflows low-zoom tiles. We fix it by serving coarser precomputed rungs
 * at low zoom: native 0.1° at z4-5, 0.2° at z2-3, 0.8° at z0-1. Each rung is its own
 * tileset built from its own `.geojsonld` (produced by `hires-maps pyramid`), but every rung
 * KEEPS THE SAME LAYER KEYS. Because the tilesets share source-layer names and cover disjoint
 * zoom ranges, compositing them all in one style makes Mapbox serve the right rung per zoom —
 * so the map style needs no per-rung layers.
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
 * Which pyramid a build refers to. Both are the new 0.1° data on the same three rungs; they differ
 * only in what the values mean, so they differ only by this infix in every id.
 *
 *  - `hires` — the new data itself           (`hires-maps pyramid`      -> `{id}-hires*.geojsonld`)
 *  - `diff`  — the new data minus the live map (`hires-maps diff-pyramid` -> `{id}-diff*.geojsonld`)
 *
 * Keeping the dataset `id` itself untouched matters: `tokenizeDatasetId` in utils.ts requires a
 * 5-digit id and would reject anything like `40105-diff`.
 */
export type PyramidVariant = "hires" | "diff";

/**
 * Comparison-map builds live in their own folder (`hires-maps` writes them there — see
 * DIFF_MAPS_DIR in its config.py), a sibling of the `old-geojson/` folder holding the live maps they
 * are differenced against. Hi-res builds stay directly in data/mapbox/mts.
 */
export const DIFF_SUBDIR = "diff-geojson";

/** Subfolder of data/mapbox/mts holding this variant's `.geojsonld` files ("" = the folder itself). */
export const pyramidSubdir = (variant: PyramidVariant = "hires"): string =>
  variant === "diff" ? DIFF_SUBDIR : "";

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
