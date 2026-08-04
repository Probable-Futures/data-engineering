#!/usr/bin/env python3
"""
Drill into specific locations: how an indicator changes across 1961 -> 2099.

    python timeseries.py --indicator days-above-35c --places Beirut,Cairo,Delhi
    python timeseries.py --indicator days-above-35c --places Beirut --smooth 10

Renders a line chart (PNG) and prints a table of the values. This is the tool
that makes the change tangible for a non-technical / client audience.
"""
from __future__ import annotations

import argparse
import warnings

import numpy as np

import lib

warnings.filterwarnings("ignore")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--indicator", required=True, help="e.g. days-above-35c")
    ap.add_argument("--places", default="Beirut",
                    help="comma-separated names from lib.PLACES, or lat:lon pairs")
    ap.add_argument("--smooth", type=int, default=1,
                    help="rolling-mean window in years (default 1 = raw)")
    args = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ind = lib.INDICATORS.get(args.indicator)
    label = ind.label if ind else args.indicator
    unit = ind.unit if ind else ""
    # da is a DataArray with dims (time, lat, lon). for example:
    #   time: 1961-01-01, ..., 2099-12-31
    #   lat:   -90.0, ..., 90.0
    #   lon:   -180.0, ..., 180.0
    # da is the main data structure that holds the downscaled climate indicator values for each time point and location. it is a 3D array where the first dimension corresponds to time, the second dimension corresponds to latitude, and the third dimension corresponds to longitude. this allows us to access the indicator values for any specific year and location by indexing into the array using the appropriate time, lat, and lon indices.
    da = lib.open_new(args.indicator)
    # years is a 1D array of the years corresponding to the time dimension of da. for example:
    #   years: 1961, 1962, ..., 2099
    # this allows us to plot the time series for each location and print the values for specific years.
    # this is possibgle because the time dimension of da is a datetime64 array, and we can extract the year component using the dt accessor.
    # to even simplify your understanding, the dt accessor is a property of the datetime64 array that allows us to access various components of the date, such as year, month, day, etc. in this case, we are only interested in the year component, so we use da["time"].dt.year to get an array of years corresponding to each time point in the data array.
    years = da["time"].dt.year.values

    fig, ax = plt.subplots(figsize=(10, 5.5))
    print(f"\n{label} ({unit}) at each location:")
    print(f"{'place':12s} {'1961':>8s} {'2020':>8s} {'2050':>8s} {'2099':>8s}")
    for token in args.places.split(","):
        token = token.strip()
        if ":" in token:
            lats, lons = token.split(":")
            lat, lon = float(lats), float(lons)
            name = token
        else:
            if token not in lib.PLACES:
                print(f"  (skip unknown place '{token}'; known: {', '.join(lib.PLACES)})")
                continue
            lat, lon = lib.PLACES[token]
            name = token
        series = lib.at_point(da, lat, lon).values.astype(float)
        plot_series = series
        if args.smooth > 1:
            k = args.smooth
            plot_series = np.convolve(series, np.ones(k) / k, mode="same")
        ax.plot(years, plot_series, label=name, linewidth=2)

        def val(y):
            i = int(np.argmin(np.abs(years - y)))
            return series[i]
        print(f"{name:12s} {val(1961):8.1f} {val(2020):8.1f} {val(2050):8.1f} {val(2099):8.1f}")

    ax.set_title(f"{label} — 1961 to 2099 (new downscaled data)")
    ax.set_xlabel("year"); ax.set_ylabel(f"{label} ({unit})")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    out = lib.OUT_DIR / f"{args.indicator}_timeseries.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
