from __future__ import annotations

import math
import re

import pytest

from svgplot.charts.pie import pieplot

DATA = {"label": ["a", "b", "c"], "value": [30.0, 50.0, 20.0]}

# Geometry pieplot derives from its fixed canvas/margins (800x600, margin
# top/right/bottom/left = 30/180/30/30): centre (325, 300), outer radius 270.
_CX, _CY = 325.0, 300.0
_OUTER_RADIUS = 270.0
_FIRST_START_ANGLE = -math.pi / 2  # slices start at 12 o'clock

_PATH_D_RE = re.compile(r'<path[^>]*\sd="([^"]+)"')
_ARC_RE = re.compile(r"A ([\d.]+),[\d.]+ 0 \d (\d) (-?[\d.]+),(-?[\d.]+)")
_LINE_RE = re.compile(r"L (-?[\d.]+),(-?[\d.]+)")
_MOVE_RE = re.compile(r"M (-?[\d.]+),(-?[\d.]+)")


def _slice_paths(svg: str) -> list[str]:
    return _PATH_D_RE.findall(svg)


def _angle_at(x: float, y: float) -> float:
    return math.atan2(y - _CY, x - _CX)


def _arc_sweep_points(start: tuple[float, float], radius: float, sweep_flag: int, end: tuple[float, float]) -> list:
    """Sample points along one circular arc about the known pie centre.

    An arc whose start and end coincide sweeps nothing -- the renderer drops the
    segment entirely (SVG spec F.6.2), so this must report no points for it rather
    than pretending it travelled all the way round.
    """
    theta1, theta2 = _angle_at(*start), _angle_at(*end)
    dtheta = (theta2 - theta1) % (2 * math.pi) if sweep_flag else -((theta1 - theta2) % (2 * math.pi))
    steps = 720
    return [
        (_CX + radius * math.cos(theta1 + dtheta * i / steps), _CY + radius * math.sin(theta1 + dtheta * i / steps))
        for i in range(steps + 1)
    ]


def _path_bbox(path_data: str) -> tuple[float, float, float, float]:
    """(min_x, min_y, max_x, max_y) actually covered by a path, arcs included."""
    points = [(float(x), float(y)) for x, y in _MOVE_RE.findall(path_data) + _LINE_RE.findall(path_data)]
    current = points[0] if points else (_CX, _CY)
    for radius, sweep_flag, end_x, end_y in _ARC_RE.findall(path_data):
        end = (float(end_x), float(end_y))
        points.extend(_arc_sweep_points(current, float(radius), int(sweep_flag), end))
        current = end
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _signed_angle_delta(angle: float, reference: float) -> float:
    """``angle - reference`` folded into (-pi, pi], so equivalent angles compare as 0."""
    return (angle - reference + math.pi) % (2 * math.pi) - math.pi


def _slice_angles(path_data: str) -> tuple[float, float]:
    """(start, end) angle of a wedge slice, from its 'L' vertex and its arc endpoint."""
    (start_x, start_y) = _LINE_RE.findall(path_data)[0]
    (_radius, _sweep, end_x, end_y) = _ARC_RE.findall(path_data)[0]
    return (_angle_at(float(start_x), float(start_y)), _angle_at(float(end_x), float(end_y)))


# ---------------------------------------------------------------------------
# basic pie
# ---------------------------------------------------------------------------


def test_pieplot_renders_one_path_per_slice() -> None:
    chart = pieplot(DATA, values="value", labels="label")
    svg = chart.to_string()
    assert svg.count("<path") == 3
    assert "series-1" in svg
    assert "series-3" in svg


def test_pieplot_generates_a_legend_entry_per_label() -> None:
    chart = pieplot(DATA, values="value", labels="label")
    svg = chart.to_string()
    assert svg.count('class="legend-text"') >= 3  # 3 legend labels + 3 value labels share this class
    assert ">a<" in svg
    assert ">b<" in svg
    assert ">c<" in svg


def test_pieplot_shows_the_value_on_each_slice() -> None:
    chart = pieplot(DATA, values="value", labels="label")
    svg = chart.to_string()
    assert ">30<" in svg
    assert ">50<" in svg
    assert ">20<" in svg


def test_pieplot_defaults_labels_to_1_based_position_when_omitted() -> None:
    chart = pieplot(DATA, values="value")
    svg = chart.to_string()
    assert ">1<" in svg
    assert ">2<" in svg
    assert ">3<" in svg


# ---------------------------------------------------------------------------
# donut
# ---------------------------------------------------------------------------


def test_pieplot_with_inner_radius_renders_a_ring_not_a_wedge() -> None:
    pie_svg = pieplot(DATA, values="value", labels="label").to_string()
    donut_svg = pieplot(DATA, values="value", labels="label", inner_radius=0.5).to_string()
    # a wedge path has no fill-rule attribute (single boundary); a ring needs
    # evenodd to punch the hole (two nested boundaries in one path).
    assert "fill-rule" not in pie_svg
    assert donut_svg.count("fill-rule") == 3


@pytest.mark.parametrize("inner_radius", [-0.1, 1.0, 1.5, float("nan"), float("inf")])
def test_pieplot_rejects_invalid_inner_radius(inner_radius: float) -> None:
    with pytest.raises(ValueError, match="inner_radius"):
        pieplot(DATA, values="value", labels="label", inner_radius=inner_radius)


# ---------------------------------------------------------------------------
# arc geometry
# ---------------------------------------------------------------------------


