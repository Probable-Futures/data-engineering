"""Tests for the hi-res builder at the coarse pyramid rungs, and for the two contracts that hold
the writer together.

Every other build test runs at `factor=1`, where a wrong cell half-width is invisible: 0.05 is
both the native half-width and what `0.05 * factor` gives at factor 1. These build at 2 and 8,
where `Grid.half` is the one expression that can ship visibly wrong geometry.

The grids below put their latitudes symmetrically about the equator on purpose. `coarsen` weights
each row by cos(lat), and symmetric rows carry equal weights, so the block average reduces to the
plain arithmetic mean and the expected value is exact rather than approximate.
"""

import json

import numpy as np
import pytest
import xarray as xr

from hires_maps import stores
from hires_maps.geojson.builder import build
from hires_maps.geojson.output import Variant, output_path
from hires_maps.geojson.stages import Grid, land_mask
from hires_maps.indicators import get
from hires_maps.mapping import MID_BASELINE_PROPERTY, property_plan

SLUG = "days-above-35c"


def _store(monkeypatch, values, lat, lon, slug: str = SLUG) -> xr.Dataset:
    """A store whose every (warming level, stat) slice holds the same 2-D array of values."""
    plan = property_plan(get(slug))
    wls = sorted({wl for _, wl, _ in plan})
    stats = sorted({stat for _, _, stat in plan})
    a = np.asarray(values, dtype="float32")
    data = np.repeat(np.repeat(a[:, :, None, None], len(wls), axis=2), len(stats), axis=3)
    ds = xr.Dataset(
        {stores.value_var(slug): (("lat", "lon", "wl", "stat"), data)},
        coords={"lat": list(lat), "lon": list(lon), "wl": wls, "stat": stats},
    )
    monkeypatch.setattr(stores, "open_store", lambda _slug: ds)
    return ds


def _one_feature(tmp_path, factor: int, **kwargs) -> dict:
    path, n = build(SLUG, tmp_path / "out.geojsonld", factor=factor, progress_every=0, **kwargs)
    lines = path.read_text().splitlines()
    assert n == len(lines)
    return json.loads(lines[0])


def test_p02_cells_are_a_tenth_of_a_degree_either_side(monkeypatch, tmp_path):
    # 2x2 native cells collapse to one 0.2° cell centred on (0.0, 0.05).
    _store(monkeypatch, [[10.0, 20.0], [30.0, 40.0]], lat=[0.05, -0.05], lon=[0.0, 0.1])
    feature = _one_feature(tmp_path, 2)

    ring = feature["geometry"]["coordinates"][0]
    assert ring == [[-0.05, -0.1], [0.15, -0.1], [0.15, 0.1], [-0.05, 0.1], [-0.05, -0.1]]
    # +/-0.1 in both directions, i.e. a 0.2° square, not the 0.1° native one
    assert max(p[1] for p in ring) - min(p[1] for p in ring) == pytest.approx(0.2)


def test_p08_cells_are_four_tenths_of_a_degree_either_side(monkeypatch, tmp_path):
    lat = [0.35, 0.25, 0.15, 0.05, -0.05, -0.15, -0.25, -0.35]
    lon = [round(i * 0.1, 1) for i in range(8)]
    _store(monkeypatch, np.full((8, 8), 40.0), lat=lat, lon=lon)
    feature = _one_feature(tmp_path, 8)

    ring = feature["geometry"]["coordinates"][0]
    assert ring == [[-0.05, -0.4], [0.75, -0.4], [0.75, 0.4], [-0.05, 0.4], [-0.05, -0.4]]
    assert max(p[1] for p in ring) - min(p[1] for p in ring) == pytest.approx(0.8)


def test_coarse_values_are_block_means_not_a_sampled_cell(monkeypatch, tmp_path):
    _store(monkeypatch, [[10.0, 20.0], [30.0, 40.0]], lat=[0.05, -0.05], lon=[0.0, 0.1])
    props = _one_feature(tmp_path, 2)["properties"]
    assert props[MID_BASELINE_PROPERTY] == 25  # mean of 10/20/30/40, not any one of them


