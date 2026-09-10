"""Tests for the builder steps that put values into the form the live map publishes: the unit
transform, the change-from-baseline conversion, and the `stat_fmt` precision of what it writes.

The first two operate on the plain `{property_name: 2-D array}` dict the builder assembles, so
they need no Zarr data. The last builds a whole file from a tiny in-memory store.
"""

import json

import numpy as np
import pytest

from hires_maps.geojson.builder import build
from hires_maps.geojson.stages import apply_transform, to_change
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
    to_change(arrays)

    assert (arrays[MID_BASELINE_PROPERTY] == 0.0).all()
    np.testing.assert_allclose(arrays["data_1c_mid"], 50.0)  # 100 - 50
    np.testing.assert_allclose(arrays["data_3c_mid"], 250.0)  # 300 - 50
    # every role is converted, not just mid
    np.testing.assert_allclose(arrays["data_2c_low"], 150.0)
    np.testing.assert_allclose(arrays["data_2c_high"], 150.0)
    assert (arrays["data_baseline_low"] == 0.0).all()
    assert (arrays["data_baseline_high"] == 0.0).all()


def test_to_change_keeps_ocean_as_nan_so_the_mask_stays_meaningful():
    # The builder takes its land mask from the baseline mid BEFORE calling to_change, because
    # the zeros written here are finite. Ocean must still come out NaN either way.
    ind = get("total-annual-precipitation")
    arrays = _arrays(ind, fill=100.0)
    for a in arrays.values():
        a[0, 0] = np.nan  # one ocean cell
    to_change(arrays)

    assert np.isnan(arrays[MID_BASELINE_PROPERTY][0, 0])
    assert np.isnan(arrays["data_2c_mid"][0, 0])
    assert np.isfinite(arrays[MID_BASELINE_PROPERTY][1, 1])


def test_apply_transform_converts_every_slice():
    ind = get("probability-of-drought")  # 0-1 fraction -> 0-100 percent
    arrays = {name: np.full((2, 2), 0.31, dtype="float32") for name, _, _ in property_plan(ind)}
    clamped = apply_transform(ind, arrays)
    assert clamped == 0
    for a in arrays.values():
        np.testing.assert_allclose(a, 31.0, rtol=1e-5)


def test_apply_transform_is_a_noop_without_one():
    ind = get("days-above-35c")
    arrays = _arrays(ind)
    before = {k: v.copy() for k, v in arrays.items()}
    assert apply_transform(ind, arrays) == 0
    for k, v in arrays.items():
        np.testing.assert_array_equal(v, before[k])


def test_water_balance_transform_then_change_matches_hand_calculation():
    # The whole point of the ordering: percentile -> z first, subtract second.
    ind = get("average-water-balance")
    arrays = _arrays(ind)
    arrays[MID_BASELINE_PROPERTY][:] = 50.0  # baseline percentile: "normal"
    arrays["data_3c_mid"][:] = 15.87  # 3 °C percentile: one sigma drier
    apply_transform(ind, arrays)
    to_change(arrays)

    assert (arrays[MID_BASELINE_PROPERTY] == 0.0).all()
    np.testing.assert_allclose(arrays["data_3c_mid"], -1.0, atol=1e-3)


def _build_props(fake_store, tmp_path, slug: str, values) -> dict:
    fake_store(slug, values)
    out, n = build(slug, tmp_path / "out.geojsonld", progress_every=0)
    assert n == 1  # the ocean cell is skipped
    return json.loads(out.read_text().splitlines()[0])["properties"]


@pytest.mark.parametrize(
    ("slug", "value", "expected"),
    [
        ("days-above-35c", 34.9, 34),  # days: truncated toward zero, not rounded to 35
        ("average-temperature", -12.7, -12),  # °C: truncation is toward zero on this side too
        ("probability-of-drought", 0.315, 31),  # % after x100: 31.5 -> 31
    ],
)
def test_absolute_maps_are_written_as_truncated_integers(
    fake_store, tmp_path, slug, value, expected
):
    props = _build_props(fake_store, tmp_path, slug, value)
    for name, written in props.items():
        assert written == expected, name
        assert isinstance(written, int), name


def test_water_balance_keeps_one_decimal(fake_store, tmp_path):
    props = _build_props(fake_store, tmp_path, "average-water-balance", 15.87)
    # Every slice holds the same percentile, so every change is 0 — but it must be a float 0.0,
    # not an int, and must not be negative zero.
    for name, written in props.items():
        assert isinstance(written, float), name
        assert written == 0.0, name
        assert not str(written).startswith("-"), name


def test_change_maps_truncate_after_subtracting_not_before(fake_store, tmp_path):
    # 1 mm/level of warming, baseline 100.4: the changes are exact multiples of 1.0 and survive
    # truncation. Truncating each absolute value first (100, 101, ...) gives the same answer here;
    # what this pins down is that the builder does not truncate twice or lose the sign.
    ind = get("total-annual-precipitation")
    per_wl = {wl: 100.4 + (wl - 0.5) for _, wl, _ in property_plan(ind)}
    props = _build_props(fake_store, tmp_path, ind.slug, per_wl)

    assert props["data_baseline_mid"] == 0
    assert props["data_1c_mid"] == 0  # +0.5 mm truncates to 0
    assert props["data_2c_mid"] == 1  # +1.5 mm truncates to 1
    assert props["data_3c_mid"] == 2  # +2.5 mm truncates to 2
    assert all(isinstance(v, int) for v in props.values())


def test_ocean_cells_would_be_written_as_null(fake_store, tmp_path):
    # The land mask keys off the baseline mid, so a cell that is NaN only at a *later* warming
    # level still becomes a feature — with null for that level, never 0.
    ind = get("days-above-35c")
    per_wl = dict.fromkeys([0.5, 1.0, 1.5, 2.0, 2.5, 3.0], 40.0) | {3.0: np.nan}
    props = _build_props(fake_store, tmp_path, ind.slug, per_wl)

    assert props["data_3c_mid"] is None
    assert props["data_2c_mid"] == 40
