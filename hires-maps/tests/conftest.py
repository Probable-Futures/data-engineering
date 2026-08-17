"""Fixtures shared by the builder and comparison-builder tests.

Both sides need the same two fakes: a Zarr-shaped store for the new data, and a `.geojsonld` for
the live map. Each fixture also redirects the module-level opener or path the code under test
reads, because a test that forgets that step is a test that reads the real data off disk.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from hires_maps import livemaps, stores
from hires_maps.indicators import get
from hires_maps.mapping import property_plan


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
