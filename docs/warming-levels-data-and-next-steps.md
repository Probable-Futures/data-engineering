# The New Warming-Level Data — What It Is and What To Do Next

Status: **notes for the team.** Written in plain language on purpose. If a sentence is
confusing, that's a mistake — tell me and I'll fix it.

Companion docs: [downscaled-data-primer.md](downscaled-data-primer.md) (the raw new data),
[HI-RES-TILES.md](HI-RES-TILES.md) (how we turn map data into web tiles).

---

## 1. The short version

The science team sent a new batch of data:
`/Users/moustafawehbe/work/pf-downscaled-data/warming_levels_aggregates` (about 7 GB, 26 maps).

**This is the batch we were waiting for.** It is the new, sharper data, but organized the
**same way as the maps we already have live** on probablefutures.org/maps — by "warming
level." That means we can now compare new against old directly, and we can build new maps
that slot into the shape our current tools already expect.

Earlier batches were organized by **calendar year** (1961, 1962, …), which did not match our
live maps and needed guesswork to line up. **This new batch removes that guesswork.**

---

## 2. What "organized by warming level" means

Our live maps don't show a specific year. They show **worlds**: "what a place looks like when
the whole planet is 1.5 °C hotter than normal," "…2 °C hotter," and so on. Each of those is a
**warming level**.

This new data has exactly those same six warming levels:

```
0.5 °C  (this is the "normal / baseline" reference)
1.0 °C
1.5 °C
2.0 °C
2.5 °C
3.0 °C
```

So it already speaks the same language as our live maps. No year-to-warming-level conversion
needed anymore.

---

## 3. What's inside one map file (using "days above 35 °C" as the example)

Each of the 26 maps is one Zarr folder (Zarr = a folder full of numbers; see the primer). To
pull out a single number you pick three things:

1. **which warming level** (0.5 → 3.0)
2. **where** (latitude, longitude — a 0.1°, ~11 km grid, land only)
3. **which statistic** — the file gives six choices: `min`, `p5`, `p50`, `p95`, `max`, `mean`

`p50` = the middle/median value, `p5` and `p95` = a low and high estimate (the uncertainty
range), `mean` = the average. Our live maps mainly use **mean** (for heat) and the low/high
for the uncertainty band, so we already know which ones we need.

Each file also ships **two** versions of every map:

- the **value** itself (e.g. `days_above_35c`) — "how many days above 35 °C in this world"
- the **change** (e.g. `diff_days_above_35c`) — "how many *more* days than the baseline world"

I checked: the "change" is simply `value at this level − value at the 0.5 baseline`. This is
handy because several of our live maps (precipitation, drought, etc.) are shown as a change,
so that version is already computed for us.

**In short:** this data has the same structure as the current live maps
(`warming level × location × statistic`), just **4× sharper** (0.1° instead of 0.2°) and from
a newer climate model.

---

## 4. How it lines up with the current live maps

All 26 new maps map one-to-one onto the maps we serve today, and the **units come straight
from `netcdfs/import/conf.yaml`** (the same file the current maps use):

| New folder | Live id | Unit |
|---|---|---|
| `average-temperature` | 40101 | °C |
| `average-daytime-temperature` | 40102 | °C |
| `average-nighttime-temperature` | 40201 | °C |
| `average-winter-temperature` | 40207 | °C |
| `ten-hottest-days` | 40103 | °C |
| `ten-hottest-nights` | 40206 | °C |
| `ten-hottest-wbmax-days` | 40305 | °C |
| `days-above-32c` (done) | 40104 | days |
| `days-above-35c` (done) | 40105 | days |
| `days-above-38c` | 40106 | days |
| `days-above-45c` | 40107 | days |
| `days-above-50c` (missing) | 40107 | days |
| `days-above-26c-wbmax` | 40301 | days |
| `days-above-28c-wbmax` | 40302 | days |
| `days-above-30c-wbmax` | 40303 | days |
| `days-above-32c-wbmax` | 40304 | days |
| `nights-above-20c` | 40203 | days |
| `nights-above-25c` | 40204 | days |
| `frost-nights` | 40202 | days |
| `freezing-days` | 40205 | days |
| `snowy-days` | 40614 | days |
| `total-annual-precipitation` | 40601 | mm |
| `wettest-90-days` | 40616 | mm |
| `wettest-day` | 40613 | mm |
| `probability-of-drought` | 40702 | % |
| `probability-of-extreme-drought` | 40701 | % |
| `average-water-balance` | 40703 | z-score |

