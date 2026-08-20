"""Tick labels stay inside the canvas and off each other (issue #123).

Two remedies, split by what a label *is*. A category label is a name, so it can be shortened
and its full form kept in a ``<title>``. A numeric or time label **is** the value it names, so
shortening it would make the axis say something false -- those get room made for them instead.
Every test here checks one of those two, or the line between them.

Widths come from ``charts._textwidth``, the same estimate the code uses. That makes these
tests blind to the estimate itself being wrong -- which is the subject of
``test_charts_textwidth.py`` -- and sharp about the geometry, which is the subject here.
"""

from __future__ import annotations

import re
import warnings
import xml.etree.ElementTree as ET
from itertools import pairwise

import pytest

import svgplot as sp
from svgplot.charts._layout import DEFAULT_WIDTH
from svgplot.charts._textwidth import text_width

_LONG = ["매우 긴 카테고리 이름입니다", "두번째로 긴 이름", "세번째 긴 이름입니다", "네번째 이름", "다섯번째"]


def _font_size(svg: str) -> float:
    """The size the tick labels are actually rendered at, read from the SVG's own CSS.

    Not a constant. The code under test used to hardcode 11.0 -- which is ``legend_font_size``
    -- and this module hardcoded the same number, so the two agreed with each other and not
    with the output: at ``poster`` the labels are 16px and every check here was measuring them
    as 11. Reading the declaration is the only way these assertions are about the file."""
    match = re.search(r"\.tick-label[^}]*font-size:\s*([\d.]+)px", svg)

    assert match, "no tick-label font-size in the stylesheet"
    return float(match.group(1))


def _tick_rows(svg: str) -> list[tuple[float, float, str, str]]:
    """Every tick label as ``(y, x, anchor, text)``.

    Parsed, not pattern-matched. The regex this replaces required ``text-anchor`` to be
    *present* and to come before ``class`` — so a label the code under test stopped anchoring
    vanished from the detector rather than failing a test, which is the exact blindness the
    rest of this file warns about. A missing anchor now reads as SVG's own default, ``start``,
    and a label carrying a ``<title>`` child (which long ones do) is read through its children
    rather than dropped by an ``[^<]*`` body.
    """
    root = ET.fromstring(svg)
    rows = []
    for node in root.iter():
        if not node.tag.endswith("text") or "tick-label" not in (node.get("class") or "").split():
            continue
        text = ((node.text or "") + "".join(child.tail or "" for child in node)).strip()
        rows.append((float(node.get("y")), float(node.get("x")), node.get("text-anchor", "start"), text))
    return rows


def _extent(position: float, anchor: str, width: float) -> tuple[float, float]:
    """The span a label occupies, from where it is anchored and how it is anchored."""
    if anchor == "start":
        return position, position + width
    if anchor == "end":
        return position - width, position
    return position - width / 2, position + width / 2


def _bottom_labels(svg: str) -> list[tuple[float, float, str]]:
    """Bottom-axis labels as ``(left, right, text)``, whatever their anchor.

    Occupied extent, and the axis found by y rather than by anchor. Filtering by
    ``text-anchor="middle"`` is how the last two rounds of this file went blind: round 2
    missed the left axis, and round 3 missed the very labels the fix had switched to
    ``start``/``end``. The anchor is a thing the code under test changes, so a detector must
    not key off it.
    """
    rows, size = _tick_rows(svg), _font_size(svg)
    if not rows:
        return []
    baseline = max(y for y, _, _, _ in rows)
    return [(*_extent(x, anchor, text_width(text, size)), text) for y, x, anchor, text in rows if y == baseline]


def _left_labels(svg: str) -> list[tuple[float, float, str]]:
    """Left-axis labels as ``(left, right, text)`` -- every tick label not on the bottom row."""
    rows, size = _tick_rows(svg), _font_size(svg)
    if not rows:
        return []
    baseline = max(y for y, _, _, _ in rows)
    return [(*_extent(x, anchor, text_width(text, size)), text) for y, x, anchor, text in rows if y != baseline]


def _centred(svg: str) -> list[tuple[float, str]]:
    """Bottom-axis labels keyed by their tick position, for tests about which ticks exist."""
    return [
        (float(x), t)
        for x, t in re.findall(r'<text x="([\d.-]+)"[^>]*text-anchor="\w+"[^>]*class="tick-label"[^>]*>([^<]*)<', svg)
    ]


