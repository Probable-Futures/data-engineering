# `hires-maps/` — build map data from the warming-level Zarr

Build Probable Futures map data from the new **downscaled, warming-level** climate data
(the Zarr batch under `~/work/pf-downscaled-data/warming_levels_aggregates`).

Pipeline (see [`../docs/hi-res-map-pipeline.md`](../docs/hi-res-map-pipeline.md)):

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

## Dev explorer

`hires-explore` inspects the Zarr files by hand while developing — **not** part of the build
pipeline, and nothing it prints reaches a map.

| Command | What it shows |
|---|---|
| `hires-explore list` | Every indicator folder on disk, with its live id, unit and `mid` statistic (or `(not in registry)`). |
| `hires-explore describe days-above-35c` | One store's shape: dimensions, warming levels, statistics, variables, and each variable's range and % ocean. |
| `hires-explore point days-above-35c --lat 33.9 --lon 35.5` | The whole warming-level × statistic table at the nearest land cell — **raw** store values, plus a note naming the transform and/or change the builder will then apply. |
| `hires-explore patch days-above-35c --wl 1.5 --lat 33.9 --lon 35.5` | A small grid of values around a point (`--size`, `--stat`), so spatial detail is readable as text. `----` is ocean. |
| `hires-explore landmean days-above-35c` | Area-weighted land-mean per warming level — the quickest check that the numbers are plausible at all. |

> **Two zarr warnings are expected** on `describe`/`point`/`patch`/`landmean`: a
> consolidated-metadata `RuntimeWarning` and a `.DS_Store` `ZarrUserWarning`. Nothing is broken —
> a blanket filter used to hide them and was removed on purpose, because the first is a real
> performance signal (`zarr.consolidate_metadata()` on the stores would speed up every open).

## Layout

```text
src/hires_maps/
  cli.py            # build/pyramid/build-all, diff/diff-pyramid/diff-all, live-maps
  config.py         # paths (PF_MTS_DIR override), grid + warming-level constants
  indicators.py     # the 26-indicator registry
  mapping.py        # warming level + stat -> property name (PlanEntry, property_plan)
  transforms.py     # pct100, percentile_to_z
  formatting.py     # stat_fmt / formatter — publication precision
  geometry.py       # cell_ring
  aggregation.py    # coarsen to the pyramid rungs
  stores.py         # IO: store_path, list_on_disk, open_store, value_var
  livemaps.py       # read the live 0.2° exports; grid alignment
  geojson/
    stages.py       # Grid, load, apply_transform, to_change, land_mask
    output.py       # Variant, rung_suffix, output_path, write_features
    builder.py      # build()
    diff_builder.py # DIFF_DECIMALS, DiffReport, build_diff()
  db/writer.py      # StatWriter (built, OFF until Phase 3)
  dev/explore.py    # hires-explore
  dev/sampling.py   # area_weighted_mean, value_at
tests/              # 14 test modules, run with .venv/bin/pytest
```

## Build the maps

| Command | What it does |
|---|---|
| `hires-maps build days-above-35c` | One indicator at the native 0.1° rung. |
| `hires-maps build days-above-35c --factor 2` | One indicator at a coarser rung (`2` = 0.2°, `8` = 0.8°). |
| `hires-maps pyramid days-above-35c` | The three rungs we publish: native, `p02`, `p08`. |
| `hires-maps build-all [--pyramid]` | Every indicator on disk — native only, or all three rungs. |

`--limit N` caps the features written on `build`, `build-all`, `diff` and `diff-all` — a smoke test
that finishes in seconds, not minutes. `--out` overrides the path for a single `build` or `diff`.
`--write-db` (on `build`, `pyramid`, `build-all`) also runs the DB writer, which is **off**: it
shapes and counts the rows it *would* write, and only on the native rung — coarse rungs are
tile-only. `hires-maps --help` carries the rest.

Output lands under `data/mapbox/mts/`, where `vector-tiles` reads it (paths from `config.py`): the
new maps as `{live_id}-hires[-pNN].geojsonld`, comparison maps in `diff-geojson/`, and the live
exports a comparison reads in `old-geojson/`. That folder is located by walking up for a parent
holding `vector-tiles/` — a **tracked** marker, unlike the gitignored `data/mapbox`, which a fresh
clone does not have. Set **`PF_MTS_DIR`** to skip the search: a wheel install, or any layout where
the walk would not land in this repo.

