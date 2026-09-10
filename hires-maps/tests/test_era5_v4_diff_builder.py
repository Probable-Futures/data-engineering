"""Tests for the ERA5-vs-**v4** comparison: the new downscaled data minus the observations.

The v3 direction is in `test_era5_diff_builder.py`. What is different here, and what these tests
therefore exist to pin:

* the v4 side is a Zarr store on the 0.1° grid, not a published GeoJSON on the 0.2° one;
* change indicators get **no** conversion, because v4 stores are already absolute — the exact
  opposite of the v3 path's `from_change`, and the single most consequential difference;
* there are three rungs, so the filenames and the cell geometry vary;
* Antarctica is a real 30% hole rather than a few hundred coastal cells.

**The fake grid's anchor is load-bearing.** `conftest.py` puts the only populated ERA5 cell at
(89.75°N, -179.75°) and `era5.parent_index` works off the true global origin, so a v4 fake at the
natural-looking `lat=(90.0, 89.9)` maps *both* its rows to ERA5 row 0 — which is NaN. Every cell
would come back null, `n == 0`, and every value assertion in this file would pass vacuously against
an empty file. The arithmetic that makes V4_LAT/V4_LON right is spelled out below; keep it.
"""

import json

import numpy as np
import pytest
import xarray as xr

from hires_maps import era5, stores
from hires_maps.config import ERA5_WARMING_LEVELS, GRID_STEP_DEG
from hires_maps.geojson.era5_diff_builder import build_era5_v4_diff
from hires_maps.geojson.output import Variant, output_path
from hires_maps.indicators import get
from hires_maps.mapping import property_plan

# v4 cells that land on the populated ERA5 cell (row 1, col 1), in units of 0.025°:
#
#   lat 89.8 -> (3600 - 3592 + 5) // 10 = 1     lat 89.7 -> (3600 - 3588 + 5) // 10 = 1
#   lon -179.8 -> ((-7192 + 7200) + 5) // 10 % 2 = 1
#   lon -179.7 -> ((-7188 + 7200) + 5) // 10 % 2 = 1
#
# and the trap: lat 90.0 -> (3600 - 3600 + 5) // 10 = 0, lat 89.9 -> (3600 - 3596 + 5) // 10 = 0,
# both of which are the fake's NaN row. 90.0 is therefore reused deliberately as the "ERA5 has no
# data here" case — Antarctica in miniature.
V4_LAT = (89.8, 89.7)
V4_LON = (-179.8, -179.7)
V4_LAT_NO_ERA5 = 90.0


@pytest.fixture
def v4_store(monkeypatch):
    """A v4-shaped Zarr store on a caller-chosen 0.1° patch, with every listed cell as land.

    `conftest.fake_store` only ever makes cell (0, 0) land, which is not enough to test block
    means. This takes an explicit `land` list of (row, col) and gives every warming level in
    `values`, so a coarsening test can lay out a 2x2 block by hand.
    """

    def make(slug: str, values: dict[float, float], *, lat=V4_LAT, lon=V4_LON, land=((0, 0),)):
        ind = get(slug)
        wls = sorted({wl for _, wl, _ in property_plan(ind)})
        stats = sorted({stat for _, _, stat in property_plan(ind)})
        data = np.full((len(lat), len(lon), len(wls), len(stats)), np.nan, dtype="float32")
        for i, j in land:
            for k, wl in enumerate(wls):
                # `values` only has to carry the two ERA5 levels; the rest are never selected.
                data[i, j, k, :] = values.get(wl, np.nan)
        ds = xr.Dataset(
            {stores.value_var(slug): (("lat", "lon", "wl", "stat"), data)},
            coords={"lat": list(lat), "lon": list(lon), "wl": wls, "stat": stats},
        )
        monkeypatch.setattr(stores, "open_store", lambda _slug: ds)
        return ds

    return make


