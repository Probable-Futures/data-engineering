# Command reference — building and publishing the experimental maps

Every command used to build, publish and register the v4, diff, ERA5 and absolute map families,
in one place. Collected from the working notes kept while building them, then checked against
`hires-maps --help`, `vector-tiles/createTilesets.ts` and `analysis/Makefile` so nothing is missing
or stale.

Two tools do the work, and they are always run in this order:

```
hires-maps <command>              # Zarr / netCDF / live export  ->  .geojsonld on disk
npm run create-tilesets -- <id> --<variant>   # .geojsonld  ->  Mapbox tileset + style
SQL                               # style id  ->  a pf_maps row the app can read
```

Nothing is published until step 2, and nothing appears in the app until step 3.

---

## The six map families

Everything below is one of these. They differ only in what the values mean and which grid they sit
on, so they differ only by an infix in every filename and tileset id.

| Variant | What a cell means | Grid | Rungs | Output folder | Colour ramp |
|---|---|---|---|---|---|
| `hires` | the new v4 data itself | 0.1° | 3 (native, `-p02`, `-p08`) | `data/mapbox/mts/` | `map` |
| `diff` | v4 − v3 — *did the numbers move* | 0.1° | 3 | `mts/diff-geojson/` | `diffMap` |
| `era5` | ERA5's own observed values | 0.25° | 1 (z2–5) | `mts/era5-geojson/` | `map` |
| `era5v3` | v3 − ERA5 — *how wrong is what we publish today* | 0.2° | 1 (z2–5) | `mts/era5-geojson/` | `diffMap` |
| `abs` | a v4 change map republished as absolute | 0.1° | 3 | `data/mapbox/mts/` | `absoluteMap` |
| `v3abs` | a v3 change map republished as absolute | 0.2° | 1 | `data/mapbox/mts/` | `absoluteMap` |

**Sign convention for both comparison families:** positive (red) means the **first-named** dataset
reads higher. `diff` is `v4 − v3`; `era5v3` is `v3 − ERA5`, so red means we publish hotter/wetter
than was actually observed.

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

### v3 vs ERA5 comparison maps

```bash
hires-maps era5-diff <slug> [--out PATH] [--limit N]
hires-maps era5-diff-all [--limit N]
```

No `--factor` — this family is a single rung on v3's 0.2° grid, so there is nothing to coarsen.

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

The `analysis/` toolkit renders static PNGs and spot-checks values without going near Mapbox
(run from `analysis/`, uses its own venv — `make setup` once):

```bash
make inspect INDICATOR=days-above-35c        # summarize a store
make inspect STORE=<path>                    # summarize any .zarr / .nc
make quicklook INDICATOR=days-above-35c YEAR=2050 [PERIOD=1971-2000]
make timeseries INDICATOR=days-above-35c PLACES=Beirut,Cairo,Delhi
make compare INDICATOR=days-above-35c [WL=1.5] [PERIOD=2024-2040]   # old vs new
make validate                                # new data vs ERA5-Land observations
make warming-levels                          # estimate breaching years / windows
make report INDICATOR=days-above-35c         # client-ready HTML
make clean
```

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

**Change maps republished as absolute**

```bash
# from hires-maps/
hires-maps absolute-pyramid wettest-day             # 40613, has a v4 store
hires-maps v3-absolute      wettest-day
hires-maps v3-absolute      dry-hot-days            # 40607, v3 only
hires-maps absolute-pyramid average-water-balance   # 40703, both
hires-maps v3-absolute      average-water-balance
hires-maps v3-absolute      wildfire-days           # 40704, v3 only

# from vector-tiles/
npm run create-tilesets -- 40613 --absolute
npm run create-tilesets -- 40613 --v3-absolute
npm run create-tilesets -- 40607 --v3-absolute
npm run create-tilesets -- 40703 --absolute
npm run create-tilesets -- 40703 --v3-absolute
npm run create-tilesets -- 40704 --v3-absolute
```

---

## 6. Known blockers and traps

**40202 frost-nights has no v3 export.** There is no `40202.geojsonld` in
`data/mapbox/mts/old-geojson/`, so neither `diff` nor `era5-diff` can be built for it. Someone has
to export it from production. This is why 40202 is absent from every comparison batch.

**40607 dry-hot-days has no `diffMap` palette.** `hires-maps era5-diff dry-hot-days` builds fine,
but `npm run create-tilesets -- 40607 --era5-diff` throws, because the diverging variants read
`dataset.diffMap` from `configs.ts` and 40607 has none. It is the only one of the 23 in that state.

**`dry-hot-days` has no v4 store**, so it is ERA5-vs-v3 only — there is no `--diff` or `--hi-res`
for it.

**The five change indicators need absolute stops, not their live ramp.** For 40601, 40607, 40613,
40614 and 40616 the live `map.stops` are a *change* scale (40601 is `[-100 … +100]` mm). Every
absolute precipitation value on Earth exceeds the top stop, so an `--era5`, `--absolute` or
`--v3-absolute` map on the old ramp renders in a single colour. Each needs its own stops in
`configs.ts` **and** in its `pf_maps` row.

**Comparison-map legends are still an open item.** The `pf_maps` rows for the comparison families
carry the climate ramp rather than the diff stops, and the ERA5 families only have two warming
levels (`baseline` and `1c`), so the app's warming-level slider needs a decision before any of this
is public. See [decisions-and-status.md](decisions-and-status.md).

**Publishing is slow and outward-facing.** Each `--era5-diff` dataset uploads ~112 MB. Publish one,
look at it in a dev style, then run the batch.

---

## Related documents

| Document | Covers |
|---|---|
| [hi-res-map-pipeline.md](hi-res-map-pipeline.md) | how the v4 pipeline works, and the resolution pyramid |
| [era5-and-gcm-maps.md](era5-and-gcm-maps.md) | the ERA5 plan, what is in the files, and why GCM is deferred |
| [era5.md](era5.md) | the ERA5 reader itself |
| [downscaled-data.md](downscaled-data.md) | what the v4 data is and where it came from |
| [decisions-and-status.md](decisions-and-status.md) | open questions and what is still blocked |