def _right_aligned(svg: str) -> list[tuple[float, str]]:
    """Left-axis labels keyed by their anchor position."""
    return [(right, text) for _, right, text in _left_labels(svg)]


def _right_aligned_rows(svg: str) -> list[tuple[float, float, str]]:
    """Left-axis labels with their y coordinate, for checking they do not stack.

    Selected by **position**, not by ``text-anchor="end"``. The anchor is something the code
    under test chooses, and this helper is the only one the left-axis stacking check has — key
    it off the anchor and a change to the anchor empties it silently.
    """
    rows = _tick_rows(svg)
    if not rows:
        return []
    left_edge = min(x for _, x, _, _ in rows)
    return [(x, y, text) for y, x, _, text in rows if x <= left_edge + 1.0]


def _outside_the_canvas(svg: str) -> list[str]:
    """Labels whose occupied extent leaves the canvas, on either axis.

    Asserts it found labels at all first. Every caller of this spells its check
    ``== []``, which an empty detector satisfies without looking at anything — the failure
    mode that let two earlier rounds of this file pass while blind.
    """
    labels = _bottom_labels(svg) + _left_labels(svg)
    assert labels, "detector found no tick labels at all"
    return [text for left, right, text in labels if left < 0 or right > DEFAULT_WIDTH]


def _overlapping(svg: str) -> list[tuple[str, str]]:
    """Adjacent bottom labels whose extents intersect, whatever their anchors."""
    labels = sorted(_bottom_labels(svg))
    return [
        (labels[index][2], labels[index + 1][2]) for index in range(len(labels) - 1) if labels[index][1] > labels[index + 1][0]
    ]


def _long_category_chart(orient: str) -> str:
    return sp.barplot({"c": _LONG, "v": [1.0, 2.0, 3.0, 4.0, 5.0]}, x="c", y="v", orient=orient).to_string()


def _many_category_chart(count: int, name: str) -> str:
    categories = [f"{name}{index}" for index in range(count)]
    return sp.barplot({"c": categories, "v": [float(i + 1) for i in range(count)]}, x="c", y="v").to_string()


# ---------------------------------------------------------------------------
# nothing leaves the canvas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("top", [1.0, 1e6, 1.2e9, 1.23456789e15, 1e-7])
def test_a_numeric_y_axis_makes_room_rather_than_letting_a_label_escape(top: float) -> None:
    """The left margin was a constant 60px, and ``1200000000000000`` starts at x=-62.8 --
    outside the ``viewBox``, where nothing renders it. The remedy cannot be shortening: the
    label is the value, and ``1234…`` is an axis telling a lie no ``<title>`` repairs."""
    svg = sp.lineplot({"x": [1, 2], "y": [0.0, top]}, x="x", y="y").to_string()

    assert _right_aligned(svg), "the y axis drew no labels"
    assert _outside_the_canvas(svg) == []


@pytest.mark.parametrize("orient", ["v", "h"])
def test_a_long_category_label_stays_inside_the_canvas_on_either_axis(orient: str) -> None:
    """``orient="h"`` puts the categories up the left edge, right-aligned, so they grow into
    the margin and then past x=0 -- measured, the longest started at x=-83.7."""
    assert _outside_the_canvas(_long_category_chart(orient)) == []


@pytest.mark.parametrize(
    ("count", "name"),
    [(5, "매우 긴 카테고리 이름입니다"), (8, "조금 긴 카테고리"), (20, "항목"), (60, "카테고리")],
    ids=["5-very-long", "8-long", "20-short", "60-short"],
)
def test_no_two_category_labels_overlap_however_many_there_are(count: int, name: str) -> None:
    """Two labels running into each other is the same defect as one running off the canvas,
    and harder to spot -- both are still there and both are still legible. Measured before
    this: eight categories named ``조금 긴 카테고리N`` overlapped in all seven adjacent pairs."""
    svg = _many_category_chart(count, name)

    assert _centred(svg), "the x axis drew no labels"
    assert _overlapping(svg) == []


def test_a_dense_categorical_axis_thins_its_labels_rather_than_cutting_them_to_nothing() -> None:
    """A 100-category axis gives each label 5.8px, and shortening to that leaves an ellipsis
    and nothing else -- a hundred of those is not a shortened axis, it is a row of dots. The
    grid lines still mark every category; it is only the text that thins."""
    warnings.simplefilter("ignore")
    rows = [f"행{index}" for index in range(100)]
    columns = [f"열{index}" for index in range(100)]
    data = {"x": columns, "y": rows, "v": [float(index) for index in range(100)]}
    svg = sp.heatmap(data, x="x", y="y", values="v").to_string()
    labels = _centred(svg)

    assert 5 <= len(labels) < 100, f"expected a thinned axis, got {len(labels)} labels"
    assert not any(label == "…" for _, label in labels), "labels were cut to nothing instead of thinned"
    assert svg.count("grid-line") > len(labels), "grid lines should still mark every category"


