"""Tests for the comparison builder: new hi-res data minus the currently-live map.

Both halves are faked — a tiny in-memory Zarr-shaped Dataset for the new side (the pattern from
`test_builder_change.py`) and a two-line `.geojsonld` for the live side — so the arithmetic and the
change-map baseline asymmetry can be pinned down without touching the real 7.8 GB of exports.
"""

import json

import pytest

from hires_maps import stores
from hires_maps.geojson.diff_builder import build_diff
from hires_maps.indicators import get
from hires_maps.mapping import property_plan

# One cell that is a live centre too, plus an ocean neighbour.
LAT = (89.8,)
LON = (-179.8, -179.6)


def _all_props(ind, value: float) -> dict:
    return {name: value for name, _, _ in property_plan(ind)}


def _run(live_export, tmp_path, slug, live_cells):
    """Write the live half, build the comparison map against whatever new-side store is in place,
    and return its parsed features. The caller sets the new side up with `fake_store` first."""
    live_export(get(slug).live_id, live_cells)
    path, n, report = build_diff(slug, tmp_path / "out.geojsonld", progress_every=0)
    lines = path.read_text().splitlines()
    return [json.loads(line)["properties"] for line in lines], n, report


def test_absolute_map_subtracts_live_from_new(fake_store, live_export, tmp_path):
    ind = get("days-above-35c")
    fake_store(ind.slug, 40.0, lat=LAT, lon=LON)
    live = [(89.8, -179.8, _all_props(ind, 30.0))]
    props, n, report = _run(live_export, tmp_path, ind.slug, live)
    assert n == 1  # the ocean cell is skipped
    for name, value in props[0].items():
        assert value == 10.0, name
        assert isinstance(value, float), name  # one decimal, not truncated to int
    assert report.both == 1
    assert report.new_only == 0
    assert report.live_only == 0


def test_diff_keeps_a_decimal_integer_truncation_would_erase(fake_store, live_export, tmp_path):
    # The whole point of DIFF_DECIMALS: a real +0.7 day disagreement must not become 0.
    ind = get("days-above-35c")
    fake_store(ind.slug, 30.7, lat=LAT, lon=LON)
    props, _, _ = _run(live_export, tmp_path, ind.slug, [(89.8, -179.8, _all_props(ind, 30.0))])
    assert props[0]["data_1c_mid"] == 0.7


def test_change_map_compares_changes_and_absolute_baselines(fake_store, live_export, tmp_path):
    # New: absolute 100 at baseline rising 10 a level -> changes of +10, +20, ... after to_change.
    # Live: an ABSOLUTE baseline of 90 alongside changes of +4 (how the live exports really look).
    slug = "total-annual-precipitation"
    ind = get(slug)
    per_wl = {0.5: 100.0, 1.0: 110.0, 1.5: 120.0, 2.0: 130.0, 2.5: 140.0, 3.0: 150.0}
    live = _all_props(ind, 4.0)
    for name, wl, _stat in property_plan(ind):
        if wl == 0.5:
            live[name] = 90.0
    fake_store(slug, per_wl, lat=LAT, lon=LON)
    props, _, _ = _run(live_export, tmp_path, slug, [(89.8, -179.8, live)])

    # baseline slot: absolute vs absolute
    assert props[0]["data_baseline_mid"] == 10.0  # 100 - 90
    # every other slot: change vs change
    assert props[0]["data_1c_mid"] == 6.0  # (110-100) - 4
    assert props[0]["data_3c_mid"] == 46.0  # (150-100) - 4


def test_cells_the_live_map_lacks_become_null_not_zero(fake_store, live_export, tmp_path):
    # A coastal fringe exists because the live grid is coarser. Those cells must be null, or the
    # whole coastline reads as a real red/blue disagreement.
    ind = get("days-above-35c")
    ds = fake_store(ind.slug, 40.0, lat=LAT, lon=LON)
    ds[stores.value_var(ind.slug)].loc[{"lon": -179.6}] = 40.0  # new has the second cell too
    rows, n, report = _run(live_export, tmp_path, ind.slug, [(89.8, -179.8, _all_props(ind, 30.0))])

    assert report.new_only == 1
    assert n == 1  # the new-only cell has no comparable value, so it is not emitted
    assert rows[0]["data_1c_mid"] == 10.0


def test_missing_live_export_raises(fake_store, live_export, tmp_path):
    fake_store("days-above-35c", 1.0, lat=LAT, lon=LON)
    with pytest.raises(FileNotFoundError, match="no live export"):
        build_diff("days-above-35c", tmp_path / "out.geojsonld", progress_every=0)


def test_unknown_indicator_raises(tmp_path):
    with pytest.raises(ValueError, match="unknown indicator"):
        build_diff("not-a-map", tmp_path / "out.geojsonld")


def test_output_path_uses_the_diff_suffix():
    from hires_maps.config import LIVE_MAPS_DIR
    from hires_maps.geojson.output import Variant, output_path

    ind = get("days-above-35c")
    assert output_path(ind, 1, variant=Variant.DIFF).name == "40105-diff.geojsonld"
    assert output_path(ind, 2, variant=Variant.DIFF).name == "40105-diff-p02.geojsonld"
    assert output_path(ind, 8, variant=Variant.DIFF).name == "40105-diff-p08.geojsonld"

    # Its own folder, a sibling of the live exports it is differenced against. `vector-tiles`
    # hardcodes the same folder name as DIFF_SUBDIR, so this name is a contract.
    parent = output_path(ind, 1, variant=Variant.DIFF).parent
    assert parent.name == "diff-geojson"
    assert parent.parent == LIVE_MAPS_DIR.parent


def test_coverage_counts_stay_on_the_native_grid_while_emitted_follows_the_rung(
    fake_store, live_export, tmp_path
):
    # The counts answer "how much of each grid has no counterpart", which only means anything
    # where the two grids meet. Recomputing them after coarsening would collapse `new_only`
    # toward 0. `emitted` is the number that follows the rung.
    ind = get("days-above-35c")
    ds = fake_store(ind.slug, 40.0, lat=(89.8, 89.7), lon=(-179.8, -179.7))
    ds[stores.value_var(ind.slug)][:] = 40.0  # all four native cells are land
    live = [
        (lat, lon, _all_props(ind, 30.0))
        for lat in (89.8, 89.6)
        for lon in (-179.8, -179.6)
    ]
    live_export(ind.live_id, live)

    path, n, report = build_diff(
        ind.slug, tmp_path / "out.geojsonld", factor=2, progress_every=0
    )

    assert report.both == 4  # four native cells, counted before coarsening
    assert report.new_only == 0
    assert report.live_only == 0
    assert report.factor == 2
    assert report.emitted == n == 1  # which is one 0.2° cell
    assert "comparable cells on the native 0.1° grid: 4" in report.summary()
    assert json.loads(path.read_text().splitlines()[0])["properties"]["data_1c_mid"] == 10.0
