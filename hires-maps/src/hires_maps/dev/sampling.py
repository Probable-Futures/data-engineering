"""DEV-ONLY point sampling of a warming-level store, for `explore.py`.

Not on the build path — the builder works on whole arrays. These pick single cells or summarise
one, which is what a human poking at the data wants and the pipeline never needs.
"""

from __future__ import annotations

import numpy as np
import xarray as xr


def area_weighted_mean(da: xr.DataArray) -> float:
    """Mean over finite cells weighted by cell area (~cos(lat)); the honest 'typical over land'."""
    lat = da["lat"].values
    w = np.cos(np.deg2rad(lat))
    shape = [1] * da.ndim
    shape[da.dims.index("lat")] = lat.size
    weights = np.broadcast_to(w.reshape(shape), da.shape)
    a = da.values
    m = np.isfinite(a)
    return float((a[m] * weights[m]).sum() / weights[m].sum())


def value_at(da: xr.DataArray, lat: float, lon: float, max_deg: float = 0.6) -> xr.DataArray:
    """Value(s) at the nearest cell to (lat, lon); snaps to the nearest land cell if the
    closest one is ocean (NaN). Keeps any wl/stat axes intact."""
    near = da.sel(lat=lat, lon=lon, method="nearest")
    if not np.all(np.isnan(np.asarray(near.values))):
        return near
    latv, lonv = da["lat"].values, da["lon"].values
    li = np.where(np.abs(latv - lat) <= max_deg)[0]
    lj = np.where(np.abs(lonv - lon) <= max_deg)[0]
    if li.size == 0 or lj.size == 0:
        return near
    block = da.isel(lat=li, lon=lj)
    ref = block
    for extra in ("wl", "stat"):
        if extra in ref.dims:
            ref = ref.isel({extra: 0})
    mask = np.isfinite(np.asarray(ref.values))
    if not mask.any():
        return near  # genuinely no land nearby
    la, lo = np.meshgrid(block["lat"].values, block["lon"].values, indexing="ij")
    dist = (la - lat) ** 2 + (lo - lon) ** 2
    dist[~mask] = np.inf
    ii, jj = np.unravel_index(int(np.argmin(dist)), dist.shape)
    return block.isel(lat=ii, lon=jj)
