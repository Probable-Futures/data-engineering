"""Read the **currently-live** maps — the 0.2° `.geojsonld` exports under `LIVE_MAPS_DIR`.

This is the "old" half of the comparison maps (`geojson/diff_builder.py`). We read the published
GeoJSON rather than the source netCDFs on purpose: these files hold the numbers that are actually
on probablefutures.org today, so a difference against them is a difference against what users see.
(The netCDFs would also work for a handful of indicators, but only `days-above-35c` is on disk, and
`data/woodwell/water_module/` is empty — no precipitation or drought maps at all.)

## The grid, and why the lookup is exact

The live grid and the new 0.1° grid are **centre-aligned**: every live cell centre lands exactly on
a new cell centre. Verified against both the netCDF coordinates and these GeoJSON polygons — the
nearest new index for live cell *k* is exactly `2 + 2k` on both axes (max error 2.8e-14), and 0 of
20,000 sampled polygon centres were off the 0.2° grid. So mapping between the grids is integer
arithmetic: no interpolation, no `reindex`, no scipy.

|      | live                              | new                                |
|------|-----------------------------------|------------------------------------|
| lat  | 899 cells, 89.8 → -89.8, step 0.2 | 1801 cells, 90.0 → -90.0, step 0.1 |
| lon  | 1799 cells, -179.8 → 179.8        | 3601 cells, -180.0 → 180.0         |

The grids are centre-aligned but **not nested**, which leaves one wrinkle: a new cell at an odd
index sits exactly on the boundary between two live cells and is equidistant from both. The tie has
to break somewhere, so `parent_index` breaks it consistently upwards (southward for latitude,
eastward for longitude). One consequence at the poles: a new cell more than half a live cell outside
the live grid gets **no** parent (index -1) rather than borrowing the nearest one, so the diff there
is null instead of a half-cell extrapolation.

## Value conventions in these files

- Properties are `data_{baseline,1c,1_5c,2c,2_5c,3c}_{low,mid,high}`. Some exports carry extra
  `data_*_mean` or `data_*_median` columns (40601 and 40101 respectively, 24 properties instead of
  18); only the low/mid/high triplet is present in every file, so that is all we read.
- Values are already quantised the way `stat_fmt` writes them — integers for °C/days/mm/%, one
  decimal for the z-score map.
- **Change maps put the ABSOLUTE baseline in the 0.5 °C slot** and the change in the others; e.g.
  40601 has `data_baseline_mid` ≈ 744 mm alongside `data_1c_mid` ≈ +24 mm. `diff_builder` handles
  that asymmetry; this module just reports the numbers as they are.
- `-99999` (error) and `-88888` (barren land) are sentinels, not data — see `ERROR_VALUE` /
  `BARREN_LAND_VALUE` in `vector-tiles/configs.ts`. They are read as no-data.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .config import LIVE_MAPS_DIR

# The live grid: northernmost/westernmost cell centre, cell size, and shape.
LAT0 = 89.8
LON0 = -179.8
STEP = 0.2
SHAPE = (899, 1799)

# Anything at or below this is a sentinel (-88888 barren land, -99999 error), not a value.
NO_DATA_MAX = -88888.0


@dataclass
class LoadReport:
    """What `load` saw — worth printing, since a silent mismatch here would skew every diff."""

    features: int  # lines read
    off_grid: int  # polygon centres that did not land on the live grid
    sentinels: int  # values dropped as -88888 / -99999
    filled: dict[str, int]  # cells populated, per property
    missing_properties: list[str]  # properties this export does not carry at all

    def summary(self) -> str:
        mid = self.filled.get("data_baseline_mid", 0)
        parts = [f"{self.features:,} live features, {mid:,} cells with a baseline mid value"]
        if self.off_grid:
            parts.append(f"{self.off_grid:,} off-grid (skipped)")
        if self.sentinels:
            parts.append(f"{self.sentinels:,} sentinel values (read as no-data)")
        if self.missing_properties:
            parts.append(f"absent from this export: {', '.join(self.missing_properties)}")
        return " | ".join(parts)


def live_path(live_id: str) -> Path:
    """Filesystem path to one live map's export, e.g. `.../old-geojson/40105.geojsonld`."""
    return LIVE_MAPS_DIR / f"{live_id}.geojsonld"


def available() -> list[str]:
    """Live map ids that have an export on disk."""
    if not LIVE_MAPS_DIR.exists():
        return []
    return sorted(p.stem for p in LIVE_MAPS_DIR.glob("*.geojsonld"))


# Both grids lie on the same 0.1° lattice, so all the index arithmetic below is done in integer
# tenths of a degree. Doing it in floating point does not work: (89.8 - 89.7) / 0.2 evaluates to
# 0.49999999999999994, so a coordinate that is exactly on a cell boundary would fall to whichever
# side the rounding error happened to land on — a half-cell shift that varies across the map.
_TENTHS_LAT0 = 898  # 89.8 * 10
_TENTHS_LON0 = -1798  # -179.8 * 10
_TENTHS_STEP = 2  # 0.2 * 10


