"""Tests that our value precision is byte-for-byte the live pipeline's `stat_fmt`.

`netcdfs/import/helpers.py` is not importable from here (it pulls in boto3, sqlalchemy and the
rest of the importer), so the reference behaviour is re-stated below from that file and checked
against ours. If `stat_fmt` there ever changes, `_live_stat_fmt` is the thing to update.
"""

import math
import random

import numpy as np
import pytest
from numpy import format_float_positional

from hires_maps.formatting import formatter, stat_fmt
from hires_maps.indicators import INDICATORS


def _live_stat_fmt(value, unit):
    """Verbatim copy of `stat_fmt` from netcdfs/import/helpers.py."""
    if unit == "z-score":
        return format_float_positional(value, precision=1)
    else:
        return int(value)


# The live helper returns a string for z-score, which Postgres parses into numeric(6,1); we
# return the float directly. Comparing through float() is the fair comparison.
def _live_number(value, unit):
    live = _live_stat_fmt(value, unit)
    return float(live) + 0.0 if unit == "z-score" else live


UNITS = ["°C", "days", "mm", "%"]


@pytest.mark.parametrize("unit", UNITS)
def test_non_z_score_units_truncate_toward_zero_like_the_live_helper(unit):
    for value in [0.0, 0.4, 0.9, 1.7, 34.9, 35.0, -0.4, -0.9, -1.7, -34.9, 364.99]:
        assert stat_fmt(value, unit) == _live_number(value, unit)
        assert isinstance(stat_fmt(value, unit), int)

    # The asymmetry is deliberate — both sides truncate, they do not round.
    assert stat_fmt(34.9, unit) == 34
    assert stat_fmt(-34.9, unit) == -34


def test_z_score_keeps_one_decimal_like_the_live_helper():
    for value in [0.0, 0.04, 0.05, 0.15, 0.25, 1.04, 3.14159, -0.05, -1.25, -3.29]:
        assert stat_fmt(value, "z-score") == _live_number(value, "z-score")


def test_z_score_matches_the_live_helper_elementwise_on_random_values():
    # round(v, 1) and format_float_positional(v, precision=1) are the same operation; this is the
    # claim formatting.py rests on, so it is checked over a wide range rather than a few cases.
    rng = random.Random(1)
    for _ in range(300_000):
        value = rng.uniform(-500.0, 500.0)
        assert stat_fmt(value, "z-score") == _live_number(value, "z-score")


def test_z_score_never_returns_negative_zero():
    # json.dumps would write "-0.0"; Postgres numeric has no signed zero, so neither do we.
    result = stat_fmt(-0.01, "z-score")
    assert result == 0.0
    assert math.copysign(1.0, result) == 1.0


@pytest.mark.parametrize("unit", [*UNITS, "z-score"])
@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_non_finite_becomes_none(unit, value):
    # Ocean, and cells the percentile -> z transform could not place. The live importer guards
    # every value with math.isnan and stores NULL; we fold that into stat_fmt itself.
    assert stat_fmt(float(value), unit) is None
    assert formatter(unit)(float(value)) is None


@pytest.mark.parametrize("unit", [*UNITS, "z-score"])
def test_formatter_agrees_with_stat_fmt(unit):
    fmt = formatter(unit)
    for value in [0.0, 0.05, -0.05, 1.7, -1.7, 34.9, -34.9, 3.14159]:
        assert fmt(value) == stat_fmt(value, unit)


def test_every_registered_indicator_has_a_unit_the_formatter_handles():
    # A new unit would silently fall into the integer branch; this makes that a decision rather
    # than an accident.
    known = {"°C", "days", "mm", "%", "z-score"}
    assert {ind.unit for ind in INDICATORS.values()} <= known


def test_float32_values_go_through_unchanged():
    # The builder hands us float(np.float32(...)); make sure that widening does not upset either
    # branch (the float32 precision caveat itself is documented in formatting.py).
    value = float(np.float32(31.0))
    assert stat_fmt(value, "%") == 31
    assert stat_fmt(float(np.float32(-2.35)), "z-score") == -2.3
