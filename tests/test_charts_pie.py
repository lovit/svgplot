from __future__ import annotations

import math
import re

import pytest

from _svg_probe import tags, texts
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
    """One legend row per label -- exactly, not "at least".

    The old form counted ``class="legend-text"`` as a whole attribute value and asked for
    ``>= 3``, with a comment saying the count included the three value labels too. Since #192
    those carry ``pie-value legend-text``, so the count silently fell from six to three and the
    check stayed green with its comment describing something it no longer measures. Counted by
    class *token*, and split so each half says which elements it is about.
    """
    svg = pieplot(DATA, values="value", labels="label").to_string()

    values = tags(svg, "text", "pie-value")
    # The legend's own rows are the ``legend-text`` elements that are *not* value labels --
    # which is the distinction the ``pie-value`` hook exists to make, used here to make it.
    legend = [
        text
        for tag, text in zip(tags(svg, "text", "legend-text"), texts(svg, "text", "legend-text"), strict=True)
        if "pie-value" not in tag["class"].split()
    ]

    assert legend == ["a", "b", "c"], "one legend row per label, in order"
    assert len(values) == 3, "and one value label per slice"


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


@pytest.mark.parametrize("bad_value", [float("inf"), float("-inf")])
def test_pieplot_rejects_non_finite_value(bad_value: float) -> None:
    """Without an explicit check these survive validation, become nan inside the
    trig, and surface as an opaque coordinate-formatting error naming neither the
    offending value nor its row."""
    data = {"label": ["a", "b"], "value": [10.0, bad_value]}
    with pytest.raises(ValueError, match="finite"):
        pieplot(data, values="value", labels="label")


def test_pieplot_value_label_preserves_small_magnitudes() -> None:
    """Value labels must not be rounded by the *coordinate* formatter, which would
    render these as "0" and "0.123457"."""
    data = {"label": ["tiny", "precise"], "value": [1e-7, 0.123456789]}
    svg = pieplot(data, values="value", labels="label").to_string()
    assert ">1e-07<" in svg
    assert ">0.123456789<" in svg


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


# --------------------------------------------------------------------------------- tooltips


def _slice_titles(svg: str) -> list[str]:
    """The ``<title>`` that is a slice ``<path>``'s first child, in document order.

    Matched through the mark: the chart's own ``<title>`` is here too, and a value label whose
    text had to be shortened would carry one.
    """
    return re.findall(r'<path\b[^>]*\bclass="series-\d+"[^>]*>\s*<title>([^<]*)</title>', svg)


def test_a_slice_says_its_share_and_the_share_up_to_and_including_it() -> None:
    """The running share is in the picture and written nowhere. A pie is read clockwise from
    twelve o'clock, so where a slice ends is already a statement about the whole -- and the only
    way to read it off the drawing is to add the slices back up."""
    data = {"label": ["검색", "추천", "직접", "기타"], "value": [420.0, 310.0, 180.0, 90.0]}
    svg = pieplot(data, values="value", labels="label", tooltip=True).to_string()

    assert _slice_titles(svg) == [
        "검색 · value: 420 · 42.0% · 42.0% cumulative",
        "추천 · value: 310 · 31.0% · 73.0% cumulative",
        "직접 · value: 180 · 18.0% · 91.0% cumulative",
        "기타 · value: 90 · 9.0% · 100.0% cumulative",
    ]


def test_the_running_share_follows_the_drawing_order_not_the_sort_order() -> None:
    """The cumulative number is only meaningful if it counts the slices in the order they are
    drawn -- it is a reading of where the wedge *ends*, not of anything about the data. So a
    fixture whose values ascend proves it: sorted descending, the running shares would be
    50/80/100 instead of 20/50/100."""
    ascending = {"label": ["a", "b", "c"], "value": [20.0, 30.0, 50.0]}
    said = _slice_titles(pieplot(ascending, values="value", labels="label", tooltip=True).to_string())

    assert [title.split(" · ")[-1] for title in said] == ["20.0% cumulative", "50.0% cumulative", "100.0% cumulative"]


def test_the_last_slice_closes_the_circle() -> None:
    """Whatever the values, the running share of the final slice is 100% -- it is the same
    statement as "the wedge ends where the first one started". Values that do not divide evenly
    are the case that would drift if the number were accumulated from the rounded shares rather
    than from the values."""
    thirds = {"label": ["a", "b", "c"], "value": [1.0, 1.0, 1.0]}
    said = _slice_titles(pieplot(thirds, values="value", labels="label", tooltip=True).to_string())

    assert [title.split(" · ")[2] for title in said] == ["33.3%", "33.3%", "33.3%"]
    assert said[-1].endswith("100.0% cumulative"), "the shares round to 99.9 but the running share does not"


