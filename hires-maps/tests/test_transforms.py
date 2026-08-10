"""Tests for the unit transforms (`transforms.py`).

The z conversion is checked against the standard library's exact `NormalDist.inv_cdf`, since our
vectorised version is an approximation.
"""

from statistics import NormalDist

import numpy as np
import pytest

from hires_maps import transforms


def test_inv_norm_cdf_matches_stdlib():
    p = np.array([0.001, 0.01, 0.02425, 0.05, 0.1, 0.3, 0.5, 0.7, 0.9, 0.95, 0.99, 0.999])
    ours = transforms.inv_norm_cdf(p)
    exact = np.array([NormalDist().inv_cdf(float(x)) for x in p])
    assert np.max(np.abs(ours - exact)) < 1e-8


def test_inv_norm_cdf_edges_and_nan():
    out = transforms.inv_norm_cdf(np.array([0.0, 1.0, np.nan]))
    assert np.isnan(out).all()  # +/-inf would poison the output; NaN is skipped downstream


def test_pct100_scales_fraction_to_percent():
    a = np.array([[0.0, 0.309, 1.0], [np.nan, 0.045, 0.5]], dtype="float32")
    out, clipped = transforms.apply("pct100", a)
    assert clipped == 0
    assert out.dtype == np.float32
    np.testing.assert_allclose(out[0], [0.0, 30.9, 100.0], rtol=1e-5)
    assert np.isnan(out[1, 0])


def test_percentile_to_z_recovers_spei_scale():
    # 50th percentile is "normal" (z=0); the live 40703 bins sit at -1 .. 1.1.
    a = np.array([50.0, 30.85, 15.87, 84.13], dtype="float32")
    out, clipped = transforms.apply("percentile_to_z", a)
    assert clipped == 0
    np.testing.assert_allclose(out, [0.0, -0.5, -1.0, 1.0], atol=1e-3)


def test_percentile_to_z_clips_tails_and_counts_them():
    # The water-balance store really does hold exact 0.0 cells at high warming.
    a = np.array([0.0, 0.01, 50.0, 100.0, np.nan], dtype="float32")
    out, clipped = transforms.apply("percentile_to_z", a)
    assert clipped == 3  # 0.0, 0.01 and 100.0 are outside the clip range; NaN is not counted
    assert np.isfinite(out[:4]).all()  # no infinities survive
    assert np.isnan(out[4])
    assert out[0] == out[1]  # both hit the floor — the spread we lose


def test_no_transform_is_identity():
    a = np.array([1.0, 2.0])
    out, clipped = transforms.apply(None, a)
    assert out is a
    assert clipped == 0


def test_unknown_transform_raises():
    with pytest.raises(ValueError, match="unknown transform"):
        transforms.apply("nope", np.array([1.0]))