def _run(tmp_path, slug, **kwargs):
    path, n, report = build_era5_v4_diff(
        slug, tmp_path / "out.geojsonld", progress_every=0, **kwargs
    )
    features = [json.loads(line) for line in path.read_text().splitlines()]
    return features, n, report


def test_subtracts_era5_from_the_v4_value(v4_store, fake_era5, tmp_path):
    v4_store("days-above-35c", {0.5: 100.0, 1.0: 130.0})
    fake_era5("days-above-35c", {0.5: 96.0, 1.0: 110.0})
    features, n, report = _run(tmp_path, "days-above-35c")
    assert n == 1
    props = features[0]["properties"]
    assert props["data_baseline_mid"] == 4.0  # 100 - 96
    assert props["data_1c_mid"] == 20.0  # 130 - 110
    assert report.both == 1
    assert report.v4_only == 0
    assert report.store_cells == 1


def test_sign_is_v4_minus_era5_not_the_other_way(v4_store, fake_era5, tmp_path):
    # Inverting this flips every colour on every map, so it gets its own test.
    v4_store("days-above-35c", {0.5: 40.0, 1.0: 40.0})
    fake_era5("days-above-35c", {0.5: 100.0, 1.0: 100.0})
    features, _, _ = _run(tmp_path, "days-above-35c")
    assert features[0]["properties"]["data_baseline_mid"] == -60.0  # v4 cooler -> negative (blue)


def test_change_indicator_is_NOT_converted_to_a_change(v4_store, fake_era5, tmp_path):
    # The mirror image of the v3 path's `from_change` test, asserting the opposite behaviour.
    # v4 stores are absolute at every level, so the 1 °C slot must compare 1010 against ERA5's
    # 905 -- not the 10 that `to_change` would have left behind.
    slug = "total-annual-precipitation"
    v4_store(slug, {0.5: 1000.0, 1.0: 1010.0})
    fake_era5(slug, {0.5: 900.0, 1.0: 905.0}, variables=("mean", "perc_5", "perc_50", "perc_95"))
    features, _, _ = _run(tmp_path, slug)
    props = features[0]["properties"]
    assert props["data_baseline_mid"] == 100.0  # 1000 - 900
    assert props["data_1c_mid"] == 105.0  # 1010 - 905, NOT (1010 - 1000) - 905 = -895
    assert get(slug).is_change is True  # the indicator IS a change map; we ignore that here


def test_keeps_a_decimal_integer_truncation_would_erase(v4_store, fake_era5, tmp_path):
    v4_store("days-above-35c", {0.5: 30.7, 1.0: 30.7})
    fake_era5("days-above-35c", {0.5: 30.0, 1.0: 30.0})
    features, _, _ = _run(tmp_path, "days-above-35c")
    value = features[0]["properties"]["data_baseline_mid"]
    assert value == pytest.approx(0.7, abs=1e-5)
    assert isinstance(value, float)


def test_emits_only_the_two_warming_levels_era5_has(v4_store, fake_era5, tmp_path):
    ind = get("days-above-35c")
    v4_store(ind.slug, {0.5: 10.0, 1.0: 20.0})
    fake_era5(ind.slug, {0.5: 1.0, 1.0: 2.0})
    features, _, _ = _run(tmp_path, ind.slug)
    props = features[0]["properties"]
    assert len(props) == 6
    assert sorted(props) == sorted(n for n, _, _ in property_plan(ind, ERA5_WARMING_LEVELS))
    assert not any("2c" in name or "3c" in name for name in props)


def test_cells_era5_lacks_are_not_emitted(v4_store, fake_era5, tmp_path):
    # Antarctica in miniature: v4 has a value, ERA5 has none. Emitting 0 there would paint a whole
    # continent as perfect agreement, which is the one thing a comparison map must never do.
    v4_store(
        "days-above-35c",
        {0.5: 100.0, 1.0: 130.0},
        lat=(V4_LAT_NO_ERA5, V4_LAT[0]),  # row 0 has no ERA5 parent value, row 1 does
        land=((0, 0), (1, 0)),
    )
    fake_era5("days-above-35c", {0.5: 96.0, 1.0: 110.0})
    features, n, report = _run(tmp_path, "days-above-35c")
    assert n == 1  # only the cell with both halves
    assert report.store_cells == 2
    assert report.both == 1
    assert report.v4_only == 1
    lats = sorted({p[1] for p in features[0]["geometry"]["coordinates"][0]})
    assert lats[-1] == pytest.approx(V4_LAT[0] + GRID_STEP_DEG / 2)


