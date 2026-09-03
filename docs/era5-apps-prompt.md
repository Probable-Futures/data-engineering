# Prompt for the apps repo — ERA5 support in the map builder

Paste everything below into Claude Code from `~/work/apps`.

---

Add support for **ERA5 maps** to the map builder: display them, and allow comparing them
side by side against our own map versions.

## What ERA5 is (background — none of this is in this repo yet)

ERA5 is **reanalysis data: observations, not a model run.** Real measurements — weather stations,
satellites, buoys — passed through a weather model that fills the gaps, giving a gridded best
estimate of what actually happened. Every map we currently serve (v3 and v4) is model output, so
ERA5 is the first thing we have that can show whether our published data is *right*, rather than
just showing that two models disagree.

Three properties of it drive everything below:

1. **It has only two warming levels: 0.5 (baseline) and 1.0 °C.** A warming level is "the world when
   global temperature was X°C above pre-industrial". Observations only reach ~1.2 °C, so there is no
   observed 1.5, 2, 2.5 or 3 °C world. The published tiles carry **only** `data_baseline_*` and
   `data_1c_*` — the other twelve properties are absent, not null.
2. **It is an absolute climate map, not a signed difference.** So it uses the dataset's **normal
   climate ramp** (`map.stops` / `map.binHexColors`), *not* the red/blue diverging diff ramp.
3. **It is 0.25° and covers all land except Antarctica.** Antarctica renders as no-data on every
   ERA5 map. That is expected, not a bug.

Also worth knowing: it is a single tileset rung covering z2–5 (no resolution pyramid — 0.25° is
sparse enough to fit the tile size limit), published from the `data-engineering` repo with
`npm run create-tilesets -- <datasetId> --era5`. The Mapbox style is created there, so this repo
only ever consumes a style id.

**24 datasets have ERA5 data:** 40101, 40102, 40103, 40104, 40105, 40106, 40107, 40201, 40202,
40203, 40204, 40205, 40206, 40207, 40301, 40302, 40303, 40304, 40305, 40601, 40607, 40613, 40614,
40616. Note 40607 has ERA5 but no v4. There is no ERA5 for drought (40701, 40702), water balance
(40703), wildfire (40704), climate zones (40901) or storm frequency (40612).

## What to mirror — read these first

We already solved "a hardcoded map style that isn't a database row" for the difference maps. **Follow
that pattern rather than inventing a second one.** Read these before planning:

| File | What it gives you |
|---|---|
| `packages/maps/src/consts/versionDiffMaps.ts` | The registry pattern: a `VersionDiffMap` type, a `diffMap(...)` factory, a `versionDiffMaps: VersionDiffMap[]` array ordered by dataset id, and lookups `getDiffMapsForDataset` / `getDiffMapForPair`. Note the convention that an **empty `mapStyleId` means "not published yet"** (see 40202). |
| `packages/maps/src/utils/useActiveDiffMap.ts` | How a hardcoded style overrides the selected dataset's own: `useActiveDiffMap()` plus `getActiveMapStyleId(selectedDataset, activeDiffMap)`. |
| `packages/maps/src/utils/mapVersions.ts` | `getVersionsOfDataset`, `getDefaultVersionPair`, `getAvailableDiffPairs`, `getDefaultDiffPair`. |
| `packages/maps/src/components/Maps/MapBuilder.tsx` | Where it all lands. `isComparing` gates `VersionComparisonMapView`; `getMapStyleLink(dataset)` builds `mapbox://styles/{account}/{dataset.mapStyleId}`; `mapStyleLink` uses `getActiveMapStyleId`. Also the `hasStyleError` / `StyleErrorBanner` path for a style Mapbox cannot load. |
| `packages/maps/src/components/Maps/VersionComparisonMapView.tsx` | The existing swipe comparison (`mapbox-gl-compare`). It takes `datasetBefore` / `datasetAfter` plus `mapStyleUrlBefore` / `mapStyleUrlAfter` — already the right shape for this. |
| `packages/maps/src/consts/mapConsts.ts` | `ComparisonMode = "none" \| "swipe" \| "diff"`, `parseComparisonMode`, and the `compare` / `version_before` / `version_after` query params. |
| `packages/maps/src/components/MapBuilderHeader.tsx` and `packages/maps/src/components/Menu/Data.tsx` | The comparison segmented control and version pickers — **both** render it, and both need to stay in step. `Data.tsx` also owns restoring comparison state from the URL. |
| `packages/lib/src/consts/mapConsts.ts` | `degreesOptions` — the six warming levels and their `dataKey`s (`data_baseline`, `data_1c`, `data_1_5c`, …). |

## Scope

**In:**

1. **A hardcoded ERA5 style registry**, mirroring `versionDiffMaps.ts`. One entry per dataset id
   that has an ERA5 style, with the style id and a "pending" convention for ones not yet published.
   I will fill in the real style ids; leave them empty or clearly marked as placeholders.
2. **Display an ERA5 map when one exists for the selected dataset.** The user needs a way to switch
   the main map to ERA5 and back. Reuse the dataset's normal ramp — ERA5 is absolute, so the key and
   legend should behave exactly like a normal climate map, not like a difference map.
3. **Side-by-side comparison with ERA5** in the map builder, via the existing `swipe` mode and
   `VersionComparisonMapView`: our map on one side, ERA5 on the other.
4. **Handle the two-warming-level limit** (see constraints).
5. **Tests**, following `packages/maps/src/utils/__tests__/versionDiffMaps.test.ts` and
   `mapVersions.test.ts`. Translation keys for any new UI string, in all four locale files under
   `packages/maps/src/locales/`.

**Out of scope — do not build:**

- **No ERA5 difference maps.** No computed "v3 minus ERA5" or "v4 minus ERA5" layer, and no new
  entries in the red/blue diff registry. Side-by-side only, for now.
- No changes to how existing v3/v4 versions or the current diff maps behave. This is additive.
- No data pipeline work — the tiles and styles are produced in the `data-engineering` repo.

## Two constraints that will bite

**1. ERA5 has no 1.5–3 °C levels.** If the user has an ERA5 map on screen and picks 2 °C, the map
goes blank, because `data_2c_mid` does not exist in the tiles. Those levels need to be disabled (with
a hint explaining why) whenever ERA5 is the displayed map or either side of a comparison. Relevant
code: `degreesOptions` in `packages/lib/src/consts/mapConsts.ts`,
`packages/maps/src/utils/useDegreesSelector.ts`, and
`packages/maps/src/components/WarmingScenarioSelection.tsx`. Note there is already precedent for
special-casing a warming level — `useDegreesSelector` intercepts 0.5 on change maps and shows a
modal.

**2. ERA5 is not a version of the dataset.** The whole swipe path is built around `versionBefore` /
`versionAfter` being `types.Map` rows from the database, selected by numeric `mapVersion`, and
persisted to the URL as numbers (`version_before=3&version_after=4`). ERA5 has no database row and no
version number. **Decide deliberately how to represent it** and explain the trade-off before
implementing — the options I can see are a synthetic `types.Map`-shaped object built from the
registry entry, a separate piece of comparison state alongside the version pair, or widening the
comparison side to a union type. Whichever you pick has to survive a URL round-trip, since `Data.tsx`
restores comparison state from query params on load.

## How to proceed

Explore the files above first, then **come back with a short plan** — especially your answer to
constraint 2 — before writing code. Flag anything in this description that turns out to be wrong
about the codebase rather than working around it.
