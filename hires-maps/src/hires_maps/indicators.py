"""The indicator registry — the single source of truth linking each new map to its live map.

`mid_stat` names the `stat` slice that feeds the headline `mid` value, following the current
pipeline (`conf.yaml`): heat and drought maps use the mean, precipitation / water-balance maps
use the median (p50).

`is_change` marks the maps the app publishes as a *change from baseline* rather than an absolute
value — the `CHANGE_MAPS_IDS` list in `geojson/Makefile`, intersected with what the new data
ships. The app never paints the baseline layer for these (it bumps 0.5 °C to 1.0 °C), so their
`data_baseline_*` properties are set to 0.

`transform` names a unit conversion from `transforms.py`, for the stores whose units do not
match the live map (the drought pair and water balance). `unit` is always the unit AFTER the
transform, i.e. what the live map actually publishes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Indicator:
    slug: str  # the warming-level folder name, e.g. "days-above-35c"
    live_id: str  # the current live-map dataset id, e.g. "40105"
    unit: str  # from netcdfs/import/conf.yaml (post-transform)
    mid_stat: Literal["mean", "p50"]  # which `stat` slice the headline `mid` value reads
    is_change: bool = False  # emit value(wl) - value(baseline) instead of the absolute value
    transform: str | None = None  # a key of transforms.TRANSFORMS, or None


_INDICATORS: list[Indicator] = [
    # temperatures (°C)
    Indicator("average-temperature", "40101", "°C", mid_stat="mean"),
    Indicator("average-daytime-temperature", "40102", "°C", mid_stat="mean"),
    Indicator("average-nighttime-temperature", "40201", "°C", mid_stat="mean"),
    Indicator("average-winter-temperature", "40207", "°C", mid_stat="mean"),
    Indicator("ten-hottest-days", "40103", "°C", mid_stat="mean"),
    Indicator("ten-hottest-nights", "40206", "°C", mid_stat="mean"),
    Indicator("ten-hottest-wbmax-days", "40305", "°C", mid_stat="mean"),
    # day counts
    Indicator("days-above-32c", "40104", "days", mid_stat="mean"),
    Indicator("days-above-35c", "40105", "days", mid_stat="mean"),
    Indicator("days-above-38c", "40106", "days", mid_stat="mean"),
    Indicator("days-above-45c", "40107", "days", mid_stat="mean"),
    Indicator("days-above-26c-wbmax", "40301", "days", mid_stat="mean"),
    Indicator("days-above-28c-wbmax", "40302", "days", mid_stat="mean"),
    Indicator("days-above-30c-wbmax", "40303", "days", mid_stat="mean"),
    Indicator("days-above-32c-wbmax", "40304", "days", mid_stat="mean"),
    Indicator("nights-above-20c", "40203", "days", mid_stat="mean"),
    Indicator("nights-above-25c", "40204", "days", mid_stat="mean"),
    Indicator("frost-nights", "40202", "days", mid_stat="mean"),
    Indicator("freezing-days", "40205", "days", mid_stat="mean"),
    # precipitation / water — all four are published as a change from baseline
    Indicator("total-annual-precipitation", "40601", "mm", mid_stat="p50", is_change=True),
    Indicator("wettest-90-days", "40616", "mm", mid_stat="p50", is_change=True),
    Indicator("wettest-day", "40613", "mm", mid_stat="p50", is_change=True),
    Indicator("snowy-days", "40614", "days", mid_stat="p50", is_change=True),
    # water balance: a change map AND a unit conversion (percentile -> SPEI z-score).
    Indicator(
        "average-water-balance",
        "40703",
        "z-score",
        mid_stat="p50",
        is_change=True,
        transform="percentile_to_z",
    ),
    # drought: absolute maps, but the store holds a 0-1 fraction where the live maps are 0-100.
    Indicator("probability-of-drought", "40702", "%", mid_stat="mean", transform="pct100"),
    Indicator("probability-of-extreme-drought", "40701", "%", mid_stat="mean", transform="pct100"),
]

INDICATORS: dict[str, Indicator] = {i.slug: i for i in _INDICATORS}


def get(slug: str) -> Indicator | None:
    return INDICATORS.get(slug)
