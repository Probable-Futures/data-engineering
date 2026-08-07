# High-Resolution Climate Tiles — Research & Experiment Notes

Status: **experiment / research** (branch `feat-hi-res-maps-experiment`). Nothing here is in production yet.

This document captures everything we currently know about moving the climate map data
from a **0.2° grid** to a **0.1° grid** (4× more cells): why the naive approach breaks,
what we already tried, what the fix is, and the pricing constraints to respect.

---

## 1. Background — what tiles are (read this first if you're new)

A web map isn't one giant image. It's a **pyramid of small square tiles**, 512×512 each.
The whole world fits in a few tiles at low zoom, and each time you zoom in by one level,
every tile splits into 4:

| Zoom | Tiles across the world | Degrees of longitude per tile (at equator) |
|------|------------------------|---------------------------------------------|
| 0    | 1 × 1 = 1              | 360°                                        |
| 2    | 4 × 4 = 16            | 90°                                         |
| 3    | 8 × 8 = 64            | 45°                                         |
| 4    | 16 × 16 = 256         | 22.5°                                       |
| 5    | 32 × 32 = 1024        | 11.25°                                      |

Key idea: **the number of tiles at a zoom level is fixed by the zoom, not by our data.**
When you zoom in, you don't get more data crammed into a tile — you get *more tiles, each
covering a smaller area*. So higher-resolution data doesn't add tiles; it adds **more
features inside each low-zoom tile**.

**Vector tiles** (what we use, via Mapbox) contain actual geometry — our climate grid is
a set of little square polygons, one per grid cell, each carrying climate values
(`data_1c_mid`, `data_2c_mid`, …) as properties.

### The size limit that causes all our problems

Mapbox Tiling Service (MTS) enforces a **maximum size per layer, per tile**:

- Default limit: **1250 KB**
- Absolute maximum: **2500 KB** (we already use this everywhere — see §4)

If a layer's data in a given tile exceeds that limit, **MTS silently drops features** to
fit, and emits a **`W201` warning** in the publish job report. That warning includes a
`capped_list` telling you *exactly* which layer, which zoom levels, and which tiles were
too big — and the `layer_size` that *would* have been needed. This is our primary
diagnostic tool.

Because a low-zoom tile covers a huge area, it must hold *every* grid cell in that area.
That's where a 4× denser grid hits the wall.

---

## 2. The problem

We want to serve 0.1° climate data (used when higher-detail source data becomes
available). The 0.1° grid has **~4× the cells** of the current 0.2° grid
(~425K features → ~1.7M features for dataset `40105`).

Observed symptom in the experiment: **maps render fine at zoom ≥ 4, but are corrupted /
missing data below zoom 4.** This is exactly the size-limit behavior above — low-zoom
tiles can't hold all the cells, so features get dropped.

---

## 3. Why it breaks at low zoom — the math

A tile at zoom `z` spans `360 / 2^z` degrees of longitude. The worst-case number of
0.1° cells packed into one tile near the equator:

| Zoom | Max 0.1° cells / tile | Fits in a 2500 KB layer? (~80–150 B/feature) |
|------|-----------------------|-----------------------------------------------|
| 3    | ~200,000              | **No** — ~10× over the limit                  |
| 4    | ~50,000               | Borderline / over, even split in half         |
| 5    | ~12,600               | Yes, comfortably                              |
| 6    | ~3,200                | Yes, trivially                                |

So:
- **z5 and up** can serve native 0.1° data as-is.
- **z4** is the fight-it-or-aggregate boundary.
- **z0–z3** *must* use aggregated (coarser) data.

> ⚠️ Treat these numbers as **order-of-magnitude**, not exact. Our layers are already
> narrow latitude bands (see §4), so a single layer only occupies its band within a big
> low-zoom tile — real per-layer counts are lower than the full-tile figure. **Don't guess
> the exact cutover zoom — read the `W201 capped_list` from an actual publish job.**

### What resolution each zoom actually needs (the ladder)

We want the map usable at **every** zoom (z0–z5), so for each zoom we pick the *coarsest*
resolution that still looks sharp. Rule of thumb: a grid cell should be at least ~1 pixel —
anything finer is invisible detail *and* wasted bytes that blow the tile budget. On a 512px
tile:

