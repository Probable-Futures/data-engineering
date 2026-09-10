# `hires-maps` — decisions, status and open questions

> *Decisions live here with their reasons. The reference docs describe only what is true now; if you
> reverse something, edit them in place and add an entry here.*

**The one file in `docs/` that is meant to change.** It carries where the work stands, why each
non-obvious choice was made, what is still open, and where the project came from. The two reference
docs — [`downscaled-data.md`](downscaled-data.md) and
[`hi-res-map-pipeline.md`](hi-res-map-pipeline.md) — carry no dates and no status, on purpose.

## Contents

- [Status](#status)
- [Decision log](#decision-log)
- [Verified results](#verified-results)
- [Open questions for Carlos](#open-questions-for-carlos)
- [Still to do](#still-to-do)
- [The database schema (Phase 3)](#the-database-schema-phase-3)
- [Project background](#project-background)
- [Source material](#source-material)

## Status

Everything below runs on the `feat-hi-res-maps-experiment` branch, under its own Mapbox id
namespace. **Production is untouched.**

| Phase | What it is | Where it stands |
|---|---|---|
| **1 — get the maps up** | build `.geojsonld` straight from the warming-level Zarr for all 28 indicators, publish tilesets and styles to a new namespace, swipe against the live map | Shipped. `hires-maps build` / `build-all`. |
| **2 — make the low zooms fit** | the three-rung resolution pyramid, `p08` z0–1 / `p02` z2–3 / native z4–5, wired into the uploader behind `--hi-res` | Shipped. `hires-maps pyramid`, `create-tilesets -- <id> --hi-res`. Re-publish verification still outstanding. |
| **3 — turn on the database** | settle the schema, flip `--write-db` on, reconcile with the app's point-value / download / API consumers | Not started. The writer exists and is tested but persists nothing. |

Alongside the phases, six more map families are built. Every command for all seven is collected in
[`commands.md`](commands.md); this table is only where each one stands.

| Family | What a cell means | Where it stands |
|---|---|---|
| `diff` | v4 − v3 — *did the numbers move* | Shipped. The **detail** diff only; the model diff is not built. |
| `era5` | ERA5's own observed values | Shipped, for all 24 indicators with an ERA5 file. |
| `era5v3` | v3 − ERA5 — *how wrong is what we publish today* | Shipped. 23 buildable, 22 publishable — 40607 has no `diffMap`. |
| `era5v4` | v4 − ERA5 — *is the new data closer to reality* | Shipped. 23 buildable and all 23 publishable. |
| `abs` / `v3abs` | a change map republished as absolute, so it can sit beside ERA5 | Built for the change indicators. Absolute stops are in `configs.ts`; the matching `pf_maps` rows are not written yet. |

The two ERA5 comparisons are the pair that answers the migration question — see
[Verified results](#verified-results).

## Decision log

### Build straight from Zarr to GeoJSON, skipping netCDF and the database

A map needs only square polygons plus the warming-level values, and the Zarr already holds exactly
that. Going through the netCDF import and a PostGIS round-trip would add two hops that change
nothing about the output. The load-bearing consequence is sequencing: with the database off the
critical path for tiles, the maps can be built and reviewed now, and the schema questions the
bigger data raises can be settled later without blocking anything.

### Precompute the coarse rungs; do not use Mapbox `union`

MTS recipes can aggregate features at publish time (a `union` block with `group_by` and
per-attribute `mean`), which would keep one source instead of three. That was the original
recommendation, on the grounds of fewer sources to maintain. It was reversed once `hires-maps`
existed: generating the coarse rungs became nearly free, because it reuses the arrays and the
feature writer already in the builder — which removed `union`'s main advantage.

| Aspect | `union` (MTS-side) | Precompute (what we ship) |
|---|---|---|
| Datasets to maintain | **1** | one per rung |
| Who averages | Mapbox, on every publish | us, once, offline |
| Publish time | slower — merges millions of features every publish | faster |
| Inspect low-zoom values offline | no | yes |
| Custom aggregation (area-weighted, model-native) | built-in methods only | full control |

The last row decided it in practice: we use an **area-weighted (cos-lat)** mean, which MTS's plain
`mean` cannot express. `union` remains viable if we ever need to cut the number of sources.

### No 0.4° rung: the coarsest rung starts at z0

A tileset pinned to `minzoom: 1, maxzoom: 1` — which is what a `p04`-only rung would be — fails
Mapbox's post-publish metadata validation with *"center zoom value must be greater than or equal to
minzoom 1"*, because the centre zoom Mapbox derives sits below that minzoom. Letting the coarsest
rung start at zoom 0 and cover z0–1 avoids the problem entirely. Nothing visible is lost: at z1 a
0.8° cell is about 2 px, so it is indistinguishable from 0.4°. Bonus: three rungs instead of four
means six tilesets instead of eight — fewer publishes and less rate-limiting.

`hires-maps pyramid` no longer generates a `-p04` file, though `--factor 4` still works if someone
wants a 0.4° build by hand.

### Serve every zoom, z0 to z5

Production stops at `minzoom: 2` — z0 and z1 were never served. The new maps extend down to
`minzoom: 0` so the map works at every zoom, including embeds and downloads. That is what makes the
coarse rungs necessary rather than optional. `maxzoom` stays 5.

### `maxzoom` stays at 5

Under Mapbox's legacy pricing, tilesets with `maxzoom < 6` are free, so raising it can quietly start
billing the account. Overzoom means nothing is lost: clients scale z5 tiles for deeper zooms and our
square cells scale perfectly. This is the most reusable rule in this folder and applies to every
tileset the repo publishes, not just the hi-res ones.

### Publish under a new id namespace

Hi-res and comparison tilesets and styles get their own ids on the same `probablefutures` account,
so a build can never overwrite a live production tileset. MapBuilder points a dev/staging dataset
entry at the new style.

### Headline value: mean for heat and drought, median for precipitation and water

`mid` is the `mean` for the heat maps **and the two drought maps** (40701, 40702), and `p50` for
precipitation, snowy days and water balance. This is not a fresh judgement — it mirrors
`use_mean_for_mid` in `netcdfs/import/conf.yaml`, so the new maps make the same choice the live maps
already make. `low` is always `p5` and `high` always `p95`.

### Change maps derive the change rather than reading `diff_*`

Every store ships a precomputed `diff_*` variable, and we do not use it. Two reasons: it is all-NaN
at the 0.5 °C baseline level, which would break the land mask; and water balance has to be
differenced *after* its percentile→z-score transform, not before. Verified equivalent on 1.2 M
sampled values — 8 differ, all by 0.1, all at float32 rounding boundaries.

### The comparison's "old" half is the published GeoJSON, not the source netCDF

`data/mapbox/mts/old-geojson/` holds all the live maps as `.geojsonld`, so the comparison is against
the numbers users actually see on probablefutures.org, and it needs no `rclone` sync. The netCDFs
would have worked for a handful of indicators at most: only `days-above-35c` was ever on disk, and
`data/woodwell/water_module/` is empty.

### Comparison values keep one decimal; map values truncate to integers

The maps themselves reproduce `stat_fmt` exactly — integers truncated toward zero — because every
published map today holds truncated integers, and rounding instead would make the new tiles disagree
with the old by up to a full unit in every popup and CSV. Comparison maps break that parity
deliberately: a real +0.7 °C disagreement truncated to 0 would make the map claim the two datasets
agree, which is the one thing a comparison map must never do.

### Comparison builds keep the absolute baseline

Live change maps put the *absolute* baseline in the 0.5 °C slot while the other levels hold changes
— 40601's export has a median `data_baseline_mid` of 727 mm next to a median `data_1c_mid` of
+12 mm. Comparison builds
therefore keep our absolute baseline too, so that slot compares absolute against absolute and every
other slot compares change against change. (Our own hi-res change maps zero the baseline instead,
matching what the live SQL forces; the app never paints that layer.)

### Comparison maps use a diverging red/blue ramp

A difference map is signed around a meaningful zero — zero means the two datasets agree — so it
needs a diverging ramp rather than the sequential climate ramps. The specific hex values and the
three rules the palette follows live with the palette itself, in `vector-tiles/configs.ts`
(`DIFF_COLORS` / `DIFF_STOPS`), because the argument is about those values and must not drift from
them.

**The first version of this palette got it wrong, and the way it failed is the reason the rules are
written down.** It was assembled on the principle that every hex should be one already used
elsewhere in `configs.ts`, so that comparison maps would sit in the same visual family as the rest.
The hexes came from the precipitation ramp (40601) and the drought ramp (40701), and the published
40105 comparison map was consequently indistinguishable from an ordinary PF climate map: teal on one
side and orange on the other rather than blue against red, with the darkest colour of all
(`#515866`) sitting in the middle, so *agreement* — the reading a comparison map should let you skip
over — dominated the view. Visual consistency with the climate maps is the opposite of what this map
needs. A comparison map answers a different question and must look like it does.

## Verified results

**The new data runs cooler than the live maps at every warming level.** Area-weighted land means for
`days-above-35c`:

| Warming level | New (0.1°) | Old / live (0.2°) |
|---|---|---|
| 0.5 (baseline) | 27.7 days | 35.9 days |
| 1.5 | 34.4 days | 48.2 days |
| 2.0 | 38.9 days | 51.8 days |
| 3.0 | 50.3 days | 64.3 days |

This matches what earlier inspection showed — the old maps ran too hot in places like the Congo
rainforest — and it is corroborated by the ERA5-Land validation, where the new data's land-mean
temperature bias against observations is **+0.008 °C**. It is worth showing the client, because it
changes the maps visibly.

**The comparison pipeline is exact where it can be checked.** Cross-checked end to end on 40105, the
one indicator with two independent sources of live values: the GeoJSON-derived live array equals
`trunc(netCDF)` for all 425,553 cells at every warming level; the emitted diffs are exact on all
74,643 cells that coincide with a live centre; and the area-weighted mean difference is negative at
every level (−13.0 / −20.5 / −21.9 days at 0.5 / 1.5 / 3.0 °C) — the expected direction.

**The grids are centre-aligned.** Every live 0.2° cell centre falls exactly on a new 0.1° cell
centre, verified against both the netCDF coordinates and the published polygons: max error 2.8e-14,
and 0 of 20,000 sampled polygon centres off-grid. This is why the comparison needs no interpolation
machinery at all.

## Open questions for Carlos

None of these block the build.

- **`ten-hottest-wbmax-days` has five warming levels, not six.** Every other store has all six. Is
  one missing, or is that deliberate?
- **A one-line sign-off on the headline statistic** — `mean` for heat, median for precipitation and
  water — being right for this data too, not just for the current maps. (Units are already settled
  from `conf.yaml`.)
- **Confirm the coarsening rule.** We use an area-weighted mean for the coarse rungs. Mean is the
  natural default for continuous values, but max (worst-case bands) is a defensible product choice
  and is a data-semantics call, not an engineering one.
- **The raw SPEI field for water balance.** We invert the percentile with `Phi^-1` and have to clamp
  the percentiles of exactly 0, where the inverse is infinite. Being handed the raw SPEI field would
  remove the clamp entirely.

Separately, **re-confirm the `maxzoom ≤ 5` pricing rule with Mapbox support** before any real
publish at scale. It is confirmed true today, and it is the constraint with a direct cost attached.

## Still to do

- **Re-publish hi-res 40105 and read the new `W201` report.** Expect no drops at any zoom. If z0
  still overflows for a big landmass, add a coarser 1.6° (`p16`) rung; if z0 is comfortable, z0–1
  could merge onto a finer rung.
- **Re-create 40105's comparison *style*.** The tilesets are published and the data is good, but
  they were styled with the first (wrong) `DIFF_COLORS`. Re-run
  `npm run create-tilesets -- 40105 --diff --publish-only` to pick up the corrected palette without
  re-uploading the sources, then repoint the dev/staging `mapStyleId` at the new style id.
- **Check the comparison map's *legend*, not its fill.** The published 40105 comparison map rendered
  `DIFF_COLORS` faithfully, so the Mapbox style drives the fill and no `pf_public.pf_maps` change is
  needed for the map itself. The legend is the open question: the style bakes in
  `["get", "data_1c_mid"]` while the app offers six warming levels, so the app holds its own copy of
  `stops` / `bin_hex_colors` from `pf_maps` — and 40105's row still carries the climate ramp
  `[1, 8, 31, 91, 181]`. If the sidebar legend shows those numbers rather than −20…+20, that row
  needs the diff values. `types.ts` already declares an `isDiff` field mirroring a DB `is_diff`
  column, but nothing in this repo reads it.
- **Build the model diff** — aggregate the new data back to 0.2° before subtracting, which separates
  "the model moved" from "the resolution changed".
- **Tune styles, colours, and the change-versus-absolute handling** for the precipitation and
  drought maps.
- **Lower the app's `MIN_ZOOM`** (currently 2.2 in `mapConsts.ts`) when we want the z0/z1 rung
  visible in MapBuilder.
- **Consider a rendered-pixel regression**: snapshot fixed cameras via the Static Images API for
  both styles and run `pixelmatch` on the PNGs. It would have caught the original low-zoom
  corruption without anyone eyeballing Studio.

## The database schema (Phase 3)

The writer is built and tested but persists nothing, because the 4×-bigger data forces three
decisions that should not be rushed:

- **A new grid.** The 0.1° grid is a new set of ~2.21 M coordinates, each with its own square `cell`
  polygon. It has to be registered alongside the existing 0.2° grid, which the live maps keep using.
- **Volume.** ≈2.21 M cells × 6 warming levels ≈ **13.3 M rows per map**, × 28 maps ≈ **372 M rows**
  — roughly an order of magnitude above today's statistics table. That forces choices on
  partitioning (likely by dataset), indexing, and bulk loading (COPY / pgloader rather than
  row-by-row inserts).
- **Which statistics to store.** The new data has six (`min`, `p5`, `p50`, `p95`, `max`, `mean`);
  today's columns are `low`/`mid`/`high` plus `mean`/`median`. We map `p5→low`, `p95→high`,
  `mean`-or-`p50`→`mid` — do we also keep `min` and `max`, or drop them?

## Project background

Distilled from the meetings; the dated minutes are in
[`history/2026-downscaling-meetings.md`](history/2026-downscaling-meetings.md).

**Apr 7, 2026 — the project was scoped and approved.** Probable Futures and Woodwell agreed to run a
statistical downscaling experiment on **one CMIP6 model** — the **MPI** model, chosen because both
ISIMIP and REMO already use it — covering **all 30 Probable Futures maps** (heat, precipitation,
drought, fire). Target resolution **9–11 km**, roughly halving the existing 22 km maps, on the
grounds that it is becoming a norm and there is material gain in precision. Compute was estimated at
**~$3,000 for the downscaling plus ~$372 to recalculate all maps**, run on **Woodwell's own Google
Cloud account** because the code already lives there. Carlos at three days a week, about **12 weeks
from April 20, 2026**.

The purpose was explicitly **internal evaluation first**: digitize the maps, use them internally,
compare them against the dynamical maps — including how each represents tipping points and other
nonlinearities — and only then decide whether to publish them or use them externally. That framing
is why everything in this repo publishes to a separate namespace and stays off production.

**Jul 22, 2026 — the analysis wish list.** Carlos, Richard, Moustafa and Peter listed what they
wanted to be able to do with the new data: compare against observational data, compare projections
against projections (old maps versus new maps), compare the raw variables directly, histograms at a
single location, and difference maps. Two items from that list are the direct provenance of shipped
decisions:

- *"Difference maps: blue and red for higher and lower"* → the diverging comparison-map ramp.
- *"Regrid with nearest neighbor — using the grid of the new maps, which is higher res"* → the
  detail diff, computed on the 0.1° grid rather than by downsampling the new data to meet the old.
- *"Compare against observational data"* → the ERA5 families, once Carlos supplied ERA5.

## Source material

- [`history/2026-downscaling-meetings.md`](history/2026-downscaling-meetings.md) — the dated minutes
  from April and July 2026, cleaned of export artifacts. Append-only; distil into this file rather
  than editing them.
- [`charting-modeled-weather-ranges.pdf`](charting-modeled-weather-ranges.pdf) — a 5-page,
  image-only Probable Futures brief on charting the modeled range (p5/p95), delivered alongside the
  April/July 2026 material. It has no text layer, so it is not searchable and nothing here quotes
  it. No part of the pipeline depends on it. It most likely relates to the Factbook "Likelihood
  chart" described in [`../DATA.md`](../DATA.md).
