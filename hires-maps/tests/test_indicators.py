"""Sanity checks for the indicator registry — cheap guards against typos/drift."""

from hires_maps.config import WL_PREFIX
from hires_maps.indicators import INDICATORS, get
from hires_maps.transforms import TRANSFORMS


def test_registry_covers_all_maps():
    # 28 downscaled stores, plus the one row with no store of its own: `dry-hot-days`, which has an
    # ERA5 file and a live export but no v4 store.
    assert len(INDICATORS) == 29


def test_dry_hot_days_is_registered_for_era5_only():
    # It is in the registry purely so the ERA5 builds can find its live id, unit and mid statistic;
    # there is no downscaled store for it. Values come from `conf.yaml`: `use_mean_for_mid: False`,
    # and the name ends "differences relative to 1971-2000".
    ind = get("dry-hot-days")
    assert (ind.live_id, ind.unit, ind.mid_stat, ind.is_change) == ("40607", "days", "p50", True)
    assert ind.transform is None


def test_mid_stat_rule():
    # heat -> mean, precip/water -> median
    assert get("days-above-35c").mid_stat == "mean"
    assert get("total-annual-precipitation").mid_stat == "p50"


def test_mid_stat_is_always_a_real_stat_axis_name():
    # `Literal["mean", "p50"]` has no runtime teeth without a type checker, and a typo here would
    # silently feed the wrong statistic into every `mid` property of one map.
    assert {ind.mid_stat for ind in INDICATORS.values()} <= {"mean", "p50"}


def test_every_indicator_has_live_id_and_unit():
    for ind in INDICATORS.values():
        assert ind.live_id and ind.unit


def test_wl_prefix_matches_live_naming():
    assert WL_PREFIX[0.5] == "baseline"
    assert WL_PREFIX[1.5] == "1_5c"


def test_change_maps_match_the_live_change_map_list():
    # geojson/Makefile CHANGE_MAPS_IDS, intersected with what we ship data for.
    # 40607 is a change map on the live side too, and arrives with the ERA5 batch.
    # 40704 has neither new data nor ERA5, and is registered for `v3-absolute` alone.
    # 40612 is the one CHANGE_MAPS_IDS entry with no registry row: its live export has no absolute
    # baseline to reconstruct from (null on every feature), and the map is already a ratio.
    changed = {ind.live_id for ind in INDICATORS.values() if ind.is_change}
    assert changed == {"40601", "40607", "40613", "40614", "40616", "40703", "40704"}
    assert "40612" not in {ind.live_id for ind in INDICATORS.values()}


def test_only_drought_and_water_balance_are_transformed():
    transformed = {ind.live_id: ind.transform for ind in INDICATORS.values() if ind.transform}
    assert transformed == {
        "40701": "pct100",  # store holds a 0-1 fraction; live map is 0-100 %
        "40702": "pct100",
        "40703": "percentile_to_z",  # store holds a percentile; live map is a SPEI z-score
    }


def test_every_transform_name_exists():
    for ind in INDICATORS.values():
        assert ind.transform is None or ind.transform in TRANSFORMS


def test_heat_maps_are_untouched():
    # The five already-published maps must keep going through the pipeline unchanged.
    for slug in (
        "average-temperature",
        "ten-hottest-nights",
        "days-above-32c",
        "days-above-35c",
        "frost-nights",
    ):
        ind = get(slug)
        assert not ind.is_change and ind.transform is None
