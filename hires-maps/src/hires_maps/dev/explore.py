"""DEV-ONLY explorer for the warming-level Zarr data.

Not part of the build pipeline — a hands-on aid for poking at the data while we develop the
GeoJSON builder. Run it as `hires-explore <command>`:

    hires-explore list
    hires-explore describe days-above-35c
    hires-explore point   days-above-35c --lat 33.9 --lon 35.5
    hires-explore patch   days-above-35c --wl 1.5 --lat 33.9 --lon 35.5
    hires-explore landmean days-above-35c
"""

from __future__ import annotations

import warnings

import numpy as np
import typer

from .. import stores
from ..config import STATS, WARMING_LEVELS, WL_PREFIX
from ..indicators import get

warnings.filterwarnings("ignore")

app = typer.Typer(
    add_completion=False,
    help="DEV-ONLY tools to inspect the warming-level Zarr data (not the build pipeline).",
)


@app.command("list")
def list_cmd() -> None:
    """List the warming-level indicators found on disk."""
    found = stores.list_on_disk()
    if not found:
        typer.echo(f"No indicators found under {stores.WL_ROOT} — is the data downloaded?")
        raise typer.Exit(1)
    typer.echo(f"{len(found)} indicators under {stores.WL_ROOT}:\n")
    typer.echo(f"  {'slug':32s} {'live id':8s} {'unit':8s} {'mid':7s}")
    for slug in found:
        ind = get(slug)
        if ind:
            typer.echo(f"  {slug:32s} {ind.live_id:8s} {ind.unit:8s} {ind.mid_stat:7s}")
        else:
            typer.echo(f"  {slug:32s} {'?':8s} {'?':8s} {'?':7s}  (not in registry)")


@app.command()
def describe(indicator: str) -> None:
    """Show a store's shape: dimensions, warming levels, statistics, variables, ranges."""
    ind = get(indicator)
    ds = stores.open_store(indicator)
    typer.echo(f"\n=== {indicator} ===")
    if ind:
        typer.echo(f"live id {ind.live_id} | unit {ind.unit} | headline stat = {ind.mid_stat}")
    typer.echo(f"dimensions : {dict(ds.sizes)}")
    typer.echo(f"warming levels : {[float(x) for x in ds['wl'].values]}")
    typer.echo(f"statistics     : {[str(x) for x in ds['stat'].values]}")
    typer.echo(f"variables      : {list(ds.data_vars)}")
    for var in ds.data_vars:
        a = ds[var].values
        pct_nan = 100.0 * np.isnan(a).mean() if a.size else float("nan")
        typer.echo(
            f"  {var:26s} dims={ds[var].dims}  "
            f"min={np.nanmin(a):.3g} mean={np.nanmean(a):.3g} max={np.nanmax(a):.3g} "
            f"NaN(ocean)={pct_nan:.1f}%"
        )
    typer.echo("")


@app.command()
def point(
    indicator: str,
    lat: float = typer.Option(..., help="latitude"),
    lon: float = typer.Option(..., help="longitude"),
) -> None:
    """Dump the (warming level x statistic) values at the nearest land cell.

    This is exactly the set of numbers one map cell/feature will carry — handy for checking
    what the GeoJSON builder should emit.
    """
    ind = get(indicator)
    unit = ind.unit if ind else ""
    ds = stores.open_store(indicator)
    cell = stores.value_at(ds[stores.value_var(indicator)], lat, lon)  # dims: wl, stat
    la, lo = float(cell["lat"]), float(cell["lon"])
    typer.echo(f"\n{indicator} at nearest land cell to ({lat}, {lon}) -> ({la:.2f}, {lo:.2f})")
    typer.echo(f"values in {unit or '?'}:\n")
    header = f"  {'warming level':16s}" + "".join(f"{s:>9s}" for s in STATS)
    typer.echo(header)
    typer.echo("  " + "-" * (len(header) - 2))
    for wl in WARMING_LEVELS:
        row = cell.sel(wl=wl)
        cells = "".join(f"{float(row.sel(stat=s)):9.1f}" for s in STATS)
        typer.echo(f"  {wl:>4} ({WL_PREFIX[wl]:8s})" + cells)
    typer.echo("")


@app.command()
def patch(
    indicator: str,
    wl: float = typer.Option(1.5, help="warming level"),
    stat: str = typer.Option("mean", help="statistic (min/p5/p50/p95/max/mean)"),
    lat: float = typer.Option(33.9, help="centre latitude"),
    lon: float = typer.Option(35.5, help="centre longitude"),
    size: int = typer.Option(6, help="grid size (cells per side)"),
) -> None:
    """Print a small grid of values around a point (a quick look at spatial detail)."""
    ds = stores.open_store(indicator)
    da = ds[stores.value_var(indicator)].sel(wl=wl, stat=stat).sortby("lat").sortby("lon")
    half = size * 0.05
    sub = da.sel(lat=slice(lat - half, lat + half), lon=slice(lon - half, lon + half))
    lats = list(sub["lat"].values)[::-1]  # north at top
    lons = list(sub["lon"].values)
    typer.echo(f"\n{indicator}  wl={wl}  stat={stat}   ('----' = ocean)\n")
    typer.echo("  lat \\ lon |" + "".join(f"{x:>8.1f}" for x in lons))
    for la in lats:
        row = ""
        for lo in lons:
            v = float(sub.sel(lat=la, lon=lo))
            row += "    ----" if np.isnan(v) else f"{v:8.1f}"
        typer.echo(f"  {la:9.1f} |{row}")
    typer.echo("")


@app.command()
def landmean(
    indicator: str,
    stat: str = typer.Option("mean", help="statistic to summarise"),
) -> None:
    """Area-weighted land-mean per warming level (a quick sanity check on the numbers)."""
    ind = get(indicator)
    unit = ind.unit if ind else ""
    ds = stores.open_store(indicator)
    da = ds[stores.value_var(indicator)]
    typer.echo(f"\n{indicator} — area-weighted land-mean per warming level (stat={stat}, {unit}):")
    for wl in WARMING_LEVELS:
        lm = stores.area_weighted_mean(da.sel(wl=wl, stat=stat))
        typer.echo(f"  {wl:>4} ({WL_PREFIX[wl]:8s}): {lm:8.2f} {unit}")
    typer.echo("")


if __name__ == "__main__":
    app()
