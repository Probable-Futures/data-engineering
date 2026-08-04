"""
Shared helpers for exploring and comparing the new downscaled climate data.

The new data (Zarr, 0.1 deg, land-only, CMIP6/MPI, calendar years 1961-2099) lives
outside this repo at $PF_DOWNSCALED_DATA (default: ~/work/pf-downscaled-data).
The current production data (netCDF, 0.2 deg, warming levels) lives in this repo
under data/woodwell/.

Nothing here touches Mapbox or Postgres — it's pure xarray + matplotlib, and it
uses its own venv (see requirements.txt) so it doesn't disturb netcdfs/import.

See docs/downscaled-data-primer.md for the plain-English background.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import xarray as xr

# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
NEW_DATA_ROOT = Path(
    os.environ.get("PF_DOWNSCALED_DATA", str(Path.home() / "work" / "pf-downscaled-data"))
)
OLD_DATA_ROOT = REPO_ROOT / "data" / "woodwell"
OUT_DIR = Path(os.environ.get("PF_ANALYSIS_OUT", str(Path(__file__).resolve().parent / "out")))
OUT_DIR.mkdir(parents=True, exist_ok=True)

# The model/scenario stamp every new store shares.
_NEW_SUFFIX = "MPI-ESM1-2-HR_ww-isimip_ssp585_day.zarr"

# Warming-level slice that represents the 1971-2000 baseline in the old netCDFs.
OLD_BASELINE_WL = 0.5
NEW_BASELINE_PERIOD = ("1971", "2000")


# ---------------------------------------------------------------------------
# Indicator registry — maps a new-data folder to its current-data counterpart.
# Seeded from netcdfs/import/conf.yaml. `comparable` is False for maps where the
# OLD file stores a *change relative to baseline* (so its baseline slice ~= 0 and
# a baseline diff against the absolute new data would be meaningless).
# ---------------------------------------------------------------------------
class Indicator:
    def __init__(self, slug, label, unit, old_id=None, old_file=None,
                 use_mean_for_mid=True, comparable=True, kind="annual"):
        self.slug = slug                      # new-data folder name
        self.label = label
        self.unit = unit
        self.old_id = old_id
        self.old_file = old_file              # relative to OLD_DATA_ROOT
        self.use_mean_for_mid = use_mean_for_mid
        self.comparable = comparable
        self.kind = kind                      # "annual" or "climatology"

    @property
    def var(self):
        # new-data variable name = folder slug with dashes -> underscores
        return self.slug.replace("-", "_")


_HEAT = "heat_module/rcm_regcm_remo"
INDICATORS = {
    i.slug: i for i in [
        Indicator("average-temperature", "Average temperature", "°C",
                  40101, f"{_HEAT}/average-temperature_v03.nc"),
        Indicator("average-daytime-temperature", "Average daytime temperature", "°C",
                  40102, f"{_HEAT}/average-daytime-temperature_v03.nc"),
        Indicator("average-nighttime-temperature", "Average nighttime temperature", "°C",
                  40201, f"{_HEAT}/average-nighttime-temperature_v03.nc"),
        Indicator("ten-hottest-days", "Temperature of the 10 hottest days", "°C",
                  40103, f"{_HEAT}/ten-hottest-days_v03.nc"),
        Indicator("ten-hottest-nights", "Temperature of the 10 hottest nights", "°C",
                  40206, f"{_HEAT}/ten-hottest-nights_v03.nc"),
        Indicator("days-above-32c", "Days above 32°C", "days",
                  40104, f"{_HEAT}/days-above-32C_v03.nc"),
        Indicator("days-above-35c", "Days above 35°C", "days",
                  40105, f"{_HEAT}/days-above-35C_v03.nc"),
        Indicator("days-above-38c", "Days above 38°C", "days",
                  40106, f"{_HEAT}/days-above-38C_v03.nc"),
        Indicator("days-above-45c", "Days above 45°C", "days",
                  40107, f"{_HEAT}/days-above-45C_v03.nc"),
        Indicator("nights-above-20c", "Nights above 20°C", "nights",
                  40203, f"{_HEAT}/nights-above-20C_v03.nc"),
        Indicator("nights-above-25c", "Nights above 25°C", "nights",
                  40204, f"{_HEAT}/nights-above-25C_v03.nc"),
        Indicator("frost-nights", "Frost nights (min < 0°C)", "nights",
                  40202, f"{_HEAT}/frost-nights_v03.nc"),
        Indicator("freezing-days", "Freezing days (max < 0°C)", "days",
                  40205, f"{_HEAT}/freezing-days_v03.nc"),
        Indicator("days-above-26c-wbmax", "Days above 26°C wet-bulb", "days",
                  40301, f"{_HEAT}/days-above-26C-wetbulb_v03.nc"),
        Indicator("days-above-28c-wbmax", "Days above 28°C wet-bulb", "days",
                  40302, f"{_HEAT}/days-above-28C-wetbulb_v03.nc"),
        Indicator("days-above-30c-wbmax", "Days above 30°C wet-bulb", "days",
                  40303, f"{_HEAT}/days-above-30C-wetbulb_v03.nc"),
        Indicator("days-above-32c-wbmax", "Days above 32°C wet-bulb", "days",
                  40304, f"{_HEAT}/days-above-32C-wetbulb_v03.nc"),
        Indicator("ten-hottest-wbmax-days", "Wet-bulb temp of the 10 hottest days", "°C",
                  40305, f"{_HEAT}/ten-hottest-wetbulb-days_v03.nc"),
        # Old counterparts store a *change* -> not baseline-comparable, but still
        # fully viewable/investigable on the new (absolute) side.
        Indicator("wettest-90-days", "Wettest 90-day precipitation", "mm",
                  40616, None, use_mean_for_mid=False, comparable=False),
        Indicator("snowy-days", "Snowy days", "days",
                  40614, None, use_mean_for_mid=False, comparable=False),
    ]
}

# A few reference locations for point/time-series drill-downs (lat, lon).
PLACES = {
    "Beirut": (33.89, 35.50),
    "Cairo": (30.04, 31.24),
    "Delhi": (28.61, 77.21),
    "Madrid": (40.42, -3.70),
    "Lagos": (6.52, 3.38),
    "NewYork": (40.71, -74.01),
    "Jakarta": (-6.21, 106.85),
    "Baghdad": (33.31, 44.36),
}

# Default regional crop (lon_min, lon_max, lat_min, lat_max): the Levant / Middle East,
# where the 0.1 deg detail (e.g. Mount Lebanon) is visible.
DEFAULT_REGION = (25.0, 60.0, 12.0, 42.0)


# ---------------------------------------------------------------------------
# Opening data
# ---------------------------------------------------------------------------
def new_store_path(slug: str) -> Path:
    return NEW_DATA_ROOT / "annual_aggregates" / slug / f"{slug}_{_NEW_SUFFIX}"


def climatology_store_path(var: str) -> Path:
    return (NEW_DATA_ROOT / "climatologies" / var /
            f"{var}_MPI-ESM1-2-HR_ww-isimip_ssp585_mean_1971-2010.zarr")


def open_new(slug: str) -> xr.DataArray:
    """New annual-aggregate DataArray with dims (time, lat, lon)."""
    ind = INDICATORS.get(slug)
    var = ind.var if ind else slug.replace("-", "_")
    ds = xr.open_zarr(new_store_path(slug))
    da = ds[var]
    return da.rename({"latitude": "lat", "longitude": "lon"}) if "latitude" in da.dims else da


def open_climatology(var: str) -> xr.DataArray:
    """Raw 1971-2010 climatology map (dims lat, lon). Units auto-converted below."""
    ds = xr.open_zarr(climatology_store_path(var))
    da = ds[var]
    if "latitude" in da.dims:
        da = da.rename({"latitude": "lat", "longitude": "lon"})
    return _convert_climatology_units(var, da)


def open_era5land_diff(kind: str) -> xr.DataArray:
    """Open the model-minus-observations map (dims lat, lon) for 'temperature' or
    'precipitation'. This is downscaled climatology minus ERA5-Land (a trusted
    real-world dataset), so ~0 everywhere means the model matches reality."""
    ds = xr.open_zarr(NEW_DATA_ROOT / "climatologies_diff_era5land" / kind)
    da = ds["diff"]
    if "latitude" in da.dims:
        da = da.rename({"latitude": "lat", "longitude": "lon"})
    # the store uses -inf as a no-data marker in places; make those NaN
    return da.where(np.isfinite(da))


def _convert_climatology_units(var: str, da: xr.DataArray) -> xr.DataArray:
    """Kelvin -> °C for temperatures; per-second rate -> mm/day for precip."""
    if var in ("tas", "tasmax", "tasmin", "temperature"):
        da = da - 273.15
        da.attrs["units"] = "°C"
    elif var in ("pr", "precipitation", "pr_bil", "pr_con2"):
        da = da * 86400.0
        da.attrs["units"] = "mm/day"
    return da


def old_at_wl(slug: str, wl: float = OLD_BASELINE_WL) -> xr.DataArray | None:
    """Old-data map (dims lat, lon) at 0.2 deg for a given warming level, or None if missing.

    wl=0.5 is the 1971-2000 baseline; 1.0/1.5/2.0/2.5/3.0 are the warming-level "worlds".
    """
    ind = INDICATORS.get(slug)
    if ind is None or ind.old_file is None:
        return None
    path = OLD_DATA_ROOT / ind.old_file
    if not path.exists():
        return None
    print(f"opening {path}")
    ds = xr.open_dataset(path)
    var = "mean" if ind.use_mean_for_mid else "perc50"
    if var not in ds:
        var = list(ds.data_vars)[0]
    da = ds[var]
    if "wl" in da.dims:
        if wl not in [float(x) for x in da["wl"].values]:
            raise SystemExit(
                f"warming level {wl} not in this file; available: "
                f"{[float(x) for x in da['wl'].values]}")
        da = da.sel(wl=wl)
    return da


def old_baseline(slug: str) -> xr.DataArray | None:
    """Convenience: the old-data 1971-2000 baseline (warming level 0.5)."""
    return old_at_wl(slug, OLD_BASELINE_WL)


def new_period(da: xr.DataArray, period: str) -> xr.DataArray:
    """Average the new yearly data over a 'YYYY-YYYY' calendar window (e.g. '2024-2040')."""
    lo, hi = period.split("-")
    return da.sel(time=slice(lo, hi)).mean("time", skipna=True)


def new_baseline(da: xr.DataArray) -> xr.DataArray:
    """Convenience: average the new yearly data over the 1971-2000 baseline period."""
    return new_period(da, "-".join(NEW_BASELINE_PERIOD))


# ---------------------------------------------------------------------------
# Regridding between the 0.2 deg (old) and 0.1 deg (new) grids
# ---------------------------------------------------------------------------
def regrid_nearest(src: xr.DataArray, target: xr.DataArray) -> xr.DataArray:
    """Nearest-neighbor resample `src` onto `target`'s lat/lon grid (no interpolation).

    Uses `.reindex(method="nearest")` (label-based, no scipy) so the result is indexed by
    the *target* grid — unlike `.sel`, which would relabel with the source cells and create
    duplicate coordinates.
    """
    return src.reindex(lat=target["lat"], lon=target["lon"], method="nearest")


def aggregate_to_old(new_01: xr.DataArray, old: xr.DataArray) -> xr.DataArray:
    """Block-average the 0.1 deg new data to ~0.2 deg, aligned to the old grid.

    Coarsen by 2x2 (mean), then snap onto the old grid by nearest neighbor so the
    two arrays share coordinates and can be differenced.
    """
    coarse = new_01.coarsen(lat=2, lon=2, boundary="trim").mean(skipna=True)
    return coarse.reindex(lat=old["lat"], lon=old["lon"], method="nearest")


# ---------------------------------------------------------------------------
# Point / location helpers
# ---------------------------------------------------------------------------
def at_point(da: xr.DataArray, lat: float, lon: float, max_deg: float = 0.6) -> xr.DataArray:
    """Value(s) at the grid cell nearest to (lat, lon), keeping a time axis if present.

    Coastal cities often land on an ocean (NaN) cell at 0.1°, so if the nearest cell has
    no data we snap to the nearest *land* cell within `max_deg` degrees.
    """
    near = da.sel(lat=lat, lon=lon, method="nearest")
    if not np.all(np.isnan(np.asarray(near.values))):
        return near
    latv, lonv = da["lat"].values, da["lon"].values
    li = np.where(np.abs(latv - lat) <= max_deg)[0]
    lj = np.where(np.abs(lonv - lon) <= max_deg)[0]
    if li.size == 0 or lj.size == 0:
        return near
    block = da.isel(lat=li, lon=lj)
    ref = block.isel(time=-1) if "time" in block.dims else block
    mask = np.isfinite(np.asarray(ref.values))
    if not mask.any():
        return near  # genuinely no land nearby
    LA, LO = np.meshgrid(block["lat"].values, block["lon"].values, indexing="ij")
    dist = (LA - lat) ** 2 + (LO - lon) ** 2
    dist[~mask] = np.inf
    ii, jj = np.unravel_index(int(np.argmin(dist)), dist.shape)
    return block.isel(lat=ii, lon=jj)


def area_weighted_mean(da: xr.DataArray) -> float:
    """Mean over finite cells, weighted by cell area (~cos(lat)).

    Without this, every 0.1° cell counts equally, which over-weights high latitudes
    (a polar cell covers far less ground than a tropical one) and — since the data is
    land-only — lets Antarctica/Greenland drag the mean around. Always prefer this for
    any "typical over land" figure.
    """
    lat = da["lat"].values
    w = np.cos(np.deg2rad(lat))
    shape = [1] * da.ndim
    shape[da.dims.index("lat")] = lat.size
    W = np.broadcast_to(w.reshape(shape), da.shape)
    a = da.values
    m = np.isfinite(a)
    return float((a[m] * W[m]).sum() / W[m].sum())


def land_mean(da: xr.DataArray) -> float:
    """Area-weighted mean over land cells (see area_weighted_mean)."""
    return area_weighted_mean(da)


# ---------------------------------------------------------------------------
# Plotting (matplotlib only; ocean/NaN shown as light gray)
# ---------------------------------------------------------------------------
def _orient(da: xr.DataArray):
    """Return (array, extent) oriented for imshow(origin='upper')."""
    da = da.sortby("lat", ascending=False).sortby("lon")
    lats = da["lat"].values
    lons = da["lon"].values
    extent = [float(lons.min()), float(lons.max()), float(lats.min()), float(lats.max())]
    return da.values, extent


def plot_map(da, title, unit, out_path, *, region=None, cmap="inferno",
             vmin=None, vmax=None, diverging=False):
    """Render a DataArray as a PNG map. `region`=(lon0,lon1,lat0,lat1) crops first."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if region is not None:
        lon0, lon1, lat0, lat1 = region
        da = da.sortby("lat").sortby("lon").sel(
            lat=slice(lat0, lat1), lon=slice(lon0, lon1))

    arr, extent = _orient(da)

    if diverging:
        cmap = "RdBu_r"
        if vmax is None:
            m = float(np.nanpercentile(np.abs(arr), 99)) or 1.0
            vmin, vmax = -m, m
    else:
        if vmin is None:
            vmin = float(np.nanpercentile(arr, 2))
        if vmax is None:
            vmax = float(np.nanpercentile(arr, 98))

    cm = plt.get_cmap(cmap).copy()
    cm.set_bad("#e9e9e9")  # ocean / no-data

    fig_w = 12 if region is None else 8
    fig, ax = plt.subplots(figsize=(fig_w, fig_w * 0.52))
    im = ax.imshow(np.ma.masked_invalid(arr), extent=extent, origin="upper",
                   cmap=cm, vmin=vmin, vmax=vmax, aspect="auto", interpolation="nearest")
    ax.set_title(title, fontsize=13)
    ax.set_xlabel("longitude"); ax.set_ylabel("latitude")
    cbar = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cbar.set_label(unit)
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    return out_path
