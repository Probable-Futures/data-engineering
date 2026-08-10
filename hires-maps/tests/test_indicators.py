"""Sanity checks for the indicator registry — cheap guards against typos/drift."""

from hires_maps.config import WL_PREFIX
from hires_maps.indicators import INDICATORS, get
from hires_maps.transforms import TRANSFORMS


def test_registry_covers_all_maps():
    assert len(INDICATORS) == 26


def test_var_name_derivation():
    assert get("days-above-35c").var == "days_above_35c"


def test_mid_stat_rule():
    # heat -> mean, precip/water -> median
    assert get("days-above-35c").mid_stat == "mean"
    assert get("total-annual-precipitation").mid_stat == "p50"


def test_every_indicator_has_live_id_and_unit():
    for ind in INDICATORS.values():
        assert ind.live_id and ind.unit


def test_wl_prefix_matches_live_naming():
    assert WL_PREFIX[0.5] == "baseline"
    assert WL_PREFIX[1.5] == "1_5c"


def test_change_maps_match_the_live_change_map_list():
    # geojson/Makefile CHANGE_MAPS_IDS, intersected with what the new data ships.
    # (40607 dry hot days, 40612 storm frequency and 40704 wildfire days are not in this batch.)
    changed = {ind.live_id for ind in INDICATORS.values() if ind.is_change}
    assert changed == {"40601", "40613", "40614", "40616", "40703"}


def test_only_drought_and_water_balance_are_transformed():
    transformed = {ind.live_id: ind.transform for ind in INDICATORS.values() if ind.transform}
    assert transformed == {
        "40701": "pct100",  # store holds a 0-1 fraction; live map is 0-100 %
        "40702": "pct100",
        "40703": "percentile_to_z",  # store holds a percentile; live map is a SPEI z-score
    }


def test_every_transform_name_exists():
    for ind in INDICATORS.values():
        assert ind.transform is None or ind.transform in TRANSFORMS


def test_heat_maps_are_untouched():
    # The five already-published maps must keep going through the pipeline unchanged.
    for slug in (
        "average-temperature",
        "ten-hottest-nights",
        "days-above-32c",
        "days-above-35c",
        "frost-nights",
    ):
        ind = get(slug)
        assert not ind.is_change and ind.transform is None
