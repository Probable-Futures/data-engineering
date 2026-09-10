# Command reference — building and publishing the experimental maps

Every command used to build, publish and register the v4, diff, ERA5 and absolute map families,
in one place. Collected from the working notes kept while building them, then checked against
`hires-maps --help` and `vector-tiles/createTilesets.ts` so nothing is missing or stale.

Two tools do the work, and they are always run in this order:

```
hires-maps <command>              # Zarr / netCDF / live export  ->  .geojsonld on disk
npm run create-tilesets -- <id> --<variant>   # .geojsonld  ->  Mapbox tileset + style
SQL                               # style id  ->  a pf_maps row the app can read
```

Nothing is published until step 2, and nothing appears in the app until step 3.

---

## The seven map families

Everything below is one of these. They differ only in what the values mean and which grid they sit
on, so they differ only by an infix in every filename and tileset id.

| Variant | What a cell means | Grid | Rungs | Output folder | Colour ramp |
|---|---|---|---|---|---|
| `hires` | the new v4 data itself | 0.1° | 3 (native, `-p02`, `-p08`) | `data/mapbox/mts/` | `map` |
| `diff` | v4 − v3 — *did the numbers move* | 0.1° | 3 | `mts/diff-geojson/` | `diffMap` |
| `era5` | ERA5's own observed values | 0.25° | 1 (z2–5) | `mts/era5-geojson/` | `map` |
| `era5v3` | v3 − ERA5 — *how wrong is what we publish today* | 0.2° | 1 (z2–5) | `mts/era5-geojson/` | `diffMap` |
| `era5v4` | v4 − ERA5 — *is the new data closer to reality* | 0.1° | 3 | `mts/era5-geojson/` | `diffMap` |
| `abs` | a v4 change map republished as absolute | 0.1° | 3 | `data/mapbox/mts/` | `absoluteMap` |
| `v3abs` | a v3 change map republished as absolute | 0.2° | 1 | `data/mapbox/mts/` | `absoluteMap` |

**Sign convention for all three comparison families:** positive (red) means the **first-named**
dataset reads higher. `diff` is `v4 − v3`; `era5v3` is `v3 − ERA5` and `era5v4` is `v4 − ERA5`, so
in both of those red means we read hotter/wetter than was actually observed.

**Why the two ERA5 comparisons are a pair.** `era5v3` measures how wrong today's published map is;
`era5v4` measures whether the new data fixes it. Run both and the migration argument becomes a
number: on `days-above-35c`, over the domain both cover, v4's area-weighted mean absolute bias is
**3.45 days against v3's 16.68** — 4.8× closer to observations — and v4's signed bias is −0.52
where v3's is +12.14.

---

## 1. Building — `hires-maps`

Run from `hires-maps/`. Use `.venv/bin/hires-maps` or activate the venv first.

### v4, the new data

```bash
hires-maps build <slug> [--factor 1|2|8] [--out PATH] [--limit N] [--write-db]
hires-maps pyramid <slug> [--write-db]      # all three rungs at once — the usual one
hires-maps build-all [--pyramid] [--limit N] [--write-db]
```

`--factor` picks the rung: `1` = 0.1° (z4–5), `2` = 0.2° (z2–3), `8` = 0.8° (z0–1).
`--limit N` writes only the first N features — a fast smoke test that touches the whole code path.
`--write-db` also runs the statistics writer, and only ever on the native rung.

### v4 vs v3 comparison maps

```bash
hires-maps diff <slug> [--factor 1|2|8] [--out PATH] [--limit N]
hires-maps diff-pyramid <slug>              # all three rungs
hires-maps diff-all [--pyramid] [--limit N]
```

### ERA5 as a map in its own right

```bash
hires-maps era5-map <slug> [--factor 1|2|4] [--out PATH] [--limit N]
hires-maps era5-map-pyramid <slug>          # 0.25° + 0.5° + 1.0°
hires-maps era5-map-all [--pyramid] [--limit N]
```

Here `--factor` means something different: `1` = 0.25°, `2` = 0.5°, `4` = 1.0°. Only one rung is
actually published (see the table above); the coarser ones exist for inspection.

### The ERA5 comparison maps — v3 or v4

```bash
hires-maps era5-diff <slug> [--reference v3|v4] [--factor N] [--pyramid] [--out PATH] [--limit N]
hires-maps era5-diff-all [--reference v3|v4] [--pyramid] [--limit N]
```

`--reference` defaults to `v3`, so the bare command judges the map that is live today.

