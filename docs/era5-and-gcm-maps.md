# ERA5 maps and comparison maps — the plan (and what to do about GCM)

> Status: **Stage A built and verified** (2026-08-26). The reader, the standalone ERA5 maps and
> their tests are in; Stages B and C (the two comparison families) are still the proposed build.
> See "Stage A: what was built" at the end for what exists and what was measured.

---

## Context

We already publish red/blue comparison maps of **v4 minus v3** — the new 0.1° downscaled data minus
what is live on probablefutures.org today. Those answer "did the numbers move, and where".

They cannot answer the more important question: **is either version actually right?** Both v3 and v4
are model output. Comparing two models tells you they disagree, not which one is closer to reality.

Carlos has now given us ERA5, which is as close to "what actually happened" as gridded data gets. So
we can finally measure our published data against observations. The manager's ask — "compare v3 with
ERA5 and create red/blue maps to show higher/lower data" — is exactly this.

The intended outcome: for every heat and water map we publish, a map showing where our data runs hot,
where it runs cold, and by how much — for both v3 (what users see today) and v4 (what we are about to
ship).

Separately, Carlos has sent raw GCM data. That is a **different and much larger** piece of work; the
last section explains what it is and why it should not be bundled into this one.

---

## Part 1 — The four datasets, in plain English

You need these four straight, because the whole plan is about which pairs are worth subtracting.

| | What it is | Resolution | Warming levels |
|---|---|---|---|
| **GCM** (CMIP6, MPI-ESM1-2-HR) | A global climate model. Simulates the physics of the whole planet's climate from first principles. Coarse, because simulating the globe is expensive. | ~100 km (0.94°) | raw daily data, 1850–2100 |
| **v3** (live today) | Regional climate models (RegCM/REMO) run at higher resolution over regions, driven by GCMs. What is on the site now. | 0.2° (~22 km) | 6 (0.5 → 3.0) |
| **v4** (new, being shipped) | The GCM above, **statistically downscaled** to a fine grid and bias-corrected against observations. | 0.1° (~11 km) | 6 (0.5 → 3.0) |
| **ERA5** (new, this plan) | **Reanalysis.** Real observations — weather stations, satellites, buoys — fed into a weather model to fill the gaps, producing a gridded best estimate of what actually happened. Not a forecast. Not a free-running simulation. | 0.25° (~28 km) | **2 only (0.5, 1.0)** |

**Why ERA5 only has two warming levels.** A warming level is "the world when global average
temperature was X°C above pre-industrial". Observations only reach about 1.2–1.3°C so far, so only
the 0.5 and 1.0 windows exist in the real record. There is no observed 3°C world to measure. Your
own reading of this was correct.

**What GCM is, concretely.** It is the *coarse original that v4 was downscaled from* — the folders
Carlos shared are MPI-ESM1-2-HR, the exact model named in every v4 filename
(`..._MPI-ESM1-2-HR_ww-isimip_ssp585_wls.zarr`). So the lineage is:

```
GCM (~100 km, raw physics)
   │  statistical downscaling + bias correction against observations
   ▼
v4 (0.1°, what we are shipping)

v3 (0.2°) is a separate lineage — regional models, different method, currently live

ERA5 (0.25°) is not a model lineage at all — it is the observational yardstick
```

That is why "GCM maps" is a real ask from the manager: showing the coarse original next to the
downscaled version demonstrates what the downscaling bought. But it is a much bigger job — see
Part 6.

**Which comparisons are worth making:**

- **v4 − v3** — already built. "Did the numbers move."
- **v3 − ERA5** — *this plan, first priority.* "How wrong is what we publish today."
- **v4 − ERA5** — *this plan.* "Is the new data closer to reality than the old data." This is the one
  that justifies the v4 migration.
- **GCM vs v4** — deferred. "What did downscaling buy."

---

## Part 2 — What is actually in the ERA5 folder (verified, not assumed)

I opened every file in `~/work/pf-downscaled-data/era5/`. 24 netCDFs, one per indicator.

**Grid:** 721 × 1440 at **0.25°**, latitude 90 → −90, longitude **0 → 359.75**.

> Two traps here. Longitude is on the **0–360** convention, not −180–180 like all our other data, so
> it has to be rolled before anything lines up. And 0.25° does **not** divide into 0.2° or 0.1°, so
> the exact integer-index trick `livemaps.py` uses for v3↔v4 does not apply — this needs its own
> lookup (solved below, still exact).

**Warming levels:** `wl = [0.5, 1.0]`. Only two, as expected.

**Statistics:** two different naming schemes, which is a trap:

