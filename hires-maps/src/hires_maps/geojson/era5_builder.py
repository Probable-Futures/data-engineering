"""Build a **standalone ERA5 map**: ERA5's own numbers, on ERA5's own 0.25° grid.

No subtraction. This exists for two reasons, and the first is why it is built and verified before
either comparison family.

**It is the only place a reader bug is catchable.** A rolled-wrong longitude axis, a missed Kelvin
conversion, or the wrong percentile column all produce an obviously broken standalone map — a world
shifted sideways, temperatures near 290, values from the wrong distribution. Buried inside
`new - era5` the same bugs produce a comparison map that is quietly wrong and still looks entirely
plausible. Verify here, and the comparisons inherit the verification.

**And it is useful on its own.** Put this next to the live v3 map in the app and you have answered
"how does our data compare to observations" visually, before computing a single difference.

## How it differs from `builder.build`

* **No transform, no change step.** ERA5 values are absolute and already in map units once
  `era5.load` has done the Kelvin conversion. Every transform in `transforms.py` belongs to the
  drought and water-balance maps, and ERA5 ships none of those — so none of them apply here.
* **Two warming levels**, so six properties per cell rather than eighteen.
* **The live precision rule**, not the comparison maps' `decimals=1`. These are absolute values, so
  they truncate to integers exactly as the published maps do and can be compared popup for popup.
* **Not masked to land.** ERA5's finite mask is not a land mask — 57.1% of the globe, including open
  Pacific but not open Atlantic. That is deliberate here: the verification build should show what
  the file actually contains, oddities included. A land-masked variant for presentation is a later
  addition, once this pass has been checked.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .. import era5, formatting
from ..config import ERA5_STEP_DEG, ERA5_WARMING_LEVELS
from ..indicators import get
from ..mapping import property_plan
from .output import Variant, output_path, write_features
from .stages import Grid, land_mask


@dataclass
class Era5MapReport:
    """Coverage of one standalone build. `cells` is the count on ERA5's native grid whatever rung
    was written, so it stays comparable across rungs; `emitted` is what actually went to disk."""

    load: era5.LoadReport
    cells: int  # cells with a baseline mid value, on the native 0.25° grid
    factor: int = 1
    emitted: int = 0

    def summary(self) -> str:
        total = era5.SHAPE[0] * era5.SHAPE[1]
        return (
            f"cells with a value on the native 0.25° grid: {self.cells:,}/{total:,} "
            f"({100 * self.cells / total:.1f}%)"
        )


def build_era5_map(
    slug: str,
    out_path: str | Path | None = None,
    *,
    factor: int = 1,
    limit: int | None = None,
    progress_every: int = 250_000,
    on_feature: Callable[[float, float, dict], None] | None = None,
) -> tuple[Path, int, Era5MapReport]:
    """Write one indicator's ERA5 map as `.geojsonld`. Returns (path, feature_count, report).

    `factor` selects the pyramid rung: 1 = native 0.25°, 2 = 0.5°, 4 = 1.0°. Coarser rungs are
    area-weighted block means of the native grid, ignoring NaN.
    """
    ind = get(slug)
    if ind is None:
        raise ValueError(f"unknown indicator '{slug}'")

    plan = property_plan(ind, ERA5_WARMING_LEVELS)
    data = era5.load(slug, plan)
    print(f"  {data.report.summary()}")

    grid = Grid(data.arrays, data.lat, data.lon, step=ERA5_STEP_DEG)
    report = Era5MapReport(
        load=data.report,
        cells=int(land_mask(grid).sum()),
        factor=factor,
    )
    print(f"  {report.summary()}")

    grid = grid.coarsened(factor)
    mask = land_mask(grid)

    path, n = write_features(
        Path(out_path)
        if out_path
        else output_path(ind, factor, variant=Variant.ERA5, step=ERA5_STEP_DEG),
        grid,
        mask,
        formatting.formatter(ind.unit),
        limit=limit,
        progress_every=progress_every,
        on_feature=on_feature,
    )
    report.emitted = n
    return path, n, report