def test_default_paths_carry_the_hires_rung_suffixes_in_the_era5_folder():
    # The regression test for two bugs that would only surface at upload time: passing a 0.2° step
    # would name these `-p04`/`-p16`, and a missing `_VARIANT_DIRS` entry would put them in `mts/`
    # while the uploader looked in `era5-geojson/`.
    ind = get("days-above-35c")
    assert output_path(ind, 1, variant=Variant.ERA5_V4).name == "40105-era5v4.geojsonld"
    assert output_path(ind, 2, variant=Variant.ERA5_V4).name == "40105-era5v4-p02.geojsonld"
    assert output_path(ind, 8, variant=Variant.ERA5_V4).name == "40105-era5v4-p08.geojsonld"
    for factor in (1, 2, 8):
        assert output_path(ind, factor, variant=Variant.ERA5_V4).parent.name == "era5-geojson"


def test_cell_geometry_is_the_native_v4_grid(v4_store, fake_era5, tmp_path):
    v4_store("days-above-35c", {0.5: 100.0, 1.0: 130.0})
    fake_era5("days-above-35c", {0.5: 96.0, 1.0: 110.0})
    features, _, _ = _run(tmp_path, "days-above-35c")
    ring = features[0]["geometry"]["coordinates"][0]
    lons = sorted({p[0] for p in ring})
    lats = sorted({p[1] for p in ring})
    assert lons[1] - lons[0] == pytest.approx(GRID_STEP_DEG)
    assert lats[1] - lats[0] == pytest.approx(GRID_STEP_DEG)


def test_coarse_rung_averages_the_comparable_cells_and_widens_the_cell(
    v4_store, fake_era5, tmp_path
):
    # A full 2x2 block, all four cells comparable but with different v4 values. The coarse cell
    # must carry their block mean and measure 0.2° per side.
    #
    # The block mean is cos(lat)-AREA-weighted, and these rows sit at 89.8°N and 89.7°N where
    # cos(lat) differs by 50% (0.00349 against 0.00524) -- so the answer is emphatically not the
    # plain mean of 115. The expectation is therefore derived from the same weights the code uses
    # rather than hardcoded, which states the property instead of a magic number. (The fake's
    # latitudes cannot be moved somewhere less extreme: `parent_index` works off the true global
    # origin, so only cells near the pole land on the fake ERA5 grid at all.)
    values = {(0, 0): 100.0, (0, 1): 110.0, (1, 0): 120.0, (1, 1): 130.0}
    ds = v4_store("days-above-35c", {0.5: 0.0, 1.0: 0.0}, land=tuple(values))
    var = stores.value_var("days-above-35c")
    for (i, j), v in values.items():
        ds[var][i, j, :, :] = v
    fake_era5("days-above-35c", {0.5: 15.0, 1.0: 15.0})

    weights = np.cos(np.radians(np.array(V4_LAT)))
    expected = (sum(values[i, j] * weights[i] for i, j in values) / (2 * weights.sum())) - 15.0
    features, n, report = _run(tmp_path, "days-above-35c", factor=2)
    assert n == 1
    assert features[0]["properties"]["data_baseline_mid"] == pytest.approx(expected, abs=0.05)
    assert expected == pytest.approx(102.0, abs=0.05)  # pin the arithmetic itself too
    ring = features[0]["geometry"]["coordinates"][0]
    assert max(p[0] for p in ring) - min(p[0] for p in ring) == pytest.approx(0.2)
    # counts stay on the native grid whatever rung was written
    assert report.both == 4
    assert report.factor == 2
    assert report.emitted == 1
    assert "native 0.1°" in report.summary()


