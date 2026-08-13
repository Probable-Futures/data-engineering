# hires-maps

Build Probable Futures map data from the new **downscaled, warming-level** climate data
(the Zarr batch under `~/work/pf-downscaled-data/warming_levels_aggregates`).

Pipeline (see [`../docs/warming-levels-data-and-next-steps.md`](../docs/warming-levels-data-and-next-steps.md)):

```
Zarr (warming levels) -> GeoJSON (.geojsonld) -> Mapbox tileset/style
```

We go straight from Zarr to GeoJSON — no netCDF, and (for now) no database on the way to the
map. The database writer is built alongside but stays **off** until Phase 3.

## Setup

```bash
cd hires-maps
python3.13 -m venv .venv
.venv/bin/pip install -e ".[dev]"
source .venv/bin/activate
```

Point at the data with `PF_DOWNSCALED_DATA=/path/to/pf-downscaled-data` if it is not at the
default `~/work/pf-downscaled-data`.

## Dev explorer (built first)

A throwaway tool for inspecting the Zarr files while developing — **not** part of the build
pipeline:

```bash
hires-explore list                                   # what's on disk
hires-explore describe days-above-35c                # shape: wl, stat, vars, ranges
hires-explore point    days-above-35c --lat 33.9 --lon 35.5   # what one cell will carry
hires-explore patch    days-above-35c --wl 1.5 --lat 33.9 --lon 35.5
hires-explore landmean days-above-35c                # sanity: land-mean per warming level
```

## Layout

```text
src/hires_maps/
  config.py        # paths + constants (data root, warming levels, stats, naming)
  indicators.py    # registry: slug -> live map id, unit, mid rule, change/transform flags
  stores.py        # open a warming-level Zarr store; list what's on disk (shared IO)
  transforms.py    # unit conversions for the stores whose units don't match the live map
  geojson/         # (Phase 1) Zarr -> .geojsonld builder + square-cell geometry   [not built yet]
  db/              # (Phase 1, OFF) writer to pf_grid_coordinates / pf_dataset_statistics  [not built yet]
  cli.py           # the build command(s)                                          [not built yet]
  dev/explore.py   # DEV-ONLY inspection tool
tests/
```

## Change maps and unit conversions

Not every store is in the form its live map publishes. The registry records this per indicator,
and the builder applies it in a fixed order — **transform → coarsen → land mask → change**:

| Live id | Map | What the builder does |
|---|---|---|
| 40601, 40613, 40614, 40616 | precipitation / snowy days | emit `value(wl) − value(0.5)`; baseline → 0 |
| 40703 | water balance | percentile → SPEI z-score, **then** the change |
| 40701, 40702 | drought | ×100 (the store holds a 0–1 fraction) |
| all others | heat, day counts | absolute values, unchanged |

Four things worth knowing:

- The change is **derived**, not read from the store's `diff_*` variable — that variable is
  all-NaN at the 0.5 °C level (which would break the land mask), and water balance has to be
  differenced *after* its transform, not before. Verified equal to `diff_*` on 1.2M sampled
  values: 8 differ, all by 0.1, all from float32 rounding boundaries. After integer truncation
  those boundaries land on whole numbers instead of tenths, so re-measured the same way: 2 of
  905k mid values across the four change maps truncate one step differently from `diff_*`
  (~1 in 450k, always by 1). Well below the maps' bin widths.
- `data_baseline_*` is 0 on change maps, matching what the live SQL forces. The app never paints
  that layer — picking 0.5 °C on a change map jumps to 1.0 °C.
- Water balance converts every real percentile and clamps only the ones where `Phi^-1` is
  infinite: percentiles of exactly 0 (**3,800** across the full grid, 3,582 in the 18 slices a
  build reads) go to ±`Z_LIMIT` = 6.0, and the build logs the count. Carlos confirmed the forward
  direction is `NormalDist().cdf(z) * 100`, so this transform is exactly its inverse. Asking him
  for the raw SPEI field would remove the clamp entirely — his pipeline evidently has it.
- Values are written at the same precision the live importer's `stat_fmt` produces
  (`netcdfs/import/helpers.py`), re-implemented in `formatting.py`: **integers truncated toward
  zero** for °C / days / mm / %, **one decimal** for the z-score map. Truncation, not rounding —
  34.9 °C is published as 34 today, so it is published as 34 here.

## Comparison maps (red/blue)

