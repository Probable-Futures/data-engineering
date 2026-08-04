#!/usr/bin/env python3
"""
Inspect any Zarr or netCDF store and print a plain-English structure summary.

    python inspect_store.py <path-to-.zarr-or-.nc>
    python inspect_store.py --indicator days-above-35c        # new-data shortcut
    python inspect_store.py --climatology tasmax              # climatology shortcut

Works on the new 0.1 deg Zarr stores, the old 0.2 deg netCDFs, and even
partially-downloaded stores (it reports what it can and flags the rest).
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import xarray as xr

import lib

warnings.filterwarnings("ignore")


def _fmt_coord(ds, name):
    v = ds[name].values
    if v.ndim == 0:
        return f"    {name:12s} scalar = {float(v):g} {ds[name].attrs.get('units','')}".rstrip()
    try:
        step = abs(float(v[1]) - float(v[0]))
        return (f"    {name:12s} {v.min():.3f} -> {v.max():.3f} "
                f"(n={v.size}, step~{step:.3f})")
    except Exception:
        return f"    {name:12s} n={v.size}"


def describe(path: Path):
    path = Path(path)
    is_zarr = path.suffix == ".zarr" or (path.is_dir())
    print(f"\n=== {path} ===")
    print(f"type: {'Zarr' if is_zarr else 'netCDF'}")
    try:
        ds = xr.open_zarr(path) if is_zarr else xr.open_dataset(path)
    except Exception as e:
        print(f"!! could not open: {e}")
        print("   (a partially-downloaded store can fail here — check the folder"
              " has zarr.json + coordinate arrays)")
        return

    print(f"dimensions : {dict(ds.sizes)}")
    print(f"data vars  : {list(ds.data_vars)}")
    print("coordinates:")
    for c in ds.coords:
        print(_fmt_coord(ds, c))

    for var in ds.data_vars:
        # da is the DataArray for this variable
        da = ds[var]
        # a is the raw numpy array of values for this variable
        # in the zarr folder, a variable is stored as a chunked array, but here we just want the whole thing
        a = da.values
        # pct_nan is the percentage of NaN values in the array, which indicates missing data
        pct_nan = 100.0 * np.isnan(a).mean() if a.size else float("nan")
        # units is the units attribute of the variable, if it exists; otherwise, it's set to "?"
        units = da.attrs.get("units", "?")
        print(f"\n  variable '{var}'  dims={da.dims}  shape={da.shape}  units={units}")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            print(f"    min={np.nanmin(a):.3g}  mean={np.nanmean(a):.3g}  "
                  f"max={np.nanmax(a):.3g}  NaN(ocean/no-data)={pct_nan:.1f}%")
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", nargs="?", help="path to a .zarr folder or .nc file")
    ap.add_argument("--indicator", help="new-data indicator slug (e.g. days-above-35c)")
    ap.add_argument("--climatology", help="climatology variable (e.g. tasmax)")
    args = ap.parse_args()

    if args.indicator:
        describe(lib.new_store_path(args.indicator))
    elif args.climatology:
        describe(lib.climatology_store_path(args.climatology))
    elif args.path:
        describe(Path(args.path))
    else:
        ap.error("give a path, --indicator, or --climatology")
        sys.exit(2)


if __name__ == "__main__":
    main()
