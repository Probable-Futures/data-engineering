"""Tests for the comparison builder: new hi-res data minus the currently-live map.

Both halves are faked — a tiny in-memory Zarr-shaped Dataset for the new side (the pattern from
`test_builder_change.py`) and a two-line `.geojsonld` for the live side — so the arithmetic and the
change-map baseline asymmetry can be pinned down without touching the real 7.8 GB of exports.
"""

import json

import numpy as np
import pytest
import xarray as xr

from hires_maps import livemaps, stores
from hires_maps.geojson.diff_builder import build_diff
from hires_maps.indicators import get
from hires_maps.mapping import property_plan

# One cell that is a live centre too, plus an ocean neighbour.
LAT = [89.8]
LON = [-179.8, -179.6]


def _fake_new_store(slug: str, per_wl: dict[float, float]) -> xr.Dataset:
    """New-side store: cell 0 carries `per_wl[wl]` in every stat, cell 1 is ocean."""
    ind = get(slug)
    wls = sorted({wl for _, wl, _ in property_plan(ind)})
    stats = sorted({stat for _, _, stat in property_plan(ind)})
    data = np.full((len(LAT), len(LON), len(wls), len(stats)), np.nan, dtype="float32")
    for k, wl in enumerate(wls):
        data[0, 0, k, :] = per_wl[wl]
    return xr.Dataset(
        {ind.var: (("lat", "lon", "wl", "stat"), data)},
        coords={"lat": LAT, "lon": LON, "wl": wls, "stat": stats},
    )


def _write_live(tmp_path, live_id: str, cells: list[tuple[float, float, dict]]) -> None:
    with (tmp_path / f"{live_id}.geojsonld").open("w") as fh:
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


def _all_props(ind, value: float) -> dict:
    return {name: value for name, _, _ in property_plan(ind)}


def _run(monkeypatch, tmp_path, slug, per_wl, live_cells):
    ds = _fake_new_store(slug, per_wl)
    monkeypatch.setattr(stores, "open_store", lambda _slug: ds)
    monkeypatch.setattr(livemaps, "LIVE_MAPS_DIR", tmp_path)
    _write_live(tmp_path, get(slug).live_id, live_cells)
    path, n, report = build_diff(slug, tmp_path / "out.geojsonld", progress_every=0)
    lines = path.read_text().splitlines()
    return [json.loads(line)["properties"] for line in lines], n, report


def test_absolute_map_subtracts_live_from_new(monkeypatch, tmp_path):
    ind = get("days-above-35c")
    props, n, report = _run(
        monkeypatch,
        tmp_path,
        "days-above-35c",
        per_wl=dict.fromkeys([0.5, 1.0, 1.5, 2.0, 2.5, 3.0], 40.0),
        live_cells=[(89.8, -179.8, _all_props(ind, 30.0))],
    )
    assert n == 1  # the ocean cell is skipped
    for name, value in props[0].items():
        assert value == 10.0, name
        assert isinstance(value, float), name  # one decimal, not truncated to int
    assert report.both == 1
    assert report.new_only == 0
    assert report.live_only == 0


def test_diff_keeps_a_decimal_that_integer_truncation_would_erase(monkeypatch, tmp_path):
    # The whole point of DIFF_DECIMALS: a real +0.7 day disagreement must not become 0.
    ind = get("days-above-35c")
    props, _, _ = _run(
        monkeypatch,
        tmp_path,
        "days-above-35c",
        per_wl=dict.fromkeys([0.5, 1.0, 1.5, 2.0, 2.5, 3.0], 30.7),
        live_cells=[(89.8, -179.8, _all_props(ind, 30.0))],
    )
    assert props[0]["data_1c_mid"] == 0.7


def test_change_map_compares_changes_and_absolute_baselines(monkeypatch, tmp_path):
    # New: absolute 100 at baseline rising 10 a level -> changes of +10, +20, ... after _to_change.
    # Live: an ABSOLUTE baseline of 90 alongside changes of +4 (how the live exports really look).
    slug = "total-annual-precipitation"
    ind = get(slug)
    per_wl = {0.5: 100.0, 1.0: 110.0, 1.5: 120.0, 2.0: 130.0, 2.5: 140.0, 3.0: 150.0}
    live = _all_props(ind, 4.0)
    for name, wl, _stat in property_plan(ind):
        if wl == 0.5:
            live[name] = 90.0
    props, _, _ = _run(monkeypatch, tmp_path, slug, per_wl, [(89.8, -179.8, live)])

    # baseline slot: absolute vs absolute
    assert props[0]["data_baseline_mid"] == 10.0  # 100 - 90
    # every other slot: change vs change
    assert props[0]["data_1c_mid"] == 6.0  # (110-100) - 4
    assert props[0]["data_3c_mid"] == 46.0  # (150-100) - 4


def test_cells_the_live_map_lacks_become_null_not_zero(monkeypatch, tmp_path):
    # A coastal fringe exists because the live grid is coarser. Those cells must be null, or the
    # whole coastline reads as a real red/blue disagreement.
    ind = get("days-above-35c")
    ds = _fake_new_store("days-above-35c", dict.fromkeys([0.5, 1.0, 1.5, 2.0, 2.5, 3.0], 40.0))
    ds[ind.var].loc[{"lat": 89.8, "lon": -179.6}] = 40.0  # new has data in the second cell too
    monkeypatch.setattr(stores, "open_store", lambda _slug: ds)
    monkeypatch.setattr(livemaps, "LIVE_MAPS_DIR", tmp_path)
    _write_live(tmp_path, ind.live_id, [(89.8, -179.8, _all_props(ind, 30.0))])  # live has only one

    path, n, report = build_diff("days-above-35c", tmp_path / "out.geojsonld", progress_every=0)
    rows = [json.loads(line)["properties"] for line in path.read_text().splitlines()]

    assert report.new_only == 1
    assert n == 1  # the new-only cell has no comparable value, so it is not emitted
    assert rows[0]["data_1c_mid"] == 10.0


def test_missing_live_export_raises(monkeypatch, tmp_path):
    ds = _fake_new_store("days-above-35c", dict.fromkeys([0.5, 1.0, 1.5, 2.0, 2.5, 3.0], 1.0))
    monkeypatch.setattr(stores, "open_store", lambda _slug: ds)
    monkeypatch.setattr(livemaps, "LIVE_MAPS_DIR", tmp_path)
    with pytest.raises(FileNotFoundError, match="no live export"):
        build_diff("days-above-35c", tmp_path / "out.geojsonld", progress_every=0)


def test_unknown_indicator_raises(tmp_path):
    with pytest.raises(ValueError, match="unknown indicator"):
        build_diff("not-a-map", tmp_path / "out.geojsonld")


def test_output_goes_to_the_diff_geojson_folder():
    from hires_maps.config import LIVE_MAPS_DIR
    from hires_maps.geojson.diff_builder import default_output

    ind = get("days-above-35c")
    assert default_output(ind, 1).name == "40105-diff.geojsonld"
    assert default_output(ind, 2).name == "40105-diff-p02.geojsonld"
    assert default_output(ind, 8).name == "40105-diff-p08.geojsonld"

    # Its own folder, a sibling of the live exports it is differenced against. `vector-tiles`
    # hardcodes the same folder name as DIFF_SUBDIR, so this name is a contract.
    parent = default_output(ind, 1).parent
    assert parent.name == "diff-geojson"
    assert parent.parent == LIVE_MAPS_DIR.parent
