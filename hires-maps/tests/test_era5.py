"""Tests for the ERA5 reader — the grid arithmetic, the longitude roll, and the unit rules.

The grid tests run on the **real axes** (constructed from their definitions, not read from disk),
because the whole lookup rests on a claim about how three lattices interact and algebra in a
docstring is not a test. The load tests use a tiny fake netCDF written to `tmp_path`, so the unit
and naming-scheme rules are pinned without opening 33 MB.
"""

import numpy as np
import pytest
import xarray as xr

from hires_maps import era5
from hires_maps.config import ERA5_WARMING_LEVELS
from hires_maps.indicators import get
from hires_maps.mapping import property_plan

# The three lattices the reader has to line up, built from their definitions.
ERA5_LAT = np.round(np.arange(90.0, -90.25, -0.25), 10)
ERA5_LON_0_360 = np.round(np.arange(0.0, 360.0, 0.25), 10)
V4_LAT = np.round(np.arange(90.0, -90.05, -0.1), 10)
V4_LON = np.round(np.arange(-180.0, 180.05, 0.1), 10)
V3_LAT = np.round(np.arange(89.8, -89.85, -0.2), 10)
V3_LON = np.round(np.arange(-179.8, 179.85, 0.2), 10)


# --------------------------------------------------------------------------------------
# The grid
# --------------------------------------------------------------------------------------
def test_the_axes_are_the_shape_the_reader_assumes():
    assert (ERA5_LAT.size, ERA5_LON_0_360.size) == era5.SHAPE
    assert (V4_LAT.size, V4_LON.size) == (1801, 3601)
    assert (V3_LAT.size, V3_LON.size) == (899, 1799)


@pytest.mark.parametrize("name,lat,lon", [("v4", V4_LAT, V4_LON), ("v3", V3_LAT, V3_LON)])
def test_no_target_centre_lands_on_an_era5_cell_boundary(name, lat, lon):
    """The property the whole lookup rests on: no ties to break, so no tie-break to get wrong.

    ERA5 boundaries sit at `10k ± 5` in units of 0.025°. If any target centre landed there, which
    ERA5 cell it belonged to would be decided by a rounding rule rather than by geometry.
    """
    for coords in (lat, lon):
        units = np.rint(np.asarray(coords, dtype=float) / 0.025).astype(np.int64)
        assert not np.any(np.abs(units) % 10 == 5), name


def test_era5_centres_map_to_themselves():
    rows = era5.parent_index(ERA5_LAT, axis="lat")
    assert np.array_equal(rows, np.arange(era5.SHAPE[0]))


def test_each_era5_cell_covers_whole_target_cells():
    # 0.25 / 0.1 = 2.5, so the blocks alternate 2 and 3 rows -- they are not clean squares.
    rows = era5.parent_index(V4_LAT, axis="lat")
    _, counts = np.unique(rows[rows >= 0], return_counts=True)
    assert set(np.unique(counts)) == {2, 3}

    # 0.25 / 0.2 = 1.25, so on the v3 grid they alternate 1 and 2.
    rows = era5.parent_index(V3_LAT, axis="lat")
    _, counts = np.unique(rows[rows >= 0], return_counts=True)
    assert set(np.unique(counts)) == {1, 2}


def test_a_target_cell_takes_the_era5_cell_it_falls_inside():
    # 89.8 is 0.05 from ERA5's 89.75 centre (index 1) and 0.2 from its 90.0 centre (index 0).
    assert era5.parent_index(np.array([89.8]), axis="lat")[0] == 1
    assert era5.parent_index(np.array([90.0]), axis="lat")[0] == 0
    assert era5.parent_index(np.array([-90.0]), axis="lat")[0] == era5.SHAPE[0] - 1


def test_latitude_outside_the_grid_has_no_parent():
    # More than half a cell beyond the pole -> -1, so a comparison there is null, not extrapolated.
    assert era5.parent_index(np.array([90.2]), axis="lat")[0] == -1
    assert era5.parent_index(np.array([-90.2]), axis="lat")[0] == -1


