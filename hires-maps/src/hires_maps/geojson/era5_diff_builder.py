"""Build the **ERA5 comparison maps**: our data minus what was actually observed.

`diff_builder.py` answers "did the numbers move" (v4 against v3). Both sides of that are model
output, so it can only ever say the two disagree — never which one is closer to reality. This
module answers the question that one cannot, in two directions:

    build_era5_v3_diff    v3 - ERA5, on the live 0.2° grid, one rung
                          "how wrong is the map on probablefutures.org today?"

    build_era5_v4_diff    v4 - ERA5, on the new 0.1° grid, three rungs
                          "is the new data closer to reality than the old data?"

In both, positive (red) means **we** read HIGHER than the observations — the same sign convention
as `diff_builder`, where red means the first-named dataset is higher, so a colour never means two
different things across the comparison families.

Run both and the pair answers the migration question with a number rather than an assertion: on
`days-above-35c` the area-weighted mean absolute bias is 3.26 days for v4 against 13.66 for v3, and
v4's signed bias is -0.50 where v3's is +9.95. (Measured on the full grids; put both on a common
grid before quoting the ratio, since v3 covers less of the globe.)

## The grid: ours, with ERA5 replicated onto it

ERA5 is 0.25° and v3 is 0.2°, so the two never share a cell. The comparison is built on the grid of
**the dataset being judged** — v3 — with ERA5 looked up per cell by
`era5.parent_index` / `era5.upsample`, exactly the way `diff_builder` treats the live side.

Building on 0.1° instead would invent detail neither dataset has and quadruple every file for
nothing: `0.25 / 0.2` is not an integer, so ERA5 arrives as blocks 1-2 v3 cells per side and the
block sizes alternate. That is the honest picture of a 0.25° yardstick, not an artifact.

The alternative — aggregating v3 *up* onto ERA5's 0.25° grid with area weights — is a legitimate
method and was measured rather than dismissed: on `days-above-35c` it returns the same
area-weighted global bias to two decimals (+9.95 days either way), because the two differ only by
`leak x local ERA5 gradient`, where `leak` is the share of a cell drawn from v3 cells whose nearest
ERA5 parent is a neighbour. That is 0 for a quarter of the grid and small wherever ERA5 is smooth.
It moves individual cells at sharp edges (8.4% of cells by more than 2 days), so it is the better
choice for a **quoted** land-mean — nearest-neighbour reuses 360 of ERA5's 1440 columns twice, and
averaging the result would count those cells twice — but not for the rendered map, which wants v3's
detail intact.

## Change maps: opposite fixes on the two sides

The live v3 exports for 40601/40607/40613/40614/40616 publish an *absolute* baseline alongside
*changes* at every other level, so the v3 path calls `stages.from_change` to put them back into
absolutes. The v4 stores hold absolute values natively (checked: 40601's baseline median is 387 mm,
not a small delta), so the v4 path calls **nothing** — it simply never runs `to_change`. Either way
both sides of the subtraction end up absolute, which is also why no unit transform is involved.

ERA5 itself is absolute at both levels and is never converted; see `era5_builder.py` for why we do
not manufacture a change from a single observed record.

## Precision

`DIFF_DECIMALS` places for every unit, in both directions — but for different reasons, so do not
copy the reasoning between them. On the v3 side the live values are already integer-truncated, so
truncating the difference *again* would turn a real +0.7 day bias into 0 and paint the map as
agreement. On the v4 side neither the Zarr nor the netCDF is truncated at all, so the sub-integer
signal is genuine rather than a rounding artifact. Same decision, opposite argument.

## Rungs

v3 gets **one rung**: 0.2°, ~425k cells, the resolution production has always served at z2-5 as a
single tileset. `hires.ts` sizes it at ~2044 KB for the worst z2 tile, inside Mapbox's 2500 KB
ceiling, so there is nothing to coarsen and `build_era5_v3_diff` takes no `factor`.

v4 gets **three** (factor 1/2/8, i.e. 0.1°/0.2°/0.8°), like every other 0.1° build: 1.54M features
overflow the low-zoom tile budget, which is the whole reason `HIRES_RUNGS` exists.

Both subtract at **native** resolution and coarsen afterwards. The reason is *not* the one
`stages.py` gives for `diff_builder` — that argument is about `livemaps`' exact-tenths lattice and
does not apply here, since `era5.parent_index` is exact at every rung. The real reason is that
`coarsen(ours - ERA5)` is not `coarsen(ours) - ERA5[parent(block centre)]`: the first area-weights
all 3-4 ERA5 parents a 0.8° block spans, the second picks whichever one the block's centre lands in.

## Antarctica: a hole for v4, a non-issue for v3

ERA5 stops at 64.25°S. v4 covers Antarctica, so `era5v4` loses **668,445 of 2,213,030 land cells
(30.2%)**, all of them polar. v3 stops at 56.8°S itself, so ERA5 covers everything v3 publishes and
`era5v3` loses only 813 cells, scattered between 51.6°N and 43.6°S — ordinary coastline and
small-island disagreements between two land masks.

Those cells are simply not emitted. Writing 0 would render a continent as perfect agreement, which
is the one thing a comparison map must never do.

One convenience worth knowing but not relying on: ERA5's last finite row puts the null boundary at
v4 row 1543, and 1544 = 8 x 193 = 2 x 772, so the hole's edge falls exactly on a block boundary at
both coarse rungs and no block is partially covered. That is a property of today's data, not of the
code — if ERA5's mask ever moves by one row it will straddle, and the native-grid coverage counts
cannot reveal it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .. import era5, formatting, livemaps
from ..config import ERA5_WARMING_LEVELS, V3_STEP_DEG
from ..indicators import get
from ..mapping import MID_BASELINE_PROPERTY, PlanEntry, property_plan
from .diff_builder import DIFF_DECIMALS
from .output import Variant, output_path, write_features
from .stages import Grid, from_change, land_mask, load


def _era5_replicated(
    slug: str, plan: list[PlanEntry], lat: np.ndarray, lon: np.ndarray
) -> tuple[dict[str, np.ndarray], era5.LoadReport]:
    """ERA5, looked up onto an arbitrary target grid. Returns (arrays keyed by plan, report).

    The whole ERA5 side of both comparison families, and the reason they share a module: the lookup
    does not care which grid it is handed. `parent_index` is exact integer arithmetic in units of
    0.025°, and no v3 or v4 cell centre ever lands on an ERA5 cell boundary (v3 centres are
    `3592 + 8k`, v4's are multiples of 4, and ERA5's boundaries are `10k +/- 5` — even can never
    equal odd), so there are no ties to break on either grid.
    """
    data = era5.load(slug, plan)
    print(f"  {data.report.summary()}")
    rows = era5.parent_index(lat, axis="lat")
    cols = era5.parent_index(lon, axis="lon")
    return {name: era5.upsample(data.arrays[name], rows, cols) for name, _, _ in plan}, data.report


@dataclass
class Era5DiffReport:
    """Coverage of one ERA5-vs-v3 build, on the v3 0.2° grid.

    `both` and `v3_only` are the pair worth reading. `both` collapsing, or `v3_only` jumping from
    its usual few hundred into the tens of thousands, is what a longitude-roll regression looks
    like from the outside.

    `era5_only` is NOT a check. ERA5's finite mask is not a land mask — it covers 57.1% of the
    globe including open ocean — so this count is ~500k on a normal v3 build simply because ERA5
    has values over water where we have no land. It is printed for completeness, not as a signal.
    """

    live: livemaps.LoadReport
    era5: era5.LoadReport
    both: int  # cells where the comparison is defined
    v3_only: int  # v3 has a value, ERA5 does not -> not emitted
    era5_only: int  # ERA5 has a value, v3 does not -> mostly ocean, not a check
    emitted: int = 0  # features actually written (set after the write)

    def summary(self) -> str:
        return (
            f"comparable cells on the v3 0.2° grid: {self.both:,} | "
            f"v3-only (null): {self.v3_only:,} | ERA5-only (null): {self.era5_only:,}"
        )


def build_era5_v3_diff(
    slug: str,
    out_path: str | Path | None = None,
    *,
    limit: int | None = None,
    progress_every: int = 250_000,
    on_feature: Callable[[float, float, dict], None] | None = None,
) -> tuple[Path, int, Era5DiffReport]:
    """Write one indicator's `v3 - ERA5` map. Returns (path, feature_count, report).

    No `factor`: the output is v3's grid at its own resolution and there is no pyramid.
    """
    ind = get(slug)
    if ind is None:
        raise ValueError(f"unknown indicator '{slug}'")

    # Six properties, not eighteen: observations only reach ~1.2 °C of warming, so `baseline` and
    # `1c` are the only levels that exist on the ERA5 side.
    plan = property_plan(ind, ERA5_WARMING_LEVELS)
    names = [name for name, _, _ in plan]

    # --- the v3 side, on its own grid, untouched apart from the change reconstruction ---
    arrays, live_report = livemaps.load(ind.live_id, names)
    print(f"  {live_report.summary()}")
    if live_report.missing_properties:
        raise ValueError(
            f"{ind.live_id}: the live export is missing {live_report.missing_properties}, so the "
            f"comparison cannot be built for every level."
        )
    if ind.is_change:
        # absolute baseline + change -> absolute, so both sides are absolute before subtracting.
        from_change(arrays, levels=ERA5_WARMING_LEVELS)

    # --- the ERA5 side, replicated onto the v3 grid by parent lookup ---
    lat, lon = livemaps.grid_axes()
    reference, era5_report = _era5_replicated(slug, plan, lat, lon)

    v3_land = np.isfinite(arrays[MID_BASELINE_PROPERTY])
    era5_land = np.isfinite(reference[MID_BASELINE_PROPERTY])
    report = Era5DiffReport(
        live=live_report,
        era5=era5_report,
        both=int((v3_land & era5_land).sum()),
        v3_only=int((v3_land & ~era5_land).sum()),
        era5_only=int((~v3_land & era5_land).sum()),
    )
    print(f"  {report.summary()}")

    # --- v3 - ERA5, dropping each replicated copy as it is consumed ---
    for name in names:
        arrays[name] = arrays[name] - reference.pop(name)

    grid = Grid(arrays, lat, lon, step=V3_STEP_DEG)

    # The subtraction already propagated NaN from either side, so the usual baseline-mid mask is
    # exactly the intersection — a cell is emitted where the comparison is defined.
    mask = land_mask(grid)

    path, n = write_features(
        Path(out_path)
        if out_path
        else output_path(ind, 1, variant=Variant.ERA5_V3, step=V3_STEP_DEG),
        grid,
        mask,
        formatting.formatter(ind.unit, decimals=DIFF_DECIMALS),
        limit=limit,
        progress_every=progress_every,
        on_feature=on_feature,
    )
    report.emitted = n
    return path, n, report


@dataclass
class Era5V4DiffReport:
    """Coverage of one ERA5-vs-v4 build. Counts are on the native 0.1° grid whatever rung is
    written, for the reason `DiffReport` documents: at factor 8 an 8x8 block holding one comparable
    cell counts wholly as `both`, so recomputing after coarsening would destroy the check.

    Expect a very large `v4_only` — it is Antarctica, ~30% of v4's land, and it is the *normal*
    reading here rather than a warning. As on the v3 side, `era5_only` is not a check at all: ERA5
    has values over open ocean, so it runs to millions.

    `both` counts the full 3601-wide grid, which includes the duplicate +180° seam column that
    `land_mask` then drops, so `emitted` is ~45 lower than `both` at native. That is expected; do
    not treat the two as equal.
    """

    store_cells: int  # v4 cells with a baseline mid value, i.e. the subject-side land count
    era5: era5.LoadReport
    both: int  # cells where the comparison is defined
    v4_only: int  # v4 has a value, ERA5 does not -> not emitted (Antarctica)
    era5_only: int  # ERA5 has a value, v4 has no land -> mostly ocean, not a check
    factor: int = 1  # the rung written: 1 = 0.1°, 2 = 0.2°, 8 = 0.8°
    emitted: int = 0  # features actually written, on that rung (set after the write)

    def summary(self) -> str:
        pct = 100 * self.v4_only / self.store_cells if self.store_cells else 0.0
        return (
            f"comparable cells on the native 0.1° grid: {self.both:,} of {self.store_cells:,} "
            f"v4 land | v4-only (not emitted): {self.v4_only:,} ({pct:.1f}%, Antarctica) | "
            f"ERA5-only: {self.era5_only:,}"
        )


def build_era5_v4_diff(
    slug: str,
    out_path: str | Path | None = None,
    *,
    factor: int = 1,
    limit: int | None = None,
    progress_every: int = 250_000,
    on_feature: Callable[[float, float, dict], None] | None = None,
) -> tuple[Path, int, Era5V4DiffReport]:
    """Write one indicator's `v4 - ERA5` map. Returns (path, feature_count, report).

    `factor` selects the pyramid rung as in `builder.build`: 1 = native 0.1°, 2 = 0.2°, 8 = 0.8°.
    The subtraction happens at native resolution and the result is coarsened afterwards.
    """
    ind = get(slug)
    if ind is None:
        raise ValueError(f"unknown indicator '{slug}'")

    # Six properties, not eighteen: observations only reach ~1.2 °C of warming, so `baseline` and
    # `1c` are the only levels that exist on the ERA5 side.
    plan = property_plan(ind, ERA5_WARMING_LEVELS)
    names = [name for name, _, _ in plan]

    # --- the v4 side, on its own native 0.1° grid ---
    grid = load(ind, plan)

    # --- the ERA5 side, replicated onto it. Loaded BEFORE the transform check below so that a
    # missing ERA5 file still raises FileNotFoundError, which the CLI turns into a clean "skip";
    # the ValueError from that check is not caught and would surface as a traceback. ---
    reference, era5_report = _era5_replicated(slug, plan, grid.lat, grid.lon)

    if ind.transform is not None:
        # No indicator reaches this today: `pct100` belongs to 40701/40702 and `percentile_to_z` to
        # 40703, and none of the three has an ERA5 file. It is a guard rather than a TODO because
        # the failure it prevents is silent — `apply_transform` exists to put v4 into the unit the
        # live maps publish, which is exactly the unit a comparison has to happen in, so skipping
        # it would compare (say) a 0-1 fraction against a 0-100 percentage and still draw a map.
        #
        # If an ERA5 file does arrive for one of those three: work out which unit that file is in,
        # then apply the transform to BOTH sides. Do not simply delete this check.
        raise ValueError(
            f"'{slug}' has the '{ind.transform}' unit transform, and ERA5 arrives untransformed. "
            f"Decide what unit the ERA5 file uses and convert both sides before comparing them — "
            f"see the comment above this check in era5_diff_builder.py."
        )

    # NO `to_change`, for any indicator. The v4 stores are absolute at every warming level (40601's
    # baseline median is 387 mm, not a delta), and ERA5 is absolute, so this is absolute-vs-absolute
    # throughout. `ind.is_change` is deliberately ignored — it describes how the map is *published*,
    # not what the store holds. The v3 path needs `from_change` precisely because v3's change is
    # baked into its published export; v4's is not.

    v4_land = np.isfinite(grid.slices[MID_BASELINE_PROPERTY])
    era5_land = np.isfinite(reference[MID_BASELINE_PROPERTY])
    report = Era5V4DiffReport(
        store_cells=int(v4_land.sum()),
        era5=era5_report,
        both=int((v4_land & era5_land).sum()),
        v4_only=int((v4_land & ~era5_land).sum()),
        era5_only=int((~v4_land & era5_land).sum()),
        factor=factor,
    )
    print(f"  {report.summary()}")

    # --- v4 - ERA5 at native resolution, dropping each replicated copy as it is consumed ---
    for name in names:
        grid.slices[name] = grid.slices[name] - reference.pop(name)

    grid = grid.coarsened(factor)

    # The subtraction already propagated NaN from either side, so the usual baseline-mid mask is
    # exactly the intersection — a cell is emitted where the comparison is defined.
    mask = land_mask(grid)

    # No `step=`: this build is native 0.1°, so the GRID_STEP_DEG default is what names the rungs
    # `-p02` / `-p08`, matching HIRES_RUNGS in vector-tiles/hires.ts. Passing V3_STEP_DEG here (as
    # the v3 path above legitimately does) would produce `-p04` / `-p16` and the upload would fail
    # looking for files that were never written.
    path, n = write_features(
        Path(out_path) if out_path else output_path(ind, factor, variant=Variant.ERA5_V4),
        grid,
        mask,
        formatting.formatter(ind.unit, decimals=DIFF_DECIMALS),
        limit=limit,
        progress_every=progress_every,
        on_feature=on_feature,
    )
    report.emitted = n
    return path, n, report
