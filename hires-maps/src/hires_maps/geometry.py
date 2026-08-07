"""Turn a grid cell centre into its square polygon — the geometry of one map feature.

Each 0.1° cell is a square spanning ±half a step around its centre point. This mirrors the
`ST_MakeEnvelope` cell the current PostGIS pipeline builds, just computed directly.
"""

from __future__ import annotations

from .config import GRID_STEP_DEG

HALF = GRID_STEP_DEG / 2.0  # 0.05° for the 0.1° grid

# Ring corner type: a [lon, lat] pair.
Ring = list[list[float]]


def cell_ring(lon: float, lat: float, half: float = HALF, ndigits: int = 3) -> Ring:
    """Closed square ring (5 points, first == last) for the cell centred at (lon, lat).

    `half` is the cell half-width in degrees (0.05 for native 0.1° cells, 0.1 for a 0.2° rung,
    etc.). Coordinates are rounded to `ndigits` and clamped to valid lon/lat. Cells at the ±180°
    seam are handled by the builder (it skips the duplicate +180° column), so no wrapping here.
    """
    w = max(round(lon - half, ndigits), -180.0)
    e = min(round(lon + half, ndigits), 180.0)
    s = max(round(lat - half, ndigits), -90.0)
    n = min(round(lat + half, ndigits), 90.0)
    return [[w, s], [e, s], [e, n], [w, n], [w, s]]