(One note for later: some live maps — precipitation, drought, water balance — are published as
a *change from baseline*, not an absolute value. The new data gives us both the value and the
change, so we can match either way.)

---

## 5. What we already found (a real result)

Because the new data is now in warming-level form, we could compare it straight against the
old data at the **same** warming levels. For "days above 35 °C" (average, over land, weighted
by real area):

| Warming level | New (0.1°) | Old / live (0.2°) |
|---|---|---|
| 0.5 (baseline) | 27.7 days | 35.9 days |
| 1.5 | 34.4 days | 48.2 days |
| 2.0 | 38.9 days | 51.8 days |
| 3.0 | 50.3 days | 64.3 days |

**The new data shows fewer extreme-heat days than the old data at every warming level.** This
matches what we saw earlier: the old maps ran too hot in places like the Congo rainforest,
and the new data — which was checked against real observations and matched them almost
perfectly (see the primer/validation notes) — corrects that. This is a point worth showing the
client, because it changes the maps in a visible way.

---

## 6. One data issue to flag with Carlos

25 of the 26 maps have all six warming levels. **One does not:** `ten-hottest-wbmax-days` has
only **five** warming levels instead of six. Worth a quick question to Carlos — is one level
missing, or is that on purpose?

(The files themselves don't write out unit labels, but we don't need to ask — the units are
already recorded per map in `netcdfs/import/conf.yaml`. The full list is in the table below.)

---

## 7. Plan: turn this data into maps

The client wants to **build the new maps** and **compare them against the current live maps**
(probablefutures.org/maps). The comparison happens inside our internal **MapBuilder /
CompareMaps** tool in the main app, not in public.

### 7.1 The approach in one line

```
Zarr (warming levels)
   → [new Python builder]  → GeoJSON (.geojsonld)  → existing vector-tiles uploader
      → Mapbox tileset + style  → MapBuilder / CompareMaps (swipe vs live map)
```

**We go straight from Zarr to GeoJSON.** No netCDF step, and — for now — no database step on
the way to the map. The database becomes a *second, optional output* of the same builder:
we write the code for it now, but keep it switched **off** until Phase 3.

All of this lives in **one new Python package at the repo root** — see the architecture in §7.7.

### 7.2 Why skip netCDF and (for now) the database

Today the GeoJSON is produced by querying the PostGIS database with `ogr2ogr`. But a map only
needs **square polygons + the warming-level values**, and the new Zarr already contains exactly
that. So we can write the GeoJSON directly and skip two hops (the netCDF import and the database
round-trip).

The key point for sequencing: **the database is no longer on the critical path for drawing
maps.** It's still needed — but for the app's *other* features (the click-a-point popup values,
the CSV downloads, the public data API), not for the tiles. That's exactly why we can build and
review the maps now and safely defer the database decisions.

### 7.3 The GeoJSON builder (the new piece we write)

A single Python tool that reads one warming-level Zarr store and streams out a GeoJSON file in
the **same format and property names our tiler and styles already use** — so the existing
recipes and map styles work unchanged.

For every land cell it writes one feature:

- **geometry**: a 0.1° square (the cell), i.e. a box ±0.05° around the cell's lon/lat.
- **properties**: one value per warming level × statistic, named the way the current maps expect:
  `data_baseline_{low,mid,high}`, `data_1c_*`, `data_1_5c_*`, `data_2c_*`, `data_2_5c_*`,
  `data_3c_*`.
  - warming level → name prefix: `0.5→baseline, 1.0→1c, 1.5→1_5c, 2.0→2c, 2.5→2_5c, 3.0→3c`
    (the same mapping the current database views use).
  - `mid` = mean for heat maps / median for precip & drought (the `use_mean_for_mid` rule
    already in `conf.yaml`); `low` = p5; `high` = p95.