| Zoom | Tile span (equator) | Degrees / pixel | Sensible resolution | Grid level |
|------|---------------------|-----------------|---------------------|------------|
| 0    | 360°                | 0.70°           | 0.8°                | `p08`      |
| 1    | 180°                | 0.35°           | 0.4°                | `p04`      |
| 2    | 90°                 | 0.18°           | 0.2°                | `p02`      |
| 3    | 45°                 | 0.088°          | 0.2° (0.1° also ok) | `p02`      |
| 4    | 22.5°               | 0.044°          | 0.1°                | `cell`     |
| 5    | 11.25°              | 0.022°          | 0.1° (native)       | `cell`     |

The **Grid level** column is the ladder the pyramid is built from (§6/§7). This is why
aggregating at low zoom loses nothing visually: at z4 a 0.1° cell is already only ~2 px,
and at z0 it would be ~1/32 of a pixel — completely invisible, while carrying ~16× more
data than the tile can hold. Serving `p08`/`p04`/`p02` at those zooms looks identical to
the eye and actually fits.

> ### ✅ What was actually implemented (this table is the original theory)
>
> The ladder we shipped has **three** rungs, not four — there is **no `p04`**:
>
> | Zoom | Rung served |
> |------|-------------|
> | 0–1  | 0.8° (`p08`) |
> | 2–3  | 0.2° (`p02`) |
> | 4–5  | 0.1° (native) |
>
> Two reasons. **(1)** A tileset pinned to `minzoom: 1, maxzoom: 1` (a `p04`-only rung) fails
> Mapbox's post-publish metadata check — *"center zoom value must be greater than or equal to
> minzoom 1"* — so the coarsest rung has to start at zoom 0. **(2)** At z1 a 0.8° cell is ~2 px,
> so dropping 0.4° there is visually irrelevant, and 0.8° is much safer against the z0 tile budget.
> See [warming-levels-data-and-next-steps.md](warming-levels-data-and-next-steps.md) §8 Phase 2.

---

## 4. Current production setup (what we're working from)

Every layer in `templates/east.recipe.json`, `west.recipe.json`, and `world.recipe.json`
(25 layers total) is already configured identically:

| Setting            | Value      | Meaning                                             |
|--------------------|------------|-----------------------------------------------------|
| `minzoom`          | **2**      | Lowest zoom generated (z0–1 not served today)       |
| `maxzoom`          | **5**      | Highest zoom generated (higher zooms *overzoom*)    |
| `tiles.layer_size` | **2500**   | Already at the absolute maximum                     |

Two consequences that shape everything below:

1. **`layer_size` is already maxed out.** There is no byte-budget lever left to pull —
   raising the size limit is not an option, because we're already at 2500 KB.
2. **The layers are already latitude bands.** Each region (`region_eu_af_6`, etc.) has a
   bbox covering a slice of latitude. This already helps keep low-zoom tiles smaller.

> **Design decision for hi-res:** current production stops at `minzoom: 2` (z0–1 were never
> served). For the new flexible maps we **will** extend down to **`minzoom: 0`** so the map
> works at every zoom. That makes the coarser rungs of the ladder (§3) — `p04` at z1 and
> `p08` at z0 — necessary, not optional.

**Overzoom:** `maxzoom: 5` does *not* limit how far users can zoom in. Clients "overzoom"
by scaling the z5 tiles, and our square grid cells scale perfectly. So maxzoom 5 gives a
fully usable map at any zoom.

---

## 5. What was tried in this branch

Three new files implement a stress-test using **synthetic** 0.1° data (we fabricated it
by subdividing the existing 0.2° grid, so we could test the pipeline before real
high-res data exists).

- **`scripts/generate_hires_test.py`** — reads the existing `40105.geojsonld` (0.2° grid,
  ~425K features) and splits every square into 4× 0.1° squares with the *same* property
  values. Output: ~1.7M features (~830 MB), file `40105-hires-test.geojsonld`.

- **`scripts/upload_hires_test.ts`** — uploads that file to Mapbox as tilesets. Its key
  trick (`splitLayer`) **splits each layer's bbox in half by latitude** into `_a`/`_b`
  sub-layers, on top of the existing regional banding, to shrink each layer's per-tile
  payload. It groups layers into 3 tilesets (`east1`/eu_af, `east2`/as_oc, `west`/na_sa),
  validates recipes, creates, and publishes them.

