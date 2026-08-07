"""Build a `.geojsonld` file directly from a warming-level Zarr store.

Output is newline-delimited GeoJSON (one Feature per line) — the exact format the
`vector-tiles` uploader ingests — with property names matching the current live maps
(`data_baseline_mid`, `data_1c_mid`, ...). So the existing recipes and styles need no changes.

One feature per land cell; ocean/NaN cells are skipped. Values are rounded to 1 decimal
(matching the current `numeric(6,1)` columns).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import numpy as np

from .. import stores
from ..aggregation import coarsen
from ..config import MTS_DIR
from ..geometry import cell_ring
from ..indicators import Indicator, get
from ..mapping import MID_BASELINE_PROPERTY, property_plan


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

    # Coarsen to the requested pyramid rung (no-op for factor 1).
    arrays, lat, lon = coarsen(arrays, lat, lon, factor)
    names = [name for name, _, _ in plan]
    half = 0.05 * factor  # cell half-width in degrees for this rung

    # Land mask from the baseline mid value; skip the duplicate +180° seam column.
    mask = np.isfinite(arrays[MID_BASELINE_PROPERTY])
    seam = np.isclose(lon, 180.0)
    if seam.any():
        mask[:, seam] = False

    idx = np.argwhere(mask)
    if limit is not None:
        idx = idx[:limit]

    out_path = Path(out_path) if out_path else default_output(ind, factor)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n = 0
    with out_path.open("w") as f:
        for i, j in idx:
            props: dict[str, float | None] = {}
            for name in names:
                v = arrays[name][i, j]
                props[name] = round(float(v), 1) if np.isfinite(v) else None
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