- Ocean / no-data cells are skipped. Values rounded to 1 decimal, coordinates trimmed — keeps
  files a sane size (~hundreds of MB per map, like the existing hi-res test file).

**Principal-engineer notes (so this is built right, not just quickly):**

- **One source of truth for the mapping.** The "warming level → prefix" and
  "statistic → low/mid/high" rules live in one small module shared by *both* the GeoJSON writer
  and the database writer, so the two can never drift apart.
- **Stream, don't load.** Process the grid in latitude bands and write features as we go, so
  memory stays flat even though each map is ~1.7 M features.
- **Match the current output exactly.** Same file format (newline-delimited GeoJSON), same
  output path (`data/mapbox/mts/<id>.geojsonld`), same property names → the existing
  `vector-tiles` uploader and styles need **no changes**.
- **Edge cases:** handle the ±180° date line and the polar rows the way the current `ogr2ogr`
  step does (`-wrapdateline`). Keep output ordering deterministic so re-runs diff cleanly.

### 7.4 The database writer — built now, switched OFF until Phase 3

The same builder gets a second output behind a `--write-db` flag (**default off**). It writes to
the **same tables we already use** (`pf_grid_coordinates` for the cells,
`pf_dataset_statistics` for the values) — we do **not** invent a parallel schema. It reuses the
existing insert logic in `netcdfs/import` where possible.

We keep it off because the 4×-bigger data raises real schema decisions that shouldn't be rushed
(this is the "I'm not sure about the schema yet" concern, made concrete):

- **A new grid.** The 0.1° grid is a *new* set of ~1.7 M coordinates (each with its own square
  `cell` polygon). It needs to be registered as a new grid alongside the existing 0.2° grid,
  which the live maps keep using.
- **Volume.** ~1.7 M cells × 6 warming levels ≈ **10 M rows per map**, × 26 maps ≈ **~270 M
  rows** — roughly 10× today's statistics table. That forces decisions on partitioning (likely
  by dataset), indexing, and bulk-loading (COPY / pgloader vs row-by-row inserts).
- **Which statistics to store.** The new data has six (`min, p5, p50, p95, max, mean`); today's
  columns are `low/mid/high` (+ `mean/median`). We map `p5→low, p95→high, mean-or-p50→mid` — do
  we also keep `min`/`max`, or drop them?

So: the writer is **coded and tested against a scratch table in Phase 1**, but not pointed at
the real database until these are settled in Phase 3.

### 7.5 Deploy to Mapbox (reuse what exists)

Drop `<id>.geojsonld` into `data/mapbox/mts/` and run the existing `vector-tiles` uploader
(`createTilesets.ts`): it uploads the source, validates the recipe, creates + publishes the
tileset, and creates the **style**. Two rules:

- **Publish to a NEW tileset/style id namespace on the same `probablefutures` Mapbox account**
  (e.g. a `-hires` / new-version suffix) so we **never overwrite the live production tilesets.**
  MapBuilder then points a dev/staging dataset entry's `mapStyleId` at the new style.
- Phase 1 uses the **current recipe as-is** (max tile size, `minzoom 2`, `maxzoom 5`, no extra
  layering). Some low-zoom tiles will drop (the `W201` warning) — accepted for Phase 1.

### 7.6 Compare against the live map (MapBuilder / CompareMaps)

The internal app already has what we need:

- **MapBuilder** loads a map from `mapbox://styles/{account}/{dataset.mapStyleId}`, where
  `mapStyleId` comes from `packages/lib/src/consts/datasets.ts`. To show a new map, publish its
  style (7.5) and point a **dev/staging dataset entry's `mapStyleId`** at the new style id.
- **CompareMaps.tsx** already uses `mapbox-gl-compare` — a swipe slider between a "before" and
  "after" map. Put the **live style** on one side and the **new style** on the other → a direct
  old-vs-new swipe, internally, before anything is released.

### 7.7 Where the code lives — a new `hires-maps` package

All the build code goes in **one new Python package at the repo root: `hires-maps/`**. Modern,
small, and split by responsibility — not one giant file, but not a maze of tiny modules either.

**Tooling:** `pyproject.toml` (standard PEP 621 metadata), Python 3.13, `ruff` (lint + format),
`pytest`, and `typer` for the command-line tools. It installs with a plain `venv` +
`pip install -e .`, and works with `uv` too if we adopt it later.

