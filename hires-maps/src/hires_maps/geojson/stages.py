"""The stages a grid of property arrays passes through between the store and a map value.

Everything here operates on a `Grid` — one `(lat, lon)` array per property, plus the coordinates
they sit on. Nothing here knows about JSON, paths or filenames; that is `output.py`.

## The builders apply these stages in different orders

    builder.build          transform -> coarsen -> land mask -> change
    build_diff             transform -> change -> subtract live -> coarsen -> land mask
    build_era5_map         (no transform, no change) -> coarsen -> land mask
    build_era5_v4_diff     subtract ERA5 -> coarsen -> land mask
    build_era5_v3_diff     from_change -> subtract ERA5 -> land mask   (one rung, no coarsen)
    build_v3_absolute      from_change -> land mask                   (one rung, no coarsen)

The ERA5 builds skip `transform` and `to_change` entirely: ERA5 is absolute and already in map
units, so both sides of an ERA5 comparison are absolute. The v3 paths run `from_change` instead,
because v3's change is baked into its published export and has to be undone first. Each builder's
own module docstring carries the reasoning.

The difference between the first two is forced, not an oversight, on two independent grounds:

1. **The live join must happen at native resolution.** `livemaps.parent_index` is exact
   integer-tenths arithmetic pinned to the live 0.2° centres (89.8, 89.6, ...), but
   `aggregation.block_centres` returns block *means*, which do not lie on that lattice — at
   factor 2 they are 89.95, 89.75, 89.55. Those are half-tenths, so `livemaps._tenths`' `np.rint`
   rounds them half-to-even (89.95 -> 900 but 89.75 -> 898) and the on-grid `% 2 == 0` check would
   pass for some blocks and fail for others. Coarsening before the join would silently produce a
   shifted parent map.

2. **`land_mask` must run after the subtraction.** The diff's mask means "cells where the
   comparison is defined" = new AND live, which only exists once `new - live` has propagated NaN
   from both sides. Masking on the new side alone would emit the ~858,098 new-only coastal cells
   as features whose value came from a NaN — exactly what
   `test_cells_the_live_map_lacks_become_null_not_zero` exists to prevent.

The one remaining difference — `to_change` before vs. after `coarsen` — is immaterial: both are
linear and commute wherever the operands' finite masks agree, which they do, since the stores
carry the same land mask at every warming level.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

import numpy as np

from .. import stores, transforms
from ..aggregation import coarsen
from ..config import GRID_STEP_DEG, WARMING_LEVELS, WL_PREFIX
from ..indicators import Indicator
from ..mapping import MID_BASELINE_PROPERTY, ROLES, PlanEntry, property_name


@dataclass(frozen=True)
class Grid:
    """One `(lat, lon)` float32 array per map property, on a shared pair of coordinate axes.

    `factor` records how many native cells per side each cell now covers (1 = native), and `step`
    is the resulting cell size in degrees. Both are needed: `factor` identifies the pyramid rung,
    `step` gives the geometry. They are only redundant when the native grid happens to be 0.1° —
    ERA5 builds start at 0.25°.
    """

    slices: dict[str, np.ndarray]
    lat: np.ndarray
    lon: np.ndarray
    factor: int = 1
    step: float = GRID_STEP_DEG

    @property
    def half(self) -> float:
        """Cell half-width in degrees: 0.05° on the native 0.1° grid, 0.1° at p02, 0.4° at p08.

        Derived from `step`, not from `GRID_STEP_DEG * factor`, because not every grid we build on
        is a multiple of 0.1°. ERA5 is 0.25°, which would need `factor=2.5` under the old rule.
        """
        return self.step / 2.0

    def coarsened(self, factor: int) -> Grid:
        """This grid as area-weighted `factor`x`factor` block means (a no-op at factor 1)."""
        slices, lat, lon = coarsen(self.slices, self.lat, self.lon, factor)
        return replace(
            self,
            slices=slices,
            lat=lat,
            lon=lon,
            factor=self.factor * factor,
            step=self.step * factor,
        )


def load(ind: Indicator, plan: list[PlanEntry]) -> Grid:
    """Load one (warming level, stat) slice per planned property, as float32 to bound memory.

    Returns a native 0.1° `Grid` whose `slices` are keyed and ordered by `plan`.
    """
    ds = stores.open_store(ind.slug)
    var = stores.value_var(ind.slug)
    slices = {
        name: ds[var].sel(wl=wl, stat=stat).values.astype("float32") for name, wl, stat in plan
    }
    return Grid(slices, ds["lat"].values.astype(float), ds["lon"].values.astype(float))


def apply_transform(ind: Indicator, arrays: dict[str, np.ndarray]) -> int:
    """Convert every slice into the unit the live map publishes. Returns values clamped.

    Runs *before* coarsening so the coarse pyramid rungs average in the published unit. That
    matters for water balance: the percentile -> z mapping is curved, so averaging percentiles
    and then converting gives a different (wrong) answer.
    """
    if ind.transform is None:
        return 0
    clamped = 0
    for name, a in arrays.items():
        arrays[name], n = transforms.apply(ind.transform, a)
        clamped += n
    return clamped


def to_change(
    arrays: dict[str, np.ndarray],
    *,
    zero_baseline: bool = True,
    levels: Sequence[float] = WARMING_LEVELS,
) -> None:
    """Turn absolute values into change-from-baseline, in place, per low/mid/high role.

    `levels` must match the levels `arrays` actually holds — ERA5 builds carry only 0.5 and 1.0, and
    the default would `KeyError` on `data_1_5c_low`.

    We derive the change rather than read the store's own `diff_*` variable, even though the store
    defines it the same way (checked at full precision: `diff_* == value(wl) - value(0.5)` exactly,
    every warming level and statistic). Two reasons: `diff_*` is all-NaN at the 0.5 °C level, which
    would leave the land mask with nothing to key off; and for water balance the subtraction has to
    happen after the percentile -> z transform, which rules out the pre-computed version.

    One caveat when cross-checking against `diff_*`: slices are loaded as float32 (to bound
    memory), which costs ~4e-6 of precision, so a cell whose true change sits that close to a
    rounding boundary can land one decimal step away from the stored `diff_*`. Measured at ~1 cell
    in 20,000, always 0.1. Far below the map's bin widths, and the same float32-then-round path the
    already-published absolute maps use.

    With `zero_baseline` (the default) the baseline itself becomes 0, i.e. "no change from
    baseline". The app never paints that layer — picking 0.5 °C on a change map jumps to 1.0 °C — so
    it only shows up in popups and CSVs.

    NOTE: the *live* change maps do not do this. They keep the **absolute** baseline in the 0.5 °C
    slot (40601's export has a median `data_baseline_mid` of 727 mm next to a median
    `data_1c_mid` of +12 mm), because the
    view that zeroes it in `netcdfs/import/util/temp.sql` is commented out of `geojson/Makefile`
    and the active export passes the stored value straight through. `zero_baseline=False` matches
    that live behaviour; the comparison maps need it so the baseline slot compares like with like.
    """
    for role in ROLES:
        baseline_name = property_name(WL_PREFIX[0.5], role)
        baseline = arrays[baseline_name]
        for wl in levels:
            if wl == 0.5:
                continue
            name = property_name(WL_PREFIX[wl], role)
            arrays[name] = arrays[name] - baseline
        if zero_baseline:
            arrays[baseline_name] = np.where(np.isfinite(baseline), 0.0, np.nan).astype("float32")


def from_change(arrays: dict[str, np.ndarray], *, levels: Sequence[float] = WARMING_LEVELS) -> None:
    """Turn change-from-baseline back into absolute values, in place, per low/mid/high role.

    The exact inverse of `to_change(zero_baseline=False)`, and the only way to get an absolute v3
    map: the live exports for the five change indicators publish an **absolute** baseline alongside
    **changes** at every other level (40601's export has a median `data_baseline_mid` of 727 mm
    next to a median `data_1c_mid` of +12 mm), so `absolute(wl) = baseline + change(wl)`.

    v4 needs none of this — its stores hold the absolute values natively and the builder simply
    skips `to_change`. This exists because v3's change is baked into the published data.

    Requires a baseline that is genuinely absolute. Running it on a v3 export whose baseline had
    already been zeroed would silently return the changes unchanged.
    """
    for role in ROLES:
        baseline = arrays[property_name(WL_PREFIX[0.5], role)]
        for wl in levels:
            if wl == 0.5:
                continue
            name = property_name(WL_PREFIX[wl], role)
            arrays[name] = arrays[name] + baseline


def land_mask(grid: Grid) -> np.ndarray:
    """Cells to emit: baseline mid has a value, minus the duplicate +180° seam column."""
    mask = np.isfinite(grid.slices[MID_BASELINE_PROPERTY])
    seam = np.isclose(grid.lon, 180.0)
    if seam.any():
        mask[:, seam] = False
    return mask
