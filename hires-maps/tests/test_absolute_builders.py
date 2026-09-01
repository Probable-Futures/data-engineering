"""Tests for the two absolute republishes of the change maps.

v4 (`absolute=True` on `builder.build`) and v3 (`build_v3_absolute`) reach the same place from
opposite directions: the v4 store is already absolute so the change step is skipped, while v3's
change is baked into the published data so it has to be undone. Both are pinned here, plus the
round-trip that proves `from_change` really is the inverse of `to_change`.
"""

import json

import numpy as np
import pytest

from hires_maps.geojson.builder import build
from hires_maps.geojson.output import Variant, output_path
from hires_maps.geojson.stages import from_change, to_change
from hires_maps.geojson.v3_absolute_builder import V3_STEP_DEG, build_v3_absolute
from hires_maps.indicators import get
from hires_maps.mapping import property_plan

CHANGE_SLUG = "total-annual-precipitation"  # 40601
LAT = (89.8,)
LON = (-179.8, -179.6)


def _all_props(ind, value: float) -> dict:
    return {name: value for name, _, _ in property_plan(ind)}


# --------------------------------------------------------------------------------------
# v4: absolute is the native form, so the change step is simply skipped
# --------------------------------------------------------------------------------------
def test_v4_absolute_keeps_the_store_values(fake_store, tmp_path):
    ind = get(CHANGE_SLUG)
    # baseline 800, rising 10 per level -> the change map would emit +10, +20, ...
    fake_store(ind.slug, {0.5: 800.0, 1.0: 810.0, 1.5: 820.0, 2.0: 830.0, 2.5: 840.0, 3.0: 850.0})
    path, n = build(ind.slug, tmp_path / "out.geojsonld", progress_every=0, absolute=True)
    props = json.loads(path.read_text().splitlines()[0])["properties"]
    assert props["data_baseline_mid"] == 800  # not zeroed
    assert props["data_1c_mid"] == 810  # absolute, not +10
    assert props["data_3c_mid"] == 850


def test_v4_change_build_is_unaffected(fake_store, tmp_path):
    # The default path must be byte-for-byte what it was before `absolute` existed.
    ind = get(CHANGE_SLUG)
    fake_store(ind.slug, {0.5: 800.0, 1.0: 810.0, 1.5: 820.0, 2.0: 830.0, 2.5: 840.0, 3.0: 850.0})
    path, _ = build(ind.slug, tmp_path / "out.geojsonld", progress_every=0)
    props = json.loads(path.read_text().splitlines()[0])["properties"]
    assert props["data_baseline_mid"] == 0  # zeroed by to_change
    assert props["data_1c_mid"] == 10
    assert props["data_3c_mid"] == 50


def test_v4_absolute_refuses_an_already_absolute_indicator(fake_store, tmp_path):
    with pytest.raises(ValueError, match="already an absolute map"):
        build("days-above-35c", tmp_path / "out.geojsonld", absolute=True)


def test_v4_absolute_writes_its_own_variant_path():
    ind = get(CHANGE_SLUG)
    assert output_path(ind, 1, variant=Variant.ABS).name == "40601-abs.geojsonld"
    assert output_path(ind, 2, variant=Variant.ABS).name == "40601-abs-p02.geojsonld"
    # and does not collide with the change version
    assert output_path(ind, 1).name == "40601-hires.geojsonld"


# --------------------------------------------------------------------------------------
# v3: the change is baked in, so it has to be undone
# --------------------------------------------------------------------------------------
def test_v3_absolute_adds_the_baseline_back(live_export, tmp_path):
    ind = get(CHANGE_SLUG)
    # The live shape: an ABSOLUTE baseline of 1000 alongside changes of +12.
    props = _all_props(ind, 12.0)
    for role in ("low", "mid", "high"):
        props[f"data_baseline_{role}"] = 1000.0
    live_export(ind.live_id, [(89.8, -179.8, props)])

    path, n, report = build_v3_absolute(ind.slug, tmp_path / "out.geojsonld", progress_every=0)
    out = json.loads(path.read_text().splitlines()[0])["properties"]
    assert n == 1
    assert out["data_baseline_mid"] == 1000  # untouched
    assert out["data_1c_mid"] == 1012  # 1000 + 12
    assert out["data_3c_mid"] == 1012
    assert report.cells == 1


def test_v3_absolute_emits_cells_on_the_live_grid(live_export, tmp_path):
    ind = get(CHANGE_SLUG)
    props = _all_props(ind, 5.0)
    for role in ("low", "mid", "high"):
        props[f"data_baseline_{role}"] = 100.0
    live_export(ind.live_id, [(89.8, -179.8, props)])
    path, _, _ = build_v3_absolute(ind.slug, tmp_path / "out.geojsonld", progress_every=0)
    ring = json.loads(path.read_text().splitlines()[0])["geometry"]["coordinates"][0]
    lons = sorted({p[0] for p in ring})
    assert lons[1] - lons[0] == pytest.approx(V3_STEP_DEG)  # 0.2°, not 0.1°


def test_v3_absolute_refuses_an_already_absolute_indicator(live_export, tmp_path):
    with pytest.raises(ValueError, match="published absolute already"):
        build_v3_absolute("days-above-35c", tmp_path / "out.geojsonld")


def test_v3_absolute_needs_a_live_export(live_export, tmp_path):
    with pytest.raises(FileNotFoundError):
        build_v3_absolute(CHANGE_SLUG, tmp_path / "out.geojsonld")


def test_v3_absolute_output_path():
    assert (
        output_path(get(CHANGE_SLUG), 1, variant=Variant.V3ABS, step=V3_STEP_DEG).name
        == "40601-v3abs.geojsonld"
    )


# --------------------------------------------------------------------------------------
# from_change is exactly the inverse of to_change
# --------------------------------------------------------------------------------------
def test_from_change_inverts_to_change():
    ind = get(CHANGE_SLUG)
    rng = np.random.default_rng(0)
    original = {
        name: rng.uniform(0, 2000, size=(3, 3)).astype("float32")
        for name, _, _ in property_plan(ind)
    }
    working = {k: v.copy() for k, v in original.items()}

    to_change(working, zero_baseline=False)
    from_change(working)

    for name, before in original.items():
        np.testing.assert_allclose(working[name], before, rtol=1e-6, atol=1e-3)


def test_from_change_leaves_nan_as_nan():
    ind = get(CHANGE_SLUG)
    arrays = {name: np.full((2, 2), np.nan, dtype="float32") for name, _, _ in property_plan(ind)}
    arrays["data_baseline_mid"][0, 0] = 100.0
    from_change(arrays)
    # a level that was NaN stays NaN even where the baseline has a value
    assert np.isnan(arrays["data_1c_mid"][0, 0])
    assert arrays["data_baseline_mid"][0, 0] == 100.0
