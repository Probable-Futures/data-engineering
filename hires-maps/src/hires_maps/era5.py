"""Read the **ERA5 reanalysis** files — the observational yardstick.

ERA5 is not a model run: it is real observations (stations, satellites, buoys) fed through a
weather model to fill the gaps, producing a gridded best estimate of what actually happened. It is
the only dataset here that can answer "is our published data right", as opposed to "do two models
disagree".

Everything else this package reads is Zarr on the 0.1° lattice. These files differ in four ways
that all have to be handled here rather than leaking into the builders:

1. **netCDF, not Zarr** — hence the `netcdf4` dependency, which nothing else in this package needs.
2. **0.25°, on a 0–360 longitude axis.** Every other grid we touch runs -180…180. The columns are
   rolled and re-sorted on load, so callers never see the 0–360 convention.
3. **Two warming levels only** (0.5 and 1.0). The observed record reaches ~1.2 °C of warming, so
   there is no 2 °C or 3 °C world to aggregate. Callers must build a 2-level `property_plan`.
4. **Two different statistic-naming schemes, and one file in the wrong unit.** See `_STAT_VARS`
   and `KELVIN_SLUGS` below — both are the kind of thing that silently corrupts a map.

## The grid, and why the lookup is exact

ERA5's 0.25° does **not** divide into 0.2° (v3) or 0.1° (v4), so the integer-tenths trick in
`livemaps.py` does not carry over. But a coarser lattice still works: in units of **0.025°** every
grid involved is an integer lattice — ERA5 centres are multiples of 10, v4 centres multiples of 4,
v3 centres `3592 + 8k`. ERA5 cell boundaries sit at `10k ± 5`, and neither `4a` nor `3592 + 8b` is
ever `5 mod 10` (proof: `4a mod 10 ∈ {0,2,4,6,8}`; `3592 + 8b mod 10 ∈ {0,2,4,6,8}`). So **no
target cell centre ever lands on an ERA5 cell boundary** — there are no ties to break and no
floating-point ambiguity. `test_era5.py` asserts this on the real axes rather than trusting the
algebra.

Latitude is clipped at the poles (index -1 → NaN, never a borrowed edge value). Longitude is
periodic, so it wraps instead: a target at 179.975° belongs to ERA5's 180.0° cell, which is the
same column as -180.0°.

## Coverage

One single finite/NaN mask, identical across all 24 files and both warming levels (checked). It is
**not** a land mask: 57.1% of the global grid is finite, which is neither land (~29%) nor
everything, and it includes open Pacific but not open Atlantic. What matters for maps is that land
coverage is complete **except Antarctica** — 30.2% of v4's land cells have no ERA5 value, and
**all 668,445 of them are south of 60°S** (ERA5's last finite row is centred at 64.25°S). The gap
is entirely polar; there is no scattered non-polar component.

Note the asymmetry between the two comparison families that follows from this. v3 stops at 56.8°S
itself, so ERA5 covers everything v3 publishes and `era5v3` has no polar hole at all (813 v3-only
cells, all coastline). v4 covers Antarctica, so `era5v4` loses 30.2% of its land cells there.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import xarray as xr

from .config import ERA5_DIR, ERA5_STEP_DEG
from .mapping import PlanEntry

SHAPE = (721, 1440)  # ERA5's grid, (lat, lon)

KELVIN_OFFSET = 273.15

# Files whose values are in Kelvin and need converting to °C.
#
# `ten-hottest-wbmax-days` is deliberately ABSENT: it is a temperature, and every naming heuristic
# would include it, but that one file already ships in °C (its range is -10…30, not 260…300).
# Verified against v4 at four cities. Do not replace this list with a rule about the slug.
KELVIN_SLUGS = frozenset(
    {
        "average-temperature",
        "average-daytime-temperature",
        "average-nighttime-temperature",
        "average-winter-temperature",
        "ten-hottest-days",
        "ten-hottest-nights",
    }
)

# ERA5 file slug -> the indicator-registry slug, for the six that differ. The registry (and so the
# rest of the pipeline) is the source of truth for names; this table exists only to find the file.
_FILE_SLUG_BY_INDICATOR = {
    "days-above-26c-wbmax": "days-above-26c-wb",
    "days-above-28c-wbmax": "days-above-28c-wb",
    "days-above-30c-wbmax": "days-above-30c-wb",
    "days-above-32c-wbmax": "days-above-32c-wb",
    "ten-hottest-wbmax-days": "ten-hottest-wb-days",
}

# `stat` name (as `mapping.role_stat` produces it) -> ERA5 variable name, one dict per naming
# scheme. ERA5 ships two: 19 heat files use `perc05`/`perc50`/`perc95`, and the five water files
# (dry-hot-days, snowy-days, total-annual-precipitation, wettest-90-days, wettest-day) use
# `perc_5`/`perc_50`/`perc_95` plus extra percentiles we do not publish. Note `perc05` vs `perc_5`:
# same meaning, different spelling, so the scheme is detected per file rather than assumed.
_STAT_VARS: tuple[dict[str, str], ...] = (
    {"p5": "perc05", "p50": "perc50", "p95": "perc95", "mean": "mean"},
    {"p5": "perc_5", "p50": "perc_50", "p95": "perc_95", "mean": "mean"},
)


@dataclass
class LoadReport:
    """What `load` saw. Worth printing: a silent unit or coverage change here would skew every map
    built from the file, and none of it would look wrong on inspection."""

    slug: str
    scheme: int  # which `_STAT_VARS` entry matched
    kelvin: bool  # whether the Kelvin -> °C conversion was applied
    finite: dict[str, int] = field(default_factory=dict)  # cells with a value, per property

    def summary(self) -> str:
        cells = SHAPE[0] * SHAPE[1]
        any_finite = max(self.finite.values(), default=0)
        parts = [
            f"{self.slug}: {any_finite:,}/{cells:,} cells with a value "
            f"({100 * any_finite / cells:.1f}%)",
            f"stat scheme {self.scheme}",
        ]
        parts.append("Kelvin -> °C applied" if self.kelvin else "already in map units")
        return " | ".join(parts)


@dataclass
class Era5Data:
    """One property array per plan entry, plus the axes they sit on (longitude already rolled)."""

    arrays: dict[str, np.ndarray]
    lat: np.ndarray
    lon: np.ndarray
    report: LoadReport


def file_slug(slug: str) -> str:
    """The ERA5 filename slug for an indicator slug (they differ for the five wet-bulb maps)."""
    return _FILE_SLUG_BY_INDICATOR.get(slug, slug)


def era5_path(slug: str) -> Path:
    """Filesystem path to one indicator's ERA5 file."""
    return ERA5_DIR / f"era5_{file_slug(slug)}_wls.nc"


