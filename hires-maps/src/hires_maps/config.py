"""Paths and constants shared across the package.

The new data lives outside this repo; point at it with $PF_DOWNSCALED_DATA if it is not at
the default location.
"""

from __future__ import annotations

import os
from pathlib import Path

# The data-engineering repo root (hires-maps/src/hires_maps/config.py -> repo root).
REPO_ROOT = Path(__file__).resolve().parents[3]

# Where the GeoJSON build output goes — the same folder the vector-tiles uploader reads.
MTS_DIR = REPO_ROOT / "data" / "mapbox" / "mts"

# The currently-live maps, exported from the production database as `{live_id}.geojsonld` on the
# 0.2° grid. A subfolder of MTS_DIR, so the uploader (which looks for `{id}.geojsonld` directly in
# MTS_DIR) never picks these up by accident. Read by `livemaps.py` for the comparison maps.
LIVE_MAPS_DIR = MTS_DIR / "old-geojson"

# Where the comparison maps (new minus live) are written — a sibling of LIVE_MAPS_DIR, so the two
# halves of a comparison sit next to each other and neither crowds the hi-res builds in MTS_DIR.
# `vector-tiles` reads this folder via the `--diff` flag (see DIFF_SUBDIR in hires.ts); the two
# names have to stay in step.
DIFF_MAPS_DIR = MTS_DIR / "diff-geojson"

# Root of the downloaded downscaled data (contains warming_levels_aggregates/, climatologies/, ...)
DATA_ROOT = Path(
    os.environ.get("PF_DOWNSCALED_DATA", str(Path.home() / "work" / "pf-downscaled-data"))
)
WL_ROOT = DATA_ROOT / "warming_levels_aggregates"

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
