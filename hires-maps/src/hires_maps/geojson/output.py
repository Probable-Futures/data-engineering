"""Serialisation and naming: a `Grid` -> `.geojsonld` on disk, at the path the uploader reads.

Knows about JSON, filenames and cell geometry; nothing about units, warming levels or transforms —
that is `stages.py`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path

import numpy as np

from ..config import DIFF_MAPS_DIR, ERA5_MAPS_DIR, GRID_STEP_DEG, MTS_DIR
from ..geometry import cell_ring
from ..indicators import Indicator
from .stages import Grid


class Variant(StrEnum):
    """Which pyramid a build belongs to. Mirrors `PyramidVariant` in `vector-tiles/hires.ts`, and
    the spelling is the contract: it is the infix in every filename both sides agree on."""

    HIRES = "hires"
    DIFF = "diff"
    ERA5 = "era5"
    # ERA5 used as the yardstick rather than as a map in its own right. Positive (red) means our
    # data reads HIGHER than the observations — the same reading as DIFF, where red means the
    # first-named dataset is higher.
    #   ERA5_V3 -> `v3 - ERA5` on the live 0.2° grid: how wrong the map we publish today is
    #   ERA5_V4 -> `v4 - ERA5` on the new 0.1° grid: whether the new data is closer to reality
    ERA5_V3 = "era5v3"
    ERA5_V4 = "era5v4"
    # The change indicators republished as ABSOLUTE maps: the five with an ERA5 counterpart
    # (40601, 40607, 40613, 40614, 40616), so they can sit beside maps that are absolute and have
    # no meaningful change form, plus 40703 and 40704 for completeness.
    #   ABS   -> v4, 0.1°: the store is already absolute, so the builder just skips `to_change`
    #   V3ABS -> v3, 0.2°: the change is baked into the published data, so `from_change` undoes it
    ABS = "abs"
    V3ABS = "v3abs"


# Variants written to their own folder rather than straight into MTS_DIR. The absolute builds sit
# in MTS_DIR alongside `hires`, since like `hires` they are the dataset's own values.
_VARIANT_DIRS = {
    Variant.DIFF: DIFF_MAPS_DIR,
    Variant.ERA5: ERA5_MAPS_DIR,
    Variant.ERA5_V3: ERA5_MAPS_DIR,
    Variant.ERA5_V4: ERA5_MAPS_DIR,
}


def rung_suffix(factor: int, step: float = GRID_STEP_DEG) -> str:
    """The pyramid rung's filename suffix: native is bare, coarser rungs are named by their size.

    `step` is the *native* cell size; the suffix reports the rung's own size in tenths of a degree.
    On the 0.1° grid that reproduces the existing `-p02` / `-p08` names exactly. On ERA5's 0.25°
    grid it gives `-p05` (0.5°) and `-p10` (1.0°). Native is always bare, which is why 0.25° never
    needs an awkward two-digit name of its own.
    """
    return "" if factor == 1 else f"-p{round(step * factor * 10):02d}"


def output_path(
    ind: Indicator,
    factor: int = 1,
    *,
    variant: Variant = Variant.HIRES,
    step: float = GRID_STEP_DEG,
) -> Path:
    """Where a build lands when the caller gives no `--out`.

        HIRES   -> `mts/{live_id}-hires[-pNN].geojsonld`
        DIFF    -> `mts/diff-geojson/{live_id}-diff[-pNN].geojsonld`
        ERA5    -> `mts/era5-geojson/{live_id}-era5[-pNN].geojsonld`
        ERA5_V3 -> `mts/era5-geojson/{live_id}-era5v3.geojsonld`
        ERA5_V4 -> `mts/era5-geojson/{live_id}-era5v4[-pNN].geojsonld`
        ABS     -> `mts/{live_id}-abs[-pNN].geojsonld`
        V3ABS   -> `mts/{live_id}-v3abs.geojsonld`

    Note which variants take a `step` and which must not. ERA5_V3 and V3ABS sit on the 0.2° lattice
    and pass `step=V3_STEP_DEG`; ERA5 passes `step=ERA5_STEP_DEG`. **ERA5_V4, DIFF, HIRES and ABS
    are all native 0.1°, so they keep the `GRID_STEP_DEG` default** — passing 0.2 for ERA5_V4 would
    name its rungs `-p04`/`-p16` instead of the `-p02`/`-p08` that `hires.ts` looks for, and the
    upload would fail only after the native file had been sent.

    All sit under a NEW `-hires`/`-diff`/`-era5` id so production tilesets are never overwritten.
    The diff folder is a sibling of the `old-geojson/` folder its live half is read from, so both
    halves of a comparison sit together, and the era5 folder is a sibling of both; `vector-tiles`
    hardcodes those folder names, so they are a contract.
    """
    directory = _VARIANT_DIRS.get(variant, MTS_DIR)
    return directory / f"{ind.live_id}-{variant}{rung_suffix(factor, step)}.geojsonld"


def write_features(
    out_path: Path,
    grid: Grid,
    mask: np.ndarray,
    fmt: Callable[[float], float | int | None],
    *,
    limit: int | None = None,
    progress_every: int = 250_000,
    on_feature: Callable[[float, float, dict], None] | None = None,
) -> tuple[Path, int]:
    """Write one Feature per masked cell as newline-delimited GeoJSON. Returns (path, count).

    Shared by the hi-res builder and the comparison builder so the two can never disagree about
    geometry, property order, or how a non-finite value is serialised (always `null`).

    Property order is `grid.slices` insertion order, which is `mapping.property_plan` order — every
    stage assigns to keys that already exist, so nothing can reorder it downstream.
    """
    idx = np.argwhere(mask)
    if limit is not None:
        idx = idx[:limit]

    half = grid.half
    lat, lon = grid.lat, grid.lon
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out_path.open("w") as f:
        for i, j in idx:
            props: dict[str, float | int | None] = {}
            for name, a in grid.slices.items():
                props[name] = fmt(float(a[i, j]))
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
