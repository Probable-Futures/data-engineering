#!/usr/bin/env python3
"""
Render the new downscaled data as PNG maps — a global view and a regional crop.

    python quicklook.py --indicator days-above-35c --year 2050
    python quicklook.py --indicator days-above-35c --period 1971-2000
    python quicklook.py --climatology tasmax
    python quicklook.py --indicator days-above-35c --year 2050 --region 25,60,12,42

Outputs land in analysis/out/. Ocean / no-data shows as light gray.
"""
from __future__ import annotations

import argparse
import warnings

import lib

warnings.filterwarnings("ignore")


def _select(da, year, period):
    if year is not None:
        return da.sel(time=str(year), method="nearest"), f"{year}"
    if period is not None:
        lo, hi = period.split("-")
        return da.sel(time=slice(lo, hi)).mean("time", skipna=True), f"{lo}-{hi} average"
    # default: most recent year
    return da.isel(time=-1), str(da["time"].dt.year.values[-1])

# since 1961 till 2100, we have for every location 139 years of aggreagated data.
# we have 1801 * 3601 = 6483601 locations , and for each location we have 139 years of data, so the total number of data points is 6483601 * 139 = 901,000,539. This is a large dataset, but it is manageable with modern computing resources. This includes the ocean, which is blank. ocean data represents around =65.9% of the data. Therefore, the land data represents around 34.1% of the data. The land data is around 307,000,000 data points. This is still a large dataset, but it is manageable with modern computing resources.

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--indicator", help="annual-aggregate slug, e.g. days-above-35c")
    g.add_argument("--climatology", help="raw climatology var, e.g. tasmax")
    ap.add_argument("--year", type=int, help="calendar year to render")
    ap.add_argument("--period", help="YYYY-YYYY to average (e.g. 1971-2000)")
    ap.add_argument("--region", help="lon0,lon1,lat0,lat1 crop (default Middle East)")
    ap.add_argument("--cmap", default="inferno")
    args = ap.parse_args()

    
    region = tuple(float(x) for x in args.region.split(",")) if args.region else lib.DEFAULT_REGION

    if args.climatology:
        da = lib.open_climatology(args.climatology)
        label = args.climatology
        unit = da.attrs.get("units", "")
        when = "1971-2010 average"
        stem = f"climatology_{args.climatology}"
    else:
        ind = lib.INDICATORS.get(args.indicator)
        label = ind.label if ind else args.indicator
        unit = ind.unit if ind else ""
        da = lib.open_new(args.indicator)
        da, when = _select(da, args.year, args.period)
        stem = f"{args.indicator}_{when.replace(' ', '_')}"

    landmean = lib.land_mean(da)
    print(f"{label} — {when}: land-mean = {landmean:.2f} {unit}")

    g_path = lib.OUT_DIR / f"{stem}_global.png"
    r_path = lib.OUT_DIR / f"{stem}_region.png"
    lib.plot_map(da, f"{label} — {when} (global, 0.1°)", unit, g_path, cmap=args.cmap)
    lib.plot_map(da, f"{label} — {when} (regional, 0.1°)", unit, r_path,
                 region=region, cmap=args.cmap)
    print(f"wrote {g_path}")
    print(f"wrote {r_path}")


if __name__ == "__main__":
    main()
