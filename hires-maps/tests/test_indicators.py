"""Sanity checks for the indicator registry — cheap guards against typos/drift."""

from hires_maps.config import WL_PREFIX
from hires_maps.indicators import INDICATORS, get


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