# ---------------------------------------------------------------------------
# the line between a name and a value
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("top", [1.23456789e15, 1e9, 987654321.0])
def test_a_numeric_label_is_never_shortened(top: float) -> None:
    """The rule that makes the two remedies different. A truncated value is a wrong value,
    and unlike a truncated name there is no form of it that is still true."""
    svg = sp.lineplot({"x": [1, 2], "y": [0.0, top]}, x="x", y="y").to_string()
    labels = [text for _, text in _right_aligned(svg)]

    assert labels, "the y axis drew no labels"
    assert not any("…" in label for label in labels), labels


def test_a_shortened_category_label_keeps_its_full_text() -> None:
    """The other half: shortening a name costs presentation, not information, and that only
    holds while the full form is somewhere in the file."""
    svg = _many_category_chart(8, "조금 긴 카테고리")

    assert any(text.endswith("…") for _, text in _centred(svg)), "nothing was shortened, so this proves nothing"
    assert "<title>조금 긴 카테고리0</title>" in svg


def test_short_labels_are_left_exactly_as_they_were() -> None:
    """The intervention is supposed to be invisible when it is not needed. A chart whose
    labels already fit has to come out byte-identical, or every existing chart changed."""
    svg = sp.barplot({"c": ["가", "나", "다"], "v": [1.0, 2.0, 3.0]}, x="c", y="v").to_string()

    assert "…" not in svg
    assert "<title>" not in svg.split("</style>")[-1] or svg.count("<title>") == 1


def test_the_widened_margin_stops_before_the_chart_disappears() -> None:
    """Room for a label is worth taking from the plot right up to the point where the plot is
    no longer the thing on the page. A label that wants more than that is shortened instead --
    for a value that means it overflows, which is the honest end of the trade."""
    from svgplot.charts._axes import _MAX_LEFT_MARGIN_FRACTION, fit_left_margin
    from svgplot.charts._layout import MARGIN_WITHOUT_LEGEND

    _, _, _, left = fit_left_margin(MARGIN_WITHOUT_LEGEND, ["가" * 60], width=DEFAULT_WIDTH)

    assert left == pytest.approx(DEFAULT_WIDTH * _MAX_LEFT_MARGIN_FRACTION)
    assert left < DEFAULT_WIDTH / 2, "the axis would be taking more of the canvas than the plot"


def test_a_wider_label_gets_a_wider_margin_and_a_narrow_one_does_not() -> None:
    """Monotone in the label, and only paid when needed -- a chart whose labels fit the
    original 60px keeps it, so its output does not move."""
    from svgplot.charts._axes import fit_left_margin
    from svgplot.charts._layout import MARGIN_WITHOUT_LEGEND

    narrow = fit_left_margin(MARGIN_WITHOUT_LEGEND, (0.0, 10.0), width=DEFAULT_WIDTH)[3]
    wide = fit_left_margin(MARGIN_WITHOUT_LEGEND, (0.0, 1.2e15), width=DEFAULT_WIDTH)[3]

    assert narrow == 60.0, "a chart that already fits should not move"
    assert wide > narrow


def test_a_horizontal_bar_chart_shows_its_category_names_in_full() -> None:
    """Shortening is the fallback, not the first answer, and the left axis is where that
    distinction is visible: a horizontal bar chart's categories have a whole margin's worth of
    room available and no neighbour to run into, so widening is free and cutting is a loss.

    Nothing else notices. Feeding the *value* domain to ``fit_left_margin`` here leaves the
    margin at 60px and the names cut to three characters -- still inside the canvas, still not
    overlapping, and still wrong."""
    svg = _long_category_chart("h")
    labels = [text for _, text in _right_aligned(svg)]

    assert labels, "the y axis drew no labels"
    assert set(labels) == set(_LONG), f"category names were shortened when there was room: {labels}"


_CONTEXTS = ["paper", "notebook", "talk", "poster"]


def _themed(context: str) -> object:
    from svgplot.theme.context import apply_context
    from svgplot.theme.presets import PRESETS

    return apply_context(PRESETS["light"], context)