def test_every_slice_gets_exactly_one_tooltip() -> None:
    svg = pieplot(DATA, values="value", labels="label", tooltip=True).to_string()

    assert len(_slice_titles(svg)) == len(_slice_paths(svg)) == len(DATA["value"])


def test_the_value_label_stops_taking_the_pointer_when_the_slices_have_something_to_say() -> None:
    """A value label sits *on top of* its own slice, so it takes the pointer at the one place
    the reader aims for. Conditional for ``treemap``'s reason: with tooltips off there is
    nothing to put in its place."""
    assert ".pie-value { pointer-events: none; }" in pieplot(DATA, values="value", labels="label", tooltip=True).to_string()
    assert "pointer-events" not in pieplot(DATA, values="value", labels="label").to_string()


def test_the_default_draws_no_tooltip_and_saying_so_changes_nothing() -> None:
    """What this can check is that ``tooltip=False`` is the same call as not writing it, and
    that no slice is titled. It is deliberately not named for byte-identity with the version
    before ``tooltip=`` existed, which it cannot see -- both sides are this branch's code.
    ``docs/gallery/*.html`` holds those bytes."""
    omitted = pieplot(DATA, values="value", labels="label").to_string()
    explicit = pieplot(DATA, values="value", labels="label", tooltip=False).to_string()

    assert omitted == explicit
    assert _slice_titles(omitted) == []


def test_a_label_too_long_to_read_is_left_out_of_the_tooltip() -> None:
    """The name is written once per slice. Dropped rather than truncated, and the slice still
    says its value and both shares."""
    long_name = "면" * 5000
    data = {"label": [long_name, "b"], "value": [60.0, 40.0]}
    svg = pieplot(data, values="value", labels="label", tooltip=True).to_string()

    assert _slice_titles(svg) == [
        "value: 60 · 60.0% · 60.0% cumulative",
        "b · value: 40 · 40.0% · 100.0% cumulative",
    ]


def test_the_total_is_the_rows_the_chart_drew() -> None:
    """A row with a value and no label is dropped from the pie, so it must not be in the
    denominator either. Summing the column instead leaves the last slice reading ``20.0%
    cumulative`` -- it contradicts the one thing the running share is for, and every test in
    this file passed while it did."""
    partial = {"label": ["a", None, "c"], "value": [10.0, 80.0, 10.0]}
    svg = pieplot(partial, values="value", labels="label", tooltip=True).to_string()

    assert _slice_titles(svg) == [
        "a · value: 10 · 50.0% · 50.0% cumulative",
        "c · value: 10 · 50.0% · 100.0% cumulative",
    ]


def test_the_column_name_is_capped_like_every_other_caller_string() -> None:
    """``values=`` is repeated once per slice, so an unreadable one would be the largest thing
    in the file. Dropped rather than truncated; the value stays. Only the *label* half of this
    was pinned, and the name half is the one pie repeats."""
    long_name = "면" * 5000
    data = {"label": ["a", "b"], long_name: [1.0, 1.0]}
    svg = pieplot(data, values=long_name, labels="label", tooltip=True).to_string()

    assert _slice_titles(svg) == ["a · 1 · 50.0% · 50.0% cumulative", "b · 1 · 50.0% · 100.0% cumulative"]
    assert long_name not in svg


def test_the_value_is_spelled_exactly_not_as_the_axis_would() -> None:
    """``format_value_label`` is a plain decimal literal, so ``1e307`` becomes 308 digits -- per
    slice, in a mark's *accessible name*, read out one at a time. ``format_number`` picks the
    shorter of two exact spellings, so it neither rounds nor expands."""
    data = {"label": ["a", "b"], "value": [1e307, 1e307]}
    svg = pieplot(data, values="value", labels="label", tooltip=True).to_string()

    assert _slice_titles(svg)[0] == "a · value: 1e+307 · 50.0% · 50.0% cumulative"


def test_a_zero_valued_slice_is_named_even_though_no_pointer_can_reach_it() -> None:
    """A zero value draws a wedge whose arc starts and ends at the same point, which renderers
    drop (SVG F.6.2). Unlike ``gaugeplot``'s rounding band -- where a *nonzero* value's arc
    vanishes and naming it would claim a mark that is not there -- here the value really is
    zero and the row really is in the data. The ``<title>`` is a named node in the accessibility
    tree for a row a sighted reader cannot point at, which is more than they had, not less.

    The running share is what makes it legible: the zero slice does not advance it."""
    data = {"label": ["a", "none", "b"], "value": [5.0, 0.0, 5.0]}
    svg = pieplot(data, values="value", labels="label", tooltip=True).to_string()

    assert _slice_titles(svg) == [
        "a · value: 5 · 50.0% · 50.0% cumulative",
        "none · value: 0 · 0.0% · 50.0% cumulative",
        "b · value: 5 · 50.0% · 100.0% cumulative",
    ]
