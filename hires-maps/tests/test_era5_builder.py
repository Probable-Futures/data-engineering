"""Tests for the standalone ERA5 map builder.

The point of the standalone map is that a reader bug is visible in it, so these tests pin the
things a comparison map would hide: the value reaching the file unmodified, the cell geometry
being 0.25° rather than 0.1°, and only the two real warming levels being emitted.
"""

import json

import numpy as np
import pytest
import xarray as xr

from hires_maps import era5
from hires_maps.config import ERA5_STEP_DEG, ERA5_WARMING_LEVELS, GRID_STEP_DEG
from hires_maps.geojson.era5_builder import build_era5_map
from hires_maps.geojson.output import Variant, output_path, rung_suffix
from hires_maps.geojson.stages import Grid
from hires_maps.indicators import get


@pytest.fixture
def fake_era5(tmp_path, monkeypatch):
    """Write a 2x2 ERA5 file for one indicator and point the reader at it.

    Cell (0, 0) is the only one with a value, so a build emits exactly one feature and the no-data
    path is exercised at the same time. `values` maps warming level -> value.
    """

    def make(
        slug: str,
        values: dict[float, float],
        variables=("mean", "perc05", "perc50", "perc95"),
        lat=(40.0, 39.75),
    ):
        lat = list(lat)
        lon = [0.0, 0.25]
        arrays = {}
        for name in variables:
            a = np.full((len(ERA5_WARMING_LEVELS), len(lat), len(lon)), np.nan, dtype="float32")
            for k, wl in enumerate(ERA5_WARMING_LEVELS):
                a[k, 0, 0] = values[wl]
            arrays[name] = (("wl", "latitude", "longitude"), a)
        ds = xr.Dataset(
            arrays,
            coords={"wl": list(ERA5_WARMING_LEVELS), "latitude": lat, "longitude": lon},
        )
        directory = tmp_path / "era5"
        directory.mkdir(exist_ok=True)
        ds.to_netcdf(directory / f"era5_{era5.file_slug(slug)}_wls.nc")
        monkeypatch.setattr(era5, "ERA5_DIR", directory)
        monkeypatch.setattr(era5, "SHAPE", (len(lat), len(lon)))
        return ds

    return make


def _run(fake_era5, tmp_path, slug, values, **kwargs):
    fake_era5(slug, values)
    path, n, report = build_era5_map(slug, tmp_path / "out.geojsonld", progress_every=0, **kwargs)
    features = [json.loads(line) for line in path.read_text().splitlines()]
    return features, n, report


def test_emits_only_the_cells_that_have_a_value(fake_era5, tmp_path):
    features, n, report = _run(fake_era5, tmp_path, "days-above-35c", {0.5: 40.0, 1.0: 55.0})
    assert n == 1
    assert report.cells == 1


def test_only_the_two_real_warming_levels_are_emitted(fake_era5, tmp_path):
    features, _, _ = _run(fake_era5, tmp_path, "days-above-35c", {0.5: 40.0, 1.0: 55.0})
    props = features[0]["properties"]
    assert sorted(props) == [
        "data_1c_high",
        "data_1c_low",
        "data_1c_mid",
        "data_baseline_high",
        "data_baseline_low",
        "data_baseline_mid",
    ]
    # No 1.5/2/2.5/3 properties at all -- absent, not null.
    assert not any("1_5c" in k or "2c" in k or "3c" in k for k in props)


def test_values_pass_through_with_the_live_truncation_rule(fake_era5, tmp_path):
    # 40.9 days must become 40, exactly as the published maps do -- NOT the comparison maps'
    # one-decimal rule. This is what makes the ERA5 map comparable to a live map popup for popup.
    features, _, _ = _run(fake_era5, tmp_path, "days-above-35c", {0.5: 40.9, 1.0: 55.2})
    props = features[0]["properties"]
    assert props["data_baseline_mid"] == 40
    assert props["data_1c_mid"] == 55
    assert isinstance(props["data_baseline_mid"], int)


def test_kelvin_conversion_reaches_the_file(fake_era5, tmp_path):
    # 300 K -> 26.85 °C -> truncated to 26. A missed conversion would emit 300, which is the whole
    # reason the standalone map is built before any comparison.
    features, _, report = _run(fake_era5, tmp_path, "average-temperature", {0.5: 300.0, 1.0: 301.0})
    assert report.load.kelvin is True
    assert features[0]["properties"]["data_baseline_mid"] == 26


def test_cells_are_quarter_degree_squares(fake_era5, tmp_path):
    features, _, _ = _run(fake_era5, tmp_path, "days-above-35c", {0.5: 40.0, 1.0: 55.0})
    ring = features[0]["geometry"]["coordinates"][0]
    lons = sorted({point[0] for point in ring})
    lats = sorted({point[1] for point in ring})
    assert lons[1] - lons[0] == pytest.approx(ERA5_STEP_DEG)
    assert lats[1] - lats[0] == pytest.approx(ERA5_STEP_DEG)
    # Centred on the cell centre (0.0, 40.0), half a step out on each side.
    assert lons == [pytest.approx(-0.125), pytest.approx(0.125)]
    assert lats == [pytest.approx(39.875), pytest.approx(40.125)]


