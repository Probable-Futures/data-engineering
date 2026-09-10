"""Tests for `dev/sampling.py`, the point lookups behind `hires-explore point` and `landmean`.

Never on the build path, so nothing here can change published output — but `value_at`'s
snap-to-land branch is the piece a human reads a number off, and it is easy to get subtly wrong.
"""

import numpy as np
import xarray as xr

from hires_maps.dev import sampling


def _grid(values, lat=(0.2, 0.1, 0.0), lon=(0.0, 0.1, 0.2)) -> xr.DataArray:
    return xr.DataArray(
        np.asarray(values, dtype="float64"),
        dims=("lat", "lon"),
        coords={"lat": list(lat), "lon": list(lon)},
    )


def test_value_at_returns_the_nearest_cell_when_it_has_a_value():
    da = _grid([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]])
    assert float(sampling.value_at(da, 0.1, 0.1)) == 5.0


def test_value_at_snaps_to_the_closest_land_cell_when_the_nearest_is_ocean():
    # The centre is ocean; its western neighbour is the closest cell that is not.
    da = _grid([[np.nan, np.nan, np.nan], [4.0, np.nan, np.nan], [np.nan, np.nan, np.nan]])
    found = sampling.value_at(da, 0.1, 0.1)
    assert float(found) == 4.0
    assert float(found["lon"]) == 0.0


def test_value_at_keeps_the_wl_and_stat_axes_intact():
    data = np.arange(2 * 2 * 3 * 2, dtype="float64").reshape(2, 2, 3, 2)
    da = xr.DataArray(
        data,
        dims=("lat", "lon", "wl", "stat"),
        coords={
            "lat": [0.1, 0.0],
            "lon": [0.0, 0.1],
            "wl": [0.5, 1.0, 1.5],
            "stat": ["p50", "mean"],
        },
    )
    cell = sampling.value_at(da, 0.1, 0.0)
    assert cell.dims == ("wl", "stat")
    assert cell.shape == (3, 2)


def test_value_at_gives_up_when_there_is_genuinely_no_land_nearby():
    # All ocean: it returns the nearest cell as-is (NaN) rather than reaching across the map.
    da = _grid(np.full((3, 3), np.nan))
    assert np.isnan(float(sampling.value_at(da, 0.1, 0.1)))


def test_value_at_will_not_search_beyond_max_deg():
    # Land exists, but further than the search radius allows.
    da = _grid([[np.nan, np.nan, np.nan], [np.nan, np.nan, np.nan], [np.nan, np.nan, 9.0]])
    assert np.isnan(float(sampling.value_at(da, 0.2, 0.0, max_deg=0.05)))


def test_area_weighted_mean_ignores_ocean_cells():
    da = _grid([[10.0, np.nan, 30.0], [np.nan, np.nan, np.nan], [np.nan, np.nan, np.nan]])
    assert sampling.area_weighted_mean(da) == 20.0


def test_area_weighted_mean_leans_toward_the_lower_latitudes():
    # cos(lat) weighting: the equatorial row counts for more than the polar one.
    da = _grid([[0.0, 0.0], [100.0, 100.0]], lat=(80.0, 0.0), lon=(0.0, 0.1))
    weighted = sampling.area_weighted_mean(da)
    assert weighted > 50.0  # a plain mean would be exactly 50
    assert weighted == float(np.cos(0.0) * 100.0 / (np.cos(np.deg2rad(80.0)) + np.cos(0.0)))