| | `--reference v3` | `--reference v4` |
|---|---|---|
| Grid | 0.2° | 0.1° |
| Rungs | 1 — `--factor`/`--pyramid` are a usage error | 3 — `--factor 1\|2\|8`, or `--pyramid` for all |
| Second half needed | a live v3 export | a downscaled v4 store |
| Buildable | 23 of 24 (40202 has no export) | 23 of 24 (`dry-hot-days` has no store) |
| Antarctica | covered | **~30% of land cells come out empty** |

The two sets are *not* the same 23. **40202 frost-nights builds under v4** — it only ever lacked the
v3 export — while `dry-hot-days` (40607) is v3-only. That is why `era5-diff-all` gates on the live
exports for v3 and on the stores for v4, and names whichever half is missing.

### Change maps republished as absolute

Needed because ERA5 is absolute, so a change map cannot sit beside it.

```bash
hires-maps absolute <slug> [--factor 1|2|8] [--out PATH] [--limit N]   # v4, 0.1°
hires-maps absolute-pyramid <slug>                                     # v4, all three rungs
hires-maps v3-absolute <slug> [--out PATH] [--limit N]                 # v3, 0.2°, one rung
```

### Inspecting what can be built

```bash
hires-maps era5-coverage        # per indicator: ERA5 file? live export? v4 store?
hires-maps absolute-coverage    # every change indicator, and what each republish needs
hires-maps live-maps            # live v3 exports on disk, paired with their indicators
```

Run these first when something will not build — they name the missing file rather than failing
halfway through.

---

## 2. Publishing — `npm run create-tilesets`

Run from `vector-tiles/`. The `--` after `npm run` is required; npm swallows the flags otherwise.

```bash
npm run create-tilesets -- <id> [<id> ...] [variant flag] [--suffix=-N] [--publish-only]
```

One variant flag per run:

```bash
npm run create-tilesets -- 40105                  # production (standard, no pyramid)
npm run create-tilesets -- 40105 --hi-res         # v4 at 0.1°, 3 rungs
npm run create-tilesets -- 40105 --diff           # v4 − v3, 3 rungs
npm run create-tilesets -- 40105 --era5           # ERA5's own values, 1 rung
npm run create-tilesets -- 40105 --era5-diff      # v3 − ERA5, 1 rung
npm run create-tilesets -- 40105 --era5-v4-diff   # v4 − ERA5, 3 rungs
npm run create-tilesets -- 40601 --absolute       # v4 change map as absolute, 3 rungs
npm run create-tilesets -- 40601 --v3-absolute    # v3 change map as absolute, 1 rung
```

Modifiers, valid with any of the above:

| Flag | Effect |
|---|---|
| `--suffix=-3` | appended to every tileset id **and** the style name — publish a second set without colliding |
| `--publish-only` | skip the slow upload + create, just publish tilesets that already exist (resume after a failure) |

Re-running the same suffix is safe: an existing tileset has its recipe updated rather than erroring.

**There is no "all datasets" mode** — `start()` exits if you pass no ids, so the ids are listed
explicitly. The batches actually used are in section 5.

Requires `MAPBOX_ACCESS_TOKEN`, `S3_BUCKET_NAME` and `APP_ENV` in `vector-tiles/.env`
(see `.env.example`).

---

## 3. Registering a map version in the database

Publishing creates a Mapbox style; the app only sees it once a `pf_maps` row points at it. This
clones the dataset's most recent row, swaps in the new style id, and marks it the latest version.

```sql
insert into pf_public.pf_maps (
  dataset_id, map_style_id, name, description, stops, bin_hex_colors, status, "order",
  is_diff, step, binning_type, bin_labels, slug, data_labels, method_used_for_mid,
  map_version, is_latest
)
select
  m.dataset_id,
  '<NEW_MAPBOX_STYLE_ID>',   -- printed by create-tilesets: "style id: ..."
  m.name, m.description, m.stops, m.bin_hex_colors,
  'draft',                   -- keep out of production until reviewed
  m."order", m.is_diff, m.step, m.binning_type, m.bin_labels, m.slug,
  m.data_labels, m.method_used_for_mid,
  4,                         -- map_version: 4 = the v4 generation
  true                       -- is_latest
from pf_public.pf_maps m
where m.dataset_id = <DATASET_ID>
order by m.map_version desc nulls last
limit 1
returning *;
```

Only two values change per dataset: the **style id** and the **dataset id**. Everything else is
inherited from the previous version, which is the point — the legend, stops and labels stay
identical so only the tiles change.

### Auditing what is on the Mapbox account