def test_the_polar_row_is_clamped_to_90_degrees(fake_era5, tmp_path):
    # ERA5's first row is centred exactly on the pole, so its cell would reach 90.125. `cell_ring`
    # clamps it -- a half-height cell at the pole, not an invalid latitude.
    fake_era5("days-above-35c", {0.5: 40.0, 1.0: 55.0}, lat=(90.0, 89.75))
    path, _, _ = build_era5_map("days-above-35c", tmp_path / "out.geojsonld", progress_every=0)
    ring = json.loads(path.read_text().splitlines()[0])["geometry"]["coordinates"][0]
    lats = sorted({point[1] for point in ring})
    assert lats == [pytest.approx(89.875), pytest.approx(90.0)]


def test_change_indicators_are_still_published_absolute(fake_era5, tmp_path):
    # `total-annual-precipitation` is is_change=True, but ERA5 is an observational record: it says
    # what was measured, and we do not derive a trend from two observed windows. So `is_change` is
    # deliberately ignored and both levels stay absolute -- 850, not 850 - 800.
    fake_era5(
        "total-annual-precipitation",
        {0.5: 800.0, 1.0: 850.0},
        variables=("mean", "perc_5", "perc_50", "perc_95"),
    )
    path, _, _ = build_era5_map(
        "total-annual-precipitation", tmp_path / "out.geojsonld", progress_every=0
    )
    props = json.loads(path.read_text().splitlines()[0])["properties"]
    assert props["data_baseline_mid"] == 800
    assert props["data_1c_mid"] == 850


def test_no_indicator_gets_a_change_step(fake_era5, tmp_path):
    # The real 40601 values at 11.5N 9.5W. Absolute means 1071 reaches the file; a change step would
    # have emitted -163. Pinned because this flipped twice and the values look plausible either way.
    fake_era5(
        "total-annual-precipitation",
        {0.5: 1234.8, 1.0: 1071.1},
        variables=("mean", "perc_5", "perc_50", "perc_95"),
    )
    path, _, _ = build_era5_map(
        "total-annual-precipitation", tmp_path / "out.geojsonld", progress_every=0
    )
    props = json.loads(path.read_text().splitlines()[0])["properties"]
    assert props["data_baseline_mid"] == 1234
    assert props["data_1c_mid"] == 1071


def test_absolute_indicators_are_untouched(fake_era5, tmp_path):
    # The other 19 behave identically -- there is now no is_change branch at all.
    features, _, _ = _run(fake_era5, tmp_path, "days-above-35c", {0.5: 40.0, 1.0: 55.0})
    props = features[0]["properties"]
    assert props["data_baseline_mid"] == 40
    assert props["data_1c_mid"] == 55


def test_unknown_indicator_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="unknown indicator"):
        build_era5_map("not-a-real-slug", tmp_path / "out.geojsonld")


# --------------------------------------------------------------------------------------
# The Grid.step refactor these builds rest on
# --------------------------------------------------------------------------------------
def test_grid_half_comes_from_step_not_from_the_global_native_step():
    slices = {"x": np.zeros((2, 2), dtype="float32")}
    lat = np.array([90.0, 89.75])
    lon = np.array([0.0, 0.25])
    assert Grid(slices, lat, lon, step=ERA5_STEP_DEG).half == pytest.approx(0.125)
    # The default keeps every existing 0.1° build unchanged.
    assert Grid(slices, lat, lon).step == GRID_STEP_DEG
    assert Grid(slices, lat, lon).half == pytest.approx(0.05)


def test_coarsening_scales_step_and_factor_together():
    slices = {"x": np.arange(16, dtype="float32").reshape(4, 4)}
    lat = np.array([90.0, 89.75, 89.5, 89.25])
    lon = np.array([0.0, 0.25, 0.5, 0.75])
    coarse = Grid(slices, lat, lon, step=ERA5_STEP_DEG).coarsened(2)
    assert coarse.factor == 2
    assert coarse.step == pytest.approx(0.5)
    assert coarse.half == pytest.approx(0.25)


def test_rung_suffix_is_unchanged_for_the_native_grid():
    # The names every already-published file carries.
    assert rung_suffix(1) == ""
    assert rung_suffix(2) == "-p02"
    assert rung_suffix(8) == "-p08"


def test_rung_suffix_names_era5_rungs_by_their_size():
    assert rung_suffix(1, ERA5_STEP_DEG) == ""
    assert rung_suffix(2, ERA5_STEP_DEG) == "-p05"  # 0.5°
    assert rung_suffix(4, ERA5_STEP_DEG) == "-p10"  # 1.0°


def test_era5_output_paths_land_in_their_own_folder():
    ind = get("days-above-35c")
    native = output_path(ind, 1, variant=Variant.ERA5, step=ERA5_STEP_DEG)
    coarse = output_path(ind, 4, variant=Variant.ERA5, step=ERA5_STEP_DEG)
    assert native.parent.name == "era5-geojson"
    assert native.name == "40105-era5.geojsonld"
    assert coarse.name == "40105-era5-p10.geojsonld"
    # And the existing variants are untouched.
    assert output_path(ind, 2).name == "40105-hires-p02.geojsonld"
    assert output_path(ind, 8, variant=Variant.DIFF).name == "40105-diff-p08.geojsonld"