**Layout:**

```text
hires-maps/
  pyproject.toml
  README.md
  src/hires_maps/
    config.py        # paths + constants: data root, the 6 warming levels, the 6 stats, naming
    indicators.py    # the registry: slug -> live map id, unit, mean-or-median rule (ONE source of truth)
    stores.py        # open a warming-level Zarr store; list what's on disk (the shared IO layer)
    geojson/         # (Phase 1) Zarr -> .geojsonld streaming builder + the square-cell geometry
    db/              # (Phase 1, built but OFF) writer to pf_grid_coordinates / pf_dataset_statistics
    cli.py           # the "build" command(s)
    dev/
      explore.py     # DEV-ONLY tool to inspect the Zarr files while developing (built FIRST)
  tests/
```

**Why a package instead of more loose scripts:** the warming-level→name mapping, the
statistic→low/mid/high mapping, the indicator registry, and the store-opening code are all
shared by the GeoJSON writer, the database writer, and the dev tools. Putting them in one place,
imported everywhere, is what stops the two writers from silently drifting apart.

The existing `analysis/` folder stays as it is (offline investigation and plots). This new
package is the **build pipeline**; the two can share the registry later if it helps.

**What we build first (this step):** before any map-conversion code, a **dev-only explorer**
inside the package (`hires_maps.dev.explore`, run as `hires-explore`) to poke at the Zarr files
while we develop. It's a throwaway/testing aid, kept clearly separate from the pipeline.

### 7.8 What the dev explorer includes

Five small commands, each answering one question we keep asking while building:

| Command | What it shows | Why we need it |
|---|---|---|
| `list` | every indicator on disk, with its live-map id, unit, and headline stat | confirm the registry matches what's actually downloaded |
| `describe <slug>` | the store's shape: warming levels, statistics, both variables (value + change), value ranges, % ocean | sanity-check a store before using it |
| `point <slug> --lat --lon` | the full **warming level × statistic** grid at the nearest land cell | this is *exactly the set of numbers one map cell will carry* — the builder's target output, cell by cell |
| `patch <slug> --wl --stat --lat --lon` | a small grid of values around a point | eyeball spatial detail (e.g. a mountain range) and spot ocean/NaN handling |
| `landmean <slug>` | area-weighted land-mean per warming level | quick "do the numbers look right and rise with warming?" check |

Examples (real output, trimmed):

```console
$ hires-explore list
26 indicators under .../warming_levels_aggregates:
  slug                             live id  unit     mid
  days-above-35c                   40105    days     mean
  total-annual-precipitation       40601    mm       p50
  ...

$ hires-explore describe days-above-35c
live id 40105 | unit days | headline stat = mean
dimensions : {'wl': 6, 'lat': 1801, 'lon': 3601, 'stat': 6}
warming levels : [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
statistics     : ['min', 'p5', 'p50', 'p95', 'max', 'mean']
variables      : ['diff_days_above_35c', 'days_above_35c']
  days_above_35c   min=0 mean=22.9 max=365 NaN(ocean)=65.9%

$ hires-explore point days-above-35c --lat 33.9 --lon 35.5
days-above-35c at nearest land cell to (33.9, 35.5) -> (33.80, 35.50)   # values in days
  warming level         min       p5      p50      p95      max     mean
   0.5 (baseline)      0.0      0.0      0.0      3.0      3.0      0.6
   1.5 (1_5c    )      0.0      0.0      1.0      5.0     15.0      2.0
   3.0 (3c      )      1.0      1.0     11.0     26.0     28.0     11.7   # <- one map cell's values

$ hires-explore patch days-above-35c --wl 2.0 --stat mean --lat 34.0 --lon 36.1
  lat \ lon |    35.8    35.9    36.0    36.1    36.2    36.3
       34.0 |     0.0     0.0     3.0    23.1    21.4     2.0     # Mount Lebanon dip vs Bekaa
       33.8 |     4.4    11.5    16.0     8.2     1.0     0.3

$ hires-explore landmean days-above-35c
days-above-35c — area-weighted land-mean per warming level (stat=mean, days):
   0.5 (baseline):    27.73 days
   1.5 (1_5c    ):    34.39 days
   3.0 (3c      ):    50.31 days
```

