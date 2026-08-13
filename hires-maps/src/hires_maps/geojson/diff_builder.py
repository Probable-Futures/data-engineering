"""Build a **comparison map**: the new hi-res data minus the currently-live map.

The product is one layer whose value at every cell is `new - live`, styled with a diverging
red/blue ramp so the sign and size of the disagreement read straight off the map, and so "the two
datasets agree" gets its own neutral band. A swipe comparison between two maps cannot show a
systematic bias — two similar-looking maps look similar. This can.

`docs/HI-RES-TILES.md` §9 defines two different comparison questions. This builds the first:

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
   levels hold changes (40601: `data_baseline_mid` ≈ 744 mm, `data_1c_mid` ≈ +24 mm). Our hi-res
   build zeroes that slot instead, so subtracting naively would compute `0 - 744 mm`. We therefore
   build the new side with `zero_baseline=False`, which makes the baseline slot an
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
from ..aggregation import coarsen
from ..config import DIFF_MAPS_DIR
from ..indicators import Indicator, get
from ..mapping import MID_BASELINE_PROPERTY, property_plan
from .builder import (
    _apply_transform,
    _to_change,
    land_mask,
    load_slices,
    rung_suffix,
    write_features,
)

# Diffs keep decimals whatever the unit — see the module docstring.
DIFF_DECIMALS = 1


@dataclass
class DiffReport:
    """Coverage of one comparison build. The mask counts are the check worth reading: a large
    `new_only` is expected (the live grid has coarser coastlines), a large `live_only` is not."""

    live: livemaps.LoadReport
    both: int  # cells where the comparison is defined
    new_only: int  # new has a value, live does not -> written as null
    live_only: int  # live has a value, new does not -> written as null

    def summary(self) -> str:
        return (
            f"comparable cells: {self.both:,} | new-only (null): {self.new_only:,} | "
            f"live-only (null): {self.live_only:,}"
        )


def default_output(ind: Indicator, factor: int = 1) -> Path:
    """`diff-geojson/{live_id}-diff[-pNN].geojsonld` — a sibling of the `old-geojson/` folder the
    live half is read from, so both sides of a comparison sit together."""
    return DIFF_MAPS_DIR / f"{ind.live_id}-diff{rung_suffix(factor)}.geojsonld"


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

    plan = property_plan(ind)
    names = [name for name, _, _ in plan]

    # --- the new side, in exactly the form its hi-res map publishes ---
    arrays, lat, lon = load_slices(slug, plan)
    clamped = _apply_transform(ind, arrays)
    if ind.is_change:
        # Keep the absolute baseline so the 0.5 slot compares like with like against the live file.
        _to_change(arrays, zero_baseline=False)
    if clamped:
        print(
            f"  {ind.transform}: clamped {clamped:,} cell-values to +/-{transforms.Z_LIMIT} "
            f"(percentiles of exactly 0 or 100, where the conversion is infinite)"
        )

    # --- the live side, upsampled onto the new grid by parent lookup ---
    live, live_report = livemaps.load(ind.live_id, names)
    print(f"  {live_report.summary()}")
    rows = livemaps.parent_index(lat, axis="lat")
    cols = livemaps.parent_index(lon, axis="lon")

    new_land = np.isfinite(arrays[MID_BASELINE_PROPERTY])
    live_land = np.isfinite(livemaps.upsample(live[MID_BASELINE_PROPERTY], rows, cols))
    report = DiffReport(
        live=live_report,
        both=int((new_land & live_land).sum()),
        new_only=int((new_land & ~live_land).sum()),
        live_only=int((~new_land & live_land).sum()),
    )
    print(f"  {report.summary()}")

    # --- new - live, one property at a time so only one upsampled copy is alive ---
    for name in names:
        arrays[name] = arrays[name] - livemaps.upsample(live[name], rows, cols)
    del live

    arrays, lat, lon = coarsen(arrays, lat, lon, factor)

    # A cell is emitted where the comparison is defined; the subtraction already propagated NaN
    # from either side, so the usual baseline-mid mask is exactly that intersection.
    mask = land_mask(arrays, lon)

    path, n = write_features(
        Path(out_path) if out_path else default_output(ind, factor),
        arrays=arrays,
        names=names,
        mask=mask,
        lat=lat,
        lon=lon,
        half=0.05 * factor,
        fmt=formatting.formatter(ind.unit, decimals=DIFF_DECIMALS),
        limit=limit,
        progress_every=progress_every,
        on_feature=on_feature,
    )
    return path, n, report