def _tenths(coords: np.ndarray | float) -> np.ndarray:
    """Coordinates as exact integer tenths of a degree."""
    return np.rint(np.asarray(coords, dtype=float) * 10.0).astype(np.int64)


def _offsets(coords: np.ndarray | float, axis: str) -> tuple[np.ndarray, int]:
    """(distance from the grid origin in tenths, number of cells along that axis)."""
    if axis == "lat":
        return _TENTHS_LAT0 - _tenths(coords), SHAPE[0]  # latitude runs north -> south
    if axis == "lon":
        return _tenths(coords) - _TENTHS_LON0, SHAPE[1]
    raise ValueError(f"axis must be 'lat' or 'lon', got {axis!r}")


def cell_index(lat: float, lon: float) -> tuple[int, int]:
    """(row, col) of the live cell centred at (lat, lon), or -1 for an axis that is off the grid.

    "Off the grid" means the coordinate is not a live cell centre at all — an odd number of tenths
    from the origin. Measured on the real exports: 0 of 20,000 cells, but a silent half-cell offset
    here would corrupt every comparison, so it is checked rather than assumed.
    """
    out = []
    for coord, axis in ((lat, "lat"), (lon, "lon")):
        delta, count = _offsets(coord, axis)
        index = int(delta) // _TENTHS_STEP
        on_grid = int(delta) % _TENTHS_STEP == 0
        out.append(index if on_grid and 0 <= index < count else -1)
    return out[0], out[1]


def parent_index(coords: np.ndarray, *, axis: str) -> np.ndarray:
    """For each new-grid coordinate, the index of the live cell covering it (-1 if none).

    Ties — a new cell exactly on the boundary between two live cells — break upwards: southward
    for latitude, eastward for longitude. `(delta + 1) // 2` on integer tenths is exactly
    round-half-up. Coordinates more than half a live cell outside the live grid get -1 rather than
    borrowing the edge cell, so the poles are null instead of extrapolated.
    """
    delta, count = _offsets(coords, axis)
    idx = (delta + 1) // _TENTHS_STEP
    return np.where((idx >= 0) & (idx < count), idx, -1)


def upsample(live: np.ndarray, rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
    """Expand a live (899, 1799) array onto the new grid using `parent_index` outputs.

    Rows/cols with no parent (-1) come back as NaN, so a diff there is null rather than a
    half-cell extrapolation.
    """
    out = live[np.ix_(np.clip(rows, 0, SHAPE[0] - 1), np.clip(cols, 0, SHAPE[1] - 1))]
    out = out.astype("float32", copy=True)
    out[rows < 0, :] = np.nan
    out[:, cols < 0] = np.nan
    return out


def load(live_id: str, names: Sequence[str]) -> tuple[dict[str, np.ndarray], LoadReport]:
    """Parse one live export into a (899, 1799) float32 array per property in `names`.

    Streamed line by line — these files are 250-320 MB each. Cells the export does not mention
    (ocean, and anywhere the live model had no value) stay NaN.
    """
    path = live_path(live_id)
    if not path.exists():
        raise FileNotFoundError(
            f"no live export for dataset {live_id} at {path}. "
            f"Available: {', '.join(available()) or '(none)'}"
        )

    arrays = {name: np.full(SHAPE, np.nan, dtype="float32") for name in names}
    filled = dict.fromkeys(names, 0)
    features = off_grid = sentinels = 0
    seen_properties: set[str] = set()

    with path.open() as fh:
        for line in fh:
            feature = json.loads(line)
            i, j = _centre_index(feature["geometry"]["coordinates"][0])
            if i < 0 or j < 0:
                off_grid += 1
                continue
            features += 1
            properties = feature["properties"]
            seen_properties.update(properties)
            for name in names:
                value = properties.get(name)
                if value is None:
                    continue
                if value <= NO_DATA_MAX:
                    sentinels += 1
                    continue
                arrays[name][i, j] = value
                filled[name] += 1

    report = LoadReport(
        features=features,
        off_grid=off_grid,
        sentinels=sentinels,
        filled=filled,
        missing_properties=[n for n in names if n not in seen_properties],
    )
    return arrays, report


def _centre_index(ring: Iterable[Sequence[float]]) -> tuple[int, int]:
    """Live cell (row, col) for a polygon ring, via its bounding-box centre."""
    lons = [point[0] for point in ring]
    lats = [point[1] for point in ring]
    lon = (min(lons) + max(lons)) / 2.0
    lat = (min(lats) + max(lats)) / 2.0
    return cell_index(lat, lon)
