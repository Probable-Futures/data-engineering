# `analysis/` — explore & compare the new downscaled climate data

A small, **self-contained Python toolkit** to see, investigate, and present the new downscaled
climate data (the Zarr batch at `~/work/pf-downscaled-data`), and compare it against the current
production maps. Pure `xarray` + `matplotlib` — **no Mapbox, no Postgres**, and its own venv so
it never disturbs `netcdfs/import` (which pins an old xarray with no Zarr v3).

Background in plain English: [`../docs/downscaled-data-primer.md`](../docs/downscaled-data-primer.md).

## Setup (once)

```bash
cd analysis
make setup            # creates ./venv and installs requirements.txt
```

If the new data isn't at the default `~/work/pf-downscaled-data`, point at it:

```bash
export PF_DOWNSCALED_DATA=/path/to/pf-downscaled-data
```

## The five commands

| Command | What it does |
|---|---|
| `make inspect INDICATOR=days-above-35c` | Print the structure of a store: dims, units, ranges, % ocean. Also `make inspect STORE=<any .zarr or .nc path>`. |
| `make quicklook INDICATOR=days-above-35c YEAR=2050` | Global + regional PNG maps for a year (or `PERIOD=1971-2000` to average). |
| `make timeseries INDICATOR=days-above-35c PLACES=Beirut,Cairo,Delhi` | Line chart of how the indicator changes 1961→2099 at chosen cities. |
| `make compare INDICATOR=days-above-35c` | Old (0.2°) vs new (0.1°) maps, two difference maps, a histogram. Add `WL=1.5 PERIOD=2024-2040` to compare a warming-level "world" instead of the baseline. |
| `make validate` | Map the new data against real observations (ERA5-Land): where and how much it's biased. A "how much should we trust this?" check. |
| `make warming-levels` | Estimate when the new data reaches +1.0…+3.0 °C and suggest year-windows to feed `compare`. |
| `make report INDICATOR=days-above-35c` | Bundle the maps + time-series + comparison into one self-contained `out/<indicator>.html` to share. |

> **Note on averages:** all "land-mean" figures are **area-weighted** (cos-lat). Without weighting,
> every 0.1° cell counts equally, which over-weights the poles and — since the data is land-only —
> lets Antarctica/Greenland distort the number (e.g. the baseline temperature reads −5 °C unweighted
> vs a realistic +8 °C weighted).

Everything writes to `out/` (git-ignored). Example one-liners:

```bash
make quicklook INDICATOR=days-above-35c PERIOD=1971-2000
make quicklook --climatology  tasmax          # raw climatology, Kelvin auto-converted to °C
make timeseries INDICATOR=nights-above-25c PLACES=Beirut,Baghdad
make report  INDICATOR=days-above-35c PLACES=Beirut,Cairo,Delhi
```

(Any script also runs directly, e.g. `venv/bin/python quicklook.py --climatology tasmax`.)

## What can be compared today

The old↔new comparison needs the **current** netCDF present locally. Only `days-above-35C`
(dataset `40105`) ships in the repo right now, so it's the pilot. To compare more indicators,
pull their current netCDFs first:

```bash
make -C ../geojson sync-woodwell-to-local     # rclone from the Woodwell GCP bucket
```

`quicklook`, `timeseries`, and `inspect` work on **all** new indicators without any old data.

### Comparison method (why baseline-period)

Old data is organized by **warming level**; new data by **calendar year**. To line them up
without guessing, we compare the **1971–2000 baseline** on both sides: the old `wl=0.5` slice
vs the new years 1971–2000 averaged. Same real-world period → any difference is the model +
resolution change, not a time mismatch. Warming-level comparisons are a later phase (they need
a year→warming-level mapping from the science team).

The two difference maps follow [`../docs/HI-RES-TILES.md`](../docs/HI-RES-TILES.md) §9:
**detail diff** (`new − nearest(old)` at 0.1° — what detail we gained) and **model diff**
(`aggregate(new)→0.2° − old` — whether the model itself moved).

## Indicator ↔ new-data folder

`lib.INDICATORS` is the registry (seeded from `netcdfs/import/conf.yaml`). Slugs match the new
`annual_aggregates/` folders: `days-above-32c/35c/38c/45c`, `nights-above-20c/25c`,
`average-temperature`, `average-daytime-temperature`, `average-nighttime-temperature`,
`ten-hottest-days`, `ten-hottest-nights`, `frost-nights`, `freezing-days`,
`days-above-26c/28c/30c/32c-wbmax`, `ten-hottest-wbmax-days`, `wettest-90-days`, `snowy-days`.
The last two are marked non-comparable at baseline (their old files store a *change*, not an
absolute value).

## Files

- `lib.py` — shared core: indicator registry, data opening, unit conversion, regridding,
  point lookup, map plotting.
- `inspect_store.py`, `quicklook.py`, `timeseries.py`, `compare_baseline.py`, `report.py` — the
  five CLIs.
- `Makefile` — the runners above. `requirements.txt` — `zarr>=3`, `xarray`, `netCDF4`, `numpy`,
  `matplotlib`.
