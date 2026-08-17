"""The shared IO layer: find and open the warming-level Zarr stores.

Everything that reads the new data goes through here, so the dev tools and the (future)
GeoJSON/DB writers all open the data the same way.
"""

from __future__ import annotations

from pathlib import Path

import xarray as xr

from .config import STORE_SUFFIX, WL_ROOT


def store_path(slug: str) -> Path:
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
