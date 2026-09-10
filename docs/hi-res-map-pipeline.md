# `hires-maps` + `vector-tiles` — the hi-res map pipeline

**Reference for how the 0.1° data becomes a web map, and the rules that shape it.** It covers why a
denser grid breaks low-zoom tiles, the constraints you may not break, the three-rung resolution
pyramid we ship, and how to build and publish. It describes only what is true now — for why the
shape is what it is, and what is still open, see
[`decisions-and-status.md`](decisions-and-status.md).

The data this consumes is described in [`downscaled-data.md`](downscaled-data.md).

## Contents

- [Vocabulary](#vocabulary)
- [How vector tiles work, and the limit that bites](#how-vector-tiles-work-and-the-limit-that-bites)
- [Hard constraints](#hard-constraints)
- [Why low zoom overflows](#why-low-zoom-overflows)
- [The resolution pyramid](#the-resolution-pyramid)
- [Building the map data](#building-the-map-data)
- [Publishing to Mapbox](#publishing-to-mapbox)
- [Viewing and comparing](#viewing-and-comparing)
- [Comparison maps: two different questions](#comparison-maps-two-different-questions)
- [The database writer](#the-database-writer)

## Vocabulary

| Word | What it means |
|---|---|
| **cell** | One little square on the map, holding one number (e.g. "34 days above 35 °C"). |
| **resolution** | How big each square is. The source data is **0.1°**, about 11 km. |
| **finer / coarser** | Smaller squares, more detail / bigger squares, less detail. "Coarsening" makes squares bigger. |
| **tile** | The map is delivered as a grid of small squares called tiles. Each tile carries every cell inside its area. |
| **zoom level** | How far in you are: **z0** is the whole world, **z5** is zoomed in. Each step doubles the detail. |
| **rung** | One complete copy of the map at one resolution, e.g. "the 0.2° rung". |
| **pyramid / ladder** | The full set of rungs stacked by zoom — coarse when zoomed out, fine when zoomed in. |
| **aggregate / coarsen** | Combine several small cells into one bigger cell by averaging their values. |

## How vector tiles work, and the limit that bites

A web map is not one giant image. It is a **pyramid of 512×512 tiles**. The whole world fits in one
tile at z0, and each zoom step splits every tile into four:

| Zoom | Tiles across the world | Degrees of longitude per tile (at the equator) |
|---|---|---|
| 0 | 1 × 1 = 1 | 360° |
| 2 | 4 × 4 = 16 | 90° |
| 3 | 8 × 8 = 64 | 45° |
| 4 | 16 × 16 = 256 | 22.5° |
| 5 | 32 × 32 = 1024 | 11.25° |

**The number of tiles at a zoom level is fixed by the zoom, not by our data.** Zooming in does not
cram more data into a tile — it gives you *more tiles, each covering a smaller area*. So finer data
does not add tiles; it adds **more features inside each low-zoom tile**.

**Vector tiles** carry real geometry. Our climate grid is a set of small square polygons, one per
cell, each holding the climate values (`data_1c_mid`, `data_2c_mid`, …) as properties.

### The size limit

Mapbox Tiling Service (MTS) enforces a **maximum size per layer, per tile**:

| Limit | Value |
|---|---|
| Default | 1250 KB |
| Absolute maximum | **2500 KB** — every one of our recipes already uses this |

If a layer's data in a tile exceeds the limit, **MTS silently drops features** to make it fit and
emits a **`W201` warning** in the publish job report. That warning carries a `capped_list` naming
exactly which layer, which zoom levels and which tiles were too big, plus the `layer_size` that
*would* have been needed. It is the primary diagnostic for this whole class of problem.

Because a low-zoom tile covers a huge area, it must hold *every* cell in that area. That is where a
4× denser grid hits the wall.

## Hard constraints

> **These four are not tuning knobs. Changing one either costs money or silently breaks the map.**
>
> 1. **`maxzoom` must stay ≤ 5.** Under Mapbox's legacy pricing, tilesets with **`maxzoom < 6` are
>    free**. Raising the recipe `maxzoom` to 6 or above can quietly start billing the account. This
>    is why every production recipe pins `maxzoom: 5`, and the hi-res pyramid must fit entirely
>    inside it. **Do not raise it.**
> 2. **`layer_size` is already maxed.** 2500 KB is the absolute MTS ceiling and every layer already
>    sits there. There is no byte-budget lever left to pull — the only remaining fix for an
>    overflowing tile is **fewer features**.
> 3. **Read the `W201 capped_list`; do not guess the cutover zoom.** Per-layer counts are much lower
>    than whole-tile arithmetic suggests, because our layers are already narrow latitude bands. Any
>    claim about which zoom overflows must come from an actual publish job report.
> 4. **Publish under a new id namespace.** Hi-res and comparison tilesets/styles get their own ids
>    on the same `probablefutures` Mapbox account, so production tilesets are never overwritten.

**Why `maxzoom: 5` still gives a usable map:** clients **overzoom**, scaling z5 tiles for deeper
zoom levels, and our square grid cells scale perfectly. `maxzoom` limits what is *generated*, not
what a user can zoom to.

### The production recipes we work from

Every layer in `templates/east.recipe.json`, `west.recipe.json` and `world.recipe.json` — **25
layers**, 17 + 7 + 1 — is configured identically:

| Setting | Value | Meaning |
|---|---|---|
| `minzoom` | **2** | Lowest zoom generated (production never served z0–1) |
| `maxzoom` | **5** | Highest zoom generated; deeper zooms overzoom |
| `tiles.layer_size` | **2500** | Already the absolute maximum |

The layers are also already **latitude bands** — each region (`region_eu_af_6`, …) has a bbox
covering a slice of latitude, which by itself keeps low-zoom tiles smaller than a global layer
would be.

The hi-res pyramid extends down to **`minzoom: 0`** so the map works at every zoom
(see [Decisions](decisions-and-status.md#serve-every-zoom-z0-to-z5)).

## Why low zoom overflows

A tile at zoom `z` spans `360 / 2^z` degrees of longitude. Worst-case 0.1° cells packed into one
tile near the equator:

| Zoom | Max 0.1° cells / tile | Fits a 2500 KB layer? (~80–150 B/feature) |
|---|---|---|
| 3 | ~200,000 | **No** — roughly 10× over |
| 4 | ~50,000 | Borderline / over, even split in half |
| 5 | ~12,600 | Yes, comfortably |
| 6 | ~3,200 | Yes, trivially |

Order of magnitude only — see constraint 3 above. The measured picture from the first hi-res
publish agrees with it: with the production recipe at native 0.1°, the `W201` report dropped
features **only at z2 and z3**; z4 and z5 were clean. Most overflowing tiles needed ~2500–3300 KB
against the 2500 KB limit, and the worst (the Asia tile `2/3/3`) needed 8183 KB. Coarsening 2×2
blocks into one cell cuts the feature count 4×, which clears even that tile (8183 → ~2050).

For `days-above-35c` the jump is from **~425K features on the live 0.2° grid to ~2.21 M on the
0.1° grid** (measured 2,212,863).

### The synthetic stress test that proved it

Before real hi-res data existed, the failure was reproduced with fabricated data — the live 0.2°
`40105.geojsonld` with every square split into four 0.1° squares carrying the same value, giving
~1.7 M features (~830 MB). Three files still in the repo do this:

| File | Role |
|---|---|
| `vector-tiles/scripts/generate_hires_test.py` | subdivides the live grid into the synthetic 0.1° file |
| `vector-tiles/scripts/upload_hires_test.ts` | uploads it, splitting each layer's bbox in half by latitude into `_a`/`_b` sub-layers |
| `vector-tiles/templates/test-40105-style.json` | a Mapbox GL style pointing at the three test tilesets, for visual inspection |

**The result is the decisive evidence.** Low zoom was corrupted *even with every size-saving lever
already applied* — maximum `layer_size`, regional latitude bands, **and** the extra `_a`/`_b`
split. If a denser grid still overflows after all that, the only remaining fix is **fewer features
at those zooms**, which means aggregation.

> **Note:** that feature count belongs to the synthetic file alone — it is exactly 425K × 4. The
> real land grid is denser, at ~2.21 M, because the synthetic file inherits the live grid's coarser
> land mask. Do not read the two numbers as versions of the same measurement.

## The resolution pyramid

The fix is to **show fewer, bigger squares when zoomed out**. At z4 a 0.1° cell is already only
about 2 px, and at z0 it is a small fraction of one — invisible detail carrying many times more
data than the tile can hold. Replacing a block of cells with one cell holding their average looks
identical to the eye and weighs a fraction as much. The rule of thumb behind every rung boundary: a
cell should be at least ~1 pixel; anything finer is wasted bytes.

```text
Original 0.1° cells            Becomes one 0.2° cell
┌──────┬──────┐
│  12  │  14  │
├──────┼──────┤   average →    ┌─────────────┐
│  13  │  13  │                │     13      │
└──────┴──────┘                └─────────────┘
4 cells, 4 numbers              1 cell, 1 number  (4× less data)
```

An 8×8 block gives a 0.8° cell — 64× less data. The code is
[`hires-maps/src/hires_maps/aggregation.py`](../hires-maps/src/hires_maps/aggregation.py).

Two details it handles carefully:

- **Ocean cells are skipped, not counted as zero.** The data is land-only, so many cells are blank.
  A 2×2 block with two land cells averages **only those two**; otherwise coastlines would be dragged
  toward zero. All four blank → the big cell stays blank.
- **Cells near the poles count for less.** A square near the pole covers far less ground than one at
  the equator, so the average weights each cell by `cos(latitude)`. A plain mean would let tiny
  polar squares distort the result. Every property is averaged this way, including the low/high
  uncertainty band.

Each rung is a block average of the **native** grid, so the squares nest and line up exactly.

### The three rungs

| Rung | Cell size | Made by | Zoom band | Features for `days-above-35c` |
|---|---|---|---|---|
| native | 0.1° | the source data itself | z4–z5 | 2,212,863 |
| `p02` | 0.2° | averaging 2×2 blocks | z2–z3 | 563,055 |
| `p08` | 0.8° | averaging 8×8 blocks | z0–z1 | 38,187 |

The zoom bands are disjoint and together cover z0–z5. The executable version of this table is
`HIRES_RUNGS` in [`vector-tiles/hires.ts`](../vector-tiles/hires.ts); the build side is
`PYRAMID_FACTORS` in `hires_maps/cli.py`. There is deliberately **no 0.4° rung** — see
[Decisions](decisions-and-status.md#no-04-rung-the-coarsest-rung-starts-at-z0).

The zoomed-out rung is **58× smaller** than the native one, which is exactly why it fits.

`p02` and `p08` are the file-name tags: `40105-hires.geojsonld`, `40105-hires-p02.geojsonld`,
`40105-hires-p08.geojsonld`.

### How the map picks a rung

Each rung is uploaded as its own tileset, pinned to its own zoom band. Crucially **all rungs use the
same internal layer names**, so the style does not need to know the pyramid exists: it composites
every rung tileset and asks for "the climate layer", and Mapbox serves whichever rung owns the
current zoom. As you zoom in the map silently swaps chunky 0.8° squares → 0.2° squares →
full-detail 0.1° squares, and you only ever see the sharpest version your screen can resolve.

> **Note:** the app's own `MIN_ZOOM` (in `mapConsts.ts`) is currently **2.2**, so it will not
> request the z0/z1 tiles until that is lowered. The rungs are built anyway, for full zoomability
> in embeds and downloads.

## Building the map data

The build goes **straight from Zarr to GeoJSON** — no netCDF step, and no database on the way to the
map:

```text
Zarr (warming levels)
   → hires-maps (Python)  → GeoJSON (.geojsonld)  → vector-tiles uploader
      → Mapbox tileset + style  → MapBuilder / CompareMaps
```

A map only needs square polygons plus the warming-level values, and the Zarr already holds exactly
that, so writing the GeoJSON directly skips two hops (the netCDF import and the PostGIS round-trip
via `ogr2ogr`). The consequence that matters for sequencing: **the database is no longer on the
critical path for drawing maps.** It is still needed for the app's other features — click-a-point
popups, CSV downloads, the public data API — but not for tiles.

```bash
cd hires-maps
hires-maps build   days-above-35c     # native 0.1° only
hires-maps pyramid days-above-35c     # all three rungs
hires-maps build-all --pyramid        # every registered indicator
```

Output lands in `data/mapbox/mts/`, the folder the uploader reads. Full command reference:
`hires-maps --help` and [`../hires-maps/README.md`](../hires-maps/README.md).

For every land cell the builder writes one feature:

- **geometry** — a square of ±half a grid step around the cell centre: ±0.05° native, ±0.1° at
  `p02`, ±0.4° at `p08`.
- **properties** — the same 18 names the live maps and styles already use:
  `data_baseline_{low,mid,high}`, `data_1c_*`, `data_1_5c_*`, `data_2c_*`, `data_2_5c_*`,
  `data_3c_*`. The warming level → prefix mapping is `0.5→baseline, 1.0→1c, 1.5→1_5c, 2.0→2c,
  2.5→2_5c, 3.0→3c`, the same one the current database views apply. `low` = `p5`, `high` = `p95`,
  `mid` = `mean` or `p50` per indicator.
- Ocean and no-data cells are skipped; a cell that is NaN at only some warming levels gets `null`
  there, **never 0**.
- Values carry exactly the precision the live importer's `stat_fmt` produces — **integers truncated
  toward zero** for °C / days / mm / %, one decimal for the z-score map. Truncation is deliberate
  parity, not cosmetics: every published map holds truncated integers, so rounding here would make
  the new tiles disagree with the old by up to a whole unit in every popup and CSV. The rule lives
  in `hires_maps/formatting.py`.

Because the format, the property names and the output path all match what the existing tooling
expects, **the `vector-tiles` uploader and the map styles need no changes.**

## Publishing to Mapbox

```bash
cd vector-tiles
export MAPBOX_ACCESS_TOKEN=...              # or put it in vector-tiles/.env
npm run create-tilesets -- 40105 --hi-res   # 6 tilesets (east+west × 3 rungs), 1 style
npm run create-tilesets -- 40105 --diff     # the comparison pyramid instead
```

The uploader uploads each rung's source, validates the recipe, creates and publishes the tilesets,
and creates the style. `--hi-res` builds the pyramid; `--diff` publishes the comparison pyramid
(`{id}-diff*.geojsonld`) with the diverging red/blue ramp instead of the climate ramp and implies
`--hi-res`. The code is `vector-tiles/hires.ts` (rung config, `setRungLayers`, the composite URL)
and `processHiResDataset` in `createTilesets.ts`.

After publishing, **read the job report's `W201`** and expect no drops at any zoom. If z0 still
overflows for a large landmass the report will say so, and the answer is a coarser 1.6° (`p16`)
rung; if z0 is comfortable, z0–1 could merge onto a finer rung. Confirm from the report.

## Viewing and comparing

The internal app already has everything needed to look at a new map next to the live one:

- **MapBuilder** loads a map from `mapbox://styles/{account}/{dataset.mapStyleId}`, where
  `mapStyleId` comes from `packages/lib/src/consts/datasets.ts`. Point a **dev/staging** dataset
  entry's `mapStyleId` at the newly published style.
- **CompareMaps.tsx** uses `mapbox-gl-compare`, a swipe slider between a "before" and an "after"
  map. Live style on one side, new style on the other, gives a direct old-vs-new swipe internally
  before anything is released.

A swipe cannot reveal a systematic bias, though: two maps that are uniformly offset still look
alike. That is what the comparison maps below exist for, and `hires-explore landmean` gives the
same answer as a single number per warming level.

## Comparison maps: two different questions

Because the grids differ by 4×, "how do the new maps differ from the live ones?" is really two
questions, and they must not be conflated — separating resolution effects from data changes is the
classic trap when comparing mismatched grids.

**Detail diff — "what detail did we gain?"** For each new 0.1° cell,
`new_value − the live 0.2° value covering it`, on the 0.1° grid. Highlights coastlines, mountains
and cities where the finer grid changes the picture. Four new cells share one live parent, so real
0.2°-blocky structure appears at deep zoom: that is signal, not an artifact.

**Model diff — "did the underlying model change?"** Aggregate the new data back to 0.2° and diff
against the live grid at matched resolution. Near zero everywhere means pure refinement; hotspots
mean the values themselves moved.

The **detail diff is built**; the model diff is not
(see [Status](decisions-and-status.md#status)).

```bash
hires-maps live-maps                     # which live exports are on disk
hires-maps diff         days-above-35c   # new − live, native 0.1°
hires-maps diff-pyramid days-above-35c   # all three rungs
hires-maps diff-all [--pyramid]          # every indicator that has both halves
```

Output goes to `data/mapbox/mts/diff-geojson/{live_id}-diff[-p02|-p08].geojsonld`, a sibling of the
`old-geojson/` folder holding the live exports it is differenced against. Both sides of a
comparison sit together, and neither crowds the `-hires` builds. `vector-tiles` hardcodes the same
folder name as `DIFF_SUBDIR` in `hires.ts`, so the two must stay in step.

Three properties of the output that surprise people, all deliberate:

- **The result keeps the standard 18 `data_*` property names**, not a single `diff` property, so
  the recipes, the fill expression and the app's warming-level switcher all work untouched.
- **Values keep one decimal for every unit**, unlike the maps themselves. A real +0.7 °C
  disagreement truncated to 0 would make the map claim agreement — the one thing a comparison map
  must never do.
- **`low`/`mid`/`high` stop being an ordered range.** Each is an independent comparison of its own
  statistic, so `low` can exceed `high`. Read them as three separate comparisons, not as a range.

The full behaviour of the comparison builder — the land-mask intersection, the change-map baseline
asymmetry, the tie-breaking parent lookup — is documented in
[`../hires-maps/README.md`](../hires-maps/README.md).

## The database writer

The builder has a second output behind a `--write-db` flag, **default off**. It targets the tables
the current pipeline already uses (`pf_grid_coordinates` for cells, `pf_dataset_statistics` for
values) rather than a parallel schema, fed by the builder's `on_feature` hook so the GeoJSON and
database stages share one pass over the data.

It is written and tested but does not persist anything: it shapes and counts the rows that *would*
be written. Turning it on is a later phase, because the bigger grid forces schema decisions that
are still open — see
[Open questions: the database schema](decisions-and-status.md#the-database-schema-phase-3).