Design rules for this tool (so it stays a *tool*, not a second pipeline):

- **Read-only.** It never writes files, tiles, or database rows.
- **Reuses the package's shared code** (`config`, `indicators`, `stores`) — so if the builder
  later opens a store or names a warming level differently, the explorer reflects that
  automatically, and we don't maintain two copies of the logic.
- **Coastal-safe lookups.** Points that land on an ocean cell snap to the nearest land cell, so
  a city like Beirut still returns values.
- **No new dependencies** beyond what the package already uses.

When it stops being useful (once the builder is trusted), it can simply be deleted — nothing in
the pipeline depends on it.

### 7.9 How we made the map work at every zoom (plain English)

This section explains, from scratch, the trick that makes the zoomed-out map work. No jargon
assumed — every term is defined as it appears.

#### The words you'll see

| Word | What it means |
|---|---|
| **cell** | One little square on the map. Our data is a grid of squares, each holding one number (e.g. "34 days above 35 °C"). |
| **resolution** | How big each square is. Our source data is **0.1°** (~11 km) per square. |
| **finer** | Smaller squares → more detail (0.1° is finer). |
| **coarser** | Bigger squares → less detail (0.8° is coarser). "Coarsening" = making squares bigger. |
| **tile** | The map isn't one big picture; it's delivered as a grid of small squares called tiles. Each tile holds all the cells inside its area. |
| **zoom level** | How far in you are: **z0** = whole world, **z5** = zoomed in. Each step in doubles the detail. |
| **rung** | One complete copy of the map at one resolution (e.g. "the 0.2° rung"). Named after rungs on a ladder. |
| **pyramid / ladder** | The full set of rungs stacked together — coarse at the bottom (zoomed out), fine at the top (zoomed in). |
| **aggregate / average down** | Combine several small cells into one bigger cell by averaging their values. |

#### The problem in one picture

A tile at a zoomed-out level covers a **huge** area, and it must carry *every* cell inside it.
Mapbox caps how much data one tile may hold (2500 KB). Our 0.1° data is so detailed that a
zoomed-out tile blows past that cap, and Mapbox silently **throws cells away** — which is why the
first attempt looked broken at low zoom.

```text
z5 (zoomed in)                 z2 (zoomed out)
one tile = small area          one tile = huge area
~12,000 cells → fits fine      ~200,000 cells → way over the limit → data dropped
```

#### The insight

When you're zoomed out, you **can't see** individual 0.1° squares anyway — each one is smaller
than a pixel on your screen. So sending them is wasted effort. Instead, we send **fewer, bigger
squares** that look identical to the eye but weigh a fraction as much.

#### How we make a bigger square: averaging

To go from 0.1° to 0.2°, we take each **2×2 block** of four small cells and replace it with one
big cell whose value is the average of the four:

```text
Original 0.1° cells            Becomes one 0.2° cell
┌──────┬──────┐
│  12  │  14  │
├──────┼──────┤   average →    ┌─────────────┐
│  13  │  13  │                │     13      │
└──────┴──────┘                └─────────────┘
4 cells, 4 numbers              1 cell, 1 number  (4× less data)
```

Do it with an **8×8 block** instead and you get a 0.8° cell — 64× less data. That's it; that's the
whole trick. The code is [`hires-maps/src/hires_maps/aggregation.py`](../hires-maps/src/hires_maps/aggregation.py).

Two details we handle carefully:

- **Ocean squares are skipped, not counted as zero.** Our data is land-only, so many cells are
  blank. If a 2×2 block has 2 land cells and 2 blank ones, we average **only the 2 real values** —
  otherwise coastlines would be wrongly dragged toward zero. If all four are blank, the big cell
  stays blank.
- **Squares near the poles count for less** (this is the "area-weighted" bit). Because the Earth
  is a ball, a square near the North Pole covers far less actual ground than one at the equator.
  So when averaging we weight each cell by `cos(latitude)` — a fancy way of saying "give the
  bigger-on-the-ground squares more say." A plain average would let tiny polar squares distort
  the result.

#### The three rungs we built

