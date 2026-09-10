"""Build a **comparison map**: the new hi-res data minus the currently-live map.

The product is one layer whose value at every cell is `new - live`, styled with a diverging
red/blue ramp so the sign and size of the disagreement read straight off the map, and so "the two
datasets agree" gets its own neutral band. A swipe comparison between two maps cannot show a
systematic bias — two similar-looking maps look similar. This can.

"Comparison maps: two different questions" in `docs/hi-res-map-pipeline.md` defines two.
This builds the first:

* **detail diff** (built here) — for every new 0.1° cell, `new - (the live 0.2° value covering it)`,
  on the 0.1° grid. Shows what the finer grid bought us, and where: coastlines, mountains, cities.
  Four neighbouring new cells share one live parent, so real 0.2°-blocky structure appears at deep
  zoom. That is the signal, not an artifact.
* **model diff** (not built) — aggregate the new data back to 0.2° first, then diff. Separates "the
  model moved" from "the resolution changed".

Both halves are put in their published form before subtracting, so we always compare like with
like: the new side goes through the same unit transform and change-from-baseline step as
`builder.build`, and the live side is read from the published GeoJSON (see `livemaps.py`).

Two asymmetries the code has to handle:

1. **Change maps.** Live change maps keep the *absolute* baseline in the 0.5 °C slot while the other
   levels hold changes (40601: median `data_baseline_mid` 727 mm, median `data_1c_mid` +12 mm). Our
   hi-res build zeroes that slot instead, so subtracting naively would compute `0 - 727 mm`. We
   therefore build the new side with `zero_baseline=False`, which makes the baseline slot an
   absolute-vs-absolute comparison while every other slot stays change-vs-change.
2. **Precision.** Live values are already truncated to integers (one decimal for the z-score map),
   so a diff is only meaningful to about ±0.5 — but it must not be truncated *again*: a real
   +0.7 °C bias would become 0 and the map would claim agreement. Diffs are written with
   `DIFF_DECIMALS` places for every unit.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .. import formatting, livemaps, transforms
from ..indicators import get
from ..mapping import MID_BASELINE_PROPERTY, property_plan
from .output import Variant, output_path, write_features
from .stages import apply_transform, land_mask, load, to_change

# Diffs keep decimals whatever the unit — see the module docstring.
DIFF_DECIMALS = 1


@dataclass
class DiffReport:
    """Coverage of one comparison build. The mask counts are the check worth reading: a large
    `new_only` is expected (the live grid has coarser coastlines), a large `live_only` is not.

    Those three counts are always taken on the **native 0.1° grid**, whatever rung is being
    written, because they answer "how much of each grid has no counterpart" — a question that only
    means anything where the two grids actually meet. Recomputing them after coarsening would
    destroy the check: at factor 8 an 8x8 block holding a single comparable cell counts wholly as
    `both`, driving `new_only` toward 0 no matter how badly the coastlines disagree. `factor` and
    `emitted` record what was actually written, so one object answers both questions.
    """

    live: livemaps.LoadReport
    both: int  # cells where the comparison is defined
    new_only: int  # new has a value, live does not -> written as null
    live_only: int  # live has a value, new does not -> written as null
    factor: int = 1  # the rung written: 1 = native 0.1°, 2 = 0.2°, 8 = 0.8°
    emitted: int = 0  # features actually written, on that rung (set after the write)

    def summary(self) -> str:
        return (
            f"comparable cells on the native 0.1° grid: {self.both:,} | "
            f"new-only (null): {self.new_only:,} | live-only (null): {self.live_only:,}"
        )


def build_diff(
    slug: str,
    out_path: str | Path | None = None,
    *,
    factor: int = 1,
    limit: int | None = None,
    progress_every: int = 250_000,
    on_feature: Callable[[float, float, dict], None] | None = None,
) -> tuple[Path, int, DiffReport]:
    """Write one indicator's comparison `.geojsonld`. Returns (path, feature_count, report).

    `factor` selects the pyramid rung exactly as in `builder.build`: 1 = native 0.1°, 2 = 0.2°,
    8 = 0.8°. Differencing happens at the native resolution and the result is coarsened afterwards;
    the block average ignores NaN, so a coarse cell reports the mean of whatever comparable cells
    it contains.
    """
    ind = get(slug)
    if ind is None:
        raise ValueError(f"unknown indicator '{slug}'")

    # --- the new side, in exactly the form its hi-res map publishes ---
    grid = load(ind, property_plan(ind))
    names = list(grid.slices)
    clamped = apply_transform(ind, grid.slices)
    if ind.is_change:
        # Keep the absolute baseline so the 0.5 slot compares like with like against the live file.
        to_change(grid.slices, zero_baseline=False)
    if clamped:
        print(
            f"  {ind.transform}: clamped {clamped:,} cell-values to +/-{transforms.Z_LIMIT} "
            f"(percentiles of exactly 0 or 100, where the conversion is infinite)"
        )

    # --- the live side, upsampled onto the new grid by parent lookup ---
    live, live_report = livemaps.load(ind.live_id, names)
    print(f"  {live_report.summary()}")
    rows = livemaps.parent_index(grid.lat, axis="lat")
    cols = livemaps.parent_index(grid.lon, axis="lon")

    new_land = np.isfinite(grid.slices[MID_BASELINE_PROPERTY])
    live_land = np.isfinite(livemaps.upsample(live[MID_BASELINE_PROPERTY], rows, cols))
    report = DiffReport(
        live=live_report,
        both=int((new_land & live_land).sum()),
        new_only=int((new_land & ~live_land).sum()),
        live_only=int((~new_land & live_land).sum()),
        factor=factor,
    )
    print(f"  {report.summary()}")

    # --- new - live, one property at a time so only one upsampled copy is alive ---
    for name in names:
        grid.slices[name] = grid.slices[name] - livemaps.upsample(live[name], rows, cols)
    del live

    grid = grid.coarsened(factor)

    # A cell is emitted where the comparison is defined; the subtraction already propagated NaN
    # from either side, so the usual baseline-mid mask is exactly that intersection.
    mask = land_mask(grid)

    path, n = write_features(
        Path(out_path) if out_path else output_path(ind, factor, variant=Variant.DIFF),
        grid,
        mask,
        formatting.formatter(ind.unit, decimals=DIFF_DECIMALS),
        limit=limit,
        progress_every=progress_every,
        on_feature=on_feature,
    )
    report.emitted = n
    return path, n, report
