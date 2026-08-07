"""The single source of truth for how warming levels + statistics become GeoJSON properties.

Both the GeoJSON writer and the (future) database writer import this, so the two can never
disagree about names or which statistic is the low/mid/high value.

The property names match what the current live-map recipes and styles already read, e.g.
`data_baseline_mid`, `data_1c_mid`, `data_1_5c_low`, `data_3c_high`.
"""

from __future__ import annotations

from .config import WARMING_LEVELS, WL_PREFIX
from .indicators import Indicator

# The three values we emit per warming level, and which stat axis each reads.
LOW_STAT = "p5"
HIGH_STAT = "p95"
ROLES = ("low", "mid", "high")


def property_name(prefix: str, role: str) -> str:
    return f"data_{prefix}_{role}"


def role_stat(role: str, ind: Indicator) -> str:
    """Which `stat` slice feeds a given role. `mid` depends on the indicator (mean vs median)."""
    if role == "low":
        return LOW_STAT
    if role == "high":
        return HIGH_STAT
    return ind.mid_stat  # "mean" for heat, "p50" for precip/drought/water


def property_plan(ind: Indicator) -> list[tuple[str, float, str]]:
    """The full list of (property_name, warming_level, stat) an indicator must emit.

    18 entries: 6 warming levels x {low, mid, high}.
    """
    plan: list[tuple[str, float, str]] = []
    for wl in WARMING_LEVELS:
        prefix = WL_PREFIX[wl]
        for role in ROLES:
            plan.append((property_name(prefix, role), wl, role_stat(role, ind)))
    return plan


MID_BASELINE_PROPERTY = property_name(WL_PREFIX[0.5], "mid")  # "data_baseline_mid"
