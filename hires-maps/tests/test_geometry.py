"""Tests for the square-cell polygon geometry."""

from hires_maps.geometry import cell_ring


def test_ring_is_closed_square():
    ring = cell_ring(35.5, 33.8, half=0.05)
    assert ring[0] == ring[-1]  # closed
    assert len(ring) == 5
    # ±0.05 around the centre
    assert ring[0] == [35.45, 33.75]
    assert ring[2] == [35.55, 33.85]


def test_ring_winding_order():
    # lower-left, lower-right, upper-right, upper-left, back to lower-left
    w, s = 35.45, 33.75
    e, n = 35.55, 33.85
    assert cell_ring(35.5, 33.8, half=0.05) == [[w, s], [e, s], [e, n], [w, n], [w, s]]


def test_coordinates_clamped_to_valid_range():
    ring = cell_ring(-179.98, -89.98, half=0.05)
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    assert min(lons) >= -180.0
    assert min(lats) >= -90.0
