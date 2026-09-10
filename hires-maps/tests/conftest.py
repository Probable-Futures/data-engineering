"""Fixtures shared by the builder and comparison-builder tests.

Three fakes, one per data source the package reads: a Zarr-shaped store for the v4 data, a
`.geojsonld` for the live v3 map, and a netCDF for ERA5. Each fixture also redirects the
module-level opener or path the code under test reads, because a test that forgets that step is a
test that reads the real data off disk.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from hires_maps import era5, livemaps, stores
from hires_maps.config import ERA5_WARMING_LEVELS
from hires_maps.indicators import get
from hires_maps.mapping import property_plan

# The fake ERA5 grid is anchored at the **top-left of the real global grid**, and has to be.
# `era5.parent_index` does absolute arithmetic against the true origin (+90°, -180°), so a fake
# placed anywhere else yields out-of-range indices, every cell comes back null, and the tests pass
# while asserting nothing. Cell (1, 1) — 89.75°N, -179.75° — is the only one given a value.
ERA5_FAKE_LAT = (90.0, 89.75)
ERA5_FAKE_LON = (-180.0, -179.75)


@pytest.fixture
def fake_store(monkeypatch) -> Callable[..., xr.Dataset]:
    """Build a tiny in-memory store for one indicator and make `stores.open_store` return it.

    Cell (0, 0) is the only land: every other cell stays NaN, so a build emits exactly one feature
    and the ocean path is exercised at the same time. `values` is either one number used at every
    warming level, or a `{warming_level: value}` dict when the levels have to differ. The Dataset
    comes back so a test can flip individual cells afterwards.
    """

    def make(slug: str, values: float | dict[float, float], *, lat=(10.0,), lon=(20.0, 20.1)):
        plan = property_plan(get(slug))
        wls = sorted({wl for _, wl, _ in plan})
        stats = sorted({stat for _, _, stat in plan})
        per_wl = values if isinstance(values, dict) else dict.fromkeys(wls, values)
        data = np.full((len(lat), len(lon), len(wls), len(stats)), np.nan, dtype="float32")
        for k, wl in enumerate(wls):
            data[0, 0, k, :] = per_wl[wl]
        ds = xr.Dataset(
            {stores.value_var(slug): (("lat", "lon", "wl", "stat"), data)},
            coords={"lat": list(lat), "lon": list(lon), "wl": wls, "stat": stats},
        )
        monkeypatch.setattr(stores, "open_store", lambda _slug: ds)
        return ds

    return make


@pytest.fixture
def live_export(tmp_path, monkeypatch) -> Callable[[str, Iterable], Path]:
    """Point `livemaps` at `tmp_path`, and return a writer for minimal live `.geojsonld` exports.

    Requesting the fixture is enough to redirect the lookup — a test for the missing-export path
    takes it without calling it. Each cell is given as `(lat, lon, properties)` and gets the 0.2°
    square ring the real exports carry, since `livemaps` recovers a cell's index from its
    polygon's bounding-box centre.
    """
    monkeypatch.setattr(livemaps, "LIVE_MAPS_DIR", tmp_path)

    def write(live_id: str, cells: Iterable[tuple[float, float, dict]]) -> Path:
        path = tmp_path / f"{live_id}.geojsonld"
        with path.open("w") as fh:
            for lat, lon, props in cells:
                ring = [
                    [lon - 0.1, lat + 0.1],
                    [lon - 0.1, lat - 0.1],
                    [lon + 0.1, lat - 0.1],
                    [lon + 0.1, lat + 0.1],
                    [lon - 0.1, lat + 0.1],
                ]
                fh.write(
                    json.dumps(
                        {
                            "type": "Feature",
                            "properties": props,
                            "geometry": {"type": "Polygon", "coordinates": [ring]},
                        }
                    )
                    + "\n"
                )
        return path

    return write


@pytest.fixture
def fake_era5(tmp_path, monkeypatch) -> Callable[..., xr.Dataset]:
    """Write a 2x2 ERA5 netCDF at the global origin and point the reader at it.

    Only cell (1, 1) carries a value — see ERA5_FAKE_LAT/LON above for why the anchor matters.
    Whichever grid is being compared against it, the cells under test must be ones whose
    `parent_index` lands on (1, 1); every other cell is a deliberate no-data case.

    `variables` selects the naming scheme: the 4-name default is the heat files, and the water
    files use the `perc_5`/`perc_50` spelling instead.

    One report field is meaningless against a fake this small and must not be asserted on:
    longitude is periodic, so `parent_index` wraps every one of the real grid's columns into the
    fake's two and about half of them find the populated column. `era5_only` therefore counts cells
    that exist only because the fake is 2 columns wide. Latitude returns -1 off the grid rather
    than wrapping, so `both` and the ours-only count are the ones worth pinning.
    """

    def make(
        slug: str,
        values: dict[float, float],
        variables=("mean", "perc05", "perc50", "perc95"),
    ) -> xr.Dataset:
        lat, lon = list(ERA5_FAKE_LAT), list(ERA5_FAKE_LON)
        arrays = {}
        for name in variables:
            a = np.full((len(ERA5_WARMING_LEVELS), len(lat), len(lon)), np.nan, dtype="float32")
            for k, wl in enumerate(ERA5_WARMING_LEVELS):
                a[k, 1, 1] = values[wl]
            arrays[name] = (("wl", "latitude", "longitude"), a)
        ds = xr.Dataset(
            arrays, coords={"wl": list(ERA5_WARMING_LEVELS), "latitude": lat, "longitude": lon}
        )
        directory = tmp_path / "era5"
        directory.mkdir(exist_ok=True)
        ds.to_netcdf(directory / f"era5_{era5.file_slug(slug)}_wls.nc")
        monkeypatch.setattr(era5, "ERA5_DIR", directory)
        monkeypatch.setattr(era5, "SHAPE", (len(lat), len(lon)))
        return ds

    return make


@pytest.fixture
def era5_props() -> Callable[..., dict]:
    """Every property a two-level (ERA5) plan asks for, all at one value — six entries."""

    def make(ind, value: float) -> dict:
        return {name: value for name, _, _ in property_plan(ind, ERA5_WARMING_LEVELS)}

    return make
