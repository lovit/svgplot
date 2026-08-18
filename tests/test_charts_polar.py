from __future__ import annotations

import math
import re

import pytest

from svgplot.charts._polar import FULL_CIRCLE_TOLERANCE, arc_path, full_ring_path, polar_point, ring_path

CX, CY, R = 100.0, 100.0, 50.0

_MOVE_RE = re.compile(r"M (-?[\d.]+),(-?[\d.]+)")
_LINE_RE = re.compile(r"L (-?[\d.]+),(-?[\d.]+)")
_ARC_RE = re.compile(r"A ([\d.]+),[\d.]+ 0 (\d) (\d) (-?[\d.]+),(-?[\d.]+)")


def _arc_extremes(start: tuple[float, float], radius: float, sweep_flag: int, end: tuple[float, float]) -> list:
    """Sample points actually traced by one arc about the known centre.

    Counting ``A`` commands proves nothing about what gets drawn: an arc whose start
    and end coincide sweeps nothing and is dropped by the renderer (SVG spec F.6.2).
    Walking the swept angular range is what distinguishes a real circle from two
    degenerate commands that render as half of one.
    """
    start_angle = math.atan2(start[1] - CY, start[0] - CX)
    end_angle = math.atan2(end[1] - CY, end[0] - CX)
    span = (end_angle - start_angle) % (2 * math.pi) if sweep_flag else -((start_angle - end_angle) % (2 * math.pi))
    steps = 64
    return [polar_point(CX, CY, radius, start_angle + span * step / steps) for step in range(steps + 1)]


def _path_bbox(path_data: str) -> tuple[float, float, float, float]:
    """(min_x, min_y, max_x, max_y) actually covered by a path, arcs included."""
    points = [(float(x), float(y)) for x, y in _MOVE_RE.findall(path_data) + _LINE_RE.findall(path_data)]
    current = points[0]
    for radius, _large_arc, sweep_flag, end_x, end_y in _ARC_RE.findall(path_data):
        end = (float(end_x), float(end_y))
        points.extend(_arc_extremes(current, float(radius), int(sweep_flag), end))
        current = end
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return min(xs), min(ys), max(xs), max(ys)


def _arc_flags(path_data: str) -> list[tuple[int, int]]:
    return [(int(large), int(sweep)) for _r, large, sweep, _x, _y in _ARC_RE.findall(path_data)]


# ---------------------------------------------------------------------------
# polar_point
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("angle", "expected"),
    [
        (0.0, (CX + R, CY)),  # 3 o'clock
        (math.pi / 2, (CX, CY + R)),  # 6 o'clock -- y grows downward in SVG
        (math.pi, (CX - R, CY)),  # 9 o'clock
        (-math.pi / 2, (CX, CY - R)),  # 12 o'clock
    ],
)
def test_polar_point_maps_the_cardinal_angles(angle: float, expected: tuple[float, float]) -> None:
    """Pins SVG's y-down convention: +pi/2 is *below* the centre, not above."""
    x, y = polar_point(CX, CY, R, angle)
    assert (x, y) == pytest.approx(expected)


def test_polar_point_stays_on_the_circle() -> None:
    for step in range(16):
        x, y = polar_point(CX, CY, R, step * math.pi / 8)
        assert math.hypot(x - CX, y - CY) == pytest.approx(R)


# ---------------------------------------------------------------------------
# large-arc-flag
# ---------------------------------------------------------------------------


def test_ring_path_sets_the_large_arc_flag_past_a_half_circle() -> None:
    over = ring_path(CX, CY, R, 0.0, 0.0, math.pi * 1.5)
    assert _arc_flags(over) == [(1, 1)]


def test_ring_path_leaves_the_large_arc_flag_clear_under_a_half_circle() -> None:
    under = ring_path(CX, CY, R, 0.0, 0.0, math.pi * 0.5)
    assert _arc_flags(under) == [(0, 1)]


def test_a_sweep_of_exactly_half_a_circle_keeps_the_small_arc_flag() -> None:
    """Exactly pi is the boundary the tolerance exists to hold steady -- angles here
    are accumulated by division, so a mathematically exact half circle arrives a few
    ULP either side of pi and must not flip the flag on that noise."""
    assert _arc_flags(ring_path(CX, CY, R, 0.0, 0.0, math.pi)) == [(0, 1)]
    assert _arc_flags(ring_path(CX, CY, R, 0.0, 0.0, math.pi + FULL_CIRCLE_TOLERANCE / 2)) == [(0, 1)]