def available() -> list[str]:
    """Indicator slugs that have an ERA5 file on disk, in registry spelling."""
    if not ERA5_DIR.exists():
        return []
    by_file = {v: k for k, v in _FILE_SLUG_BY_INDICATOR.items()}
    out = []
    for path in ERA5_DIR.glob("era5_*_wls.nc"):
        stem = path.name[len("era5_") : -len("_wls.nc")]
        out.append(by_file.get(stem, stem))
    return sorted(out)


# --------------------------------------------------------------------------------------
# Grid arithmetic. All of it in integer units of 0.025° — see "why the lookup is exact" above.
# Floating point does not work here: the whole point is deciding which side of a cell boundary a
# coordinate falls on, and that is exactly where float error changes the answer.
# --------------------------------------------------------------------------------------
_UNIT_DEG = 0.025
_STEP_UNITS = round(ERA5_STEP_DEG / _UNIT_DEG)  # 10
_HALF_UNITS = _STEP_UNITS // 2  # 5
_LAT0_UNITS = 3600  # ERA5's northernmost centre, +90.0°
_LON_SPAN_UNITS = 14400  # a full 360° turn
_LON0_UNITS = -7200  # the westernmost centre after the roll, -180.0°


def _units(coords: np.ndarray | float) -> np.ndarray:
    """Coordinates as exact integer 0.025° units."""
    return np.rint(np.asarray(coords, dtype=float) / _UNIT_DEG).astype(np.int64)


