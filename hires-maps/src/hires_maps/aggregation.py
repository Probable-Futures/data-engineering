"""Coarsen the native 0.1° grid into the pyramid rungs (0.2° and 0.8° are published).

Phase 2 serves coarser cells at low zoom so tiles fit (see docs §8). Each rung is an
area-weighted N×N block average of the native grid — nesting perfectly, so the squares line up.

`factor` is cells-per-side per block: 2 → 0.2°, 4 → 0.4° (unused), 8 → 0.8°.
"""

from __future__ import annotations

import numpy as np


def _trim(n: int, factor: int) -> int:
    return (n // factor) * factor


def block_weighted_mean(a: np.ndarray, lat: np.ndarray, factor: int) -> np.ndarray:
    """Area-weighted (cos-lat) mean of every `factor`×`factor` block of a (lat, lon) array.

    NaN (ocean) cells are ignored; a block that is entirely NaN stays NaN.
    """
    nlat, nlon = _trim(a.shape[0], factor), _trim(a.shape[1], factor)
    a = a[:nlat, :nlon]
    w = np.cos(np.deg2rad(lat[:nlat]))[:, None]
    w = np.broadcast_to(w, a.shape)

    finite = np.isfinite(a)
    num = np.where(finite, a * w, 0.0).reshape(nlat // factor, factor, nlon // factor, factor)
    den = np.where(finite, w, 0.0).reshape(nlat // factor, factor, nlon // factor, factor)
    num = num.sum(axis=(1, 3))
    den = den.sum(axis=(1, 3))
    with np.errstate(invalid="ignore", divide="ignore"):
        out = num / den
    out[den == 0] = np.nan
    return out.astype("float32")


def block_centres(coord: np.ndarray, factor: int) -> np.ndarray:
    """Centre coordinate of each block (mean of the cells it covers)."""
    n = _trim(coord.size, factor)
    return coord[:n].reshape(-1, factor).mean(axis=1)


def coarsen(
    arrays: dict[str, np.ndarray], lat: np.ndarray, lon: np.ndarray, factor: int
) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray]:
    """Coarsen every property array by `factor`, returning (arrays, lat, lon) for the rung."""
    if factor == 1:
        return arrays, lat, lon
    coarse = {name: block_weighted_mean(a, lat, factor) for name, a in arrays.items()}
    return coarse, block_centres(lat, factor), block_centres(lon, factor)