Seven map families across dozens of datasets adds up, and Mapbox offers no reverse lookup from a
tileset to the styles using it. `tileset-usage` builds one — it lists every tileset and every style
(drafts included), reads each style's `sources`, and subtracts:

```bash
npm run tileset-usage                                    # tilesets no style references
npm run tileset-usage -- --index                         # the full tileset -> styles index
npm run tileset-usage -- probablefutures.40101-east-v3    # check one tileset
npm run tileset-usage -- --no-drafts                     # faster; see the caveat below
```

Reports land in `vector-tiles/tileset-audit/` (gitignored). It is **read-only** — it never deletes.

Two things to know before acting on the output: drafts are scanned by default because a tileset used
only by a style's unpublished draft is still in use, and "no style references it" is not "nobody
needs it" — an app config or a saved URL can point at a tileset no style does. Check before
deleting.

### Inspection and cleanup

```sql
-- what exists
select dataset_id, name, is_diff from pf_public.pf_maps where dataset_id > 40000 order by dataset_id;
select * from pf_public.pf_maps where is_latest and dataset_id > 40000;
select dataset_id, name from pf_public.pf_maps where dataset_id in (40701, 40702);
select * from pf_public.pf_datasets where id in (40701, 40702);
select * from pf_public.pf_dataset_statistics where dataset_id in (40701) limit 10;

-- roll back a batch (destructive — check the select first)
delete from pf_public.pf_maps
where map_version = 4 and extract(year from created_at)::int = 2026;
```

> The working notes contain a line beginning `u pf_public.pf_maps where status = 'draft' ...` with
> no verb. It is a truncated fragment, not a runnable statement — do not paste it. Whatever it was
> meant to be (`update` or `delete from`), write it out in full and run the `select` version first.

---

## 4. Verification before publishing

Publishing is the slow, outward-facing step. These are the cheap checks that come first.

```bash
# a build that touches every code path but writes a small file
hires-maps era5-diff days-above-35c --limit 5000
```

`hires-explore` reads the stores directly, without building anything (run from `hires-maps/`):

```bash
hires-explore list                                          # every store on disk, with its live id
hires-explore describe days-above-35c                       # shape, levels, stats, ranges, % ocean
hires-explore point days-above-35c --lat 33.9 --lon 35.5    # the whole wl x stat table at one cell
hires-explore patch days-above-35c --wl 1.5 --lat 33.9 --lon 35.5   # a grid of values around it
hires-explore landmean days-above-35c                       # area-weighted land mean per level
```

`landmean` is the quickest check that a build's numbers are plausible at all, and the one that
catches a systematic bias a swipe comparison cannot.

Point at the data with `PF_DOWNSCALED_DATA=<path>` if it is not in the default location.

---

## 5. The batches that were actually run

Kept because re-running one of these is common. Semicolon-chained so a failure stops the run.

**v4 hi-res, second batch of indicators**

```bash
for id in 40102 40103 40106 40107 40201 40203 40204 40205 40207 40303 40304 40701; do
  npm run create-tilesets -- $id --hi-res
done
```

**v4 − v3 comparison maps — build then publish**

```bash
# build (from hires-maps/)
for s in frost-nights ten-hottest-nights days-above-26c-wbmax days-above-28c-wbmax \
         total-annual-precipitation snowy-days probability-of-drought \
         average-daytime-temperature ten-hottest-days days-above-38c days-above-45c \
         average-nighttime-temperature nights-above-20c nights-above-25c freezing-days \
         average-winter-temperature days-above-30c-wbmax days-above-32c \
         days-above-32c-wbmax probability-of-extreme-drought; do
  hires-maps diff-pyramid "$s"
done

# publish (from vector-tiles/)
for id in 40101 40104 40202 40206 40301 40302 40601 40614 40702 40102 40103 40106 40107 \
          40201 40203 40204 40205 40207 40303 40304 40701; do
  npm run create-tilesets -- $id --diff
done
```

**Standalone ERA5 maps**

```bash
hires-maps era5-map-all                      # every indicator with an ERA5 file
# or a subset:
for s in total-annual-precipitation dry-hot-days wettest-day snowy-days wettest-90-days; do
  hires-maps era5-map "$s"
done
```

**v3 vs ERA5 comparison maps** — 22 of the 23 buildable ones can be published; see section 6.

```bash
# build (from hires-maps/) — ~2 min, ~2.5 GB
hires-maps era5-diff-all

# publish (from vector-tiles/)
npm run create-tilesets -- \
  40101 40102 40103 40104 40105 40106 40107 \
  40201 40203 40204 40205 40206 40207 \
  40301 40302 40303 40304 40305 \
  40601 40613 40614 40616 \
  --era5-diff
```