We do this twice, producing three versions of every map:

| Rung | Cell size | Made by | Used at zoom | Real feature count (days-above-35 °C) |
|---|---|---|---|---|
| native | 0.1° | (the source data itself) | z4–z5 | 2,212,863 |
| `p02` | 0.2° | averaging 2×2 blocks | z2–z3 | 563,055 |
| `p08` | 0.8° | averaging 8×8 blocks | z0–z1 | 38,187 |

(`p02` = "point-oh-**2** degrees", `p08` = "point-oh-**8**". Those are the file-name tags:
`40105-hires.geojsonld`, `40105-hires-p02.geojsonld`, `40105-hires-p08.geojsonld`.)

Notice the shrinkage: the zoomed-out version is **58× smaller** than the original — which is
exactly why it now fits in a tile.

#### How the map knows which rung to use

Each rung is uploaded to Mapbox as its own tileset, and each is told **which zoom range it's
responsible for** (`minzoom`/`maxzoom`). The ranges don't overlap and together cover z0–z5.
Crucially, all three rungs use the **same internal layer names**, so the map style doesn't need to
know the pyramid exists — it just asks for "the climate layer" and Mapbox serves whichever rung
owns the zoom you're currently at.

So as you zoom in, the map silently swaps: chunky 0.8° squares → 0.2° squares → full-detail 0.1°
squares. You only ever see the sharpest version your screen can actually resolve.

---

## 8. The three phases

### Phase 1 — get the maps up (no extra layering)
- Build the GeoJSON **directly from Zarr** (7.3) for **all 26 maps**. (Do `days-above-35c` first
  as a smoke-test of the whole path, then run the rest through the same builder.)
- Publish tilesets + styles to a **new namespace** with the **current recipe as-is** (7.5).
  Accept that some low-zoom tiles drop.
- **Write the database code but keep it OFF** (`--write-db` defaults off; tested against a
  scratch table only).
- View the result and **swipe-compare it against the live map** in MapBuilder / CompareMaps
  (7.6).

### Phase 2 — make the low zooms fit (the resolution pyramid)

**What the first publish actually told us (evidence, not guesses).** With Phase 1's recipe
(minzoom 2, native 0.1°), the `W201` report dropped features **only at zoom 2 and 3** — zoom 4
and 5 were clean. So native 0.1° is fine from z4 up; only the two lowest zooms overflow. And the
overflow is small: most tiles needed ~2500–3300 KB against the 2500 KB limit, the worst (Asia
tile `2/3/3`) 8183 KB. Averaging each **2×2 block of cells into one (a 0.2° cell) cuts the
feature count 4×**, which clears even that worst tile (8183 → ~2050 < 2500).

**Decisions taken:**

- **We precompute the coarser levels ourselves** in `hires-maps` (the §6 approach in
  [HI-RES-TILES.md](HI-RES-TILES.md)) — not Mapbox `union`. We already hold the data in the
  builder, so making coarser copies is cheap, we control the maths, and publishes stay fast.
- **We serve every zoom, 0 → 5.** Because we serve z0/z1 too, we need the full ladder, not just
  the 0.2° rung:

| Zoom | Resolution served | How it's made |
|---|---|---|
| 0–1 | 0.8° (`p08`) | average 8×8 blocks of native cells |
| 2–3 | 0.2° (`p02`) | average 2×2 blocks |
| 4–5 | 0.1° (native) | the Phase 1 output, unchanged |

> **Why no separate 0.4° rung at z1** (we originally planned one): a tileset pinned to
> `minzoom: 1, maxzoom: 1` fails Mapbox's post-publish metadata check — *"center zoom value must
> be greater than or equal to minzoom 1"* — because the centre zoom Mapbox derives falls below that
> minzoom. Letting the coarsest rung start at zoom 0 and cover **z0–1** avoids the problem entirely.
> Nothing visible is lost: at z1 a 0.8° cell is ~2 px. Bonus: 3 rungs instead of 4 means 6 tilesets
> instead of 8 — fewer publishes, less rate-limiting.

Each coarser level is a 2×2 average of the level above it, so the squares nest and line up
perfectly. `maxzoom` stays **5** (the pricing rule — HI-RES-TILES.md §8); `minzoom` becomes **0**.

