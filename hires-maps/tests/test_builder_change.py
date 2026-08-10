"""Tests for the two builder steps that put values into the form the live map publishes:
the unit transform and the change-from-baseline conversion.

Both operate on the plain `{property_name: 2-D array}` dict the builder assembles, so they need
no Zarr data.
"""

import numpy as np

from hires_maps.geojson.builder import _apply_transform, _to_change
from hires_maps.indicators import get
from hires_maps.mapping import MID_BASELINE_PROPERTY, property_plan


def _arrays(ind, fill: float = 1.0) -> dict[str, np.ndarray]:
    """One 2x2 array per planned property, distinct per warming level so subtraction is visible."""
    out = {}
    for name, wl, _stat in property_plan(ind):
        out[name] = np.full((2, 2), fill * wl, dtype="float32")
    return out


def test_to_change_subtracts_baseline_and_zeroes_it():
    ind = get("total-annual-precipitation")
    arrays = _arrays(ind, fill=100.0)  # baseline=50, 1c=100, 1_5c=150, ... 3c=300
    _to_change(arrays)

    assert (arrays[MID_BASELINE_PROPERTY] == 0.0).all()
    np.testing.assert_allclose(arrays["data_1c_mid"], 50.0)  # 100 - 50
    np.testing.assert_allclose(arrays["data_3c_mid"], 250.0)  # 300 - 50
    # every role is converted, not just mid
    np.testing.assert_allclose(arrays["data_2c_low"], 150.0)
    np.testing.assert_allclose(arrays["data_2c_high"], 150.0)
    assert (arrays["data_baseline_low"] == 0.0).all()
    assert (arrays["data_baseline_high"] == 0.0).all()


def test_to_change_keeps_ocean_as_nan_so_the_mask_stays_meaningful():
    # The builder takes its land mask from the baseline mid BEFORE calling _to_change, because
    # the zeros written here are finite. Ocean must still come out NaN either way.
    ind = get("total-annual-precipitation")
    arrays = _arrays(ind, fill=100.0)
    for a in arrays.values():
        a[0, 0] = np.nan  # one ocean cell
    _to_change(arrays)

    assert np.isnan(arrays[MID_BASELINE_PROPERTY][0, 0])
    assert np.isnan(arrays["data_2c_mid"][0, 0])
    assert np.isfinite(arrays[MID_BASELINE_PROPERTY][1, 1])


def test_apply_transform_converts_every_slice():
    ind = get("probability-of-drought")  # 0-1 fraction -> 0-100 percent
    arrays = {name: np.full((2, 2), 0.31, dtype="float32") for name, _, _ in property_plan(ind)}
    clipped = _apply_transform(ind, arrays)
    assert clipped == 0
    for a in arrays.values():
        np.testing.assert_allclose(a, 31.0, rtol=1e-5)


def test_apply_transform_is_a_noop_without_one():
    ind = get("days-above-35c")
    arrays = _arrays(ind)
    before = {k: v.copy() for k, v in arrays.items()}
    assert _apply_transform(ind, arrays) == 0
    for k, v in arrays.items():
        np.testing.assert_array_equal(v, before[k])


def test_water_balance_transform_then_change_matches_hand_calculation():
    # The whole point of the ordering: percentile -> z first, subtract second.
    ind = get("average-water-balance")
    arrays = _arrays(ind)
    arrays[MID_BASELINE_PROPERTY][:] = 50.0  # baseline percentile: "normal"
    arrays["data_3c_mid"][:] = 15.87  # 3 °C percentile: one sigma drier
    _apply_transform(ind, arrays)
    _to_change(arrays)

    assert (arrays[MID_BASELINE_PROPERTY] == 0.0).all()
    np.testing.assert_allclose(arrays["data_3c_mid"], -1.0, atol=1e-3)