- **`templates/test-40105-style.json`** — a Mapbox GL style pointing its `composite`
  source at the three test tilesets, used to visually inspect the result in Studio.

**Result / key finding:** the corruption at low zoom happened **even with every
size-saving lever already applied** — max `layer_size` (2500), regional latitude bands,
*and* the extra `_a`/`_b` split. This is the decisive evidence: if 0.1° still overflows
low-zoom tiles after all that, the *only* remaining fix is **fewer features** at those
zooms, i.e. aggregation. It confirmed the failure mode is real and well-understood, not a
misconfiguration.

---

## 6. Recommended fix — a resolution pyramid

### The idea in plain terms (applies to both §6 and §7)

Both fixes solve the same thing — "too many 0.1° squares to fit in a zoomed-out tile" —
the same way: **show fewer, bigger squares when zoomed out.** When you're zoomed out you
can't even see individual 0.1° cells (each is ~2 px or smaller), so there's no point
sending them. Instead, replace each block of 4 cells with 1 bigger cell whose value is the
**average** of the four. It looks identical to the eye but is 4× cheaper:

```text
Zoomed IN (z5+): keep detail        Zoomed OUT (z2-3): merge to 1
┌─────┬─────┐                       ┌───────────┐
│ 12  │ 14  │                       │           │
├─────┼─────┤   →  average = 13  →  │    13     │
│ 13  │ 13  │                       │           │
└─────┴─────┘                       └───────────┘
4 cells, 4 values                   1 cell, 1 value
```

That averaging step is what "aggregation" means. §6 and §7 are just two ways to make it
happen — the only difference is **who does the averaging and when**:

- **§6 (pyramid):** *we* pre-build the coarse dataset ourselves; Mapbox just serves it.
- **§7 (`union`):** *Mapbox* builds the coarse data automatically from one dataset.

### How the pyramid works

Serve coarse data at low zoom and fine data at high zoom by handing Mapbox **one dataset
per rung of the ladder** (§3), each as its own layer with its own `minzoom`/`maxzoom`:

| Dataset             | Resolution | Used at zooms | Shipped? |
|---------------------|------------|---------------|----------|
| `region_*_p08`      | 0.8°       | z0–z1         | ✅ yes   |
| `region_*_p04`      | 0.4°       | z1            | ❌ dropped — see the note in §3 |
| `region_*_p02`      | 0.2°       | z2–z3         | ✅ yes   |
| `region_*_hires`    | 0.1°       | z4–z5         | ✅ yes (native) |

As the user zooms in, the map automatically swaps to the next-finer layer. It's a
"pyramid" because it's layers of increasing detail stacked by zoom. We create each coarse
dataset ourselves with a script (the averaging shown above, done in Python, in advance) —
each is a straight 4→1 (or 2→1) mean of the level below it.

The exact cutover zooms should be confirmed from the **`W201 capped_list`** of a real
publish, not guessed. Our existing `_a`/`_b` latitude split may be enough to squeeze native
0.1° down into z4; if the report says otherwise, adjust a boundary.

> **Downside of the precompute pyramid:** covering z0–z5 well means **~4 datasets/sources
> to generate and keep in sync**, not two. That maintenance cost is the main argument for
> letting Mapbox do it instead (§7).

Keep the pyramid within `minzoom: 2` — z0–1 aren't served today, so don't build for them.

### Aggregation semantics — a decision for the data owner

"Combine 4 cells into 1" needs a rule per property:
- **Mean** — the natural default for continuous values (temperature, days-above-threshold).
- **Max** — if the product wants worst-case bands.
- **Mode** — for any categorical property.

This is a data-semantics call, worth a one-line confirmation from the data owner (Carlos /
the client) before building.

---

## 7. Alternative — MTS built-in feature aggregation (`union`)

We may not need to precompute a separate 0.2° source in Python at all. The recipe layer
type already supports a `union` block (see `types.ts`):

```ts
interface RecipeUnion {
  where?: Expression;
  group_by?: string[];
  aggregate?: Record<string, string>;   // MTS-native aggregation
  maintain_direction?: boolean;
  simplification?: RecipeSimplification;
}
```

