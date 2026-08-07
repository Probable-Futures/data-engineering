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

/** GeoJSON file id (under data/mapbox/mts) for one rung of a hi-res dataset. */
export const hiResFileId = (datasetId: string, rung: HiResRung): string =>
  `${datasetId}-hires${rung.suffix}`;

/** Dataset id used to mint this rung's tileset ids (keeps production ids untouched). */
export const hiResDatasetId = (datasetId: string, rung: HiResRung): string =>
  `${datasetId}-hires${rung.suffix}`;

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
