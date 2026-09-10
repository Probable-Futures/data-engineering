"""Tests for the ERA5-vs-**v3** comparison: the live v3 data minus the observations.

Both halves are faked — the shared `fake_era5` fixture for the observations and a `.geojsonld` for
v3 (the pattern from `test_diff_builder.py`) — so the join, the sign, the change reconstruction and
the null handling can be pinned down without touching the real files.

`conftest.py` explains why the fake ERA5 grid must sit at the true global origin. The v3 constants
below are the consequence: they are the coordinates that land on the one populated ERA5 cell.

The v4 direction lives in `test_era5_v4_diff_builder.py`.
"""

import json

import pytest

from hires_maps import era5
from hires_maps.config import ERA5_WARMING_LEVELS, V3_STEP_DEG
from hires_maps.geojson.era5_diff_builder import build_era5_v3_diff
from hires_maps.geojson.output import Variant, output_path
from hires_maps.indicators import get
from hires_maps.mapping import property_plan

# The v3 cell used throughout, and the ERA5 cell it falls inside.
#
#   v3 89.8°N  -> ERA5 row 1 (89.75°N): (3600 - 3592 + 5) // 10 = 1
#   v3 -179.8° -> ERA5 col 1 (-179.75°): (-7192 + 7200 + 5) // 10 = 1
#
# and v3 89.4°N -> row (3600 - 3576 + 5) // 10 = 2, which is off a 2-row fake grid: null.
V3_LAT, V3_LON = 89.8, -179.8
V3_LAT_NO_PARENT = 89.4


def _era5_props(ind, value: float) -> dict:
    """Every property an ERA5-level plan asks for, at one value — the six-entry, two-level plan.

    Same thing as the `era5_props` fixture in conftest; kept as a plain function here because these
    tests call it inline while building their `live_export` rows.
    """
    return {name: value for name, _, _ in property_plan(ind, ERA5_WARMING_LEVELS)}


def _run(fake_era5, live_export, tmp_path, slug, era5_values, live_cells):
    fake_era5(slug, era5_values)
    live_export(get(slug).live_id, live_cells)
    path, n, report = build_era5_v3_diff(slug, tmp_path / "out.geojsonld", progress_every=0)
    features = [json.loads(line) for line in path.read_text().splitlines()]
    return features, n, report


def test_subtracts_era5_from_the_live_v3_value(fake_era5, live_export, tmp_path):
    ind = get("days-above-35c")
    features, n, report = _run(
        fake_era5,
        live_export,
        tmp_path,
        ind.slug,
        {0.5: 96.0, 1.0: 110.0},
        [(V3_LAT, V3_LON, _era5_props(ind, 163.0))],
    )
    assert n == 1
    props = features[0]["properties"]
    assert props["data_baseline_mid"] == 67.0  # 163 - 96, v3 reads HIGHER -> positive
    assert props["data_1c_mid"] == 53.0  # 163 - 110
    assert report.both == 1
    assert report.v3_only == 0


def test_sign_is_v3_minus_era5_not_the_other_way(fake_era5, live_export, tmp_path):
    # The single most consequential thing to get wrong: it inverts every colour on every map.
    ind = get("days-above-35c")
    features, _, _ = _run(
        fake_era5,
        live_export,
        tmp_path,
        ind.slug,
        {0.5: 100.0, 1.0: 100.0},
        [(V3_LAT, V3_LON, _era5_props(ind, 40.0))],
    )
    assert features[0]["properties"]["data_baseline_mid"] == -60.0  # v3 cooler -> negative (blue)


def test_keeps_a_decimal_integer_truncation_would_erase(fake_era5, live_export, tmp_path):
    # A real +0.7 day bias must not truncate to 0 and render as "these agree".
    ind = get("days-above-35c")
    features, _, _ = _run(
        fake_era5,
        live_export,
        tmp_path,
        ind.slug,
        {0.5: 30.0, 1.0: 30.0},
        [(V3_LAT, V3_LON, _era5_props(ind, 30.7))],
    )
    value = features[0]["properties"]["data_baseline_mid"]
    assert value == pytest.approx(0.7)
    assert isinstance(value, float)


def test_emits_only_the_two_warming_levels_era5_has(fake_era5, live_export, tmp_path):
    ind = get("days-above-35c")
    features, _, _ = _run(
        fake_era5,
        live_export,
        tmp_path,
        ind.slug,
        {0.5: 10.0, 1.0: 20.0},
        [(V3_LAT, V3_LON, _era5_props(ind, 50.0))],
    )
    assert sorted(features[0]["properties"]) == sorted(
        name for name, _, _ in property_plan(ind, ERA5_WARMING_LEVELS)
    )
    assert len(features[0]["properties"]) == 6
    assert not any("2c" in name or "3c" in name for name in features[0]["properties"])


