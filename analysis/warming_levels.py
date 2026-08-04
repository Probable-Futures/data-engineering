#!/usr/bin/env python3
"""
Estimate when the new data reaches each warming level, and suggest year-windows.

    python warming_levels.py
    python warming_levels.py --window 8      # +/- years around each crossing

Warming levels (1.0, 1.5, 2.0, 2.5, 3.0 °C) are the axis the CURRENT maps use, but
the new data is calendar years. This tool computes the new data's own warming curve
(area-weighted land-mean average temperature per year, vs the 1971-2000 baseline),
finds the year each level is first crossed, and prints a candidate window to feed into
`compare_baseline.py --wl X --period YYYY-YYYY`.

IMPORTANT CAVEAT: official warming levels are defined on the GLOBAL (land + ocean) mean.
This data is land-only, and land warms faster than ocean, so these crossings are too
EARLY versus the true global definition. Treat as a rough guide and confirm the official
breaching years with the science team (Carlos).
"""
from __future__ import annotations

import argparse
import warnings

import numpy as np

import lib

warnings.filterwarnings("ignore")

LEVELS = [1.0, 1.5, 2.0, 2.5, 3.0]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--window", type=int, default=8,
                    help="half-width in years of the suggested window around each crossing")
    args = ap.parse_args()

    da = lib.open_new("average-temperature")          # °C per year
    years = da["time"].dt.year.values
    # area-weighted land-mean per year
    curve = np.array([lib.area_weighted_mean(da.isel(time=i)) for i in range(da.sizes["time"])])
    base = curve[(years >= 1971) & (years <= 2000)].mean()
    anom = curve - base

    print(f"\nWarming curve from new data (area-weighted land-mean average temperature)")
    print(f"  1971-2000 baseline = {base:.2f} °C  |  {years[0]}: {anom[0]:+.2f}  "
          f"{years[-1]}: {anom[-1]:+.2f}")
    print(f"\n  level   first-crossed   suggested window (±{args.window}y)   "
          f"-> compare command")
    rows = []
    for lvl in LEVELS:
        idx = np.argmax(anom >= lvl) if np.any(anom >= lvl) else None
        if idx is None:
            print(f"  +{lvl:.1f}°C   not reached")
            continue
        yr = int(years[idx])
        lo, hi = yr - args.window, yr + args.window
        rows.append((lvl, yr, lo, hi))
        print(f"  +{lvl:.1f}°C   {yr}            {lo}-{hi}"
              f"            --wl {lvl:g} --period {lo}-{hi}")

    # plot
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.plot(years, anom, color="#cc3311", lw=2)
    ax.axhline(0, color="k", lw=0.8)
    for lvl, yr, lo, hi in rows:
        ax.axhline(lvl, color="#888", ls=":", lw=1)
        ax.axvspan(lo, hi, color="#4477aa", alpha=0.12)
        ax.plot(yr, lvl, "o", color="#cc3311")
        ax.annotate(f"+{lvl:g}°C  {yr}", (yr, lvl), textcoords="offset points",
                    xytext=(5, -12), fontsize=9)
    ax.set_title("New data warming curve — land-mean temp anomaly vs 1971-2000\n"
                 "(land-only → crosses EARLIER than the official global definition)")
    ax.set_xlabel("year"); ax.set_ylabel("°C above 1971-2000 baseline"); ax.grid(alpha=0.3)
    fig.tight_layout()
    out = lib.OUT_DIR / "warming_levels.png"
    fig.savefig(out, dpi=130); plt.close(fig)
    print(f"\nwrote {out}")
    print("\nReminder: land-only crossings run early; confirm official breaching years with Carlos.")


if __name__ == "__main__":
    main()
