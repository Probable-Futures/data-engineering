"""Tests for reading the live 0.2° exports and mapping their grid onto the new 0.1° grid.

The grid facts asserted here were verified against the real data: every live cell centre lands
exactly on a new cell centre, and the nearest new index for live cell k is 2 + 2k on both axes.
"""

import json

import numpy as np
import pytest

from hires_maps import livemaps


def test_cell_index_corners_and_middle():
    assert livemaps.cell_index(89.8, -179.8) == (0, 0)  # north-west corner
    assert livemaps.cell_index(-89.8, 179.8) == (898, 1798)  # south-east corner
    assert livemaps.cell_index(45.2, -94.6) == (223, 426)  # a real cell from 40105


def test_parent_index_matches_the_verified_2k_plus_2_relation():
    # The new grid, as the store ships it.
    new_lat = np.round(np.linspace(90.0, -90.0, 1801), 1)
    new_lon = np.round(np.linspace(-180.0, 180.0, 3601), 1)
    rows = livemaps.parent_index(new_lat, axis="lat")
    cols = livemaps.parent_index(new_lon, axis="lon")

    # Live cell k sits at new index 2 + 2k, and must map back to itself.
    for k in (0, 1, 2, 100, 898):
        assert rows[2 + 2 * k] == k
    for k in (0, 1, 2, 100, 1798):
        assert cols[2 + 2 * k] == k

    # Every new cell either has a parent in range or is flagged -1; nothing else.
    assert set(np.unique(rows[rows < 0])) <= {-1}
    assert rows.max() == 898
    assert cols.max() == 1798


def test_parent_index_breaks_boundary_ties_upwards():
    # 89.7 is exactly between live cells 89.8 (row 0) and 89.6 (row 1); the tie goes south.
    assert livemaps.parent_index(np.array([89.7]), axis="lat")[0] == 1
    # -179.7 is between live cells -179.8 (col 0) and -179.6 (col 1); the tie goes east.
    assert livemaps.parent_index(np.array([-179.7]), axis="lon")[0] == 1


def test_parent_index_refuses_to_extrapolate_past_the_poles():
    # The live grid stops at +/-89.8. A new cell a full cell beyond it has no parent, rather than
    # borrowing the edge value.
    assert livemaps.parent_index(np.array([90.0]), axis="lat")[0] == -1
    assert livemaps.parent_index(np.array([-90.0]), axis="lat")[0] == -1
    assert livemaps.parent_index(np.array([89.9]), axis="lat")[0] == 0  # still inside


def test_cell_index_flags_a_centre_that_is_not_on_the_live_grid():
    # 89.7 is a new-grid centre but not a live one (an odd number of tenths from the origin).
    assert livemaps.cell_index(89.7, -179.8) == (-1, 0)
    assert livemaps.cell_index(89.8, -179.7) == (0, -1)
    assert livemaps.cell_index(95.0, -179.8) == (-1, 0)  # off the grid entirely


def test_parent_index_rejects_a_bad_axis():
    with pytest.raises(ValueError, match="axis must be"):
        livemaps.parent_index(np.array([0.0]), axis="depth")


def test_upsample_expands_and_nulls_parentless_cells():
    live = np.arange(float(livemaps.SHAPE[0] * livemaps.SHAPE[1]), dtype="float32").reshape(
        livemaps.SHAPE
    )
    rows = np.array([-1, 0, 0, 1])
    cols = np.array([-1, 0, 1])
    out = livemaps.upsample(live, rows, cols)

    assert out.shape == (4, 3)
    assert np.isnan(out[0, :]).all()  # parentless row
    assert np.isnan(out[:, 0]).all()  # parentless column
    assert out[1, 1] == live[0, 0]
    assert out[2, 1] == live[0, 0]  # two new cells share one live parent
    assert out[3, 2] == live[1, 1]


def _write_live(tmp_path, monkeypatch, features):
    """Write a minimal live export and point livemaps at it."""
    monkeypatch.setattr(livemaps, "LIVE_MAPS_DIR", tmp_path)
    path = tmp_path / "40105.geojsonld"
    with path.open("w") as fh:
        for lat, lon, props in features:
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


def test_load_places_values_on_the_live_grid(tmp_path, monkeypatch):
    _write_live(
        tmp_path,
        monkeypatch,
        [
            (89.8, -179.8, {"data_baseline_mid": 3.0, "data_1c_mid": 4.0}),
            (45.2, -94.6, {"data_baseline_mid": 7.0, "data_1c_mid": 9.0}),
        ],
    )
    arrays, report = livemaps.load("40105", ["data_baseline_mid", "data_1c_mid"])

    assert arrays["data_baseline_mid"].shape == livemaps.SHAPE
    assert arrays["data_baseline_mid"][0, 0] == 3.0
    assert arrays["data_1c_mid"][223, 426] == 9.0
    assert np.isnan(arrays["data_baseline_mid"][500, 500])  # never mentioned -> no data
    assert report.features == 2
    assert report.filled["data_baseline_mid"] == 2
    assert report.off_grid == 0
    assert report.missing_properties == []


def test_load_treats_sentinels_as_no_data(tmp_path, monkeypatch):
    # -99999 (error) and -88888 (barren land) are markers, not values.
    _write_live(
        tmp_path,
        monkeypatch,
        [
            (89.8, -179.8, {"data_baseline_mid": -99999.0}),
            (89.6, -179.8, {"data_baseline_mid": -88888.0}),
            (89.4, -179.8, {"data_baseline_mid": 12.0}),
        ],
    )
    arrays, report = livemaps.load("40105", ["data_baseline_mid"])

    assert np.isnan(arrays["data_baseline_mid"][0, 0])
    assert np.isnan(arrays["data_baseline_mid"][1, 0])
    assert arrays["data_baseline_mid"][2, 0] == 12.0
    assert report.sentinels == 2
    assert report.filled["data_baseline_mid"] == 1


def test_load_reports_properties_this_export_lacks(tmp_path, monkeypatch):
    # Live exports carry 18 or 24 properties depending on how they were exported.
    _write_live(tmp_path, monkeypatch, [(89.8, -179.8, {"data_baseline_mid": 1.0})])
    _, report = livemaps.load("40105", ["data_baseline_mid", "data_baseline_median"])

    assert report.missing_properties == ["data_baseline_median"]
    assert "absent from this export" in report.summary()


def test_load_raises_a_useful_error_when_the_export_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(livemaps, "LIVE_MAPS_DIR", tmp_path)
    with pytest.raises(FileNotFoundError, match="no live export for dataset 49999"):
        livemaps.load("49999", ["data_baseline_mid"])