# ---------------------------------------------------------------------------
# wedge vs annulus
# ---------------------------------------------------------------------------


def test_ring_path_with_no_inner_radius_is_a_wedge_anchored_at_the_centre() -> None:
    wedge = ring_path(CX, CY, R, 0.0, -math.pi / 2, 0.0)

    assert _MOVE_RE.findall(wedge) == [("100", "100")]  # starts at the centre
    assert len(_LINE_RE.findall(wedge)) == 1  # centre -> rim, then one arc back
    assert len(_ARC_RE.findall(wedge)) == 1
    assert wedge.endswith("Z")


def test_ring_path_with_an_inner_radius_is_an_annulus_sector() -> None:
    ring = ring_path(CX, CY, R, 20.0, -math.pi / 2, 0.0)

    radii = [float(r) for r, *_ in _ARC_RE.findall(ring)]
    assert radii == [50.0, 20.0]  # outer arc forward, inner arc back
    assert _arc_flags(ring) == [(0, 1), (0, 0)]  # opposite sweep directions
    # No vertex at the centre: the hole means the path never touches it.
    assert ("100", "100") not in _MOVE_RE.findall(ring)


def test_an_inner_radius_keeps_every_point_outside_the_hole() -> None:
    inner_r = 20.0
    ring = ring_path(CX, CY, R, inner_r, -math.pi / 2, math.pi / 2)

    vertices = _MOVE_RE.findall(ring) + _LINE_RE.findall(ring) + [(x, y) for *_, x, y in _ARC_RE.findall(ring)]
    for raw_x, raw_y in vertices:
        assert math.hypot(float(raw_x) - CX, float(raw_y) - CY) >= inner_r - 1e-6


# ---------------------------------------------------------------------------
# full circle -- the SVG F.6.2 trap
# ---------------------------------------------------------------------------


def test_full_ring_path_draws_a_whole_circle_not_a_half_one() -> None:
    """The regression this module exists to prevent. A single ``A`` spanning 360
    degrees has coincident endpoints and is dropped entirely, so the path must carry
    two arcs -- and the check has to be geometric, because a path can carry two arc
    *commands* and still trace only half a circle.
    """
    path = full_ring_path(CX, CY, R, 0.0)

    assert len(_ARC_RE.findall(path)) == 2
    min_x, min_y, max_x, max_y = _path_bbox(path)
    assert max_x - min_x == pytest.approx(2 * R, abs=0.1)
    assert max_y - min_y == pytest.approx(2 * R, abs=0.1)


def test_full_ring_path_with_an_inner_radius_draws_two_whole_loops() -> None:
    inner_r = 20.0
    path = full_ring_path(CX, CY, R, inner_r)

    outer_loop, inner_loop = (loop for loop in path.split("Z") if loop.strip())
    for loop, radius in ((outer_loop, R), (inner_loop, inner_r)):
        min_x, min_y, max_x, max_y = _path_bbox(loop)
        assert max_x - min_x == pytest.approx(2 * radius, abs=0.1)
        assert max_y - min_y == pytest.approx(2 * radius, abs=0.1)


# ---------------------------------------------------------------------------
# arc_path (open, stroked)
# ---------------------------------------------------------------------------


def test_arc_path_is_open_with_no_centre_anchor() -> None:
    """A stroked arc must not close back through the centre the way a wedge does."""
    path = arc_path(CX, CY, R, -math.pi / 2, 0.0)

    assert not path.endswith("Z")
    assert not _LINE_RE.findall(path)
    assert _MOVE_RE.findall(path) == [("100", "50")]  # starts at 12 o'clock


def test_arc_path_follows_the_sweep_direction() -> None:
    forward = arc_path(CX, CY, R, 0.0, math.pi / 2)
    backward = arc_path(CX, CY, R, math.pi / 2, 0.0)

    assert _arc_flags(forward) == [(0, 1)]
    assert _arc_flags(backward) == [(0, 0)]


def test_arc_path_spanning_a_full_turn_falls_back_to_two_arcs() -> None:
    """Same F.6.2 trap as full_ring_path, reachable through the stroked path too."""
    path = arc_path(CX, CY, R, -math.pi / 2, -math.pi / 2 + 2 * math.pi)

    assert len(_ARC_RE.findall(path)) == 2
    min_x, min_y, max_x, max_y = _path_bbox(path)
    assert max_x - min_x == pytest.approx(2 * R, abs=0.1)
    assert max_y - min_y == pytest.approx(2 * R, abs=0.1)
