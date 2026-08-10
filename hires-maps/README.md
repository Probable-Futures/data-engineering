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

Three things worth knowing:

- The change is **derived**, not read from the store's `diff_*` variable — that variable is
  all-NaN at the 0.5 °C level (which would break the land mask), and water balance has to be
  differenced *after* its transform, not before. Verified equal to `diff_*` on 1.2M sampled
  values: 8 differ, all by 0.1, all from float32 rounding boundaries.
- `data_baseline_*` is 0 on change maps, matching what the live SQL forces. The app never paints
  that layer — picking 0.5 °C on a change map jumps to 1.0 °C.
- Water balance clips ~222k cell-values at the percentile floor (0.55% of land values) and the
  build logs the count. That detail exists in the live map; ask Carlos for the raw SPEI field.

## Tooling

`pyproject.toml` (PEP 621), Python 3.13, `ruff` (lint + format), `pytest`, `typer` for CLIs.
Run checks with `.venv/bin/ruff check .` and `.venv/bin/pytest`.
