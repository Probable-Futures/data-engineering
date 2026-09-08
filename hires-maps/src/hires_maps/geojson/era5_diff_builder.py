"""Build an **ERA5 comparison map**: what we publish today, minus what was observed.

`diff_builder.py` answers "did the numbers move" (v4 against v3). Both sides of that are model
output, so it can only ever say the two disagree — never which one is closer to reality. This
answers the question that one cannot: **how wrong is the map on probablefutures.org today?**

    value = v3 - ERA5      positive (red) = we publish HIGHER than the observations

Same sign convention as `diff_builder`, where red means the first-named dataset is higher, so a
colour never means two different things across the comparison families.

## The grid: v3's own 0.2°, ERA5 replicated onto it

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

## Two asymmetries, both already solved elsewhere in the package

1. **Change maps.** The live exports for 40601/40607/40613/40614/40616 publish an *absolute*
   baseline alongside *changes* at every other level. Subtracting an absolute ERA5 value from a v3
   delta would produce nonsense that still renders as a plausible map, so `stages.from_change` puts
   the v3 side back into absolutes first. ERA5 is absolute at both levels and is never converted —
   see `era5_builder.py` for why we do not manufacture a change from a single observed record.

2. **Precision.** Live values are already truncated to integers, so the difference is only
   meaningful to about +/-0.5 — but truncating it *again* would turn a real +0.7 day bias into 0
   and paint the map as agreement. Diffs keep `DIFF_DECIMALS` places for every unit, as in
   `diff_builder`.

## One rung, not a pyramid

Output is v3's 0.2° grid, ~425k cells. That is the resolution production has always served at z2-5
as a single tileset, and `hires.ts` already sizes it: a 0.2° comparison lands at ~2044 KB for the
worst z2 tile, inside Mapbox's 2500 KB ceiling. So there is nothing to coarsen and no `factor`
argument — same shape as the ERA5 and v3abs variants.

## Antarctica is NOT the gap here, unlike the ERA5-vs-v4 comparison

ERA5 stops at 64.25°S, which costs a v4-grid comparison 30% of its land cells. It costs this one
nothing: **v3 has no data south of 56.8°S either**, so ERA5 covers everything v3 publishes.
Measured on 40105: 425,553 v3 cells, 424,740 of them comparable — the 813 that are not sit between
51.6°N and 43.6°S and are ordinary coastline and small-island disagreements between two land
masks, not a polar hole.

`report.v3_only` should therefore stay in the hundreds. If it jumps into the tens of thousands the
two grids have stopped lining up, which is what a longitude-roll regression looks like from the
outside — so it is always printed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .. import era5, formatting, livemaps
from ..config import ERA5_WARMING_LEVELS, V3_STEP_DEG
from ..indicators import get
from ..mapping import MID_BASELINE_PROPERTY, property_plan
from .diff_builder import DIFF_DECIMALS
from .output import Variant, output_path, write_features
from .stages import Grid, from_change, land_mask


@dataclass
class Era5DiffReport:
    """Coverage of one ERA5-vs-v3 build, on the v3 0.2° grid.

    The three counts are the check worth reading. A large `v3_only` is expected and is almost
    entirely Antarctica; a large `era5_only` is not, and neither is a `both` that has collapsed —
    either would mean the two grids stopped lining up, which is what a longitude-roll bug looks
    like from the outside.
    """

    live: livemaps.LoadReport
    era5: era5.LoadReport
    both: int  # cells where the comparison is defined
    v3_only: int  # v3 has a value, ERA5 does not -> written as null (Antarctica)
    era5_only: int  # ERA5 has a value, v3 does not -> written as null
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
    data = era5.load(slug, plan)
    print(f"  {data.report.summary()}")
    lat, lon = livemaps.grid_axes()
    rows = era5.parent_index(lat, axis="lat")
    cols = era5.parent_index(lon, axis="lon")

    v3_land = np.isfinite(arrays[MID_BASELINE_PROPERTY])
    era5_land = np.isfinite(era5.upsample(data.arrays[MID_BASELINE_PROPERTY], rows, cols))
    report = Era5DiffReport(
        live=live_report,
        era5=data.report,
        both=int((v3_land & era5_land).sum()),
        v3_only=int((v3_land & ~era5_land).sum()),
        era5_only=int((~v3_land & era5_land).sum()),
    )
    print(f"  {report.summary()}")

    # --- v3 - ERA5, one property at a time so only one replicated copy is alive ---
    for name in names:
        arrays[name] = arrays[name] - era5.upsample(data.arrays[name], rows, cols)
    del data

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