```bash
hires-maps live-maps                          # which live exports are on disk
hires-maps diff days-above-35c                # new - live, native 0.1°
hires-maps diff-pyramid days-above-35c        # ...all three rungs
hires-maps diff-all [--pyramid]               # every indicator that has both halves
```

These answer "how does the new data differ from what is live today?" — the question a swipe
comparison cannot answer, because a systematic bias makes two maps that still look alike. The
output is one layer whose value is `new - live`, published with the diverging red/blue ramp in
`vector-tiles/configs.ts` (`DIFF_COLORS` / `DIFF_STOPS`) and uploaded with
`npm run create-tilesets -- <id> --diff`.

**Why red/blue.** A difference map is signed around a meaningful zero, and zero is its most
important value: it means *the two datasets agree*. That calls for a **diverging** ramp rather than
the sequential climate ramps — hue carries the sign (blue = new is lower, red = higher), saturation
carries the magnitude, and the neutral middle band is a real reading, not a gap. Three rules the
palette follows: stops symmetric about zero (asymmetric stops make the eye see a bias that is not
there), a grey neutral rather than white (white reads as no-data on a map), and red/blue rather than
red/green so it survives the common colour-blindness cases. Same convention as
`analysis/lib.py:plot_map(diverging=True)`, which uses `RdBu_r` for the static plots.

**Which difference.** `docs/HI-RES-TILES.md` §9 defines two. This builds the **detail diff**: for
every new 0.1° cell, `new - (the live 0.2° value covering it)`, on the 0.1° grid — what the finer
grid bought us, and where. Four new cells share one live parent, so genuine 0.2°-blocky structure
appears at deep zoom; that is the signal. The **model diff** (aggregate the new data to 0.2° first,
then subtract) separates "the model moved" from "the resolution changed" and is not built yet.

Details that matter:

- The live half comes from `data/mapbox/mts/old-geojson/*.geojsonld` — the **published** values, so
  the comparison is against what users actually see. `livemaps.py` reads them.
- Output goes to `data/mapbox/mts/diff-geojson/{live_id}-diff[-p02|-p08].geojsonld`, a sibling of
  that folder, so both halves of a comparison sit together and neither crowds the `-hires` builds.
  `vector-tiles` hardcodes the same folder name as `DIFF_SUBDIR` in `hires.ts` — the two have to stay
  in step. (It is passed to the uploader separately from the dataset id, because that id also becomes
  the Mapbox tileset source id, which cannot contain a slash.)
- The grids are **centre-aligned**: every live cell centre falls exactly on a new cell centre
  (nearest new index for live cell *k* is `2 + 2k`), so the parent lookup is integer arithmetic, no
  interpolation. It is done in integer tenths of a degree because in floating point
  `(89.8 - 89.7) / 0.2` is `0.4999…`, which would shift boundary cells unpredictably.
- They are aligned but not *nested*, so odd-indexed new cells sit on a live cell boundary and are
  equidistant from two parents. Ties break upwards (southward / eastward), consistently.
- The comparison is only defined where both halves have a value, so cells outside the intersection
  are `null`, never 0 — otherwise every coastline reads as a real disagreement. Each build prints
  the three counts. For 40105: 1,354,932 comparable, 858,098 new-only, 347,280 live-only (both
  fringes are coastline and island effects, the live grid being coarser).
- **Change maps** need care: the live ones keep the *absolute* baseline in the 0.5 °C slot while the
  other levels hold changes (40601 ships `data_baseline_mid` ≈ 744 mm next to `data_1c_mid` ≈
  +24 mm). Comparison builds therefore keep our absolute baseline too (`zero_baseline=False`), so
  the baseline slot is absolute-vs-absolute and every other slot is change-vs-change.
- Diffs are written with **one decimal for every unit** (`DIFF_DECIMALS`), not integer-truncated
  like the maps themselves: a real +0.7 °C disagreement would truncate to 0 and the map would claim
  agreement.
- **`low`/`mid`/`high` stop being an ordered range.** Each is an independent comparison of its own
  statistic, so `low` can exceed `high` — a real cell in India reads `low +2.0, mid -4.9,
  high -17.0`, meaning the two datasets disagree least at the 5th percentile and most at the 95th.
  The map itself is unaffected (the fill reads `mid` only), but the app's popup will render the
  triplet as a "cooler year / average year / warmer year" range, which is meaningless here. Read
  them as three separate comparisons.

## Tooling

`pyproject.toml` (PEP 621), Python 3.13, `ruff` (lint + format), `pytest`, `typer` for CLIs.
Run checks with `.venv/bin/ruff check .` and `.venv/bin/pytest`.