MTS `union` can merge features over a zoom range and **aggregate their attributes**
(methods: `sum`, `product`, `min`, `max`, `mean`) directly in the recipe — which maps
exactly onto the mean/max decision in §6. Confirmed against `types.ts`: `tiles.union` is an
array (line 122), and `features.attributes.set` (line 111) lets us compute a
**zoom-dependent grouping key**.

### How it maps to our grid

`union` merges features that share a `group_by` value. Our grid cells all have *different*
climate values, so we can't group on those — instead, when generating the 0.1° GeoJSON, we
**stamp each cell with its parent-block IDs at every ladder rung** (§3; all trivial to
compute):

- `cell_id` — the 0.1° cell itself, e.g. `floor(lon/0.1)_floor(lat/0.1)`
- `p02` — the 0.2° parent block, `floor(lon/0.2)_floor(lat/0.2)`
- `p04` — the 0.4° block, `floor(lon/0.4)_floor(lat/0.4)`
- `p08` — the 0.8° block, `floor(lon/0.8)_floor(lat/0.8)`

Then one recipe does everything, via a zoom-dependent `union_key` that picks the rung for
each zoom: at z5/z4 every cell keeps its own `cell_id` (nothing merges → native 0.1°); as
you zoom out, cells collapse onto progressively coarser shared blocks (`p02` → `p04` →
`p08`), each an averaged square.

```jsonc
{
  "source": "mapbox://tileset-source/probablefutures/40105-hires-01",
  "minzoom": 0,
  "maxzoom": 5,
  "features": {
    "attributes": {
      "set": {
        // ladder from §3: z0->0.8°, z1->0.4°, z2-3->0.2°, z4-5->native 0.1°
        "union_key": ["case",
          ["<=", ["zoom"], 0], ["get", "p08"],
          ["<=", ["zoom"], 1], ["get", "p04"],
          ["<=", ["zoom"], 3], ["get", "p02"],
          ["get", "cell_id"]
        ]
      },
      "allowed_output": ["data_1c_mid", "data_1c_low", "..."]
    }
  },
  "tiles": {
    "layer_size": 2500,
    "union": [{
      "group_by": ["union_key"],
      "aggregate": {
        // one entry PER continuous attribute (~35 of them), all "mean"
        "data_1c_mid": "mean", "data_1c_low": "mean", "data_1c_high": "mean"
        // ... data_baseline_*, data_1_5c_*, data_2c_*, data_2_5c_*, data_3c_*
      },
      "simplification": { "distance": 1, "outward_only": false }
    }]
  }
}
```

The `outward_only` trick avoids sliver gaps between merged squares (adjacent polygons are
made to slightly overlap pre-union so they dissolve cleanly). Note our `RecipeSimplification`
type requires `distance` alongside `outward_only` (`types.ts` line 92).

### Project-specific notes (things Fable's generic example missed)

- **`minzoom: 0`** — unlike production (z2), we serve every zoom (see §4 decision), so the
  `union_key` needs the full ladder including `p04` (z1) and `p08` (z0).
- **z0 is one tile for the whole world**, so even 0.4° can overflow there — that's why the
  ladder drops to 0.8° (`p08`) at z0. If the `W201 capped_list` shows z0 still overflows
  for a large region, add a coarser `p16` (1.6°) rung; if z0 comfortably fits at 0.4°, you
  can drop `p08` and merge z0–1 onto `p04`. Confirm from the report, don't guess.
- **`aggregate` must list all ~35 output attributes**, not just three. Every attribute in
  `allowed_output` that isn't given a method is dropped after union. Since all our values
  are continuous, it's `mean` for every one — the "no `mode` for categoricals" limitation
  doesn't affect us.
- **The `union` block must be templated onto every layer** (all 25 regional layers, or the
  `_a`/`_b` test layers) — exactly like `layer_size: 2500` already is.
- **Feature IDs change after union**, but our styles read values via `["get", "..."]`
  property expressions, not feature-state by ID, so this is low-risk for us.

### Tradeoffs vs. the §6 precompute