**v4 vs ERA5 comparison maps** — all 23 build and all 23 publish; no blockers in this family.

```bash
# build (from hires-maps/). Native only is ~9 GB across 23; --pyramid is ~12 GB and ~6 min.
hires-maps era5-diff-all --reference v4 --pyramid

# publish (from vector-tiles/). Note 40202, which the v3 family cannot do.
npm run create-tilesets -- \
  40101 40102 40103 40104 40105 40106 40107 \
  40201 40202 40203 40204 40205 40206 40207 \
  40301 40302 40303 40304 40305 \
  40601 40613 40614 40616 \
  --era5-v4-diff
```

Per indicator that is ~408 MB native + ~105 MB at `-p02` + ~7 MB at `-p08`. Check disk before the
batch: 23 × 3 rungs is about 12 GB.

**Late additions: 40110 days-above-50c and 40305 ten-hottest-wbmax-days**

```bash
hires-maps pyramid days-above-50c
hires-maps diff-pyramid days-above-50c
hires-maps pyramid ten-hottest-wbmax-days
hires-maps diff-pyramid ten-hottest-wbmax-days

npm run create-tilesets -- 40110 --hi-res
npm run create-tilesets -- 40110 --diff
npm run create-tilesets -- 40305 --hi-res
npm run create-tilesets -- 40305 --diff
```

**Late addition: 40704 wildfire-danger-days.** Its v4 store arrived after the rest, so it was
absent from every batch above. Note the slug is `wildfire-danger-days` — the store folder's name,
not `conf.yaml`'s `change-wildfire-days_v03`.

```bash
# from hires-maps/
hires-maps pyramid      wildfire-danger-days   # 1,433,601 / 368,198 /  25,612 features
hires-maps diff-pyramid wildfire-danger-days   # 1,172,235 / 306,064 /  21,955 features

# from vector-tiles/
npm run create-tilesets -- 40704 --hi-res
npm run create-tilesets -- 40704 --diff
```

Two readings on the diff worth knowing before you look at it:

- **The live export is unusually sparse.** 383,829 features but only 345,915 with a baseline mid
  value, and **682,452 sentinel values** read as no-data — far more than any other indicator,
  because barren land has no fuel and is flagged rather than zeroed. Coverage comes out at 1,172,235
  comparable cells, 261,411 v4-only and 211,425 live-only.
- **Every diff value is a whole number, and that is the data, not truncation.** 40704's `mid` is
  `p50`, and the median of an integer day count is an integer: 0 of 1,433,646 `p50` values in the
  store are fractional, against 94.5% of the `mean` values. `DIFF_DECIMALS` is applied as always;
  there is simply no sub-integer signal to keep.

**Change maps republished as absolute**

```bash
# from hires-maps/
hires-maps absolute-pyramid wettest-day             # 40613, has a v4 store
hires-maps v3-absolute      wettest-day
hires-maps v3-absolute      dry-hot-days            # 40607, v3 only
hires-maps absolute-pyramid average-water-balance   # 40703, both
hires-maps v3-absolute      average-water-balance
hires-maps absolute-pyramid wildfire-danger-days    # 40704, both (v4 store arrived late)
hires-maps v3-absolute      wildfire-danger-days

# from vector-tiles/
npm run create-tilesets -- 40613 --absolute
npm run create-tilesets -- 40613 --v3-absolute
npm run create-tilesets -- 40607 --v3-absolute
npm run create-tilesets -- 40703 --absolute
npm run create-tilesets -- 40703 --v3-absolute
npm run create-tilesets -- 40704 --absolute
npm run create-tilesets -- 40704 --v3-absolute
```

---

## 6. Known blockers and traps

**40202 frost-nights has no v3 export.** There is no `40202.geojsonld` in
`data/mapbox/mts/old-geojson/`, so `diff` and `era5-diff --reference v3` cannot be built for it, and
it is absent from those batches. It **does** build under `--reference v4`, which needs only the ERA5
file and the v4 store — so this is the one blocker Stage C clears rather than inherits.

**40607 dry-hot-days has no `diffMap` palette.** `hires-maps era5-diff dry-hot-days` builds fine,
but `npm run create-tilesets -- 40607 --era5-diff` throws, because the diverging variants read
`dataset.diffMap` from `configs.ts` and 40607 has none. It is the only one of the 23 in that state,
and it takes `diffMap(DIFF_STOPS.days)` like every other day-count map whenever someone wants it
published.