Then publish: `cd ../vector-tiles && npm run create-tilesets -- 40105 --hi-res` — see
["Publishing to Mapbox"](../docs/hi-res-map-pipeline.md#publishing-to-mapbox).

## Change maps and unit conversions

Not every store is in the form its live map publishes. The registry records this per indicator, and
`builder.py` applies it in a fixed order — **transform → coarsen → land mask → change**. The
comparison builder necessarily uses a different order (the live join has to happen before
coarsening, its land mask after the subtraction); the reconciliation table is in
`geojson/stages.py`'s module docstring.

| Live id | Map | What the builder does |
|---|---|---|
| 40601, 40613, 40614, 40616 | precipitation / snowy days | emit `value(wl) − value(0.5)`; baseline → 0 |
| 40703 | water balance | percentile → SPEI z-score, **then** the change |
| 40701, 40702 | drought | ×100 (the store holds a 0–1 fraction) |
| all others | heat, day counts | absolute values, unchanged |

Four things worth knowing:

- The change is **derived**, not read from the store's `diff_*` variable — that variable is
  all-NaN at the 0.5 °C level (which would break the land mask), and water balance has to be
  differenced *after* its transform, not before. Verified against `diff_*` at publication
  precision: 2 of 905k mid values across the four change maps truncate one step differently
  (~1 in 450k, always by 1), well below the maps' bin widths.
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

`diff`, `diff-pyramid` and `diff-all` mirror the three build commands above, and `live-maps` lists
the live exports on disk. Run `hires-maps --help` for their options.

These answer "how does the new data differ from what is live today?" — the question a swipe
comparison cannot answer, because a systematic bias makes two maps that still look alike. The
output is one layer whose value is `new - live`, published with the diverging red/blue ramp in
`vector-tiles/configs.ts` (`DIFF_COLORS` / `DIFF_STOPS`) and uploaded with
`npm run create-tilesets -- <id> --diff`.

**Why red/blue.** Zero is a difference map's most important reading — it means *the two datasets
agree* — so the ramp has to be **diverging**, not one of the sequential climate ramps. Hue carries
the sign (blue = new is lower, red = higher), saturation the magnitude, and the neutral middle band
is a real value rather than a gap. The palette, the stops and the full reasoning live in
`vector-tiles/configs.ts` (`DIFF_COLORS` / `DIFF_STOPS`).

**Which difference.** ["Comparison maps: two different questions"][two-questions] defines two. This
builds the **detail diff**: for every new 0.1° cell, `new - (the live 0.2° value covering it)`, on
the 0.1° grid — what the finer grid bought us, and where. Four new cells share one live parent, so
genuine 0.2°-blocky structure appears at deep zoom; that is the signal. The **model diff**
(aggregate the new data to 0.2° first, then subtract) separates "the model moved" from "the
resolution changed", and is not built.

[two-questions]: ../docs/hi-res-map-pipeline.md#comparison-maps-two-different-questions

Details that matter:

- The live half comes from `data/mapbox/mts/old-geojson/*.geojsonld` — the **published** values,
  so the comparison is against what users actually see. `livemaps.py` reads them.
- Output goes to `data/mapbox/mts/diff-geojson/{live_id}-diff[-p02|-p08].geojsonld`, a sibling of
  that folder, so both halves of a comparison sit together and neither crowds the `-hires` builds.
  `vector-tiles` hardcodes the same folder name as `DIFF_SUBDIR` in `hires.ts` — the two have to
  stay in step. (It is passed to the uploader separately from the dataset id, because that id also
  becomes the Mapbox tileset source id, which cannot contain a slash.)
- The grids are **centre-aligned**, so the live parent of a new cell is exact integer arithmetic —
  no interpolation. The tie-break for cells sitting on a live boundary, and why the arithmetic is
  done in integer tenths, are in `livemaps.py`.
- The comparison is only defined where both halves have a value, so cells outside the intersection
  are `null`, never 0 — otherwise every coastline reads as a real disagreement. Each build prints
  the three counts as **comparable cells on the native 0.1° grid** — measured there even when
  writing a coarse rung, since at factor 8 a block holding one comparable cell would read as
  entirely comparable. For 40105: **1,354,932** comparable, **858,098** new-only, **347,280**
  live-only; both fringes are coastline and island effects, the live grid being coarser.
- **Change maps** need care: the live ones keep the *absolute* baseline in the 0.5 °C slot while
  the other levels hold changes (40601 ships `data_baseline_mid` ≈ 744 mm next to `data_1c_mid` ≈
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