def test_p08_averages_the_whole_64_cell_block(monkeypatch, tmp_path):
    lat = [0.35, 0.25, 0.15, 0.05, -0.05, -0.15, -0.25, -0.35]
    lon = [round(i * 0.1, 1) for i in range(8)]
    rows = np.tile(np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0]), (8, 1))
    _store(monkeypatch, rows, lat=lat, lon=lon)
    props = _one_feature(tmp_path, 8)["properties"]
    assert props[MID_BASELINE_PROPERTY] == 45  # mean of 10..80


def test_rung_filenames_carry_the_p02_p08_suffix():
    ind = get(SLUG)
    assert output_path(ind, 1).name == "40105-hires.geojsonld"
    assert output_path(ind, 2).name == "40105-hires-p02.geojsonld"
    assert output_path(ind, 8).name == "40105-hires-p08.geojsonld"
    # The hi-res rungs sit directly in the uploader's folder, not the diff subfolder.
    assert output_path(ind, 1).parent == output_path(ind, 1, variant=Variant.HIRES).parent
    assert output_path(ind, 1).parent != output_path(ind, 1, variant=Variant.DIFF).parent


def test_limit_truncates_a_coarse_build(monkeypatch, tmp_path):
    # 4x4 native cells -> four 0.2° cells; --limit stops after the first three.
    lat = [0.15, 0.05, -0.05, -0.15]
    lon = [0.0, 0.1, 0.2, 0.3]
    _store(monkeypatch, np.full((4, 4), 12.0), lat=lat, lon=lon)
    path, n = build(SLUG, tmp_path / "all.geojsonld", factor=2, progress_every=0)
    assert n == 4
    path, n = build(SLUG, tmp_path / "cut.geojsonld", factor=2, limit=3, progress_every=0)
    assert n == 3
    assert len(path.read_text().splitlines()) == 3


def test_land_mask_drops_the_duplicate_seam_column():
    # -180° and +180° are the same meridian; the store ships both, so one has to go or every
    # feature there is written twice.
    lon = np.array([179.8, 179.9, 180.0])
    slices = {MID_BASELINE_PROPERTY: np.ones((1, 3), dtype="float32")}
    mask = land_mask(Grid(slices, np.array([0.0]), lon))
    assert mask.tolist() == [[True, True, False]]


def test_ocean_stays_masked_even_though_the_seam_check_runs_after_it():
    slices = {MID_BASELINE_PROPERTY: np.array([[1.0, np.nan, 1.0]], dtype="float32")}
    mask = land_mask(Grid(slices, np.array([0.0]), np.array([0.0, 0.1, 0.2])))
    assert mask.tolist() == [[True, False, True]]


def test_property_order_is_exactly_the_property_plan(monkeypatch, tmp_path):
    # `write_features` iterates `grid.slices` rather than a parallel list of names. That is only
    # correct because insertion order is `property_plan` order at every stage, so pin it here.
    _store(monkeypatch, [[10.0, 20.0], [30.0, 40.0]], lat=[0.05, -0.05], lon=[0.0, 0.1])
    props = _one_feature(tmp_path, 2)["properties"]
    assert list(props) == [name for name, _, _ in property_plan(get(SLUG))]


def test_property_order_holds_for_a_change_map_too(monkeypatch, tmp_path):
    # Change maps rewrite the baseline arrays in place; that must not reorder the dict.
    slug = "total-annual-precipitation"
    _store(monkeypatch, [[10.0, 20.0], [30.0, 40.0]], lat=[0.05, -0.05], lon=[0.0, 0.1], slug=slug)
    path, _ = build(slug, tmp_path / "out.geojsonld", factor=2, progress_every=0)
    props = json.loads(path.read_text().splitlines()[0])["properties"]
    assert list(props) == [name for name, _, _ in property_plan(get(slug))]
