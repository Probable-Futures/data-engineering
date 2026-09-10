"""Value precision — the last step before a value becomes a map property.

Two rules, keyed off the indicator's unit. `z-score` (only water balance) keeps one decimal;
everything else (`°C`, `days`, `mm`, `%`) becomes a plain integer, **truncated toward zero** rather
than rounded, so 34.9 °C becomes 34 and -34.9 becomes -34. That truncation is deliberate parity
with the published data, not an oversight: it is what every currently-live map contains, so the new
tiles have to do it too or the two disagree in every popup and CSV. Both rules mirror `stat_fmt` in
`netcdfs/import/helpers.py`, which every value the live importer writes goes through:

    def stat_fmt(pandas_value, unit):
        if unit == "z-score":
            return format_float_positional(pandas_value, precision=1)
        else:
            return int(pandas_value)
"""

from __future__ import annotations

from collections.abc import Callable
from math import isfinite

# The one unit the live helper special-cases, and the precision it uses for it.
Z_SCORE_UNIT = "z-score"
Z_SCORE_DECIMALS = 1


def stat_fmt(value: float, unit: str) -> float | int | None:
    """Put one value at the precision its unit publishes at. Non-finite -> None.

    NaN/inf collapse to None the way `to_remo_stat` does in the live importer (it guards every
    value with `math.isnan` before calling `stat_fmt`); for us that is ocean, or a cell the
    percentile -> z transform could not place.

    Not on the build path — both builders use `formatter()`. This is the executable statement of
    the live rule that `test_formatting.py` diffs `formatter` against.
    """
    if not isfinite(value):
        return None
    if unit == Z_SCORE_UNIT:
        # + 0.0 so a value that rounds to negative zero serialises as 0.0 rather than -0.0;
        # Postgres `numeric` has no signed zero either, so this keeps the two in step.
        return round(value, Z_SCORE_DECIMALS) + 0.0
    return int(value)


def _unit_decimals(unit: str) -> int | None:
    """Decimal places this unit publishes at, or None for the integer branch."""
    return Z_SCORE_DECIMALS if unit == Z_SCORE_UNIT else None


def formatter(unit: str, *, decimals: int | None = None) -> Callable[[float], float | int | None]:
    """`stat_fmt` with the unit bound, for the builder's per-cell loop.

    The unit is fixed for a whole indicator, so resolving the branch once keeps a string compare
    out of a loop that runs ~18 times per cell across ~100M cells.

    `decimals` overrides the unit rule and keeps that many decimal places for every unit. The
    comparison maps (`geojson/diff_builder.py`) need it: integer truncation would erase exactly the
    signal they exist to show, since a real +0.7 °C disagreement between two datasets truncates to
    0 and renders as "these agree".
    """
    places = decimals if decimals is not None else _unit_decimals(unit)
    if places is None:

        def fmt_int(value: float) -> int | None:
            return int(value) if isfinite(value) else None

        return fmt_int

    def fmt_fixed(value: float) -> float | None:
        return round(value, places) + 0.0 if isfinite(value) else None

    return fmt_fixed