def test_longitude_is_periodic_and_never_has_no_parent():
    cols = era5.parent_index(V4_LON, axis="lon")
    assert (cols >= 0).all()
    # +180 and -180 are the same meridian, so they must land in the same column.
    assert era5.parent_index(np.array([180.0]), axis="lon")[0] == 0
    assert era5.parent_index(np.array([-180.0]), axis="lon")[0] == 0
    # 179.975 is a quarter-cell from 180.0, which wraps back to column 0.
    assert era5.parent_index(np.array([179.975]), axis="lon")[0] == 0


# --------------------------------------------------------------------------------------
# The longitude roll
# --------------------------------------------------------------------------------------
def test_roll_longitude_produces_an_ascending_minus180_axis():
    lon, order = era5.roll_longitude(ERA5_LON_0_360)
    assert lon.size == era5.SHAPE[1]
    assert np.all(np.diff(lon) > 0)
    assert lon[0] == pytest.approx(-180.0)
    assert lon[-1] == pytest.approx(179.75)
    # No duplicated meridian: 180.0 becomes -180.0, and 359.75 is the last 0-360 value.
    assert np.unique(lon).size == lon.size


def test_roll_longitude_order_moves_the_right_columns():
    lon, order = era5.roll_longitude(ERA5_LON_0_360)
    # 0-360 value 359.75 is -0.25 after the roll; 180.0 is -180.0 and becomes the first column.
    assert ERA5_LON_0_360[order[0]] == pytest.approx(180.0)
    assert lon[np.searchsorted(lon, -0.25)] == pytest.approx(-0.25)
    assert ERA5_LON_0_360[order[np.searchsorted(lon, -0.25)]] == pytest.approx(359.75)


# --------------------------------------------------------------------------------------
# Loading: naming schemes and units
# --------------------------------------------------------------------------------------
def _write_era5(tmp_path, monkeypatch, slug: str, variables: dict[str, float]):
    """A 2x4 stand-in for one ERA5 file, on a longitude axis that spans the 0-360 wrap."""
    lat = [90.0, 89.75]
    lon = [0.0, 0.25, 179.75, 359.75]
    ds = xr.Dataset(
        {
            name: (
                ("wl", "latitude", "longitude"),
                np.full((2, len(lat), len(lon)), value, dtype="float32"),
            )
            for name, value in variables.items()
        },
        coords={"wl": list(ERA5_WARMING_LEVELS), "latitude": lat, "longitude": lon},
    )
    directory = tmp_path / "era5"
    directory.mkdir(exist_ok=True)
    ds.to_netcdf(directory / f"era5_{era5.file_slug(slug)}_wls.nc")
    monkeypatch.setattr(era5, "ERA5_DIR", directory)
    monkeypatch.setattr(era5, "SHAPE", (len(lat), len(lon)))
    return ds


HEAT_VARS = {"mean": 300.0, "perc05": 295.0, "perc50": 299.0, "perc95": 305.0}
WATER_VARS = {"mean": 800.0, "perc_5": 700.0, "perc_50": 790.0, "perc_95": 900.0}


def test_kelvin_files_are_converted(tmp_path, monkeypatch):
    slug = "average-temperature"
    _write_era5(tmp_path, monkeypatch, slug, HEAT_VARS)
    data = era5.load(slug, property_plan(get(slug), ERA5_WARMING_LEVELS))
    assert data.report.kelvin is True
    assert data.arrays["data_baseline_mid"][0, 0] == pytest.approx(300.0 - 273.15, abs=1e-4)


def test_the_wet_bulb_temperature_file_is_not_converted(tmp_path, monkeypatch):
    # `ten-hottest-wbmax-days` is a temperature already in °C. Every naming heuristic would
    # convert it; converting it would put the map 273 degrees out.
    slug = "ten-hottest-wbmax-days"
    _write_era5(tmp_path, monkeypatch, slug, {**HEAT_VARS, "mean": 25.0})
    data = era5.load(slug, property_plan(get(slug), ERA5_WARMING_LEVELS))
    assert data.report.kelvin is False
    assert data.arrays["data_baseline_mid"][0, 0] == pytest.approx(25.0)


def test_kelvin_slugs_excludes_the_wet_bulb_file():
    assert "ten-hottest-wbmax-days" not in era5.KELVIN_SLUGS
    assert "ten-hottest-days" in era5.KELVIN_SLUGS
    assert len(era5.KELVIN_SLUGS) == 6


