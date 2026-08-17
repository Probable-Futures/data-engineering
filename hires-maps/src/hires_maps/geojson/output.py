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

from ..config import DIFF_MAPS_DIR, MTS_DIR
from ..geometry import cell_ring
from ..indicators import Indicator
from .stages import Grid


class Variant(StrEnum):
    """Which pyramid a build belongs to. Mirrors `PyramidVariant` in `vector-tiles/hires.ts`, and
    the spelling is the contract: it is the infix in every filename both sides agree on."""

    HIRES = "hires"
    DIFF = "diff"


def rung_suffix(factor: int) -> str:
    """The pyramid rung's filename suffix: native is bare, coarser rungs get `-p02` / `-p08`."""
    return "" if factor == 1 else f"-p{factor:02d}"


def output_path(ind: Indicator, factor: int = 1, *, variant: Variant = Variant.HIRES) -> Path:
    """Where a build lands when the caller gives no `--out`.

        HIRES -> `mts/{live_id}-hires[-pNN].geojsonld`
        DIFF  -> `mts/diff-geojson/{live_id}-diff[-pNN].geojsonld`

    Both sit under a NEW `-hires`/`-diff` id so production tilesets are never overwritten. The
    diff folder is a sibling of the `old-geojson/` folder its live half is read from, so both
    halves of a comparison sit together; `vector-tiles` hardcodes that folder name as
    `DIFF_SUBDIR`, so it is a contract.
    """
    directory = DIFF_MAPS_DIR if variant is Variant.DIFF else MTS_DIR
    return directory / f"{ind.live_id}-{variant}{rung_suffix(factor)}.geojsonld"


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
