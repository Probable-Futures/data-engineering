"""Republish a **currently-live v3 change map as an absolute map**, on the live 0.2° grid.

Why this exists: the ERA5 maps are absolute, because deriving a change from two windows of a single
observed record measures weather variability as much as climate. So to put v3 beside ERA5 for the
five change indicators that have an ERA5 counterpart (40601, 40607, 40613, 40614, 40616), v3 has to
be absolute too. 40703 and 40704 have no ERA5 partner but run through the same path.

## Where the numbers come from

The live exports already contain everything needed. For these indicators they publish an
**absolute baseline** alongside **changes** at every other level — 40601's export has a median
`data_baseline_mid` of 727 mm next to a median `data_1c_mid` of +12 mm — so:

    absolute(wl) = data_baseline_* + data_{wl}_*

That is `stages.from_change`, the exact inverse of the `to_change` the live pipeline applied.
Verified on every registered change indicator: the baseline is absolute and the other levels are
changes. Two of them are worth knowing about before reading the output:

  - **40703** is a SPEI z-score, normalised to the baseline period, so its live baseline is ~0
    everywhere (median 0.0, range -0.2..0.3). `from_change` runs, but absolute ≈ change: the
    republished map is the change map shifted by less than one legend bin.
  - **40612** is the one live change map this builder cannot touch, and why `indicators.py` has no
    row for it: its export ships `data_baseline_mid` as null on every feature, so there is no
    absolute baseline to add back. It is also already absolute in spirit — a return-period ratio
    ("x as frequent") whose baseline is 1x by definition.

Reading the published GeoJSON rather than Postgres is deliberate, and the same choice `livemaps.py`
makes for the comparison maps: these files hold the numbers that are actually on
probablefutures.org today, and `pf_dataset_statistics` is empty locally while the source netCDFs
for `water_module` are no longer on disk. The equivalent SQL route exists —
`pf_private.aggregate_pf_statistics_change_to_absolute` in `netcdfs/import/util/temp.sql`, wired up
through the commented-out `EXPORT_QUERY_WITH_ABSOLUTE_VALUES_FOR_CHANGE_MAPS` in
`geojson/Makefile` — and computes the same sum. Use that if the values need to land in the database
as well; this builder only produces tiles.

## One rung, not a pyramid

Output is the live 0.2° grid, ~425k land cells. That is the resolution production has always
served at z2-5 as a single tileset, so there is nothing to coarsen for tile-size reasons. Same
shape as the ERA5 variant.

## Not a substitute for fixing the legend

An absolute map needs absolute stops. The live `map.stops` for these datasets are change scales
(40601 is `[-100, -40, -10, 10, 40, 100]` mm) and every absolute precipitation value on Earth
exceeds the top one, so on the old ramp the whole map renders in a single colour. Each of these
needs its own stops in `configs.ts` and in its `pf_maps` row.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .. import formatting, livemaps
from ..config import V3_STEP_DEG
from ..indicators import get
from ..mapping import MID_BASELINE_PROPERTY, property_plan
from .output import Variant, output_path, write_features
from .stages import Grid, from_change, land_mask

# `V3_STEP_DEG` (0.2) is re-exported here because this was the first build whose output is the v3
# lattice rather than the 0.1° one. It now lives in config.py, shared with the ERA5-vs-v3 builder.
__all__ = ["V3_STEP_DEG", "V3AbsoluteReport", "build_v3_absolute"]


@dataclass
class V3AbsoluteReport:
    """Coverage of one build, plus the check that the reconstruction was meaningful."""

    live: livemaps.LoadReport
    cells: int  # cells with an absolute baseline, i.e. what can be emitted
    emitted: int = 0

    def summary(self) -> str:
        return f"cells with a baseline value on the live 0.2° grid: {self.cells:,}"


def build_v3_absolute(
    slug: str,
    out_path: str | Path | None = None,
    *,
    limit: int | None = None,
    progress_every: int = 250_000,
    on_feature: Callable[[float, float, dict], None] | None = None,
) -> tuple[Path, int, V3AbsoluteReport]:
    """Write one indicator's absolute v3 map. Returns (path, feature_count, report).

    No `factor`: the output is the live grid at its own resolution, and there is no pyramid.
    """
    ind = get(slug)
    if ind is None:
        raise ValueError(f"unknown indicator '{slug}'")
    if not ind.is_change:
        raise ValueError(
            f"'{slug}' is published absolute already — there is no change to undo. This builder is "
            f"only for the change indicators."
        )

    plan = property_plan(ind)
    names = [name for name, _, _ in plan]
    arrays, live_report = livemaps.load(ind.live_id, names)
    print(f"  {live_report.summary()}")
    if live_report.missing_properties:
        raise ValueError(
            f"{ind.live_id}: the live export is missing {live_report.missing_properties}, so the "
            f"absolute values cannot be reconstructed for every level."
        )

    # changes -> absolutes, using the export's own absolute baseline.
    from_change(arrays)

    lat, lon = livemaps.grid_axes()
    grid = Grid(arrays, lat, lon, step=V3_STEP_DEG)
    report = V3AbsoluteReport(
        live=live_report,
        cells=int(np.isfinite(grid.slices[MID_BASELINE_PROPERTY]).sum()),
    )
    print(f"  {report.summary()}")

    mask = land_mask(grid)
    path, n = write_features(
        Path(out_path)
        if out_path
        else output_path(ind, 1, variant=Variant.V3ABS, step=V3_STEP_DEG),
        grid,
        mask,
        formatting.formatter(ind.unit),
        limit=limit,
        progress_every=progress_every,
        on_feature=on_feature,
    )
    report.emitted = n
    return path, n, report