def test_cells_era5_lacks_become_null_not_zero(fake_era5, live_export, tmp_path):
    # Antarctica in miniature: v3 has a value, ERA5 has none. Zero would paint a whole continent
    # as perfect agreement; the cell must simply not be emitted.
    ind = get("days-above-35c")
    features, n, report = _run(
        fake_era5,
        live_export,
        tmp_path,
        ind.slug,
        {0.5: 96.0, 1.0: 110.0},
        [
            (V3_LAT, V3_LON, _era5_props(ind, 163.0)),
            (V3_LAT_NO_PARENT, V3_LON, _era5_props(ind, 163.0)),  # no ERA5 parent row
        ],
    )
    assert n == 1  # only the cell with both halves
    assert report.both == 1
    assert report.v3_only == 1
    # and the one that survived is the cell that had an ERA5 parent, not the other one
    lats = sorted({point[1] for point in features[0]["geometry"]["coordinates"][0]})
    assert lats[0] == pytest.approx(V3_LAT - 0.1)
    assert lats[-1] == pytest.approx(V3_LAT + 0.1)


def test_change_map_reconstructs_absolutes_before_subtracting(fake_era5, live_export, tmp_path):
    # The live export ships an ABSOLUTE baseline (1041 mm) next to a CHANGE at 1 °C (+12 mm).
    # ERA5 is absolute at both levels, so the 1 °C slot must compare 1053 against ERA5 — not 12.
    slug = "total-annual-precipitation"
    ind = get(slug)
    live = _era5_props(ind, 12.0)
    for name, wl, _stat in property_plan(ind, ERA5_WARMING_LEVELS):
        if wl == 0.5:
            live[name] = 1041.0
    features, _, _ = _run(
        fake_era5, live_export, tmp_path, slug, {0.5: 1000.0, 1.0: 1010.0}, [(V3_LAT, V3_LON, live)]
    )
    props = features[0]["properties"]
    assert props["data_baseline_mid"] == 41.0  # 1041 - 1000, absolute vs absolute
    assert props["data_1c_mid"] == 43.0  # (1041 + 12) - 1010, NOT 12 - 1010


def test_cell_geometry_is_the_v3_grid_not_era5s(fake_era5, live_export, tmp_path):
    # The output sits on v3's 0.2° lattice; a 0.25° polygon here would mean the grid was taken
    # from the wrong side of the comparison.
    ind = get("days-above-35c")
    features, _, _ = _run(
        fake_era5,
        live_export,
        tmp_path,
        ind.slug,
        {0.5: 96.0, 1.0: 110.0},
        [(V3_LAT, V3_LON, _era5_props(ind, 163.0))],
    )
    ring = features[0]["geometry"]["coordinates"][0]
    lons = sorted({point[0] for point in ring})
    lats = sorted({point[1] for point in ring})
    assert lons[1] - lons[0] == pytest.approx(V3_STEP_DEG)
    assert lats[1] - lats[0] == pytest.approx(V3_STEP_DEG)


def test_default_output_path_is_a_single_bare_rung_in_the_era5_folder(fake_era5, live_export):
    # No pyramid, so no `-pNN` suffix — and it lands beside the standalone ERA5 maps.
    path = output_path(get("days-above-35c"), 1, variant=Variant.ERA5_V3, step=V3_STEP_DEG)
    assert path.name == "40105-era5v3.geojsonld"
    assert path.parent.name == "era5-geojson"


def test_missing_era5_file_raises_file_not_found(live_export, tmp_path, monkeypatch):
    # What `era5-diff-all` catches to report a blocker by name instead of dying. The redirect is
    # what makes this a test rather than a read of the real 33 MB netCDF off disk.
    monkeypatch.setattr(era5, "ERA5_DIR", tmp_path / "no-era5-here")
    live_export("40105", [(V3_LAT, V3_LON, _era5_props(get("days-above-35c"), 1.0))])
    with pytest.raises(FileNotFoundError):
        build_era5_v3_diff("days-above-35c", tmp_path / "out.geojsonld", progress_every=0)


def test_missing_live_export_raises_file_not_found(fake_era5, live_export, tmp_path):
    fake_era5("days-above-35c", {0.5: 1.0, 1.0: 1.0})  # ERA5 present, v3 export absent
    with pytest.raises(FileNotFoundError):
        build_era5_v3_diff("days-above-35c", tmp_path / "out.geojsonld", progress_every=0)


def test_unknown_indicator_is_a_value_error(tmp_path):
    with pytest.raises(ValueError, match="unknown indicator"):
        build_era5_v3_diff("not-an-indicator", tmp_path / "out.geojsonld")
