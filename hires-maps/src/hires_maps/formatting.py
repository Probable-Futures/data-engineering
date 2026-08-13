"""Value precision — the last step before a value becomes a map property.

This mirrors `stat_fmt` in `netcdfs/import/helpers.py` so the new pipeline publishes the *same
numbers* as the live one. There, every value the importer writes goes through:

    def stat_fmt(pandas_value, unit):
        if unit == "z-score":
            return format_float_positional(pandas_value, precision=1)
        else:
            return int(pandas_value)

So there are exactly two behaviours, keyed off the indicator's unit:

* **`z-score`** (only water balance) — one decimal place. The live helper returns a *string*,
  which Postgres then parses into its `numeric(6,1)` column; we go straight to a float, because
  GeoJSON properties must be JSON numbers. `round(v, 1)` is the same operation as
  `format_float_positional(v, precision=1)` — both round the exact binary value, half to even
  (verified elementwise over 300k random values in `tests/test_formatting.py`).

* **everything else** (`°C`, `days`, `mm`, `%`) — a plain **integer**, and note that `int()`
  *truncates toward zero* rather than rounding: 34.9 °C becomes 34, and -34.9 becomes -34. That
  is lossy and asymmetric about zero, but it is what every currently-published map contains, so
  the new tiles have to do it too or the two disagree on the values in every popup and CSV.

Two consequences worth keeping in mind for the hi-res pipeline specifically:

* The builder loads slices as float32 (to bound memory), so a value whose float64 form sits a
  hair above an integer can land a hair below it in float32 and truncate one step lower. Only
  values that are *not* exactly representable are at risk — whole numbers up to 2^24 are exact in
  float32 — so this is the same ~4e-6 precision question the builder already documents, not a new
  one. Integer truncation just makes it visible at whole numbers rather than at tenths.

* Truncation happens *after* the change-from-baseline subtraction, matching the live pipeline:
  there the NetCDF for a change map already holds the difference, and `stat_fmt` is applied to
  that difference, never to the two absolute values separately.
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
    """
    if not isfinite(value):
        return None
    if unit == Z_SCORE_UNIT:
        # + 0.0 so a value that rounds to negative zero serialises as 0.0 rather than -0.0;
        # Postgres `numeric` has no signed zero either, so this keeps the two in step.
        return round(value, Z_SCORE_DECIMALS) + 0.0
    return int(value)  # truncation toward zero, exactly as the live helper does


def formatter(unit: str, *, decimals: int | None = None) -> Callable[[float], float | int | None]:
    """`stat_fmt` with the unit bound, for the builder's per-cell loop.

    The unit is fixed for a whole indicator, so resolving the branch once keeps a string compare
    out of a loop that runs ~18 times per cell across ~100M cells.

    `decimals` overrides the unit rule and keeps that many decimal places for every unit. The
    comparison maps (`geojson/diff_builder.py`) need it: integer truncation would erase exactly the
    signal they exist to show, since a real +0.7 °C disagreement between two datasets truncates to
    0 and renders as "these agree".
    """
    if decimals is not None:
        places = decimals

        def fmt_fixed(value: float) -> float | None:
            return round(value, places) + 0.0 if isfinite(value) else None

        return fmt_fixed

    if unit == Z_SCORE_UNIT:

        def fmt_z(value: float) -> float | None:
            return round(value, Z_SCORE_DECIMALS) + 0.0 if isfinite(value) else None

        return fmt_z

    def fmt_int(value: float) -> int | None:
        return int(value) if isfinite(value) else None

    return fmt_int