| Files | Variables |
|---|---|
| 19 heat files | `mean`, `perc05`, `perc50`, `perc95` |
| 5 water files (`dry-hot-days`, `snowy-days`, `total-annual-precipitation`, `wettest-90-days`, `wettest-day`) | `mean`, `perc_0`, `perc_5`, `perc_25`, `perc_50`, `perc_75`, `perc_95`, `perc_100` |

Note `perc05` vs `perc_5` and `perc50` vs `perc_50` — same meaning, different spelling. A lookup
table keyed on the file, not a string-munge.

**Units — verified against v4 at five cities:**

- **6 files are in Kelvin** and need `− 273.15`: `average-temperature`,
  `average-daytime-temperature`, `average-nighttime-temperature`, `average-winter-temperature`,
  `ten-hottest-days`, `ten-hottest-nights`. (Cairo average temperature: ERA5 294.54 K → 21.39 °C,
  v4 21.37 °C, v3 22 °C. Lines up.)
- **`ten-hottest-wb-days` is already in °C** despite being a temperature (range −10 to 30). This one
  file breaks the pattern; do not apply a blanket rule to anything with "temperature" or "hottest" in
  the name.
- Day counts and millimetres are already in our units. ERA5 annual precipitation matched v4 closely
  at every city tested (New York: ERA5 1150 mm, v4 1141 mm) — while v3 read 1571 mm. Interesting on
  its own: for precipitation, ERA5 backs v4 over v3.

**Coverage:** one single finite/NaN mask, identical across all 24 files and both warming levels.
Measured against the v4 land grid: **69.8% of v4 land cells have ERA5 data; the missing 30.2% is
Antarctica** (664,844 of 668,445 gap cells are south of 60°S). Everything else on land is covered.

**Slug names differ from v4's** and need an alias table:

| ERA5 file | v4 folder | PF id |
|---|---|---|
| `days-above-26c-wb` | `days-above-26c-wbmax` | 40301 |
| `days-above-28c-wb` | `days-above-28c-wbmax` | 40302 |
| `days-above-30c-wb` | `days-above-30c-wbmax` | 40303 |
| `days-above-32c-wb` | `days-above-32c-wbmax` | 40304 |
| `ten-hottest-wb-days` | `ten-hottest-wbmax-days` | 40305 |
| `dry-hot-days` | *(none — ERA5 only)* | 40607 |

**Coverage against what we can build:**

- **ERA5 vs v3: 23 of 24.** `frost-nights` (40202) is blocked — there is no `40202.geojsonld` in
  `data/mapbox/mts/old-geojson/`. Someone needs to export it from production. (This is the same
  reason 40202 has no v4−v3 diff either.)
- **ERA5 vs v4: 23 of 24.** `dry-hot-days` (40607) is blocked — no v4 store exists for it.
- **`dry-hot-days` is a bonus**: ERA5 covers 40607, which v4 does not. It is the only ERA5-vs-v3 map
  with no v4 counterpart.
- ERA5 has **nothing** for the drought maps (40701, 40702), water balance (40703), wildfire (40704),
  climate zones (40901), or storm frequency (40612).

**A useful simplification that falls out of that last point:** every existing unit transform in
`transforms.py` (`pct100`, `percentile_to_z`) applies only to the drought and water-balance maps —
and ERA5 has none of those. So **no existing transform is needed on any ERA5 map.** The only new
conversion is Kelvin → °C on the ERA5 side.

---

## Part 3 — What we are building

**Three** things, built in this order:

**0. The ERA5 maps themselves** — ERA5 rendered as an ordinary climate map on its own 0.25° grid, no
subtraction involved. This is built and verified *first*. Two reasons. It is the only way to check the
reader in isolation: a longitude-roll bug, a missed Kelvin conversion or a wrong percentile column all
show up immediately on a standalone map, whereas inside a subtraction they just make the diff quietly
wrong in a way that still looks plausible. And it delivers the manager's ask visually on its own —
putting the ERA5 map next to the live v3 map in the app *is* a comparison, before we compute a single
difference.

**1. ERA5 vs v3** — the red/blue comparison, first priority of the two diffs.

**2. ERA5 vs v4** — same, on the v4 grid.

The two comparison families use the existing red/blue `DIFF_COLORS` ramp from
[vector-tiles/configs.ts](../vector-tiles/configs.ts). The standalone ERA5 maps use each dataset's
**normal climate ramp** (`dataset.map`), because they are absolute climate maps, not signed
differences.

### Decisions taken

**Output grid: each comparison is built on the grid of the dataset being judged.**