def test_both_statistic_naming_schemes_resolve(tmp_path, monkeypatch):
    # Heat files use perc05/perc50/perc95; the five water files use perc_5/perc_50/perc_95.
    heat = "days-above-35c"
    _write_era5(tmp_path, monkeypatch, heat, {**HEAT_VARS, "perc05": 1.0, "perc95": 9.0})
    data = era5.load(heat, property_plan(get(heat), ERA5_WARMING_LEVELS))
    assert data.report.scheme == 0
    assert data.arrays["data_baseline_low"][0, 0] == pytest.approx(1.0)
    assert data.arrays["data_baseline_high"][0, 0] == pytest.approx(9.0)

    water = "total-annual-precipitation"
    _write_era5(tmp_path, monkeypatch, water, WATER_VARS)
    data = era5.load(water, property_plan(get(water), ERA5_WARMING_LEVELS))
    assert data.report.scheme == 1
    assert data.arrays["data_baseline_low"][0, 0] == pytest.approx(700.0)
    # mid reads p50 for this indicator, not mean.
    assert data.arrays["data_baseline_mid"][0, 0] == pytest.approx(790.0)


def test_a_file_matching_neither_scheme_is_an_error(tmp_path, monkeypatch):
    slug = "days-above-35c"
    _write_era5(tmp_path, monkeypatch, slug, {"mean": 1.0, "p05": 0.0, "p50": 1.0, "p95": 2.0})
    with pytest.raises(ValueError, match="neither known naming scheme"):
        era5.load(slug, property_plan(get(slug), ERA5_WARMING_LEVELS))


def test_load_returns_a_rolled_longitude_axis(tmp_path, monkeypatch):
    slug = "days-above-35c"
    _write_era5(tmp_path, monkeypatch, slug, HEAT_VARS)
    data = era5.load(slug, property_plan(get(slug), ERA5_WARMING_LEVELS))
    # The fake axis is [0, 0.25, 179.75, 359.75]; only 359.75 is past the wrap, becoming -0.25.
    assert list(np.round(data.lon, 4)) == [-0.25, 0.0, 0.25, 179.75]
    assert np.all(np.diff(data.lon) > 0)


def test_asking_for_a_warming_level_era5_lacks_is_an_error(tmp_path, monkeypatch):
    slug = "days-above-35c"
    _write_era5(tmp_path, monkeypatch, slug, HEAT_VARS)
    with pytest.raises(ValueError, match=r"no warming level 1\.5"):
        era5.load(slug, property_plan(get(slug)))  # the default 6-level plan


def test_a_missing_file_names_what_is_available(tmp_path, monkeypatch):
    _write_era5(tmp_path, monkeypatch, "days-above-35c", HEAT_VARS)
    with pytest.raises(FileNotFoundError, match="days-above-35c"):
        era5.load("frost-nights", property_plan(get("frost-nights"), ERA5_WARMING_LEVELS))


# --------------------------------------------------------------------------------------
# Slug aliasing
# --------------------------------------------------------------------------------------
def test_the_five_wet_bulb_slugs_map_to_their_era5_filenames():
    assert era5.file_slug("days-above-26c-wbmax") == "days-above-26c-wb"
    assert era5.file_slug("ten-hottest-wbmax-days") == "ten-hottest-wb-days"
    # Everything else is spelled the same in both places.
    assert era5.file_slug("days-above-35c") == "days-above-35c"
    assert era5.file_slug("dry-hot-days") == "dry-hot-days"


def test_available_reports_registry_spelling(tmp_path, monkeypatch):
    _write_era5(tmp_path, monkeypatch, "ten-hottest-wbmax-days", HEAT_VARS)
    # The file on disk is `era5_ten-hottest-wb-days_wls.nc`; callers work in registry slugs.
    assert era5.available() == ["ten-hottest-wbmax-days"]


def test_upsample_marks_parentless_rows_as_nan():
    grid = np.arange(6, dtype="float32").reshape(2, 3)
    out = era5.upsample(grid, np.array([0, -1]), np.array([0, 1, 2]))
    assert out[0].tolist() == [0.0, 1.0, 2.0]
    assert np.isnan(out[1]).all()