| Aspect | `union` (§7) | Python precompute (§6) |
| --- | --- | --- |
| Datasets to maintain | **1** | ~4 (one per ladder rung) |
| Who averages | Mapbox, per publish | us, once, offline |
| Publish time | Slower (merges ~1.7M features every publish) | Faster |
| Inspect low-zoom values offline | No | Yes |
| Custom aggregation (area-weighted, model-native) | Built-in methods only | Full control |

**Original recommendation:** try `union` first — one recipe change, one source of truth, simpler
ops; keep the Python precompute (§6) as the fallback.

> ### ✅ Decision: we shipped the §6 precompute, not `union`
>
> Once the `hires-maps` package existed, generating the coarse rungs became nearly free — it
> reuses the arrays and feature-writer already in the builder — which removed `union`'s main
> advantage (fewer sources to maintain). The precompute also wins on the things we care about
> here: **publishes stay fast** (no merging ~2.2 M features on every publish), the low-zoom
> values are **inspectable offline**, and we control the maths — we use an **area-weighted**
> (cos-lat) mean rather than MTS's plain `mean`.
>
> `union` remains a viable alternative if we ever want to cut the number of sources.

---

## 8. Pricing constraint — keep `maxzoom` ≤ 5

**Confirmed true:** under Mapbox's legacy pricing, tilesets with **`maxzoom < 6` are
free.** Bumping the recipe `maxzoom` to 6+ can quietly start billing the account.

This is why every production recipe pins `maxzoom: 5` — and thanks to overzoom (§4), that
still gives a fully usable map at any zoom. **Do not raise `maxzoom` to 6+ for the hi-res
data.** Fit the resolution pyramid entirely within `maxzoom: 5`.

---

## 9. Comparing old vs new maps (analysis tooling)

Because the grids differ by 4×, there are really **two different comparison questions**:

1. **"What detail did we gain?"** — diff at 0.1°: for each new cell,
   `new_value − old_parent_0.2°_value` (nearest-neighbor upsample of the old grid). Render
   with a diverging color ramp. Highlights coastlines, mountains, urban areas where finer
   resolution changes the picture.
2. **"Did the underlying model change?"** — aggregate the new data back to 0.2° and diff
   against the old grid at matched resolution. Near-zero everywhere ⇒ pure refinement;
   hotspots ⇒ the values themselves moved. This separates *resolution* effects from *data*
   changes (the classic trap when comparing mismatched grids).

Both diffs are just GeoJSON with a `diff` property, so they flow through the existing
pipeline with a diverging style ramp instead of the climate ramp.

Supporting tools:
- **Swipe comparison** — `mapbox-gl-compare` slider between old and new styles in one HTML
  page. Most persuasive artifact for a client meeting.
- **Stats notebook (Python, off-Mapbox)** — histograms of diffs, per-latitude-band and
  per-scenario summaries, old-vs-new scatter, ranked largest-divergence regions. Catches
  systematic bias a map can hide (e.g. "new data runs 0.5 days hotter everywhere").
- **Rendered-pixel regression** — snapshot fixed cameras via the Static Images API for
  both styles and run `pixelmatch` on the PNGs. Automated check that a re-publish didn't
  silently drop features again (would have caught the low-zoom corruption without eyeballing
  Studio).

---

## 10. Suggested next steps

1. Update `generate_hires_test.py` to stamp each cell with its ladder IDs (`cell_id`,
   `p02`, `p04`, `p08` — see §7), then re-publish the hi-res test with the single-source
   **`union` recipe** (`minzoom: 0`, `maxzoom: 5`, `layer_size: 2500`) and confirm the
   corruption across z0–z3 disappears — de-risks the whole approach with fake data before
   real data is invested.
2. Pull the publish job reports and **save the `W201 capped_list` numbers** — that's the
   evidence-based answer to which exact zoom each ladder rung should cover (e.g. whether z0
   needs `p08` or a coarser `p16`).
3. **Confirm with the data owner**: aggregation function (mean?), and re-confirm the
   `maxzoom ≤ 5` pricing constraint with Mapbox support before real data arrives.
4. **Spike the `union` approach** (§7) against the precompute approach and see which one
   the `capped_list` clears.
5. Build the 0.1° diff prototype (§9) against the existing `40105` data to validate the
   comparison tooling end-to-end.
