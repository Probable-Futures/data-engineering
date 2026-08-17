# `pf-downscaled-data/` — the new downscaled climate data

**Reference for the raw material.** This describes what the science team delivered: where it lives,
how the grid works, what units the numbers are in, what the 26 indicators are, and how to open a
store. It is **not** a plan and **not** a status page — nothing here should ever need a date or a
checkbox. For what we decided to do with the data, see
[`decisions-and-status.md`](decisions-and-status.md); for how it becomes a web map, see
[`hi-res-map-pipeline.md`](hi-res-map-pipeline.md).

Written for someone who works with data but has never worked with climate data. Every term is
explained the first time it appears. If a sentence uses a word you don't know, that is a bug in this
doc — say so.

## Contents

- [Where it lives](#where-it-lives)
- [Where the numbers come from](#where-the-numbers-come-from)
- [The file format: Zarr](#the-file-format-zarr)
- [The grid](#the-grid)
- [Reading the file names](#reading-the-file-names)
- [The folders on disk](#the-folders-on-disk)
- [The two batches, and which tool reads which](#the-two-batches-and-which-tool-reads-which)
- [Inside one warming-level store](#inside-one-warming-level-store)
- [The 26 indicators](#the-26-indicators)
- [Units](#units)
- [Opening a store yourself](#opening-a-store-yourself)

## Where it lives

Outside this repo, at **`$PF_DOWNSCALED_DATA`** (default `~/work/pf-downscaled-data`). Both tools
that read it resolve the same variable — `hires_maps/config.py` and `analysis/lib.py` — so exporting
it once points everything at the right place:

```bash
export PF_DOWNSCALED_DATA=/path/to/pf-downscaled-data
```

## Where the numbers come from

Three ideas make the rest click.

**A climate model is a giant weather simulation.** Physics simulations of the whole atmosphere,
run to estimate weather far into the future. The one used here is **`MPI-ESM1-2-HR`** — treat it as
a brand name. It was chosen because both ISIMIP and REMO already use it.

**Those simulations are blurry, and downscaling sharpens them.** The raw simulation splits the
world into big squares (~25 km or larger), so one number has to describe a mountain and its valley
at once. **Downscaling** produces smaller squares — here ~11 km — so mountains, coasts and cities
show up distinctly. This entire project is that sharpening exercise; "downscaled" in the folder
name means "the sharpened version".

**One emissions future is baked in.** How much the world warms depends on how much greenhouse gas
humanity emits, and scientists model a few named scenarios. This data uses **`ssp585`**, the
high-emissions one. Everything here assumes that scenario.

## The file format: Zarr

Today's Probable Futures maps are **GeoJSON**: a list of shapes, each carrying its values. Geometry
and values bundled together.

This data is **Zarr**, which stores only *a big grid of raw numbers* — like an enormous
spreadsheet — plus small "ruler" lists saying what each row and column means (a list of latitudes
`lat`, a list of longitudes `lon`, and depending on the batch a list of years or warming levels).
There are **no shapes and no map inside**; you rebuild the geometry yourself from the rulers. That
rebuild is our job, not the mapping tool's.

A `.zarr` is a **folder**, not a file:

```text
tasmax_..._1971-2010.zarr/       <- the whole thing (a folder)
├── zarr.json                    <- table of contents: what's inside, how big
├── tasmax/                      <- the actual grid of numbers
├── lat/                         <- the latitude ruler  (1801 numbers)
└── lon/                         <- the longitude ruler (3601 numbers)
```

The numbers are compressed, so a text editor is useless on them — you need a few lines of Python
(see [Opening a store yourself](#opening-a-store-yourself)).

> **Note:** these are **Zarr version 3** folders. A reader that only understands the older Zarr v2
> layout will fail on them. This is why `analysis/` and `hires-maps/` each have their own venv:
> `netcdfs/import` pins an old `xarray` with no Zarr v3 support.

## The grid

Every store uses the same global grid:

| Property | Value |
|---|---|
| Cell size | **0.1°** on a side — about **11 km** at the equator |
| Rows (north→south) | **1801**, from `+90°` to `−90°` |
| Columns (west→east) | **3601**, from `−180°` to `+180°` |
| Total cells | ≈ **6.5 million** |
| Land cells with data | ≈ **2.2 million** (measured 2,212,863 for `days-above-35c`) |
| Ocean | **blank** (`NaN`) — about **66%** of the grid |

The science team skipped the ocean on purpose. Two consequences worth carrying forward: real
per-tile feature counts are well below the worst case a full grid would imply, and the stress cases
for tiling are **coastlines and islands**, not open ocean.

The live 0.2° maps sit on a grid that is **centre-aligned** with this one — every live cell centre
falls exactly on a new cell centre — which is what makes the comparison maps exact integer
arithmetic rather than interpolation. The arithmetic and its tie-breaking rule live in
`hires_maps/livemaps.py`.

## Reading the file names

The names look like a barcode, but each piece means something:

```text
tasmax_MPI-ESM1-2-HR_ww-isimip_ssp585_mean_1971-2010.zarr
```

| Piece | Plain meaning |
|---|---|
| `tasmax` | **what** it measures — here the daily **high** temperature |
| `MPI-ESM1-2-HR` | **which** simulation produced it |
| `ww-isimip` | **how** it was processed — the science team's recipe. Safe to ignore. |
| `ssp585` | **which** future scenario — the high-emissions one |
| `mean_1971-2010` | an **average over 1971–2010** — a "typical recent conditions" snapshot |
| `day` | built from **daily** data |
| `wls` | sliced by **warming level** rather than by year |

Two words that recur:

- **climatology** — a long-term average (e.g. the 1971–2010 mean). One number per spot, no time
  axis. "The normal."
- **aggregate** — a summary computed from many daily values, e.g. "how many days were hotter than
  32 °C". One number per spot *per year* (or per warming level).

## The folders on disk

| Folder | What it holds | Used for |
|---|---|---|
| `warming_levels_aggregates/` | 26 indicators × 6 warming levels (≈7 GB) | **building the new maps** (`hires-maps/`) |
| `annual_aggregates/` | the same indicators, one value per calendar year 1961–2099 | offline analysis (`analysis/`) |
| `climatologies/` | the raw ingredients, averaged over 1971–2010 | context; unit checks |
| `climatologies_diff_era5land/` | model minus real-world observations | validation |
| `daily/` | the raw day-by-day values behind everything above | spot checks only |

### `climatologies/` — the raw ingredients

Each folder is one measurement averaged over 1971–2010: a single map, no time axis.

| Folder | What it measures | Measured range | Units |
|---|---|---|---|
| `tasmax` | daily **high** temperature | 221 to 336 | **Kelvin** — subtract 273.15 for °C |
| `tasmin` | daily **low** temperature | 216 to 301 | Kelvin |
| `tas` | daily **average** temperature | 219 to 307 | Kelvin |
| `pr` | **precipitation** rate | 0.00000002 to 0.001 | per-second rate — ×86,400 for mm/day (max ≈ 91) |
| `hurs` | **humidity** | 16 to 94 | percent (0–100) |
| `sfcwind` | **wind speed** | 0.1 to 15 | metres per second (×3.6 for km/h) |
| `rsds` | **sunshine** reaching the ground | 71 to 309 | watts per square metre |
| `pr_bil`, `pr_con2` | precipitation, two other methods | — | experiments — compare against `pr` |
| `temperature` | *nothing new* | — | verified byte-for-byte a copy of `tas` |
| `precipitation` | *nothing new* | — | a copy of `pr` |

### `climatologies_diff_era5land/` — the "did we get it right?" check

Two stores (`temperature`, `precipitation`), each a map of **model minus real-world observations**.
ERA5-Land is a trusted observational dataset — the answer key. A perfect model would be zero
everywhere; the measured land-mean temperature difference is **+0.008 °C**, essentially zero. That
is the strongest single piece of evidence that the sharpened data tracks reality with no systematic
warm or cold bias. This folder is for confidence, not for making maps.

### `daily/` — the raw day-by-day values

The individual daily values behind every summary above (~140 years × 365 days × 6.5 M cells), which
makes it by far the largest folder. **No map needs it.** It is there for spot checks such as "show
me the daily history at this one location".

## The two batches, and which tool reads which

The same 26 indicators arrived twice, sliced two different ways. This is not a duplicate — the two
slicings answer different questions, and both are still in use:

| Batch | Sliced by | Shape of one store | Read by |
|---|---|---|---|
| `annual_aggregates/` | **calendar year**, 1961–2099 | `time × lat × lon` | `analysis/` (`analysis/lib.py`) |
| `warming_levels_aggregates/` | **warming level**, 0.5–3.0 °C | `wl × lat × lon × stat` | `hires-maps/` (the build pipeline) |

The warming-level batch is the one the map build needs, because it is shaped **exactly like the
maps already live on probablefutures.org**. Our live maps do not show a year; they show *worlds* —
"what a place looks like when the whole planet is 1.5 °C hotter than normal". Six of them:

```text
0.5 °C   <- the baseline / "normal" reference (the 1971-2000 period)
1.0 °C
1.5 °C
2.0 °C
2.5 °C
3.0 °C
```

The calendar-year batch needs a year → warming-level conversion before it can be lined up against a
live map, because different scenarios reach "+2 °C" in different years. `analysis/` sidesteps that
by comparing the **1971–2000 baseline period** on both sides instead.

## Inside one warming-level store

Each of the 26 indicators is one Zarr folder. To pull out a single number you pick three things:

1. **which warming level** — 0.5 through 3.0
2. **where** — latitude and longitude on the 0.1° grid, land only
3. **which statistic** — one of six: `min`, `p5`, `p50`, `p95`, `max`, `mean`

`p50` is the median, `p5` and `p95` are a low and high estimate (the uncertainty range), `mean` is
the average. The live maps publish three of these per warming level: `low` = `p5`, `high` = `p95`,
and `mid` = either `mean` or `p50` depending on the indicator (see the table below).

Each store also ships **two variables**: the value itself (e.g. `days_above_35c`) and the change
from baseline (e.g. `diff_days_above_35c`). The change is exactly `value(level) − value(0.5)`;
verified on 1.2 M sampled values. The build derives the change itself rather than reading
`diff_*` — for the reason, see
[Decisions](decisions-and-status.md#change-maps-derive-the-change-rather-than-reading-diff_).

One store is short a level: **`ten-hottest-wbmax-days` has five warming levels, not six**. See
[Open questions for Carlos](decisions-and-status.md#open-questions-for-carlos).

## The 26 indicators

Every indicator maps one-to-one onto a map we serve today. Units come from
`netcdfs/import/conf.yaml`, the same file the current maps use — the stores themselves carry no
unit labels.

> **The source of truth is `hires_maps/indicators.py`.** This table is a readable copy. If they
> disagree, the code is right.

| Folder / slug | Live id | Unit | `mid` is | Change map? | Transform |
|---|---|---|---|---|---|
| `average-temperature` | 40101 | °C | mean | — | — |
| `average-daytime-temperature` | 40102 | °C | mean | — | — |
| `average-nighttime-temperature` | 40201 | °C | mean | — | — |
| `average-winter-temperature` | 40207 | °C | mean | — | — |
| `ten-hottest-days` | 40103 | °C | mean | — | — |
| `ten-hottest-nights` | 40206 | °C | mean | — | — |
| `ten-hottest-wbmax-days` | 40305 | °C | mean | — | — |
| `days-above-32c` | 40104 | days | mean | — | — |
| `days-above-35c` | 40105 | days | mean | — | — |
| `days-above-38c` | 40106 | days | mean | — | — |
| `days-above-45c` | 40107 | days | mean | — | — |
| `days-above-26c-wbmax` | 40301 | days | mean | — | — |
| `days-above-28c-wbmax` | 40302 | days | mean | — | — |
| `days-above-30c-wbmax` | 40303 | days | mean | — | — |
| `days-above-32c-wbmax` | 40304 | days | mean | — | — |
| `nights-above-20c` | 40203 | days | mean | — | — |
| `nights-above-25c` | 40204 | days | mean | — | — |
| `frost-nights` | 40202 | days | mean | — | — |
| `freezing-days` | 40205 | days | mean | — | — |
| `total-annual-precipitation` | 40601 | mm | p50 | yes | — |
| `wettest-90-days` | 40616 | mm | p50 | yes | — |
| `wettest-day` | 40613 | mm | p50 | yes | — |
| `snowy-days` | 40614 | days | p50 | yes | — |
| `average-water-balance` | 40703 | z-score | p50 | yes | `percentile_to_z` |
| `probability-of-drought` | 40702 | % | mean | — | `pct100` |
| `probability-of-extreme-drought` | 40701 | % | mean | — | `pct100` |

Reading the last three columns:

- **`mid` is** — which statistic becomes the map's headline value. `mean` for the heat maps **and
  the two drought maps**; `p50` (median) for precipitation, snowy days and water balance. This
  follows `use_mean_for_mid` in `conf.yaml` exactly, so the new maps make the same choice the live
  maps do.
- **Change map?** — these five are published as a *change from the baseline world*, not an absolute
  value. The app never paints the baseline layer for them.
- **Transform** — a unit conversion applied because the store's units differ from what the live map
  publishes: the drought pair holds a 0–1 fraction where the live maps are 0–100, and water balance
  holds a percentile where the live map publishes an SPEI z-score. `unit` above is always the unit
  **after** the transform.

## Units

The single most common way to misread this data is to trust a number's units by looking at it.

| If you see… | It's stored as… | To make it readable… |
|---|---|---|
| a temperature ~200–340 in `climatologies/` | **Kelvin** | subtract **273.15** → °C |
| a temperature ~−40 to +40 in the aggregate batches | **already °C** | nothing to do |
| a tiny rain number like `0.00002` | a per-**second** rate | multiply by **86,400** → mm/day |
| humidity 0–100 | percent | nothing to do |
| wind 0–15 | metres/second | ×3.6 → km/h |
| a drought value 0–1 | a **fraction** | ×100 → % (this is the `pct100` transform) |
| a blank / `NaN` | **no data** — it is ocean | skip it, leave transparent |
| `-inf` | another no-data marker (only in the ERA5-Land diff stores) | skip it |

**The two classic mistakes:**

1. Seeing `271` and reading it as an error. It is Kelvin — −2 °C.
2. Seeing `0.00002` for rain and reading it as basically zero. Times 86,400 it is ~1.6 mm/day.

> **The Kelvin trap.** Units differ *per folder*, not per project: `climatologies/` is in Kelvin
> while both aggregate batches are already in °C. Always check the folder you are in; never assume
> from a neighbouring one.

## Opening a store yourself

The Zarr readers are deliberately not in `netcdfs/import`'s environment (it pins an old `xarray`).
Use `analysis/`'s venv, `hires-maps`' venv, or a throwaway one:

```bash
python3 -m venv /tmp/zarrenv
/tmp/zarrenv/bin/pip install "zarr>=3" xarray numpy
```

`xarray` opens the folder and hands you the numbers and the rulers together:

```python
import os
import xarray as xr

BASE = os.environ.get("PF_DOWNSCALED_DATA", os.path.expanduser("~/work/pf-downscaled-data"))

# --- a warming-level store: the batch the map build reads ---
ds = xr.open_zarr(f"{BASE}/warming_levels_aggregates/days-above-35c/"
                  "days-above-35c_MPI-ESM1-2-HR_ww-isimip_ssp585_wls.zarr")
print(ds)                                       # dims: wl x lat x lon x stat
print(ds["days_above_35c"].sel(wl=1.5, stat="mean")
        .sel(lat=33.9, lon=35.5, method="nearest").item())

# --- a climatology: one map, Kelvin ---
clim = xr.open_zarr(f"{BASE}/climatologies/tasmax/"
                    "tasmax_MPI-ESM1-2-HR_ww-isimip_ssp585_mean_1971-2010.zarr")
celsius = clim["tasmax"] - 273.15
print(float(celsius.sel(lat=40.7, lon=-74.0, method="nearest")), "°C")

# --- a calendar-year store: pick a year ---
ann = xr.open_zarr(f"{BASE}/annual_aggregates/days-above-32c/"
                   "days-above-32c_MPI-ESM1-2-HR_ww-isimip_ssp585_day.zarr")
print(ann.time.values[[0, -1]])                 # 1961 ... 2099
```

For anything more than a one-off lookup there are two ready-made tools rather than a scratch script:

- **`hires-explore`** (in `hires-maps/`) — list, describe, point, patch and land-mean commands over
  the warming-level batch. See [`../hires-maps/README.md`](../hires-maps/README.md).
- **`analysis/`** — plots, time series, ERA5-Land validation and old-vs-new comparison over the
  calendar-year batch. See [`../analysis/README.md`](../analysis/README.md).
