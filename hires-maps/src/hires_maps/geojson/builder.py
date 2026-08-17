"""Build a `.geojsonld` file directly from a warming-level Zarr store.

Output is newline-delimited GeoJSON (one Feature per line) — the exact format the
`vector-tiles` uploader ingests — with property names matching the current live maps
(`data_baseline_mid`, `data_1c_mid`, ...). So the existing recipes and styles need no changes.

One feature per land cell; ocean/NaN cells are skipped. Values carry the same precision the live
pipeline stores — integers for °C/days/mm/%, one decimal for z-score — see `formatting.py`.

Every indicator is read from its **absolute** variable and then put into the unit and form its
live map publishes, in this order: unit transform -> coarsen to the rung -> land mask ->
change-from-baseline. That is *this* builder's order; the comparison builder necessarily differs.
`stages.py`'s module docstring holds both orders and why neither can adopt the other's.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .. import formatting, transforms
from ..indicators import get
from ..mapping import property_plan
from .output import output_path, write_features
from .stages import apply_transform, land_mask, load, to_change


def build(
    slug: str,
    out_path: str | Path | None = None,
    *,
    factor: int = 1,
    limit: int | None = None,
    progress_every: int = 250_000,
    on_feature: Callable[[float, float, dict], None] | None = None,
) -> tuple[Path, int]:
    """Write one indicator's `.geojsonld`. Returns (path, feature_count).

    `factor` selects the rung: 1 = native 0.1°, 2 = 0.2° (p02), 8 = 0.8° (p08). 4 is
    supported but not published (see PYRAMID_FACTORS in cli.py).
    Coarser rungs are area-weighted N×N block averages of the native grid.

    `on_feature(lon, lat, properties)` is called for every emitted feature — the hook the DB
    writer uses (Phase 3) without the builder needing to know about the database.
    """
    ind = get(slug)
    if ind is None:
        raise ValueError(f"unknown indicator '{slug}'")

    grid = load(ind, property_plan(ind))

    clamped = apply_transform(ind, grid.slices)
    grid = grid.coarsened(factor)

    # The mask has to be taken before `to_change`, which replaces the baseline array with zeros —
    # zeros are finite, so afterwards every ocean cell would look like land.
    mask = land_mask(grid)

    if ind.is_change:
        to_change(grid.slices)
    if clamped:
        print(
            f"  {ind.transform}: clamped {clamped:,} cell-values to +/-{transforms.Z_LIMIT} "
            f"(percentiles of exactly 0 or 100, where the conversion is infinite; counted on the "
            f"native grid, before coarsening)"
        )

    return write_features(
        Path(out_path) if out_path else output_path(ind, factor),
        grid,
        mask,
        formatting.formatter(ind.unit),
        limit=limit,
        progress_every=progress_every,
        on_feature=on_feature,
    )
