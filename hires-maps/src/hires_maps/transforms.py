"""Unit transforms applied to the raw Zarr values before they become map properties.

The stores are not all in the unit the matching live map publishes. Two need converting
(see `indicators.py` for which):

* **`pct100`** — the two drought stores hold a **0-1 fraction** even though their metadata says
  `units: percent`. Their baselines land on 0.31 and 0.045, exactly the fractions the live
  definitions predict (percent of months with SPEI-12 below -0.5 and -1.6), and they cap at
  1.0 at high warming. The live maps are 0-100, so multiply by 100.

* **`percentile_to_z`** — the water-balance store holds a *percentile* of the fitted
  water-balance distribution (`"Water balance percentile (SPEI-style, GLO fit)"`), but the live
  map is a change in **SPEI z-score** (bins -1 .. 1.1). SPEI *is* the standard-normal quantile
  of that percentile, so `z = Phi^-1(p / 100)`. Cross-check: the baseline percentile converts
  to a land-mean z of +0.03, i.e. "baseline is normal", as it must be.

  Carlos confirmed the forward direction (`statistics.NormalDist().cdf(z) * 100`), so this is
  exactly its inverse.

  Two consequences for water balance. The percentile scale bottoms out: measured over the full
  grid (all 6 warming levels x 6 statistics, 79,669,080 finite values) **3,800 are exactly 0**,
  where `Phi^-1` is -infinity — those are clamped to `Z_LIMIT` below. Everything else, down to a
  percentile of 0.00023 (z = -4.6), converts exactly. And because the mapping is curved, the
  change has to be taken **after** this transform, never before; that is why the builder derives
  the change itself instead of reading the store's `diff_*` variable.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

# The z-score assigned to a percentile of exactly 0 or 100, where Phi^-1 is infinite. 6.0 is
# Phi^-1(1e-9): far past any SPEI value the live map shows, so it reads as "off the bottom of the
# scale" while still sorting into the correct (most extreme) bin.
#
# Only exact 0/100 need this. Deliberately NOT a percentile floor: an earlier version clipped
# everything below the 0.05th percentile, which collapsed 522,057 values that Phi^-1 places
# perfectly well onto one number. The tail of this data is real — keep it.
Z_LIMIT = 6.0

# Acklam's rational approximation to the inverse standard-normal CDF. |error| < 1.15e-9, far
# below the 1-decimal rounding the builder applies. Vectorised on purpose: scipy is not a
# dependency and `statistics.NormalDist().inv_cdf` is scalar-only, which would mean ~100M
# Python-level calls per indicator.
_A = (
    -3.969683028665376e01,
    2.209460984245205e02,
    -2.759285104469687e02,
    1.383577518672690e02,
    -3.066479806614716e01,
    2.506628277459239e00,
)
_B = (
    -5.447609879822406e01,
    1.615858368580409e02,
    -1.556989798598866e02,
    6.680131188771972e01,
    -1.328068155288572e01,
)
_C = (
    -7.784894002430293e-03,
    -3.223964580411365e-01,
    -2.400758277161838e00,
    -2.549732539343734e00,
    4.374664141464968e00,
    2.938163982698783e00,
)
_D = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00)
_P_LOW = 0.02425  # below this (and above 1 - this) the tail branch is used


def _tail(q: np.ndarray) -> np.ndarray:
    num = ((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]
    den = (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0
    return num / den


def inv_norm_cdf(p: np.ndarray) -> np.ndarray:
    """Phi^-1(p) for p in (0, 1), elementwise. NaN in -> NaN out; 0 and 1 -> NaN."""
    p = np.asarray(p, dtype="float64")
    out = np.full(p.shape, np.nan)
    with np.errstate(invalid="ignore"):
        lower = (p > 0.0) & (p < _P_LOW)
        upper = (p > 1.0 - _P_LOW) & (p < 1.0)
        central = (p >= _P_LOW) & (p <= 1.0 - _P_LOW)
    out[lower] = _tail(np.sqrt(-2.0 * np.log(p[lower])))
    out[upper] = -_tail(np.sqrt(-2.0 * np.log1p(-p[upper])))
    q = p[central] - 0.5
    r = q * q
    num = (((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r + _A[5]) * q
    den = ((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r + _B[4]) * r + 1.0
    out[central] = num / den
    return out


def _pct100(a: np.ndarray) -> tuple[np.ndarray, int]:
    """0-1 fraction -> 0-100 percent."""
    return (a * np.float32(100.0)).astype("float32"), 0


def _percentile_to_z(a: np.ndarray) -> tuple[np.ndarray, int]:
    """0-100 percentile -> SPEI z-score. Returns (z, values clamped at +/-Z_LIMIT).

    Only a percentile of exactly 0 or 100 is clamped — `inv_norm_cdf` returns NaN there, and a
    NaN would be written as `null`, punching a hole in the map at the very driest cells. Real tail
    values are converted as they are.
    """
    finite = np.isfinite(a)
    p = a.astype("float64") / 100.0
    z = inv_norm_cdf(p)  # NaN at exactly 0 and 1
    with np.errstate(invalid="ignore"):
        off_scale = finite & ~np.isfinite(z)
        clamped = int((off_scale | (np.abs(z) > Z_LIMIT)).sum())
        z = np.where(off_scale, np.where(p <= 0.0, -Z_LIMIT, Z_LIMIT), z)
    z = np.clip(z, -Z_LIMIT, Z_LIMIT)
    return np.where(finite, z, np.nan).astype("float32"), clamped


TRANSFORMS: dict[str, Callable[[np.ndarray], tuple[np.ndarray, int]]] = {
    "pct100": _pct100,
    "percentile_to_z": _percentile_to_z,
}


def apply(name: str | None, a: np.ndarray) -> tuple[np.ndarray, int]:
    """Apply a named transform (or none). Returns (values, cells clipped)."""
    if name is None:
        return a, 0
    try:
        fn = TRANSFORMS[name]
    except KeyError:
        raise ValueError(f"unknown transform '{name}' (have: {sorted(TRANSFORMS)})") from None
    return fn(a)