**`dry-hot-days` has no v4 store**, so it is ERA5-vs-v3 only — there is no `--diff`, `--hi-res` or
`--era5-v4-diff` for it. It is the only registry entry in that state; every other slug in
`indicators.py` has a store on disk.

**A store whose folder name is not in the registry is skipped silently.** `build-all`, `diff-all`
and `era5-*-all` print it under "not in the indicator registry" and move on, so a slug typo costs
you a whole map without failing. This is what hid 40704's v4 store: the registry called it
`wildfire-days` while the folder was `wildfire-danger-days`. Run `hires-explore list` after any
data drop — it flags every folder the registry does not know.

**`era5v4` is blank over Antarctica.** ERA5 stops at 64.25°S and v4 does not, so 668,445 of v4's
2,213,030 land cells (30.2%) have nothing to compare against and are simply not emitted. The build
prints that count; it is the expected reading, not a warning. It does not arise for `era5v3`,
because v3 stops at 56.8°S itself.

**`era5_only` in the build output is not a check.** ERA5's finite mask covers 57.1% of the globe
including open ocean, so this count runs to hundreds of thousands (v3) or millions (v4) simply
because ERA5 has values where we have no land. `both` and the ours-only count are the numbers worth
reading.

**The five change indicators need absolute stops, not their live ramp.** For 40601, 40607, 40613,
40614 and 40616 the live `map.stops` are a *change* scale (40601 is `[-100 … +100]` mm). Every
absolute precipitation value on Earth exceeds the top stop, so an `--era5`, `--absolute` or
`--v3-absolute` map on the old ramp renders in a single colour. Each needs its own stops in
`configs.ts` **and** in its `pf_maps` row.

**Comparison-map legends are still an open item.** The `pf_maps` rows for the comparison families
carry the climate ramp rather than the diff stops, and the ERA5 families only have two warming
levels (`baseline` and `1c`), so the app's warming-level slider needs a decision before any of this
is public. See [decisions-and-status.md](decisions-and-status.md).

**The `DIFF_STOPS` ramp saturates on the millimetre maps.** For 40601 roughly 19% of `era5v4` cells
fall beyond the ±100 mm top stop, so those regions render as flat dark red or blue. This is not
caused by the ERA5 families — the shipped v4−v3 diff for 40601 is already 15.6% out of range — but
they inherit it. Widening `DIFF_STOPS.millimeters` (or adding a `precipitationTotal` entry) fixes it
for all three diverging variants at once.

**And on 40704 at the high warming levels — the worst case so far.** `DIFF_STOPS.days` is ±20, and
the v4−v3 diff for wildfire danger days runs well past it as warming rises:

| Level | p5 | p50 | p95 | range | beyond ±20 |
|---|---|---|---|---|---|
| baseline | −16 | −8 | 4 | −20…19 | 0.0% |
| 1 °C | −13 | −2 | 9 | −40…47 | 1.2% |
| 1.5 °C | −16 | −2 | 12 | −62…101 | 3.6% |
| 2 °C | −15 | −1 | 19 | −78…128 | 6.3% |
| 2.5 °C | −19 | −1 | 30 | −70…172 | 13.1% |
| 3 °C | −25 | 0 | 35 | −63…182 | 20.5% |

The published style's fill expression reads `data_1c_mid`, where only 1.2% clips, so the default
view is fine and the shipped `diffMap(DIFF_STOPS.days)` is the right family. If the 2.5/3 °C views
matter, 40704 needs its own wider stops (roughly ±40 would bring 3 °C down to ~5%) rather than a
change to `DIFF_STOPS.days`, which every other day-count map shares and which fits them.

**Publishing is slow and outward-facing.** Each `--era5-diff` dataset uploads ~112 MB, and each
`--era5-v4-diff` dataset ~520 MB across its three rungs. Publish one, look at it in a dev style,
then run the batch.

---

## Related documents

| Document | Covers |
|---|---|
| [hi-res-map-pipeline.md](hi-res-map-pipeline.md) | how the v4 pipeline works, and the resolution pyramid |
| [era5-and-gcm-maps.md](era5-and-gcm-maps.md) | the ERA5 plan, what is in the files, and why GCM is deferred |
| [era5.md](era5.md) | the ERA5 reader itself |
| [downscaled-data.md](downscaled-data.md) | what the v4 data is and where it came from |
| [decisions-and-status.md](decisions-and-status.md) | open questions and what is still blocked |
