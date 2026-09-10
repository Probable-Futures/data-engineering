"""Tests for the warming-level/stat -> property-name mapping (the single source of truth)."""

from hires_maps.indicators import get
from hires_maps.mapping import MID_BASELINE_PROPERTY, property_name, property_plan, role_stat


def test_property_names_match_live_schema():
    assert property_name("baseline", "mid") == "data_baseline_mid"
    assert property_name("1_5c", "low") == "data_1_5c_low"
    assert property_name("3c", "high") == "data_3c_high"


def test_plan_has_18_entries_covering_all_levels():
    plan = property_plan(get("days-above-35c"))
    assert len(plan) == 18  # 6 warming levels x {low, mid, high}
    names = {name for name, _, _ in plan}
    assert "data_baseline_mid" in names
    assert "data_3c_high" in names


def test_mid_stat_follows_indicator_rule():
    # heat -> mean, precip/water -> median (p50)
    assert role_stat("mid", get("days-above-35c")) == "mean"
    assert role_stat("mid", get("total-annual-precipitation")) == "p50"
    assert role_stat("low", get("days-above-35c")) == "p5"
    assert role_stat("high", get("days-above-35c")) == "p95"


def test_mid_baseline_property_constant():
    assert MID_BASELINE_PROPERTY == "data_baseline_mid"
