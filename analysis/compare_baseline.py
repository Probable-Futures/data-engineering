#!/usr/bin/env python3
"""
Compare NEW vs CURRENT data at a matched climate state.

    # baseline (default): old 1971-2000 (wl=0.5) vs new 1971-2000 average
    python compare_baseline.py --indicator days-above-35c

    # a warming level: old "+1.5°C world" vs a new calendar window you choose
    python compare_baseline.py --indicator days-above-35c --wl 1.5 --period 2024-2040

Produces four artifacts in analysis/out/ + a printed stats summary:
  1. side-by-side   old 0.2° vs new 0.1°
  2. detail diff    new - regrid_nearest(old)   at 0.1°  (what detail did we gain?)
  3. model diff     aggregate(new)->0.2° - old  at 0.2°  (did the model itself move?)
  4. histogram      of the model-change diff + per-latitude-band table

The old data is organized by WARMING LEVEL and the new data by CALENDAR YEAR, so to
compare a "+X°C world" we pick the old wl slice and a new year-window that reaches
roughly that warming. Choosing the window is the caller's call (--period); this script
does not compute breaching years.

The two diffs follow "Comparison maps: two different questions" in
docs/hi-res-map-pipeline.md. Needs the old netCDF present locally
(only days-above-35C ships in the repo today; pull others with
`make -C ../geojson sync-woodwell-to-local`).
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
    ap.add_argument("--wl", type=float, default=0.5,
                    help="old-data warming level: 0.5 (baseline), 1.0, 1.5, 2.0, 2.5, 3.0")
    ap.add_argument("--period", default="1971-2000",
                    help="new-data calendar window to average, YYYY-YYYY (e.g. 2024-2040)")
    args = ap.parse_args()

    ind = lib.INDICATORS.get(args.indicator)
    if ind is None:
        raise SystemExit(f"unknown indicator '{args.indicator}'")
    if not ind.comparable:
        raise SystemExit(
            f"'{args.indicator}' isn't comparable: its current-data file stores a "
            f"*change relative to baseline*, so this diff is meaningless. "
            f"Use quicklook/timeseries to view the new data instead.")

    # A scenario tag drives the titles + output filenames so runs don't overwrite
    # each other (baseline vs wl1.5 vs wl2.0 ...).
    is_baseline = (args.wl == 0.5 and args.period == "1971-2000")
    scen = "baseline" if is_baseline else f"wl{args.wl:g}"
    stem = f"{args.indicator}_cmp_{scen}"
    old_state = "baseline" if is_baseline else f"+{args.wl:g}°C world"
    new_state = f"{args.period} avg"

    label, unit = ind.label, ind.unit
    old = lib.old_at_wl(args.indicator, args.wl)
    if old is None:
        raise SystemExit(
            f"current-data netCDF for '{args.indicator}' not found locally "
            f"({ind.old_file}). Pull it with `make -C ../geojson sync-woodwell-to-local`.")
    old = old.rename({old.dims[-2]: "lat", old.dims[-1]: "lon"}) if "lat" not in old.dims else old

    new_yearly = lib.open_new(args.indicator)
    new = lib.new_period(new_yearly, args.period)

    old_lm, new_lm = lib.land_mean(old), lib.land_mean(new)

    # let's print the number of cells in the old and new data
    print(f"\n{label} — old and new data:")
    print(f"  old: {old.size} cells")
    print(f"  new: {new.size} cells")
    print(f"  ratio: {new.size / old.size:.1f}")

    print(f"\n{label} — comparing OLD {old_state} vs NEW {new_state} (area-weighted land-means):")
    # The mean of the data is calculated by summing the data values over the time dimension,
    # and dividing by the number of data cells.
    print(f"  OLD (0.2°, CMIP5/RegCM ensemble, {old_state}): {old_lm:.2f} {unit}")
    print(f"  NEW (0.1°, CMIP6/MPI, {new_state}):            {new_lm:.2f} {unit}")
    print(f"  difference (new - old):                        {new_lm - old_lm:+.2f} {unit}")

    # 1. side by side ------------------------------------------------------
    vmax = float(np.nanpercentile(np.concatenate(
        [old.values[np.isfinite(old.values)], new.values[np.isfinite(new.values)]]), 98))
    p_old = lib.plot_map(old, f"{label} — OLD {old_state} (0.2°)", unit,
                         lib.OUT_DIR / f"{stem}_old.png", vmin=0, vmax=vmax)
    p_new = lib.plot_map(new, f"{label} — NEW {new_state} (0.1°)", unit,
                         lib.OUT_DIR / f"{stem}_new.png", vmin=0, vmax=vmax)

    # 2. detail diff at 0.1° ----------------------------------------------
    old_up = lib.regrid_nearest(old, new)
    detail = new - old_up
    detail.attrs["units"] = unit
    p_detail = lib.plot_map(
        detail, f"{label} — detail diff  new − old  ({old_state}, 0.1°)", unit,
        lib.OUT_DIR / f"{stem}_detail_diff.png", diverging=True)

    # 3. model-change diff at 0.2° ----------------------------------------
    new_down = lib.aggregate_to_old(new, old)
    model = new_down - old
    model.attrs["units"] = unit
    p_model = lib.plot_map(
        model, f"{label} — model diff  new→0.2° − old  ({old_state})", unit,
        lib.OUT_DIR / f"{stem}_model_diff.png", diverging=True)

    # 4. histogram + per-latitude-band table ------------------------------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    d = model.values[np.isfinite(model.values)]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(d, bins=80, color="#4477aa")
    ax.axvline(0, color="k", lw=1)
    ax.axvline(float(np.nanmean(d)), color="crimson", lw=2,
               label=f"mean {np.nanmean(d):+.2f}")
    ax.set_title(f"{label} — model-change diff (new→0.2° − old, {old_state}), land cells")
    ax.set_xlabel(f"difference ({unit})"); ax.set_ylabel("cells"); ax.legend()
    fig.tight_layout()
    p_hist = lib.OUT_DIR / f"{stem}_hist.png"
    fig.savefig(p_hist, dpi=130); plt.close(fig)

    print(f"\nModel-change diff (new {new_state} aggregated to 0.2° minus old {old_state}):")
    print(f"  mean {np.nanmean(d):+.2f}   median {np.nanmedian(d):+.2f}   "
          f"std {np.nanstd(d):.2f}   |diff|>5: {100*np.mean(np.abs(d)>5):.1f}% of land")
    print("\n  per-latitude band (area-weighted mean diff):")
    lat = model["lat"].values
    desc = bool(lat[0] > lat[-1])
    for lo, hi in [(-90, -60), (-60, -30), (-30, 0), (0, 30), (30, 60), (60, 90)]:
        sub = model.sel(lat=slice(*sorted((lo, hi), reverse=desc)))
        vals = sub.values[np.isfinite(sub.values)]
        if vals.size:
            print(f"    {lo:+4d}..{hi:+4d}°:  {lib.area_weighted_mean(sub):+6.2f} {unit}"
                  f"   (n={vals.size})")

    for p in (p_old, p_new, p_detail, p_model, p_hist):
        print(f"wrote {p}")


if __name__ == "__main__":
    main()