> Note: the app currently starts at zoom **2.2** (`MIN_ZOOM` in `mapConsts.ts`), so it won't
> request the z0/z1 tiles until we lower that. We build them anyway for full zoomability (embeds,
> downloads, future use) — flip `MIN_ZOOM` when we want them visible in MapBuilder.

**Part A — generate the rungs (`hires-maps`).** Add a coarsening step to the builder: from the
native 0.1° arrays, make the 0.2° and 0.8° versions by area-weighted N×N block averaging of
every property, and emit one `.geojsonld` per rung (`40105-hires.geojsonld`,
`40105-hires-p02.geojsonld`, `-p08`). Small addition — the builder already holds the
arrays and the feature-writing code; the coarse rungs just use bigger cells. (We average all
properties, including the low/high uncertainty band — a fine visual approximation at zoom-out,
where that band isn't read closely.)

**Part B — stack the rungs behind a `--hi-res` flag (`vector-tiles`). ✅ implemented.** Each
rung becomes its **own east+west tileset** built from its own `.geojsonld`, but **all rungs keep
the same layer keys** and are pinned to disjoint zoom bands (`p08` z0–1, `p02` z2–3,
native z4–5). Because the tilesets share source-layer names and cover different zooms, the style
just **composites all rungs** and Mapbox serves the right resolution per zoom — so the map style
needs no per-rung layers (only its `composite` URL lists the extra tilesets). Publishes under a
`-hires` id namespace, so production is untouched.

Code: `vector-tiles/hires.ts` (rung config + `setRungLayers` + composite URL) and a
`processHiResDataset` in `createTilesets.ts`. Run it with:

```bash
hires-maps pyramid days-above-35c              # produce 40105-hires[-p02/-p08].geojsonld
ts-node createTilesets.ts 40105 --hi-res       # upload rungs, build/publish 6 tilesets, 1 style
```

(Typechecks; the actual publish needs `MAPBOX_ACCESS_TOKEN` in `vector-tiles/.env`.)

**Verify.** Re-publish hi-res `40105` and read the new `W201` — expect **no drops** at any zoom.
If z0 still overflows for a big landmass, the report will say so → add a coarser 1.6° (`p16`)
rung; if z0 is comfortable, we can merge z0–1 onto one rung. Confirm from the report, don't guess.
Then swipe hi-res vs live in MapBuilder to check it looks right at every zoom.

**Also in Phase 2:** tune styles/colours and the change-vs-absolute handling for the
precip / drought maps.

### Phase 3 — turn on the database
- Settle the schema decisions in 7.4 (new grid, volume/partitioning, which statistics to keep).
- Flip `--write-db` on, load the coordinates + statistics, and reconcile with the app's
  point-value / download / API consumers.

### Decisions locked in
- **Scope:** build all 26 maps in Phase 1 (smoke-test `days-above-35c` first).
- **Namespace:** new tileset/style ids on the `probablefutures` account; production untouched.
- **Headline value:** `mean` for heat maps, `p50` (median) for precip / drought / water-balance —
  matching the current live maps (`use_mean_for_mid` in `conf.yaml`).
- **Phase 2 low-zoom fix:** **precompute** the coarse rungs in `hires-maps` (not Mapbox `union`),
  and serve **minzoom 0 → maxzoom 5** via the pyramid (`p08` z0–1 / `p02` z2–3 / native z4–5), wired in
  `createTilesets` behind a **`--hi-res`** flag.

### Still to confirm with Carlos (not blocking the build)
- The missing warming level on `ten-hottest-wbmax-days` (5 instead of 6).
- A one-line sign-off that `mean`-for-heat / `median`-for-precip is right for this data too.
  (Units are already known from `conf.yaml` — see §4.)

---

## 9. One-line summary

The new warming-level data is the sharper version of our live maps, in the same shape — so we
build a small tool that turns each Zarr map **straight into GeoJSON** (skipping netCDF and, for
now, the database), publish it to Mapbox under a new id, and **swipe-compare it against the live
map in MapBuilder**. The database write path is built in Phase 1 but stays off until Phase 3,
once the schema questions the bigger data raises are settled.
