"""Paths and constants shared across the package.

The new data lives outside this repo; point at it with $PF_DOWNSCALED_DATA if it is not at
the default location.
"""

from __future__ import annotations

import os
from pathlib import Path

MTS_DIR_ENV = "PF_MTS_DIR"


def _find_mts_dir() -> Path:
    """Locate `data/mapbox/mts`, the folder the vector-tiles uploader reads.

    Found by walking up from this file (and from the working directory, for an installed wheel)
    for a parent holding `vector-tiles/`. That directory is the marker because it is tracked and
    because it names the actual coupling — `vector-tiles/utils.ts` resolves the same path from its
    side. `data/mapbox` itself is gitignored, so it cannot be the marker: it does not exist in a
    fresh clone until the first build writes it.

    Set $PF_MTS_DIR to skip the search. Deliberately never raises — `hires-maps --help` and every
    unit test import this module without touching disk — so a failed search falls back to a
    concrete path under the working directory, and the first write is what fails, with the path
    it tried in the message.
    """
    override = os.environ.get(MTS_DIR_ENV)
    if override:
        return Path(override)
    for start in (Path(__file__).resolve().parent, Path.cwd().resolve()):
        for parent in (start, *start.parents):
            if (parent / "vector-tiles").is_dir():
                return parent / "data" / "mapbox" / "mts"
    return Path.cwd() / "data" / "mapbox" / "mts"


# Where the GeoJSON build output goes — the same folder the vector-tiles uploader reads.
MTS_DIR = _find_mts_dir()

# The currently-live maps, exported from the production database as `{live_id}.geojsonld` on the
# 0.2° grid. A subfolder of MTS_DIR, so the uploader (which looks for `{id}.geojsonld` directly in
# MTS_DIR) never picks these up by accident. Read by `livemaps.py` for the comparison maps.
LIVE_MAPS_DIR = MTS_DIR / "old-geojson"

# Where the comparison maps (new minus live) are written — a sibling of LIVE_MAPS_DIR, so the two
# halves of a comparison sit next to each other and neither crowds the hi-res builds in MTS_DIR.
# `vector-tiles` reads this folder via the `--diff` flag (see DIFF_SUBDIR in hires.ts); the two
# names have to stay in step.
DIFF_MAPS_DIR = MTS_DIR / "diff-geojson"

# Where ERA5 builds land: the standalone ERA5 maps and (later) both comparison families. A sibling
# of DIFF_MAPS_DIR for the same reason — `vector-tiles` reads this folder by name, so it is a
# contract; see ERA5_SUBDIR in hires.ts once that side is wired up.
ERA5_MAPS_DIR = MTS_DIR / "era5-geojson"

# Root of the downloaded downscaled data (contains warming_levels_aggregates/, climatologies/, ...)
DATA_ROOT = Path(
    os.environ.get("PF_DOWNSCALED_DATA", str(Path.home() / "work" / "pf-downscaled-data"))
)
WL_ROOT = DATA_ROOT / "warming_levels_aggregates"

# The ERA5 reanalysis files: one netCDF per indicator, named `era5_{slug}_wls.nc`. Read by
# `era5.py`. Unlike everything else here these are netCDF, not Zarr, and they are on their own
# 0.25° grid — see the module docstring there for the three ways they differ from the Zarr stores.
ERA5_DIR = DATA_ROOT / "era5"

# ERA5's grid step, and the only two warming levels observations can cover (the record reaches
# ~1.2 °C of warming, so there is no observed 2 °C or 3 °C world to aggregate).
ERA5_STEP_DEG = 0.25
ERA5_WARMING_LEVELS: tuple[float, ...] = (0.5, 1.0)

# The store filename inside each indicator folder is "<slug>_<STORE_SUFFIX>".
STORE_SUFFIX = "MPI-ESM1-2-HR_ww-isimip_ssp585_wls.zarr"

# The six warming levels every store carries (0.5 is the 1971-2000 baseline).
WARMING_LEVELS: tuple[float, ...] = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0)

# The six statistics stored along the `stat` axis.
STATS: tuple[str, ...] = ("min", "p5", "p50", "p95", "max", "mean")

# Warming level -> the property-name prefix the live-map GeoJSON/styles use.
# (Same mapping the current database views apply: 0.5->baseline, 1.0->1c, ...)
WL_PREFIX: dict[float, str] = {
    0.5: "baseline",
    1.0: "1c",
    1.5: "1_5c",
    2.0: "2c",
    2.5: "2_5c",
    3.0: "3c",
}

# Global 0.1-degree grid; each cell is a square +/- half a step around its centre point.
GRID_STEP_DEG = 0.1
