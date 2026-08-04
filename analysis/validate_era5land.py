#!/usr/bin/env python3
"""
Validate the new data against real-world observations (ERA5-Land).

    python validate_era5land.py                 # both temperature + precipitation
    python validate_era5land.py --kind temperature

The science team already computed `downscaled climatology − ERA5-Land observations`
for temperature and precipitation. If the downscaling is good, this difference is ~0
everywhere. This script maps WHERE it isn't (mountains, coasts, deserts) and prints the
bias stats — a direct "how much should we trust this data?" QA artifact.
"""
from __future__ import annotations

import argparse
import warnings

import numpy as np

import lib

warnings.filterwarnings("ignore")


def run(kind: str):
    da = lib.open_era5land_diff(kind)
    unit = "°C" if kind == "temperature" else "mm/day (approx)"
    vals = da.values[np.isfinite(da.values)]
    wmean = lib.area_weighted_mean(da)

    print(f"\n{kind} — model minus ERA5-Land observations:")
    print(f"  area-weighted mean bias : {wmean:+.3f} {unit}")
    print(f"  median : {np.median(vals):+.3f}   std : {vals.std():.3f}   "
          f"p1..p99 : {np.percentile(vals,1):+.2f} .. {np.percentile(vals,99):+.2f}")
    print(f"  cells within ±0.5 {unit}: {100*np.mean(np.abs(vals)<=0.5):.1f}% of valid land")

    print("  worst-bias latitude bands (area-weighted):")
    lat = da["lat"].values
    desc = bool(lat[0] > lat[-1])
    for lo, hi in [(-90, -60), (-60, -30), (-30, 0), (0, 30), (30, 60), (60, 90)]:
        sub = da.sel(lat=slice(*sorted((lo, hi), reverse=desc)))
        v = sub.values[np.isfinite(sub.values)]
        if v.size:
            print(f"    {lo:+4d}..{hi:+4d}°: mean {lib.area_weighted_mean(sub):+.3f}  "
                  f"std {v.std():.3f}  (n={v.size})")

    g = lib.plot_map(da, f"{kind} bias: new climatology − ERA5-Land (global)", unit,
                     lib.OUT_DIR / f"validate_{kind}_global.png", diverging=True)
    r = lib.plot_map(da, f"{kind} bias vs ERA5-Land (regional)", unit,
                     lib.OUT_DIR / f"validate_{kind}_region.png",
                     region=lib.DEFAULT_REGION, diverging=True)
    print(f"wrote {g}")
    print(f"wrote {r}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kind", choices=["temperature", "precipitation", "both"], default="both")
    args = ap.parse_args()
    kinds = ["temperature", "precipitation"] if args.kind == "both" else [args.kind]
    for k in kinds:
        run(k)


if __name__ == "__main__":
    main()
