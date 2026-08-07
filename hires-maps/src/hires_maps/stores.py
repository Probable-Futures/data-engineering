"""The shared IO layer: find and open the warming-level Zarr stores.

Everything that reads the new data goes through here, so the dev tools and the (future)
GeoJSON/DB writers all open the data the same way.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr

from .config import STORE_SUFFIX, WL_ROOT


def store_path(slug: str) -> Path:
    """Filesystem path to an indicator's warming-level Zarr store."""
    return WL_ROOT / slug / f"{slug}_{STORE_SUFFIX}"


def list_on_disk() -> list[str]:
    """Indicator slugs that actually have a folder under warming_levels_aggregates/."""
    if not WL_ROOT.exists():
        return []
    return sorted(p.name for p in WL_ROOT.iterdir() if p.is_dir() and not p.name.startswith("."))


def open_store(slug: str) -> xr.Dataset:
    """Open a warming-level store, with coords normalised to lat/lon."""
    ds = xr.open_zarr(store_path(slug))
    rename = {}
    if "latitude" in ds.dims:
        rename["latitude"] = "lat"
    if "longitude" in ds.dims:
        rename["longitude"] = "lon"
    return ds.rename(rename) if rename else ds


def value_var(slug: str) -> str:
    """The absolute-value variable name inside the store (e.g. 'days_above_35c')."""
    return slug.replace("-", "_")


def diff_var(slug: str) -> str:
    """The change-from-baseline variable name (e.g. 'diff_days_above_35c')."""
    return f"diff_{value_var(slug)}"


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