@pytest.mark.parametrize("context", _CONTEXTS)
@pytest.mark.parametrize("orient", ["v", "h"])
def test_the_remedies_hold_at_every_label_size_a_context_sets(context: str, orient: str) -> None:
    """``tick_label_font_size`` is a public field and ``apply_context`` scales it -- 8px on
    ``paper``, 16 on ``poster``. The estimate was measured against a hardcoded 11.0, which is
    ``legend_font_size`` and not this one, so a poster's labels were counted a third short and
    every defect this module fixes was still there. Nothing noticed, because the tests
    hardcoded the same wrong number."""
    svg = sp.barplot(
        {"c": _LONG, "v": [1.0, 2.0, 3.0, 4.0, 5.0]}, x="c", y="v", orient=orient, theme=_themed(context)
    ).to_string()

    assert _outside_the_canvas(svg) == []
    assert _overlapping(svg) == []


@pytest.mark.parametrize("count", [53, 100, 200, 500])
def test_a_left_axis_thins_its_labels_before_they_stack_on_each_other(count: int) -> None:
    """Thinning was applied to the bottom axis only, and the acceptance criterion does not
    name an axis. A horizontal bar chart of 53 categories put its labels 9.81px apart at a
    10px font; at 200 they were 2.60px apart. Nothing caught it because the overlap test
    looked at ``text-anchor="middle"``, which is the *other* axis."""
    categories = [f"항목{index}" for index in range(count)]
    svg = sp.barplot({"c": categories, "v": [float(i + 1) for i in range(count)]}, x="c", y="v", orient="h").to_string()
    rows = sorted(y for _, y, _ in _right_aligned_rows(svg))
    size = _font_size(svg)

    assert rows, "the left axis drew no labels"
    assert all(later - earlier >= 1.2 * size for earlier, later in pairwise(rows)), rows


@pytest.mark.parametrize(
    ("name", "chart"),
    [
        ("histplot", lambda: sp.histplot({"v": [i * 1e14 for i in range(1, 20)]}, x="v")),
        ("ecdfplot", lambda: sp.ecdfplot({"v": [i * 1e14 for i in range(1, 20)]}, x="v")),
        ("barplot-h", lambda: sp.barplot({"c": ["a", "b"], "v": [1.0, 1.23456789e15]}, x="c", y="v", orient="h")),
        ("negative-domain", lambda: sp.scatterplot({"x": [-1.2e15, 0.0], "y": [0.0, 1.0]}, x="x", y="y")),
    ],
)
def test_a_numeric_bottom_axis_thins_rather_than_letting_its_values_collide(name: str, chart: object) -> None:
    """The third case the split remedy missed: a chart whose *values* run along the bottom.
    Widening a margin does not help there and shortening is forbidden, so what is left is
    drawing fewer of them -- which costs resolution and never truth."""
    svg = chart().to_string()  # type: ignore[operator]

    assert _centred(svg), f"{name} drew no bottom labels"
    assert _overlapping(svg) == []
    assert _outside_the_canvas(svg) == []


def test_the_fallback_label_size_matches_the_theme_field_it_stands_in_for() -> None:
    """Unreachable from any chart -- all twelve pass ``theme.tick_label_font_size`` -- which
    is exactly why it drifted to 11.0 unnoticed and stayed there through two rounds. A
    fallback that disagrees with the thing it falls back to is worse than none, because a
    direct caller of ``render_x_axis`` gets an estimate calibrated for a size nothing uses."""
    from svgplot.charts._axes import _DEFAULT_LABEL_FONT_SIZE
    from svgplot.theme.base import Theme

    assert Theme().tick_label_font_size == _DEFAULT_LABEL_FONT_SIZE


@pytest.mark.parametrize(("width", "left"), [(100.0, 60.0), (800.0, 300.0), (50.0, 60.0)])
def test_fitting_a_margin_never_makes_it_smaller(width: float, left: float) -> None:
    """The function widens; the name and the docstring both say so. Clamping the *result* to
    the cap instead of the *addition* let a narrow canvas shrink the caller's own margin --
    60px became 30 at ``width=100`` -- and every chart today passes 800, so nothing reached
    it. Issue #120 (caller-set size) is what reaches it."""
    from svgplot.charts._axes import fit_left_margin

    fitted = fit_left_margin((30.0, 40.0, 50.0, left), (0.0, 1.2e15), width=width)

    assert fitted[3] >= left, f"the margin shrank from {left} to {fitted[3]}"