```
ERA5 vs v3:   v3 native 0.2°, ERA5 replicated onto it   →  0.2° cells
ERA5 vs v4:   v4 native 0.1°, ERA5 replicated onto it   →  0.1° cells
```

Neither ERA5 (0.25°) nor v3 (0.2°) has 0.1° detail, so building the v3 comparison on the 0.1° grid
would invent detail and quadruple every file for nothing. On the v3 grid each map is well under
100 MB instead of ~700 MB.

**Warming levels: emit only the two that exist** — `data_baseline_*` and `data_1c_*`, six properties
per cell instead of eighteen. The 1.5–3°C levels are simply absent rather than present-and-null.

**Sign: `ours − ERA5`.** Red = our data reads **higher** than observations, blue = lower, grey = they
agree. Same reading as the existing v4−v3 maps (red = first-named dataset is higher), so one colour
never means two different things across map types.

### What each level means

- **Baseline (0.5)** — v3/v4's modelled 1971–2000 against ERA5's observed equivalent period. This is
  a straight **model bias** measurement and it is the headline map.
- **1.0 °C** — our modelled 1°C world against the observed period when the world was 1°C warmer.
  Also a bias check, slightly softer because the observed window is short.

---

## Part 4 — Implementation

The existing pipeline already does 90% of this. `diff_builder.py` computes
`new − (a coarser reference replicated onto the target grid)`, which is structurally the same
operation. The work is a new reference reader plus a second target grid.

### 4.1 `hires-maps/src/hires_maps/era5.py` — new

The ERA5 reader, mirroring the role [`livemaps.py`](../hires-maps/src/hires_maps/livemaps.py) plays
for v3. Contents:

- `ERA5_SLUG_ALIASES` — the six-row table from Part 2, plus the `dry-hot-days` → 40607 entry.
- `ERA5_VARS` — role (`low`/`mid`/`high`) → ERA5 variable name, per naming scheme. Keyed off which
  scheme the file uses, not off string manipulation.
- `KELVIN_SLUGS` — the six files needing `− 273.15`. Explicitly listed, with a comment naming
  `ten-hottest-wb-days` as the deliberate exception.
- `load(slug, roles)` → one `(721, 1440)` float32 array per (warming level, role), longitude already
  rolled to −180…180 and units already converted. Plus a `LoadReport` like `livemaps.LoadReport`, so
  a silent coverage change is visible rather than skewing every map.
- `parent_index(coords, *, axis)` → for each target coordinate, the index of the ERA5 cell covering
  it, or −1. **Exact integer arithmetic in units of 0.025°**, following the same reasoning as
  `livemaps._tenths`: ERA5 centres are multiples of 10 in those units and boundaries fall on
  `10k ± 5`, while v4 centres are multiples of 4 and v3 centres are `3592 + 8b`. I verified
  numerically that **zero** target centres on either grid land on an ERA5 boundary, so there are no
  ties to break and no floating-point ambiguity.
- `upsample(era5, rows, cols)` — same signature and NaN-at-−1 behaviour as `livemaps.upsample`.

> Reuse note: do **not** reimplement `upsample`; `livemaps.upsample` is already generic apart from
> its hardcoded `SHAPE`. Lift the shape into a parameter and share the function.

### 4.2 `hires-maps/src/hires_maps/indicators.py` — extend

