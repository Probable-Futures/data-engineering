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
  indicators.py    # registry: slug -> live map id, unit, mean-or-median rule (one source of truth)
  stores.py        # open a warming-level Zarr store; list what's on disk (shared IO)
  geojson/         # (Phase 1) Zarr -> .geojsonld builder + square-cell geometry   [not built yet]
  db/              # (Phase 1, OFF) writer to pf_grid_coordinates / pf_dataset_statistics  [not built yet]
  cli.py           # the build command(s)                                          [not built yet]
  dev/explore.py   # DEV-ONLY inspection tool
tests/
```

## Tooling

`pyproject.toml` (PEP 621), Python 3.13, `ruff` (lint + format), `pytest`, `typer` for CLIs.
Run checks with `.venv/bin/ruff check .` and `.venv/bin/pytest`.
