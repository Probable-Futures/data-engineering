"""The single source of truth for how warming levels + statistics become GeoJSON properties.

Both the GeoJSON writer and the (future) database writer import this, so the two can never
disagree about names or which statistic is the low/mid/high value.

The property names match what the current live-map recipes and styles already read, e.g.
`data_baseline_mid`, `data_1c_mid`, `data_1_5c_low`, `data_3c_high`.
"""

from __future__ import annotations

from collections.abc import Sequence

from .config import WARMING_LEVELS, WL_PREFIX
from .indicators import Indicator

# The three values we emit per warming level, and which stat axis each reads.
LOW_STAT = "p5"
HIGH_STAT = "p95"
ROLES = ("low", "mid", "high")

# One row of a build plan: which property to emit, and the (warming level, stat) slice it reads.
PlanEntry = tuple[str, float, str]


def property_name(prefix: str, role: str) -> str:
    return f"data_{prefix}_{role}"


def role_stat(role: str, ind: Indicator) -> str:
    """Which `stat` slice feeds a given role. `mid` depends on the indicator (mean vs median)."""
    if role == "low":
        return LOW_STAT
    if role == "high":
        return HIGH_STAT
    return ind.mid_stat


def property_plan(ind: Indicator, levels: Sequence[float] = WARMING_LEVELS) -> list[PlanEntry]:
    """The full list of (property_name, warming_level, stat) an indicator must emit.

    18 entries by default: 6 warming levels x {low, mid, high}.

    `levels` narrows that. ERA5 builds pass `config.ERA5_WARMING_LEVELS` and get 6 entries, because
    observations only reach ~1.2 °C of warming — there is no 2 °C or 3 °C world to aggregate. The
    absent levels are omitted rather than emitted as null: a property that is null everywhere would
    render as the no-data colour across the whole map, which reads as a broken map rather than as
    "this level does not exist".
    """
    plan: list[PlanEntry] = []
    for wl in levels:
        prefix = WL_PREFIX[wl]
        for role in ROLES:
            plan.append((property_name(prefix, role), wl, role_stat(role, ind)))
    return plan


MID_BASELINE_PROPERTY = property_name(WL_PREFIX[0.5], "mid")
