#!/usr/bin/env python3
"""
Assemble a single self-contained HTML report for one indicator — client-ready.

    python report.py --indicator days-above-35c
    python report.py --indicator days-above-35c --places Beirut,Cairo,Delhi

Bundles the maps, a location time-series, and (when the current-data netCDF is
present) the old-vs-new comparison into ONE .html file with images embedded as
data-URIs, so it opens anywhere with no dependencies. Plain-language captions
throughout. Output: analysis/out/<indicator>.html
"""
from __future__ import annotations

import argparse
import base64
import warnings
from pathlib import Path

import numpy as np

import lib

warnings.filterwarnings("ignore")


def _b64(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()


def _fig(caption, path):
    return (f'<figure><img src="{_b64(path)}"/>'
            f'<figcaption>{caption}</figcaption></figure>')


def build(indicator: str, places: str) -> Path:
    ind = lib.INDICATORS.get(indicator)
    if ind is None:
        raise SystemExit(f"unknown indicator '{indicator}'")
    label, unit = ind.label, ind.unit
    tmp = lib.OUT_DIR / "_report_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    blocks = []

    da = lib.open_new(indicator)
    y0 = int(da["time"].dt.year.values[0])
    y1 = int(da["time"].dt.year.values[-1])
    base = lib.new_baseline(da)
    last = da.isel(time=-1)

    # --- maps -----------------------------------------------------------
    vmax = float(np.nanpercentile(last.values[np.isfinite(last.values)], 98))
    p_base = lib.plot_map(base, f"{label} — 1971-2000 baseline (0.1°)", unit,
                          tmp / "base.png", vmin=0, vmax=vmax)
    p_last = lib.plot_map(last, f"{label} — {y1} (0.1°)", unit,
                          tmp / "last.png", vmin=0, vmax=vmax)
    p_reg = lib.plot_map(last, f"{label} — {y1} (regional)", unit,
                         tmp / "region.png", region=lib.DEFAULT_REGION, vmin=0, vmax=vmax)

    blocks.append("<h2>1. What the new data looks like</h2>")
    blocks.append('<div class="row">')
    blocks.append(_fig(f"Historical baseline (average of {y0 + 10}s–2000). "
                       f"Ocean is blank — this data is land-only.", p_base))
    blocks.append(_fig(f"End-of-century ({y1}) under the high-emissions scenario. "
                       f"Compare the spread of hot colors to the baseline.", p_last))
    blocks.append("</div>")
    blocks.append('<div class="row">')
    blocks.append(_fig("Zoomed to the Middle East / Levant, where the 11 km detail "
                       "resolves coastlines and mountains.", p_reg))
    blocks.append("</div>")

    # --- time series ----------------------------------------------------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    years = da["time"].dt.year.values
    fig, ax = plt.subplots(figsize=(10, 5))
    rows = []
    for name in [p.strip() for p in places.split(",") if p.strip() in lib.PLACES]:
        lat, lon = lib.PLACES[name]
        s = lib.at_point(da, lat, lon).values.astype(float)
        ax.plot(years, s, label=name, linewidth=2)
        rows.append((name, s[0], s[int(np.argmin(np.abs(years - 2050)))], s[-1]))
    ax.set_title(f"{label} — {y0} to {y1}")
    ax.set_xlabel("year"); ax.set_ylabel(f"{label} ({unit})"); ax.grid(alpha=0.3); ax.legend()
    fig.tight_layout(); p_ts = tmp / "ts.png"; fig.savefig(p_ts, dpi=130); plt.close(fig)

    tbl = "".join(f"<tr><td>{n}</td><td>{a:.1f}</td><td>{b:.1f}</td><td>{c:.1f}</td></tr>"
                  for n, a, b, c in rows)
    blocks.append("<h2>2. How specific places change over time</h2>")
    blocks.append(_fig(f"{label} at selected cities, every year {y0}–{y1}.", p_ts))
    blocks.append(f"<table><tr><th>place</th><th>{y0}</th><th>2050</th><th>{y1}</th></tr>"
                  f"{tbl}</table>")

    # --- comparison -----------------------------------------------------
    old = lib.old_baseline(indicator) if ind.comparable else None
    if old is not None:
        old = old.rename({old.dims[-2]: "lat", old.dims[-1]: "lon"}) if "lat" not in old.dims else old
        vmx = float(np.nanpercentile(np.concatenate(
            [old.values[np.isfinite(old.values)], base.values[np.isfinite(base.values)]]), 98))
        p_old = lib.plot_map(old, "CURRENT data — baseline (0.2°)", unit,
                             tmp / "old.png", vmin=0, vmax=vmx)
        p_newb = lib.plot_map(base, "NEW data — baseline (0.1°)", unit,
                              tmp / "newb.png", vmin=0, vmax=vmx)
        model = lib.aggregate_to_old(base, old) - old
        p_mdiff = lib.plot_map(model, "Model-change diff (new→0.2° − current)", unit,
                               tmp / "mdiff.png", diverging=True)
        o_lm, n_lm = lib.land_mean(old), lib.land_mean(base)
        blocks.append("<h2>3. New data vs the current maps (same 1971-2000 baseline)</h2>")
        blocks.append(f"<p>Over land, the current data averages <b>{o_lm:.1f} {unit}</b> and the "
                      f"new data <b>{n_lm:.1f} {unit}</b> "
                      f"(<b>{n_lm - o_lm:+.1f} {unit}</b>). Same real-world period on both sides, "
                      f"so the difference reflects the model + resolution change, not time.</p>")
        blocks.append('<div class="row">')
        blocks.append(_fig("Current production data (CMIP5, 0.2°).", p_old))
        blocks.append(_fig("New downscaled data (CMIP6/MPI, 0.1°).", p_newb))
        blocks.append("</div>")
        blocks.append(_fig("Difference after matching resolution: red = new is higher, "
                           "blue = new is lower. Near-white = the two agree.", p_mdiff))
    else:
        blocks.append("<h2>3. New data vs the current maps</h2>")
        reason = ("its current-data file stores a <i>change relative to baseline</i>, which isn't "
                  "directly comparable to the new absolute values"
                  if ind.comparable is False else
                  "the current-data netCDF isn't downloaded locally yet")
        blocks.append(f"<p>Skipped — {reason}.</p>")

    html = _TEMPLATE.format(
        title=f"{label} — new downscaled data",
        label=label, unit=unit, body="\n".join(blocks))
    out = lib.OUT_DIR / f"{indicator}.html"
    out.write_text(html, encoding="utf-8")
    return out


_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:1100px;margin:2rem auto;
      padding:0 1rem;color:#1a1a1a;line-height:1.5}}
 h1{{font-size:1.6rem}} h2{{margin-top:2.2rem;border-bottom:2px solid #eee;padding-bottom:.3rem}}
 .row{{display:flex;flex-wrap:wrap;gap:1rem}} .row figure{{flex:1;min-width:340px}}
 figure{{margin:1rem 0}} img{{width:100%;border:1px solid #ddd;border-radius:6px}}
 figcaption{{font-size:.9rem;color:#555;margin-top:.4rem}}
 table{{border-collapse:collapse;margin:1rem 0}} td,th{{border:1px solid #ccc;padding:.3rem .7rem;text-align:right}}
 th:first-child,td:first-child{{text-align:left}}
 .lead{{color:#444}}
</style></head><body>
<h1>{title}</h1>
<p class="lead">New downscaled climate data: CMIP6 / MPI-ESM1-2-HR, statistically downscaled to
0.1° (~11 km), land only, high-emissions scenario. Values are <b>{label}</b> in <b>{unit}</b>.
This is a first look for internal review — not a published product.</p>
{body}
<hr><p style="color:#888;font-size:.85rem">Generated by analysis/report.py · Probable Futures data-engineering</p>
</body></html>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--indicator", required=True)
    ap.add_argument("--places", default="Beirut,Cairo,Delhi")
    args = ap.parse_args()
    out = build(args.indicator, args.places)
    print(f"wrote {out}")
    print(f"open it with:  open {out}")


if __name__ == "__main__":
    main()