def test_a_partly_null_block_reports_only_its_comparable_cells(v4_store, fake_era5, tmp_path):
    # Three of the four cells have no ERA5 parent value; the block must report the survivor's diff,
    # not a mean diluted toward zero by three nulls.
    ds = v4_store(
        "days-above-35c",
        {0.5: 0.0, 1.0: 0.0},
        lat=(V4_LAT[0], V4_LAT_NO_ERA5),  # row 1 (90.0) has no ERA5 value
        land=((0, 0), (0, 1), (1, 0), (1, 1)),
    )
    var = stores.value_var("days-above-35c")
    ds[var][:, :, :, :] = 200.0
    ds[var][0, 0, :, :] = 100.0  # the only cell whose ERA5 parent has a value... and its neighbour
    fake_era5("days-above-35c", {0.5: 15.0, 1.0: 15.0})
    features, n, _ = _run(tmp_path, "days-above-35c", factor=2)
    assert n == 1
    # row 0 is comparable (both columns), row 1 is not -> mean(100, 200) - 15
    assert features[0]["properties"]["data_baseline_mid"] == pytest.approx(135.0, abs=0.05)


def test_a_fully_null_block_is_dropped(v4_store, fake_era5, tmp_path):
    # Every cell in the block has a v4 value and no ERA5 parent value: nothing to emit at all.
    v4_store(
        "days-above-35c",
        {0.5: 100.0, 1.0: 130.0},
        lat=(V4_LAT_NO_ERA5, 89.9),  # both rows map to the fake's NaN ERA5 row
        land=((0, 0), (0, 1), (1, 0), (1, 1)),
    )
    fake_era5("days-above-35c", {0.5: 96.0, 1.0: 110.0})
    features, n, report = _run(tmp_path, "days-above-35c", factor=2)
    assert n == 0
    assert features == []
    assert report.both == 0
    assert report.v4_only == 4


def test_transform_guard_raises_rather_than_comparing_mismatched_units(
    v4_store, fake_era5, tmp_path
):
    # `probability-of-drought` carries `pct100`: the store holds a 0-1 fraction and the live map is
    # 0-100. Comparing the raw store against an untransformed ERA5 file would still draw a map.
    slug = "probability-of-drought"
    v4_store(slug, {0.5: 0.4, 1.0: 0.5})
    fake_era5(slug, {0.5: 40.0, 1.0: 50.0})
    with pytest.raises(ValueError, match="unit transform"):
        build_era5_v4_diff(slug, tmp_path / "out.geojsonld", progress_every=0)


def test_a_missing_era5_file_beats_the_transform_guard(v4_store, tmp_path, monkeypatch):
    # Error precedence matters: the CLI catches FileNotFoundError and turns it into a clean "skip",
    # but not ValueError. A transformed indicator with no ERA5 file must take the catchable path.
    monkeypatch.setattr(era5, "ERA5_DIR", tmp_path / "no-era5-here")
    v4_store("probability-of-drought", {0.5: 0.4, 1.0: 0.5})
    with pytest.raises(FileNotFoundError):
        build_era5_v4_diff("probability-of-drought", tmp_path / "out.geojsonld", progress_every=0)


def test_missing_era5_file_raises_file_not_found(v4_store, tmp_path, monkeypatch):
    monkeypatch.setattr(era5, "ERA5_DIR", tmp_path / "no-era5-here")
    v4_store("days-above-35c", {0.5: 1.0, 1.0: 1.0})
    with pytest.raises(FileNotFoundError):
        build_era5_v4_diff("days-above-35c", tmp_path / "out.geojsonld", progress_every=0)


def test_unknown_indicator_is_a_value_error(tmp_path):
    with pytest.raises(ValueError, match="unknown indicator"):
        build_era5_v4_diff("not-an-indicator", tmp_path / "out.geojsonld")
