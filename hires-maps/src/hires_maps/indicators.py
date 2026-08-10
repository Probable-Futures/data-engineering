"""The indicator registry — the single source of truth linking each new map to its live map.

`use_mean_for_mid` follows the current pipeline (`conf.yaml`): heat maps use the mean as the
headline value, precipitation / drought / water-balance maps use the median (p50).

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


@dataclass(frozen=True)
class Indicator:
    slug: str  # the warming-level folder name, e.g. "days-above-35c"
    live_id: str  # the current live-map dataset id, e.g. "40105"
    unit: str  # from netcdfs/import/conf.yaml (post-transform)
    use_mean_for_mid: bool  # True -> mid = mean (heat); False -> mid = p50/median (precip/drought)
    is_change: bool = False  # emit value(wl) - value(baseline) instead of the absolute value
    transform: str | None = None  # a key of transforms.TRANSFORMS, or None

    @property
    def var(self) -> str:
        """The Zarr variable name = slug with dashes turned into underscores."""
        return self.slug.replace("-", "_")

    @property
    def mid_stat(self) -> str:
        return "mean" if self.use_mean_for_mid else "p50"


_MEAN = True  # heat-style: headline value is the mean
_MED = False  # precip/water-style: headline value is the median
_CHANGE = True  # published as a change from baseline, not an absolute value

_INDICATORS: list[Indicator] = [
    # temperatures (°C)
    Indicator("average-temperature", "40101", "°C", _MEAN),
    Indicator("average-daytime-temperature", "40102", "°C", _MEAN),
    Indicator("average-nighttime-temperature", "40201", "°C", _MEAN),
    Indicator("average-winter-temperature", "40207", "°C", _MEAN),
    Indicator("ten-hottest-days", "40103", "°C", _MEAN),
    Indicator("ten-hottest-nights", "40206", "°C", _MEAN),
    Indicator("ten-hottest-wbmax-days", "40305", "°C", _MEAN),
    # day counts
    Indicator("days-above-32c", "40104", "days", _MEAN),
    Indicator("days-above-35c", "40105", "days", _MEAN),
    Indicator("days-above-38c", "40106", "days", _MEAN),
    Indicator("days-above-45c", "40107", "days", _MEAN),
    Indicator("days-above-26c-wbmax", "40301", "days", _MEAN),
    Indicator("days-above-28c-wbmax", "40302", "days", _MEAN),
    Indicator("days-above-30c-wbmax", "40303", "days", _MEAN),
    Indicator("days-above-32c-wbmax", "40304", "days", _MEAN),
    Indicator("nights-above-20c", "40203", "days", _MEAN),
    Indicator("nights-above-25c", "40204", "days", _MEAN),
    Indicator("frost-nights", "40202", "days", _MEAN),
    Indicator("freezing-days", "40205", "days", _MEAN),
    # precipitation / water — all four are published as a change from baseline
    Indicator("total-annual-precipitation", "40601", "mm", _MED, is_change=_CHANGE),
    Indicator("wettest-90-days", "40616", "mm", _MED, is_change=_CHANGE),
    Indicator("wettest-day", "40613", "mm", _MED, is_change=_CHANGE),
    Indicator("snowy-days", "40614", "days", _MED, is_change=_CHANGE),
    # water balance: a change map AND a unit conversion (percentile -> SPEI z-score).
    Indicator(
        "average-water-balance",
        "40703",
        "z-score",
        _MED,
        is_change=_CHANGE,
        transform="percentile_to_z",
    ),
    # drought: absolute maps, but the store holds a 0-1 fraction where the live maps are 0-100.
    Indicator("probability-of-drought", "40702", "%", _MEAN, transform="pct100"),
    Indicator("probability-of-extreme-drought", "40701", "%", _MEAN, transform="pct100"),
]

INDICATORS: dict[str, Indicator] = {i.slug: i for i in _INDICATORS}


def get(slug: str) -> Indicator | None:
    return INDICATORS.get(slug)
