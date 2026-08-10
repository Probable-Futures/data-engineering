"""Build a `.geojsonld` file directly from a warming-level Zarr store.

Output is newline-delimited GeoJSON (one Feature per line) — the exact format the
`vector-tiles` uploader ingests — with property names matching the current live maps
(`data_baseline_mid`, `data_1c_mid`, ...). So the existing recipes and styles need no changes.

One feature per land cell; ocean/NaN cells are skipped. Values carry the same precision the live
pipeline stores — integers for °C/days/mm/%, one decimal for z-score — see `formatting.py`.

Every indicator is read from its **absolute** variable and then put into the unit and form its
live map publishes, in this order: unit transform -> coarsen to the rung -> land mask ->
change-from-baseline. See `_apply_transform` and `_to_change` for why that order.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import numpy as np

from .. import formatting, stores, transforms
from ..aggregation import coarsen
from ..config import MTS_DIR, WARMING_LEVELS, WL_PREFIX
from ..geometry import cell_ring
from ..indicators import Indicator, get
from ..mapping import MID_BASELINE_PROPERTY, ROLES, property_name, property_plan


def _apply_transform(ind: Indicator, arrays: dict[str, np.ndarray]) -> int:
    """Convert every slice into the unit the live map publishes. Returns cells clipped.

    Runs *before* coarsening so the coarse pyramid rungs average in the published unit. That
    matters for water balance: the percentile -> z mapping is curved, so averaging percentiles
    and then converting gives a different (wrong) answer.
    """
    if ind.transform is None:
        return 0
    clipped = 0
    for name, a in arrays.items():
        arrays[name], n = transforms.apply(ind.transform, a)
        clipped += n
    return clipped


def _to_change(arrays: dict[str, np.ndarray]) -> None:
    """Turn absolute values into change-from-baseline, in place, per low/mid/high role.

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

    The baseline itself becomes 0 ("no change from baseline"), matching what the live pipeline
    forces for change maps in `netcdfs/import/util/temp.sql`. The app never paints that layer —
    picking 0.5 °C on a change map jumps to 1.0 °C — so it only ever shows up in popups and CSVs.
    """
    for role in ROLES:
        baseline_name = property_name(WL_PREFIX[0.5], role)
        baseline = arrays[baseline_name]
        for wl in WARMING_LEVELS:
            if wl == 0.5:
                continue
            name = property_name(WL_PREFIX[wl], role)
            arrays[name] = arrays[name] - baseline
        arrays[baseline_name] = np.where(np.isfinite(baseline), 0.0, np.nan).astype("float32")


def default_output(ind: Indicator, factor: int = 1) -> Path:
    """Output path in the vector-tiles input folder, under a NEW `-hires` id so production
    tilesets are never overwritten. Coarse pyramid rungs get a `-pNN` suffix (p02/p08)."""
    suffix = "" if factor == 1 else f"-p{factor:02d}"
    return MTS_DIR / f"{ind.live_id}-hires{suffix}.geojsonld"


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

    ds = stores.open_store(slug)
    var = stores.value_var(slug)
    lat = ds["lat"].values.astype(float)
    lon = ds["lon"].values.astype(float)

    # Load each needed (warming level, stat) slice once, as float32 to bound memory.
    plan = property_plan(ind)  # (property_name, wl, stat)
    arrays: dict[str, np.ndarray] = {
        name: ds[var].sel(wl=wl, stat=stat).values.astype("float32") for name, wl, stat in plan
    }

    # Into the published unit, then down to the requested pyramid rung (coarsen is a no-op at 1).
    clipped = _apply_transform(ind, arrays)
    arrays, lat, lon = coarsen(arrays, lat, lon, factor)
    names = [name for name, _, _ in plan]
    half = 0.05 * factor  # cell half-width in degrees for this rung

    # Land mask from the baseline mid value; skip the duplicate +180° seam column.
    # This has to happen before `_to_change`, which replaces that array with zeros — zeros are
    # finite, so afterwards every ocean cell would look like land.
    mask = np.isfinite(arrays[MID_BASELINE_PROPERTY])
    seam = np.isclose(lon, 180.0)
    if seam.any():
        mask[:, seam] = False

    if ind.is_change:
        _to_change(arrays)
    if clipped:
        print(
            f"  {ind.transform}: clipped {clipped:,} cell-values at the distribution tail "
            f"(counted on the native grid, before coarsening; they lose their spread "
            f"— see transforms.py)"
        )

    idx = np.argwhere(mask)
    if limit is not None:
        idx = idx[:limit]

    out_path = Path(out_path) if out_path else default_output(ind, factor)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Same precision the live importer's `stat_fmt` gives this unit; NaN cells become null.
    fmt = formatting.formatter(ind.unit)

    n = 0
    with out_path.open("w") as f:
        for i, j in idx:
            props: dict[str, float | int | None] = {}
            for name in names:
                props[name] = fmt(float(arrays[name][i, j]))
            feature = {
                "type": "Feature",
                "properties": props,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [cell_ring(float(lon[j]), float(lat[i]), half=half)],
                },
            }
            f.write(json.dumps(feature, separators=(",", ":")))
            f.write("\n")
            if on_feature is not None:
                on_feature(float(lon[j]), float(lat[i]), props)
            n += 1
            if progress_every and n % progress_every == 0:
                print(f"  {n:,} features…")

    return out_path, n
