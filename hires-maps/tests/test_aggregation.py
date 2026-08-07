"""Tests for the pyramid coarsening (area-weighted block means)."""

import numpy as np

from hires_maps.aggregation import block_centres, block_weighted_mean, coarsen


def test_factor_one_is_identity():
    a = {"x": np.arange(8, dtype="float32").reshape(2, 4)}
    lat = np.array([1.0, 2.0])
    lon = np.array([10.0, 11.0, 12.0, 13.0])
    out, la, lo = coarsen(a, lat, lon, 1)
    assert out is a and np.array_equal(la, lat) and np.array_equal(lo, lon)


def test_block_mean_near_equator_is_plain_average():
    # near the equator cos(lat) ~ 1, so a 2x2 block mean ~= arithmetic mean
    a = np.array([[10.0, 20.0], [30.0, 40.0]], dtype="float32")
    lat = np.array([0.1, 0.0])
    out = block_weighted_mean(a, lat, 2)
    assert out.shape == (1, 1)
    assert abs(float(out[0, 0]) - 25.0) < 0.05


def test_nan_cells_are_ignored():
    a = np.array([[10.0, np.nan], [np.nan, 30.0]], dtype="float32")
    lat = np.array([0.1, 0.0])
    out = block_weighted_mean(a, lat, 2)
    assert abs(float(out[0, 0]) - 20.0) < 0.05  # mean of the two finite cells


def test_all_nan_block_stays_nan():
    a = np.full((2, 2), np.nan, dtype="float32")
    lat = np.array([0.1, 0.0])
    assert np.isnan(block_weighted_mean(a, lat, 2)[0, 0])


def test_block_centres():
    lon = np.array([0.0, 0.1, 0.2, 0.3])
    np.testing.assert_allclose(block_centres(lon, 2), [0.05, 0.25])


def test_trim_handles_odd_dimensions():
    # 3x3, factor 2 -> trims to the top-left 2x2 -> one block; the 3rd row/col are dropped
    a = np.array(
        [[10.0, 20.0, 99.0], [30.0, 40.0, 99.0], [99.0, 99.0, 99.0]], dtype="float32"
    )
    lat = np.array([0.2, 0.1, 0.0])
    out = block_weighted_mean(a, lat, 2)
    assert out.shape == (1, 1)
    assert abs(float(out[0, 0]) - 25.0) < 0.1  # mean of the 2x2 block, ignores the 99s