def roll_longitude(lon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """ERA5's 0–360 longitude axis as -180…180, ascending.

    Returns `(lon, order)` — the rolled axis and the column permutation that produced it, so the
    same reordering can be applied to the data arrays. ERA5 carries a column at exactly 180.0,
    which becomes -180.0; there is no duplicate, because 359.75 is the last value.
    """
    wrapped = (_units(lon) + 7200) % _LON_SPAN_UNITS - 7200
    order = np.argsort(wrapped, kind="stable")
    return wrapped[order] * _UNIT_DEG, order


def parent_index(coords: np.ndarray, *, axis: str) -> np.ndarray:
    """For each target coordinate, the index of the ERA5 cell covering it.

    Latitude returns -1 for a coordinate more than half a cell outside the grid, so the poles come
    back as NaN rather than a borrowed edge value — matching `livemaps.parent_index`. Longitude is
    periodic and wraps instead, so it never returns -1.
    """
    if axis == "lat":
        delta = _LAT0_UNITS - _units(coords)  # latitude runs north -> south
        idx = (delta + _HALF_UNITS) // _STEP_UNITS
        return np.where((idx >= 0) & (idx < SHAPE[0]), idx, -1)
    if axis == "lon":
        delta = (_units(coords) - _LON0_UNITS) % _LON_SPAN_UNITS
        return ((delta + _HALF_UNITS) // _STEP_UNITS) % SHAPE[1]
    raise ValueError(f"axis must be 'lat' or 'lon', got {axis!r}")


def upsample(era5: np.ndarray, rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
    """Expand an ERA5 (721, 1440) array onto a finer grid using `parent_index` outputs.

    Rows with no parent (-1) come back as NaN, so a comparison there is null rather than a
    part-cell extrapolation. Only used by the comparison builders; the standalone map reads the
    ERA5 grid directly.
    """
    out = era5[np.ix_(np.clip(rows, 0, SHAPE[0] - 1), np.clip(cols, 0, SHAPE[1] - 1))]
    out = out.astype("float32", copy=True)
    out[rows < 0, :] = np.nan
    out[:, cols < 0] = np.nan
    return out


def _detect_scheme(ds: xr.Dataset, slug: str) -> int:
    """Which `_STAT_VARS` entry this file uses. Raises rather than guessing."""
    present = set(ds.data_vars)
    for i, table in enumerate(_STAT_VARS):
        if set(table.values()) <= present:
            return i
    raise ValueError(
        f"{slug}: ERA5 file has variables {sorted(present)}, which match neither known naming "
        f"scheme ({sorted(_STAT_VARS[0].values())} or {sorted(_STAT_VARS[1].values())})"
    )


def load(slug: str, plan: Sequence[PlanEntry]) -> Era5Data:
    """Load one array per planned property, in map units, on a -180…180 longitude axis.

    `plan` comes from `mapping.property_plan(ind, ERA5_WARMING_LEVELS)` — asking for a warming
    level ERA5 does not carry is an error here rather than a silently empty map.
    """
    path = era5_path(slug)
    if not path.exists():
        raise FileNotFoundError(
            f"no ERA5 file for '{slug}' at {path}. Available: {', '.join(available()) or '(none)'}"
        )

    ds = xr.open_dataset(path)
    scheme = _detect_scheme(ds, slug)
    stat_vars = _STAT_VARS[scheme]
    kelvin = slug in KELVIN_SLUGS
    levels = {float(w) for w in ds["wl"].values}

    lon, order = roll_longitude(ds["longitude"].values)
    lat = np.asarray(ds["latitude"].values, dtype=float)

    arrays: dict[str, np.ndarray] = {}
    finite: dict[str, int] = {}
    for name, wl, stat in plan:
        if wl not in levels:
            raise ValueError(
                f"{slug}: ERA5 has no warming level {wl} (it carries {sorted(levels)}). "
                f"Build the plan with config.ERA5_WARMING_LEVELS."
            )
        var = stat_vars[stat]
        a = ds[var].sel(wl=wl).values.astype("float32")[:, order]
        if kelvin:
            a = a - np.float32(KELVIN_OFFSET)
        arrays[name] = a
        finite[name] = int(np.isfinite(a).sum())

    report = LoadReport(slug=slug, scheme=scheme, kelvin=kelvin, finite=finite)
    return Era5Data(arrays=arrays, lat=lat, lon=lon, report=report)