def test_pieplot_sets_large_arc_flag_for_a_slice_over_180_degrees() -> None:
    data = {"label": ["big", "small"], "value": [80.0, 20.0]}
    svg = pieplot(data, values="value", labels="label").to_string()
    # the large-arc-flag is the first of the two flags following the radii/x-axis-rotation
    # in an "A rx,ry x-axis-rotation large-arc-flag sweep-flag x,y" command.
    arc_commands = re.findall(r"A [\d.]+,[\d.]+ 0 (\d) (\d)", svg)
    assert ("1", "1") in arc_commands  # the 80% slice's outer arc


def test_pieplot_does_not_set_large_arc_flag_for_a_slice_under_180_degrees() -> None:
    data_with_rest = {"label": ["small", "rest"], "value": [1.0, 99.0]}
    svg = pieplot(data_with_rest, values="value", labels="label").to_string()
    arc_commands = re.findall(r"A [\d.]+,[\d.]+ 0 (\d) (\d)", svg)
    assert ("0", "1") in arc_commands


def test_pieplot_single_full_value_renders_a_visible_full_circle() -> None:
    """A 100% slice must span the full diameter in *both* axes.

    Counting arc commands is not enough: an ``A`` whose start and end points
    coincide is dropped entirely by the renderer (SVG spec F.6.2), so a path can
    carry two arcs and still draw only half a circle.
    """
    data = {"label": ["only"], "value": [10.0]}
    svg = pieplot(data, values="value", labels="label").to_string()
    (slice_path,) = _slice_paths(svg)
    min_x, min_y, max_x, max_y = _path_bbox(slice_path)
    assert max_x - min_x == pytest.approx(max_y - min_y)  # a circle, not a half-circle
    assert max_y - min_y == pytest.approx(2 * _OUTER_RADIUS)


def test_pieplot_single_full_value_donut_renders_a_visible_ring() -> None:
    """Both loops of the ring (outer and inner) must be full circles, not half-circles."""
    data = {"label": ["only"], "value": [10.0]}
    svg = pieplot(data, values="value", labels="label", inner_radius=0.5).to_string()
    assert "fill-rule" in svg
    (ring_path,) = _slice_paths(svg)
    outer_loop, inner_loop = (loop for loop in ring_path.split("Z") if loop.strip())
    for loop, radius in ((outer_loop, _OUTER_RADIUS), (inner_loop, _OUTER_RADIUS * 0.5)):
        min_x, min_y, max_x, max_y = _path_bbox(loop)
        assert max_x - min_x == pytest.approx(2 * radius)
        assert max_y - min_y == pytest.approx(2 * radius)


def test_pieplot_slice_sweeps_are_contiguous_and_sum_to_a_full_circle() -> None:
    """Recover each slice's start/end angle from its rendered arc endpoints and
    confirm each slice ends exactly where the next begins, with no gap or overlap.
    """
    data = {"label": ["a", "b", "c"], "value": [30.0, 50.0, 20.0]}
    svg = pieplot(data, values="value", labels="label").to_string()
    paths = _slice_paths(svg)
    assert len(paths) == 3

    total = sum(data["value"])
    sweeps = []
    expected_start = _FIRST_START_ANGLE
    for path, value in zip(paths, data["value"], strict=True):
        start, end = _slice_angles(path)
        # atan2 wraps to (-pi, pi], so compare angles as a signed difference folded
        # into (-pi, pi] -- a plain "% 2*pi" turns a tiny negative into ~2*pi.
        assert _signed_angle_delta(start, expected_start) == pytest.approx(0.0, abs=1e-9)
        sweep = (end - start) % (2 * math.pi)
        assert sweep == pytest.approx(value / total * 2 * math.pi)
        expected_start += sweep
        sweeps.append(sweep)

    assert sum(sweeps) == pytest.approx(2 * math.pi)


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


def test_pieplot_rejects_negative_value() -> None:
    data = {"label": ["a", "b"], "value": [10.0, -5.0]}
    with pytest.raises(ValueError, match="non-negative"):
        pieplot(data, values="value", labels="label")


def test_pieplot_rejects_all_zero_values() -> None:
    data = {"label": ["a", "b"], "value": [0.0, 0.0]}
    with pytest.raises(ValueError, match="zero"):
        pieplot(data, values="value", labels="label")


def test_pieplot_drops_rows_with_missing_value_or_label() -> None:
    data = {"label": ["a", None, "c"], "value": [10.0, 20.0, None]}
    chart = pieplot(data, values="value", labels="label")
    svg = chart.to_string()
    assert svg.count("<path") == 1
    assert ">a<" in svg


def test_pieplot_raises_when_all_rows_missing() -> None:
    data = {"label": [None, None], "value": [None, None]}
    with pytest.raises(ValueError, match="missing"):
        pieplot(data, values="value", labels="label")


def test_pieplot_raises_on_empty_data() -> None:
    with pytest.raises(ValueError, match="at least one row"):
        pieplot({"label": [], "value": []}, values="value", labels="label")


def test_pieplot_raises_keyerror_for_unknown_values_column() -> None:
    with pytest.raises(KeyError):
        pieplot(DATA, values="nope", labels="label")


def test_pieplot_raises_keyerror_for_unknown_labels_column() -> None:
    with pytest.raises(KeyError):
        pieplot(DATA, values="value", labels="nope")


def test_pieplot_raises_keyerror_for_unknown_theme_preset() -> None:
    with pytest.raises(KeyError):
        pieplot(DATA, values="value", labels="label", theme="not-a-real-preset")


def test_pieplot_raises_typeerror_for_bad_theme_type() -> None:
    with pytest.raises(TypeError):
        pieplot(DATA, values="value", labels="label", theme=123)  # type: ignore[arg-type]