- Add `dry-hot-days` → `40607`, `unit="days"`, `mid_stat="p50"`, `is_change=True`. (From
  `netcdfs/import/conf.yaml`: `use_mean_for_mid: False`, and the name ends "differences relative to
  1971-2000".) It has no v4 store, so it is ERA5-vs-v3 only — the registry entry exists purely to
  give it a live id, unit and mid statistic.
- Add an `era5_slug` field (or resolve via the alias table in `era5.py` — either is fine, but pick
  one place).

### 4.3 `geojson/stages.py` — give `Grid` an explicit step (small refactor, unlocks everything else)

`Grid.half` is currently `GRID_STEP_DEG / 2.0 * self.factor`, which hardcodes a 0.1° base. That works
for every grid we build today, but neither new grid fits it: the v3 grid needs 0.2° (survivable — it
happens to fall out of `factor=2`) and the **ERA5 grid needs 0.25°, which would require `factor=2.5`.**

Fix it properly rather than working around it:

```python
@dataclass(frozen=True)
class Grid:
    slices: dict[str, np.ndarray]
    lat: np.ndarray
    lon: np.ndarray
    step: float = GRID_STEP_DEG   # this grid's own cell size in degrees
    factor: int = 1               # rung bookkeeping, unchanged

    @property
    def half(self) -> float:
        return self.step / 2.0
```

`coarsened(f)` multiplies `step` by `f` alongside `factor`. `stages.load` passes `step=GRID_STEP_DEG`,
so every existing build is byte-identical. The v3 path then says `step=0.2` explicitly instead of
relying on a coincidence, which is worth it on its own.

One knock-on: `output.rung_suffix` derives `-p02` / `-p08` from `factor`, which only reads correctly
because the base is 0.1°. Switch it to derive from the **step** — `0.2 → -p02`, `0.8 → -p08`
(unchanged for every existing file), and it then also gives `0.5 → -p05`, `1.0 → -p10` for the ERA5
rungs. Native is always the bare suffix, so 0.25° never needs an awkward name.

### 4.4 `hires-maps/src/hires_maps/geojson/era5_builder.py` — new (build this first)

The standalone ERA5 map: ERA5's own numbers, on ERA5's own 0.25° grid, no subtraction. This is the
first thing built and the first thing verified.

1. `era5.load(slug, roles)` for the 2-level, 3-role plan → 6 arrays.
2. Build a `Grid` with the ERA5 lat/lon and **`step=0.25`**.
3. **No transform, no change step** — ERA5 values are already absolute and already in our units after
   the reader's Kelvin conversion.
4. Mask, then `output.write_features` with `formatting.formatter(ind.unit)` — the **normal** unit rule,
   integer truncation and all, *not* the `decimals=1` override the comparison maps use. That makes the
   ERA5 map directly comparable to the published v3/v4 maps, popup for popup.
5. Rungs: native 0.25°, then 0.5° and 1.0°.

**On the mask — deliberately not a land mask by default.** ERA5's finite mask is not a land mask: 57.1%
of the global grid is finite, which is neither land (~29%) nor everything. It includes open ocean in
places (mid-Pacific has values; mid-Atlantic does not). Land coverage is complete outside Antarctica,
which is all our maps need — but for the *verification* build we want to see exactly what the file
contains, oddities included, so the default mask is "ERA5 is finite, minus the +180° seam column".

Add `--land-mask v3|v4` for a presentable version that intersects with a real land mask, once the
verification pass is done. **And put the ocean-coverage pattern to Carlos** — if it is an artifact of
how these files were produced, it is worth knowing whether it touched the land values too.

**Colour ramp.** These are absolute climate maps, so they reuse each dataset's existing `map` ramp
from `configs.ts`, not `DIFF_COLORS`. One caveat: for the five change-map indicators (40601, 40607,
40613, 40614, 40616) the live ramp is designed for *changes*, while ERA5 is absolute — so the live
ramp will not fit those. Start the standalone pass with the **19 heat maps**, where the live ramp is
already absolute and reusable, and handle the five water maps afterwards (either new absolute stops,
or build them as `1c − baseline` to match the live semantics — decide when we get there).

### 4.5 `hires-maps/src/hires_maps/geojson/era5_diff_builder.py` — new

Reuses `stages.py` throughout. Two entry points, or one with a `reference` argument:

**`build_era5_v4_diff(slug, factor)`** — nearly identical to today's `build_diff`:

1. `stages.load(ind, plan)` where `plan` is the **2-level** plan (see 4.4).
2. **Skip `to_change` entirely** — ERA5 is absolute, so compare absolute to absolute. This is
   cleaner than the `zero_baseline=False` dance `diff_builder` needs, and it is why no transform is
   required.
3. `era5.parent_index` on the v4 lat/lon, `era5.upsample`, subtract.
4. `grid.coarsened(factor)`, `stages.land_mask`, `output.write_features` with
   `formatting.formatter(unit, decimals=1)`.
5. Rungs: factor **1, 2, 8** — same three as today.

**`build_era5_v3_diff(slug, factor)`** — the new grid path:

1. `livemaps.load(ind.live_id, property_names)` — this already returns arrays exactly on the v3
   `(899, 1799)` lattice, no resampling.
2. **Reconstruct absolutes for the four change maps** (40601, 40613, 40614, 40616, and 40607). The
   live change maps keep an *absolute* baseline but a *change* at 1°C — so
   `v3_1c_absolute = data_baseline_mid + data_1c_mid`, per role. Without this, the 1°C comparison
   would subtract an absolute ERA5 value from a v3 delta and produce nonsense. The baseline
   comparison needs no fixing.
3. Construct a `Grid` with the v3 lat/lon axes and **`factor=2`** — `Grid.half` is
   `GRID_STEP_DEG / 2 * factor`, so factor 2 gives the 0.1° half-width that 0.2° cells need.
4. `era5.parent_index` on the v3 lat/lon, `era5.upsample`, subtract.
5. Rungs: **factor 2 (native 0.2°) and factor 8** (`grid.coarsened(4)`). `output.rung_suffix` already
   turns those into `-p02` and `-p08`, which is exactly what the tiling side expects. There is no
   native-resolution rung for this variant.

Both report coverage the way `DiffReport` does — `both` / `new_only` / `live_only` counted on the
native grid. Expect a large `new_only` driven by Antarctica; that is the check that will catch a
longitude-roll bug, so it must be printed.

### 4.6 `hires-maps/src/hires_maps/mapping.py` — extend

`property_plan` hardcodes all six warming levels. Add a levels argument:

```python
def property_plan(ind, levels=WARMING_LEVELS): ...
```

ERA5 builds pass `(0.5, 1.0)`. Every existing caller keeps the six-level default, so nothing else
changes.

### 4.7 `hires-maps/src/hires_maps/config.py` and `geojson/output.py`

- `ERA5_DIR = DATA_ROOT / "era5"`.
- `ERA5_MAPS_DIR = MTS_DIR / "era5-geojson"` — a sibling of `diff-geojson`, same reasoning: both
  halves of a comparison sit together and neither crowds the hi-res builds.
- Extend the `Variant` StrEnum with `ERA5 = "era5"` (the standalone map), `ERA5_V3 = "era5v3"` and
  `ERA5_V4 = "era5v4"` (the two comparisons). The docstring already says the spelling is a contract
  with `vector-tiles/hires.ts` — keep them in step.
- Filenames: `{live_id}-era5[-pNN].geojsonld`, `{live_id}-era5v3[-pNN].geojsonld`,
  `{live_id}-era5v4[-pNN].geojsonld`. All three land in `era5-geojson/`.

> **Check before committing to those names:** Mapbox tileset ids have a 32-character limit.
> `40105-era5v4-p08` plus the version and suffix that `createTilesetIds` appends is three characters
> longer than today's `40105-diff-p08`. Measure the longest generated id first; shorten to `e5v3`/
> `e5v4` if it is tight.

### 4.8 `hires-maps/src/hires_maps/cli.py` — new commands

Following the existing `build` / `pyramid` / `build-all` and `diff` / `diff-pyramid` / `diff-all`
shapes:

```
hires-maps era5-coverage                 # what can be built, and what blocks the rest
hires-maps era5-map <slug> [--factor N] [--limit N] [--land-mask v3|v4]
hires-maps era5-map-pyramid <slug>
hires-maps era5-map-all [--pyramid]
hires-maps era5-diff <slug> --reference v3|v4 [--factor N] [--limit N]
hires-maps era5-pyramid <slug> --reference v3|v4
hires-maps era5-all [--reference v3|v4] [--pyramid]
```

`era5-all` should reuse the `_on_disk` pattern and report the two known blockers by name (40202 needs
a v3 export; 40607 has no v4 store) rather than failing silently.

### 4.9 `vector-tiles/` — plumbing

- `hires.ts`: add `"era5"`, `"era5v3"` and `"era5v4"` to `PyramidVariant`; add
  `ERA5_SUBDIR = "era5-geojson"` to `pyramidSubdir`.
- `hires.ts`: **rungs become per-variant.** `HIRES_RUNGS` is currently a single global list, and each
  new variant has a different native resolution. The coarsest rung always covers z0–1 and the finest
  always runs up to z5:

  ```
  hires / diff / era5v4   0.1°:   ""(z4-5)   -p02(z2-3)  -p08(z0-1)
  era5v3                  0.2°:              -p02(z2-5)  -p08(z0-1)
  era5 (standalone)      0.25°:   ""(z2-5)   -p05(  — )  -p10(z0-1)
  ```

  For `era5v3` and `era5` the native rung stretches to cover the band a finer rung would have held,
  because there is no finer rung to hold it.
- `configs.ts`: the two **comparison** families reuse `DIFF_COLORS` and the existing `DIFF_STOPS`
  families unchanged — same kind of signed quantity, same units. New `diffMap` entries are needed for
  40607 (`days`) and, once its export exists, 40202; everything else already has one after the recent
  fix. The **standalone** ERA5 map instead reads each dataset's existing `map` ramp, so it needs no new
  config at all for the 19 heat maps.
- `createTilesets.ts`: the `--diff` flag becomes a variant selector (`--variant era5|era5v3|era5v4`).
  The `diffMap`-missing guard at line 443 must fire for the comparison variants but **not** for the
  standalone `era5` variant, which legitimately uses `dataset.map`.

### 4.10 Tests

Follow `tests/test_diff_builder.py` and `tests/test_livemaps.py`. The ones that matter:

- **Longitude roll** — an ERA5 cell at 359.75° must land at −0.25°, and the ±180° seam must not
  duplicate or drop a column. This is the bug most likely to silently shift every map.
- **No ties** — assert zero target centres land on an ERA5 boundary, on both grids. Cheap, and it
  locks in the property the whole lookup relies on.
- **Kelvin** — `average-temperature` converts; `ten-hottest-wb-days` does **not**.
- **Both variable-naming schemes** resolve to the right role.
- **Change-map reconstruction** — for 40601, `v3_1c_absolute` equals baseline + change, and the
  emitted 1°C diff is not `change − absolute`.
- **Antarctica is null, not zero** — mirroring the existing
  `test_cells_the_live_map_lacks_become_null_not_zero`.
- **Cell geometry per grid** — a standalone ERA5 feature's polygon is 0.25° across, a v3-grid one is
  0.2°, a v4-grid one is 0.1°. This is what the `Grid.step` refactor exists to get right, so pin it.
- **`Grid.step` is backward compatible** — an existing 0.1° build produces byte-identical output
  before and after the refactor. Assert against a stored fixture rather than eyeballing it.
- **Standalone values are unmodified** — a handful of cells in an `era5-map` output equal the netCDF
  value (after Kelvin conversion and the live truncation rule) exactly. This is the test that makes
  the whole reader trustworthy, so it should read the source file directly rather than a fixture.

---

## Part 5 — Order of work

**Stage A — the reader, and ERA5 as a map in its own right. Nothing subtracted yet.**

1. `Grid.step` refactor (4.3) + the backward-compatibility test. Small, and everything else sits on
   top of it.
2. `era5.py` + tests. Nothing downstream can be trusted until the reader is.
3. `era5-coverage` — confirms the 23/23 counts and the two blockers against the real files.
4. `era5-map days-above-35c` (40105 — the indicator every previous pipeline change was validated on).
   Render it as a static PNG via `analysis/` and check it against the netCDF directly.
5. `era5-map average-temperature` (40101) as the second check, because it exercises the Kelvin path
   that 40105 does not.
6. **Verify hard here.** A longitude-roll bug, a missed Kelvin conversion or the wrong percentile
   column are all obvious on a standalone map and nearly invisible once buried in a subtraction. Do
   not move to Stage B with anything unexplained.
7. Publish one standalone ERA5 map and look at it in the app **next to the live v3 map**. That side by
   side is already useful to the team, and it validates the tiling plumbing for the new variant before
   any diff exists.
8. Batch the remaining 17 heat maps. Decide what to do about the five change maps' ramps (4.4).

**Stage B — ERA5 vs v3.**

1. `build_era5_v3_diff` for 40105. Static PNG first.
2. Sanity-check sign and magnitude against known bias: v3 read ~+1 °C hot at Delhi and Cairo in my
   spot checks, so the baseline temperature map should be mildly red there — not blue, not saturated.
3. Publish 40105 `era5v3` end to end; confirm fill and legend.
4. Batch the remaining 22.

**Stage C — ERA5 vs v4.** Repeat all four Stage B steps for `era5v4`.

Publishing is the expensive, outward-facing step. One map fully right before uploading the other 60-odd.

---

## Part 6 — Things that will look like bugs but are not

Worth writing into the map descriptions, because someone will ask.

**Antarctica is blank.** ERA5 has no data there. 30% of v4's land cells, all of it south of 60°S.

**The maps are blocky, and the blocks are uneven.** ERA5 at 0.25° replicated onto 0.1° gives blocks
that are 2 or 3 cells per side, not a clean 2×2 — because 0.25 / 0.1 = 2.5. On the v3 0.2° grid it is
1 or 2 cells per side. This is the same nearest-neighbour replication the data scientist asked about
for the v4−v3 maps, with the extra wrinkle that the block sizes alternate. Not an artifact of a bug.

**Only two warming levels.** By design — see Part 1.

**The standalone ERA5 map has values over some ocean.** Unlike every other PF map, it is not land-only
by default — ERA5's finite mask covers 57.1% of the globe and includes open ocean in places. That is
deliberate for the verification build (Part 4.4): we want to see what the file actually contains. Use
`--land-mask` for a presentable version.

**v3's precipitation looks much worse than v4's.** In the spot checks, ERA5 agreed with v4 within a
few percent on annual precipitation while v3 was 30–90% higher. If that holds up across the grid it
is a genuine finding, and one of the strongest arguments for the v4 migration. Worth confirming
before repeating it to anyone.

---

## Part 7 — GCM: what it is and why it is not in this plan

The two folders you downloaded:

| Folder | Contents |
|---|---|
| `GCM-CMIP6-historical-1850-2014` | 18 GB, `tas` daily, 60,265 days |
| `gcm-simulated-data-SSP858-2015-2100` | 9 GB, `tas` daily, 31,411 days |

(The folder name says SSP858; the data is **ssp585**. Carlos's message has the same typo. Worth
renaming to avoid confusion later.)

Both are MPI-ESM1-2-HR on a **192 × 384 Gaussian grid** — about 0.94°, and the latitude spacing is
*not* uniform (−89.28, −88.36, −87.42, …), which rules out any integer-index alignment. Units Kelvin.

**Why this is a much bigger job than ERA5.** ERA5 arrived as finished indicators at warming levels —
the same shape as our existing data, so it slots into the pipeline. GCM is **raw daily temperature**.
To make a single PF map from it you would have to rebuild the whole scientific pipeline that Woodwell
normally runs for us:

1. Define the warming levels — compute global mean temperature per year from the daily data, find
   the 20–30 year window centred on each +0.5/1.0/1.5/2.0/2.5/3.0 °C crossing.
2. Compute the annual indicator from daily values inside each window.
3. Compute the `min`/`p5`/`p50`/`p95`/`max`/`mean` spread across the years in the window.
4. Only then resample onto a map grid.

Steps 1–3 are Woodwell's science, not our pipeline, and getting them subtly wrong would produce a
map that looks plausible and is wrong.

**And only one indicator is even possible.** The folders contain `tas` (daily mean temperature) only.
That gives **average temperature (40101)** and nothing else:

- days above 32/35/38/45 °C need `tasmax`
- nights above 20/25 °C, frost nights need `tasmin`
- all wet-bulb maps need humidity
- all precipitation maps need `pr`

This matches the scientist's own read — *"trickier to process… we should discuss further what to do
with them"* and *"there are no pf maps with cmip6 data, since that has not been needed before."*

**Recommendation:** finish the ERA5 maps first, then go back to Carlos with three questions:

1. Should we compute warming levels and annual aggregates ourselves, or can Woodwell supply GCM data
   already aggregated to warming levels — the same shape the ERA5 files arrived in? The second is
   days of work instead of weeks, and removes the risk of us getting the science wrong.
2. If we must process the raw data, can we get the exact warming-level year windows Woodwell used for
   v3 and v4? Comparing GCM to v4 is meaningless unless both use the same windows.
3. Do we need `tasmax` / `tasmin` / `pr` too, or is average temperature enough for the point being
   made? If the goal is "show what downscaling bought", one well-chosen indicator may be plenty.

---

## Part 8 — Verification

**During development** (no publishing, fast):

```bash
cd hires-maps
.venv/bin/python -m pytest tests/ -q
.venv/bin/hires-maps era5-coverage
.venv/bin/hires-maps era5-map days-above-35c --limit 5000        # Stage A
.venv/bin/hires-maps era5-diff days-above-35c --reference v3 --limit 5000   # Stage B
```

### Stage A — the standalone map (the one that matters most)

This is where a reader bug is catchable. Checks, in order of how much they buy:

- **Spot values against the source.** Pick ten cells, read the same lat/lon straight out of the
  netCDF with xarray, apply Kelvin and the truncation rule by hand, and compare. If this passes for
  both a Kelvin file (40101) and a non-Kelvin one (40305), the reader is sound.
- **The map looks like the world.** Render it as a PNG via `analysis/` — a longitude-roll bug shows up
  instantly as a map shifted half a world sideways, and is completely invisible in a feature count.
- **Ranges are physical.** Average temperature between roughly −40 and +40 °C, day counts in 0–366,
  precipitation non-negative. A Kelvin file that slipped through unconverted reads ~290, which is
  unmistakable.
- **Feature count ≈ 594k** — 57.1% of the 721 × 1440 grid, minus the seam column.
- **Every feature has exactly 6 `data_*` properties**, and a polygon measures 0.25° per side.

### Stage B/C — the comparison maps

- Feature count ≈ 300k for a v3-grid map (the ~425k v3 land cells minus Antarctica), and ~1.54M for a
  v4-grid map (the measured ERA5 ∩ v4-land intersection).
- Polygons measure 0.2° and 0.1° per side respectively.
- **Land-mean has the sign the spot checks predict**: v3 baseline temperature ran ~1 °C hot at Delhi
  and Cairo, so the mean should be positive and small — not zero, not ±10.
- Render as a static PNG with the `diverging=True` path in
  [analysis/lib.py:326](../analysis/lib.py#L326) before spending an upload.
- **Cross-check the arithmetic once**: for a few cells, confirm the emitted diff equals
  `standalone_v3_value − standalone_era5_value` from the Stage A output. If Stage A is verified, this
  makes Stage B verified too.

**End to end**, one map per stage:

```bash
cd vector-tiles
npm run create-tilesets -- 40105 --variant era5      # Stage A
npm run create-tilesets -- 40105 --variant era5v3    # Stage B
```

then point a dev style at each and confirm the fill and the legend agree.

---

## Known blockers to clear

- **`40202.geojsonld` does not exist** in `data/mapbox/mts/old-geojson/`. Blocks the frost-nights
  ERA5-vs-v3 map (and the v4-vs-v3 one, which is why 40202 was never published). Needs exporting
  from production.
- **The `pf_maps` legend rows** for every comparison map still carry the climate ramp rather than the
  diff stops — the open item at
  [decisions-and-status.md:208](decisions-and-status.md#L208). The ERA5 maps inherit
  this, and additionally only have two warming levels, so the app's slider behaviour on them needs a
  decision before public release.

---

## Stage A: what was built

Implemented and verified 2026-08-26. Stages B and C are untouched.

### Code

| File | What |
|---|---|
| `hires-maps/src/hires_maps/era5.py` | **new.** The reader: slug aliases, both statistic-naming schemes, the Kelvin list, the longitude roll, and the exact 0.025°-unit `parent_index` / `upsample` the comparison builders will use |
| `hires-maps/src/hires_maps/geojson/era5_builder.py` | **new.** `build_era5_map` — the standalone map |
| `hires-maps/src/hires_maps/geojson/stages.py` | `Grid` gains an explicit `step`; `half` derives from it |
| `hires-maps/src/hires_maps/geojson/output.py` | `Variant.ERA5`; `rung_suffix` / `output_path` take a native `step` |
| `hires-maps/src/hires_maps/mapping.py` | `property_plan(ind, levels=...)` |
| `hires-maps/src/hires_maps/indicators.py` | `dry-hot-days` (40607), ERA5-only |
| `hires-maps/src/hires_maps/config.py` | `ERA5_DIR`, `ERA5_MAPS_DIR`, `ERA5_STEP_DEG`, `ERA5_WARMING_LEVELS` |
| `hires-maps/src/hires_maps/cli.py` | `era5-coverage`, `era5-map`, `era5-map-pyramid`, `era5-map-all` |
| `hires-maps/pyproject.toml` | `netcdf4` — the ERA5 files are the only netCDF this package reads |

Tests: `tests/test_era5.py` (21) and `tests/test_era5_builder.py` (18). Suite is **170 passing**, ruff
clean. `test_indicators.py` needed two updates, both because the registry is no longer exactly the
set of downscaled stores.

### Verified

- **`era5-coverage` reports 24 ERA5 maps, 23 vs v3, 23 vs v4** — matching the counts predicted from
  the raw files, with 40202 and `dry-hot-days` named as the two blockers.
- **Values are exact.** 240 spot checks across 40105 (no conversion) and 40101 (Kelvin), each read
  independently from the netCDF and truncated by hand: **240 matched, 0 mismatched.**
- **All 24 files load**, including both naming schemes and `dry-hot-days`.
- **593,276 features** per native map — 57.1% of the 721 × 1440 grid, as measured on the raw files.
- Six properties per feature; values 0–321 days and −28…+33 °C; latitude stops at −64.25°.
- **Rasterized back from the emitted GeoJSON and rendered**: continents in the right places (no
  longitude shift), Sahara/Australia/India hot, mountain ranges visible in the temperature field,
  Antarctica absent.
- Coarse rungs work: the 1.0° rung emits 37,772 features with 1.0° cells, and the polar row is
  clamped to 90° rather than overshooting it.

### New finding for Carlos

The ocean gaps are **large rectangles roughly aligned to a 5° grid** — 87% of 5°×5° blocks are
all-or-nothing. That is not what a physical mask looks like; it looks like tile-wise processing where
some ocean tiles were never written. It does not affect any map we build (all land except Antarctica
is covered), but it is worth confirming the same tiling did not affect land values.

### Next

Stage A steps 7–8 remain: publish one standalone map and eyeball it next to the live v3 map, then
batch the remaining 22. Deciding the five change maps' ramps (Part 4.4) blocks the water maps only.