def test_a_left_axis_thins_only_its_labels_and_keeps_every_grid_line() -> None:
    """The justification for thinning, asserted rather than assumed.

    "Grid lines and tick marks still go on every tick; it is only the text that thins" is what
    makes thinning a smaller loss than shortening -- and the left axis was skipping the whole
    loop iteration, so a 100x100 heatmap drew all 100 column boundaries and 34 row boundaries.
    A reader could not line a cell up with its row. Three docstrings claimed otherwise."""
    warnings.simplefilter("ignore")
    rows = [f"행{index}" for index in range(100)]
    columns = [f"열{index}" for index in range(100)]
    svg = sp.heatmap(
        {"x": columns, "y": rows, "v": [float(index) for index in range(100)]}, x="x", y="y", values="v"
    ).to_string()
    lines = re.findall(r'<line x1="([\d.]+)" y1="([\d.]+)" x2="([\d.]+)" y2="([\d.]+)"[^>]*class="grid-line"', svg)
    horizontal = [line for line in lines if line[1] == line[3]]
    vertical = [line for line in lines if line[0] == line[2]]

    assert len(horizontal) == 100, f"row boundaries thinned to {len(horizontal)}"
    assert len(vertical) == 100, f"column boundaries thinned to {len(vertical)}"
    assert len(_right_aligned(svg)) < 100, "the labels themselves should still thin"


@pytest.mark.parametrize(
    ("name", "chart"),
    [
        ("scatterplot", lambda: sp.scatterplot({"x": [0.0, 1.2e15], "y": [0.0, 1.0]}, x="x", y="y")),
        ("lineplot", lambda: sp.lineplot({"x": [0.0, 1.2e15], "y": [0.0, 1.0]}, x="x", y="y")),
        ("histplot", lambda: sp.histplot({"v": [0.0, 1.2e15]}, x="v")),
        ("ecdfplot", lambda: sp.ecdfplot({"v": [0.0, 1.2e15]}, x="v")),
        ("barplot-h", lambda: sp.barplot({"c": ["a", "b"], "v": [1.0, 1.23456789e15]}, x="c", y="v", orient="h")),
        ("negative-domain", lambda: sp.scatterplot({"x": [-1.2e15, 0.0], "y": [0.0, 1.0]}, x="x", y="y")),
    ],
)
def test_the_end_labels_of_a_numeric_bottom_axis_stay_on_the_canvas(name: str, chart: object) -> None:
    """Thinning fixes crowding and cannot fix the ends: the extreme tick sits at the extreme
    value however few ticks there are, and a centred label there has room on one side only.
    Measured, ``scatterplot({'x': [0, 1.2e15]})`` put ``1200000000000000`` 18.4px past the
    right edge -- no truncation possible, since the label is the value.

    Both ends, because they are separate branches: a domain running to a large *negative*
    number puts the wide label on the left, where the remedy is to anchor at ``start`` rather
    than ``end``. The earlier fixtures hid all of this -- ``histplot``'s never emitted an end
    tick at all, and every one of them ran positive."""
    svg = chart().to_string()  # type: ignore[operator]

    assert _centred(svg) or _right_aligned(svg), f"{name} drew no labels"
    assert _outside_the_canvas(svg) == [], name


def test_a_heatmaps_row_names_get_the_margin_widened_for_them_too() -> None:
    """``heatmap`` was the one chart of eleven that never called ``fit_left_margin``, so its
    row names were cut to the default 54px however much room the canvas had. Shortening a name
    that would have fit is the loss this whole remedy is arranged to avoid."""
    warnings.simplefilter("ignore")
    rows = [f"매우 긴 행 이름입니다 {index}" for index in range(4)]
    columns = [f"열{index}" for index in range(4)]
    svg = sp.heatmap(
        {"x": columns, "y": rows, "v": [float(index) for index in range(4)]}, x="x", y="y", values="v"
    ).to_string()
    drawn = {text for _, text in _right_aligned(svg)}

    assert drawn == set(rows), f"row names were shortened when there was room: {drawn}"


def test_a_left_label_is_measured_against_the_room_left_of_the_tick_mark() -> None:
    """The budget is ``area.left`` minus the tick mark's own offset, not ``area.left``. Off by
    that offset, a label is cut one character late and starts 6px outside the canvas -- and
    the offset grows with ``theme.tick_size``, so a poster is worse."""
    svg = sp.barplot({"c": ["가" * 40], "v": [1.0]}, x="c", y="v", orient="h").to_string()

    assert _outside_the_canvas(svg) == []
