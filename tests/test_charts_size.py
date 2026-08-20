"""Caller-chosen canvas size (issue #120).

Three things have to hold at once and they pull against each other: a chart called the
old way must be **byte-identical**, a smaller canvas must still leave a usable plot area,
and nothing may be drawn outside the canvas. The tests here are grouped in that order.
"""

from __future__ import annotations

import contextlib
import math
import re
import warnings
from collections.abc import Callable

import pytest

import svgplot as sp
from svgplot.charts._layout import (
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    LEGEND_X_OFFSET,
    MARGIN_WITH_LEGEND,
    MARGIN_WITHOUT_LEGEND,
    MAX_MARGIN_FRACTION,
    MAX_TICKS,
    MIN_HEIGHT,
    MIN_TICKS,
    MIN_WIDTH,
    TICK_SPACING_X,
    TICK_SPACING_Y,
    fit_margin,
    plot_area,
    resolve_size,
    ticks_for,
)
from svgplot.charts._legend import legend_ink_height, legend_text_room, minimum_legend_text_width

DATA = {
    "day": [1, 2, 3, 4, 1, 2, 3, 4],
    "value": [10.0, 15.0, 7.0, 20.0, 5.0, 8.0, 3.0, 12.0],
    "weight": [1.0, 4.0, 2.0, 5.0, 3.0, 1.0, 4.0, 2.0],
    "category": ["a", "b", "c", "d", "a", "b", "c", "d"],
    "group": ["x", "x", "x", "x", "y", "y", "y", "y"],
}

GAUGE_DATA = {"value": [72.0, 91.0], "category": ["uptime", "hit rate"]}

# Every chart that gained width=/height=. sparkline is deliberately absent -- it already
# had them, with its own defaults and no axes to fit, and its own section is below.
SIZED_CHARTS: list[tuple[str, Callable[..., sp.Chart]]] = [
    ("lineplot", lambda **kw: sp.lineplot(DATA, x="day", y="value", **kw)),
    ("lineplot_hue", lambda **kw: sp.lineplot(DATA, x="day", y="value", hue="group", **kw)),
    ("scatterplot", lambda **kw: sp.scatterplot(DATA, x="day", y="value", size="weight", **kw)),
    # hue *and* size: two legends stacked, which is the combination whose second legend
    # used to start below the canvas while each legend on its own looked fine.
    ("scatterplot_hue_size", lambda **kw: sp.scatterplot(DATA, x="day", y="value", hue="group", size="weight", **kw)),
    ("barplot", lambda **kw: sp.barplot(DATA, x="category", y="value", **kw)),
    ("barplot_hue", lambda **kw: sp.barplot(DATA, x="category", y="value", hue="group", **kw)),
    ("histplot", lambda **kw: sp.histplot(DATA, x="value", bins=4, **kw)),
    ("areaplot", lambda **kw: sp.areaplot(DATA, x="day", y="value", **kw)),
    ("pieplot", lambda **kw: sp.pieplot(DATA, values="value", labels="category", **kw)),
    ("boxplot", lambda **kw: sp.boxplot(DATA, x="group", y="value", **kw)),
    ("ecdfplot", lambda **kw: sp.ecdfplot(DATA, x="value", hue="group", **kw)),
    ("kdeplot", lambda **kw: sp.kdeplot(DATA, x="value", hue="group", **kw)),
    ("violinplot", lambda **kw: sp.violinplot(DATA, x="group", y="value", **kw)),
    ("regplot", lambda **kw: sp.regplot(DATA, x="day", y="value", **kw)),
    ("heatmap", lambda **kw: sp.heatmap(DATA, x="day", y="group", values="value", **kw)),
    ("radarplot", lambda **kw: sp.radarplot(DATA, x="category", y="value", hue="group", **kw)),
    ("treemap", lambda **kw: sp.treemap(DATA, values="value", labels="category", **kw)),
    # Two rows, not the fixture's eight: a gauge's rings have their own thickness rule,
    # and on a small canvas that rule binds before the canvas minimum does. Its own test
    # below covers what happens when it does.
    ("gaugeplot", lambda **kw: sp.gaugeplot(GAUGE_DATA, value="value", labels="category", **kw)),
]
CHART_IDS = [name for name, _ in SIZED_CHARTS]

_TAG_RE = re.compile(r"<(rect|line|circle|text|path)\b[^>]*>")
_ATTR_RE = re.compile(r'([\w:-]+)="([^"]*)"')


_PATH_TOKEN_RE = re.compile(r"[A-Za-z]|-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
# How many numbers each path command takes, and how many of them are coordinates. ``A`` is
# the one that matters: it takes seven numbers of which only the last two are a point, so
# splitting a ``d`` on odd/even positions flips x and y for **everything after the first
# arc** -- and this package's ``pieplot``/``gaugeplot``/donut paths are exactly ``M L A``
# sequences. A synthetic case proved the old parser reported 0 for a point 50px below the
# canvas.
_PATH_ARITY = {"M": 2, "L": 2, "T": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "A": 7, "Z": 0}


def _path_points(data: str) -> list[tuple[float, float]]:
    """The endpoint of every command in a ``d``, as (x, y).

    An arc's radii and flags are dropped rather than misread as a point. Its *bulge* is not
    sampled, so a curve that leaves the canvas without either endpoint leaving it is still
    invisible here -- stated rather than implied, because the previous version of this comment
    claimed the parser over-counted when it in fact under-counted.
    """
    tokens = _PATH_TOKEN_RE.findall(data)
    points: list[tuple[float, float]] = []
    index = 0
    command = "M"
    while index < len(tokens):
        if tokens[index].isalpha():
            command = tokens[index].upper()
            index += 1
            continue
        arity = _PATH_ARITY.get(command, 2)
        if arity == 0:
            index += 1
            continue
        numbers = [float(token) for token in tokens[index : index + arity]]
        index += arity
        if len(numbers) < arity:
            break
        if command == "H":
            points.append((numbers[0], points[-1][1] if points else 0.0))
        elif command == "V":
            points.append((points[-1][0] if points else 0.0, numbers[0]))
        else:
            points.append((numbers[-2], numbers[-1]))
    return points


def _worst_overflow(svg: str, width: float, height: float) -> float:
    """How far outside the canvas the furthest drawn element reaches, in pixels.

    Covers rect corners, circle *edges* (centre plus radius), line endpoints, text anchors
    and the coordinate pairs inside a ``<path>``'s ``d``. The last two were the holes: with
    ``d`` unparsed this helper saw nothing at all of ``line``/``area``/``kde``/``ecdf``/
    ``violin``/``radar``/``pie``/``gauge``'s data marks, and with ``r`` ignored it
    under-reported a scatter overflow by the marker radius. An arc's ``A`` parameters are
    dropped rather than read as a point — see :func:`_path_points`, and note that an arc's
    bulge is not sampled.

    Glyph extents are still invisible: this package has no font metrics, so a text element
    contributes only its anchor. The plot background is skipped because it is the canvas.
    """
    worst = 0.0
    for tag in _TAG_RE.finditer(svg):
        attrs = dict(_ATTR_RE.findall(tag.group()))
        if "plot-background" in attrs.get("class", "").split():
            continue
        xs: list[float] = []
        ys: list[float] = []
        for key, raw in attrs.items():
            try:
                value = float(raw)
            except ValueError:
                continue
            if key in ("x", "x1", "x2", "cx"):
                xs.append(value)
            elif key in ("y", "y1", "y2", "cy"):
                ys.append(value)
        if "width" in attrs and "x" in attrs:
            with contextlib.suppress(ValueError):
                xs.append(float(attrs["x"]) + float(attrs["width"]))
        if "height" in attrs and "y" in attrs:
            with contextlib.suppress(ValueError):
                ys.append(float(attrs["y"]) + float(attrs["height"]))
        if "r" in attrs:
            with contextlib.suppress(ValueError):
                radius = float(attrs["r"])
                xs.extend([value + radius for value in xs] + [value - radius for value in xs])
                ys.extend([value + radius for value in ys] + [value - radius for value in ys])
        if "d" in attrs:
            for point_x, point_y in _path_points(attrs["d"]):
                xs.append(point_x)
                ys.append(point_y)
        worst = max([worst, *(value - width for value in xs), *(-value for value in xs)])
        worst = max([worst, *(value - height for value in ys), *(-value for value in ys)])
    return worst


def _tick_labels(svg: str, width: float, height: float, margin: object) -> tuple[list[str], list[str]]:
    """The drawn tick label texts, split into (x-axis, y-axis).

    Split on the **x** coordinate: a y-axis label sits left of the plot area, an x-axis label
    inside its width. Splitting on y instead looks right and is not — ``render_y_axis`` nudges
    its labels down by half the tick offset, so the y label at the domain's minimum lands
    *below* ``area.bottom`` and gets counted as an x label. ``lineplot`` happens to escape
    that because its y domain has slack; ``regplot`` and ``histplot``, whose axes start
    exactly at a data bound, do not.

    Not ``text-anchor`` either, which is an attribute the tick code itself sets and so
    exactly the thing a helper must not key on if it is to notice that code changing.
    """
    area = plot_area(width, height, margin=fit_margin(margin, width, height))
    xs: list[str] = []
    ys: list[str] = []
    for match in re.finditer(r"<text([^>]*)>([^<]*)</text>", svg):
        attrs = dict(_ATTR_RE.findall(match.group(1)))
        if "tick-label" not in attrs.get("class", "").split():
            continue
        (ys if float(attrs["x"]) < area.left else xs).append(match.group(2))
    return xs, ys


def _canvas(svg: str) -> tuple[str, str]:
    root = re.search(r"<svg\b[^>]*>", svg)
    assert root is not None
    attrs = dict(_ATTR_RE.findall(root.group()))
    return attrs["width"], attrs["height"]


# --- 1. the default call does not move -------------------------------------------------


@pytest.mark.parametrize(("name", "build"), SIZED_CHARTS, ids=CHART_IDS)
def test_passing_the_defaults_explicitly_is_the_same_chart(name: str, build: Callable[..., sp.Chart]) -> None:
    """The whole feature has to be invisible to every existing call. Byte-identical, not
    "looks the same" -- a chart is a document in this package."""
    assert build().to_string() == build(width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT).to_string()


@pytest.mark.parametrize(("name", "build"), SIZED_CHARTS, ids=CHART_IDS)
def test_the_default_canvas_is_still_800_by_600(name: str, build: Callable[..., sp.Chart]) -> None:
    assert _canvas(build().to_string()) == ("800", "600")


def test_the_derived_tick_count_is_five_for_both_margin_presets_at_the_default_size() -> None:
    """This is *why* the default is byte-identical rather than a coincidence: every chart
    used to pass a fixed ``tick_count=5``, and the two presets leave different plot widths,
    so a single spacing has to round both of them back to 5."""
    for margin in (MARGIN_WITH_LEGEND, MARGIN_WITHOUT_LEGEND):
        area = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=fit_margin(margin, DEFAULT_WIDTH, DEFAULT_HEIGHT))
        assert ticks_for(area.width, TICK_SPACING_X) == 5
        assert ticks_for(area.height, TICK_SPACING_Y) == 5


def test_the_margin_clamp_cannot_engage_at_the_default_size() -> None:
    """The other half of the same reason."""
    for margin in (MARGIN_WITH_LEGEND, MARGIN_WITHOUT_LEGEND):
        assert fit_margin(margin, DEFAULT_WIDTH, DEFAULT_HEIGHT) == margin


# --- 2. a chosen size takes effect -----------------------------------------------------


@pytest.mark.parametrize(("name", "build"), SIZED_CHARTS, ids=CHART_IDS)
def test_the_canvas_is_the_size_that_was_asked_for(name: str, build: Callable[..., sp.Chart]) -> None:
    assert _canvas(build(width=420, height=320).to_string()) == ("420", "320")


@pytest.mark.parametrize(("name", "build"), SIZED_CHARTS, ids=CHART_IDS)
def test_the_background_covers_the_whole_canvas(name: str, build: Callable[..., sp.Chart]) -> None:
    """A background left at 800x600 on a 420x320 canvas would paint outside it, which is
    both wrong and invisible in a size assertion on the root element alone."""
    svg = build(width=420, height=320).to_string()
    background = re.search(r'<rect\b[^>]*class="plot-background"[^>]*/>', svg)
    assert background is not None
    attrs = dict(_ATTR_RE.findall(background.group()))
    assert (attrs["width"], attrs["height"]) == ("420", "320")


def test_width_and_height_can_be_set_independently() -> None:
    assert _canvas(sp.lineplot(DATA, x="day", y="value", width=500).to_string()) == ("500", "600")
    assert _canvas(sp.lineplot(DATA, x="day", y="value", height=400).to_string()) == ("800", "400")


# --- 3. margins do not eat a small canvas ----------------------------------------------


@pytest.mark.parametrize("width", [800, 600, 400, 300, MIN_WIDTH])
def test_the_plot_area_keeps_the_majority_of_the_canvas(width: float) -> None:
    """The issue's sharpest example: at 300 px the untouched preset left an 80 px plot
    area (300 - 160 - 60). The clamp is what stops that."""
    area = plot_area(width, 600, margin=fit_margin(MARGIN_WITH_LEGEND, width, 600))

    assert area.width >= width * (1 - MAX_MARGIN_FRACTION)
    assert area.width > 80.0


def test_a_chart_actually_uses_the_fitted_margin() -> None:
    """The clamp has to be wired into each chart, not merely available: a chart that passed
    the raw preset would draw an 80 px plot area at 300 px wide while ``fit_margin`` sat
    there computing 165. Read back from the drawn spine, which is the plot area's own edge.
    """
    svg = sp.barplot(DATA, x="category", y="value", hue="group", width=300, height=240).to_string()
    spine = re.search(r'<line\b[^>]*class="spine"[^>]*/>', svg)
    assert spine is not None
    attrs = dict(_ATTR_RE.findall(spine.group()))

    assert float(attrs["x2"]) - float(attrs["x1"]) == pytest.approx(165.0)


def test_the_measured_plot_area_at_the_issue_s_example_width() -> None:
    """The number the acceptance criterion asks to be measured, pinned so it stays true."""
    area = plot_area(300, 240, margin=fit_margin(MARGIN_WITH_LEGEND, 300, 240))

    assert (round(area.width, 1), round(area.height, 1)) == (165.0, 160.0)


def test_both_sides_of_a_pair_shrink_together() -> None:
    """Trimming only the legend gutter would leave the tick labels their full 60 px on a
    canvas that has none to spare; trimming only the tick gutter would do the reverse."""
    top, right, bottom, left = fit_margin(MARGIN_WITH_LEGEND, 300, 600)

    assert right / left == pytest.approx(160.0 / 60.0)
    assert (top, bottom) == (30.0, 50.0)  # vertical has room at this height, so untouched


def test_the_vertical_pair_is_clamped_by_the_same_rule() -> None:
    """No margin preset this package ships is tall enough to reach the vertical clamp at
    any allowed canvas size -- the tallest is 80 px against a 81 px budget at the minimum
    height. It is not dead code, though: ``fit_margin`` takes whatever margin it is given,
    and the rule has to be the same on both axes or a tall custom margin would eat a short
    canvas exactly the way the shipped horizontal preset ate a narrow one."""
    top, right, bottom, left = fit_margin((100.0, 10.0, 200.0, 10.0), 800, 400)

    assert top + bottom == pytest.approx(400 * MAX_MARGIN_FRACTION)
    assert bottom / top == pytest.approx(2.0)
    assert (left, right) == (10.0, 10.0)


def test_a_margin_that_already_fits_is_left_alone() -> None:
    """Never scales up: a caller who asked for a small margin wanted a big plot area."""
    assert fit_margin((5.0, 5.0, 5.0, 5.0), 300, 240) == (5.0, 5.0, 5.0, 5.0)


@pytest.mark.parametrize(("name", "build"), SIZED_CHARTS, ids=CHART_IDS)
@pytest.mark.parametrize(("width", "height"), [(800, 600), (500, 375), (400, 300)])
def test_nothing_is_drawn_outside_the_canvas(name: str, build: Callable[..., sp.Chart], width: float, height: float) -> None:
    """The failure this whole clamp exists to prevent, checked on every chart type at every
    size rather than argued about for one."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", sp.SvgplotWarning)
        svg = build(width=width, height=height).to_string()

    assert _worst_overflow(svg, width, height) == pytest.approx(0.0, abs=1e-6)


# The same charts over two categories instead of four. A legend row is 20 px tall, so at
# the minimum height only about seven rows fit below the top margin -- which is a property
# of the *data*, not of this feature, and is refused with its own message (below). These
# builders keep the sweep about geometry rather than about legend length.
SMALL = {
    "day": [1, 2, 1, 2],
    "value": [10.0, 20.0, 5.0, 12.0],
    "weight": [1.0, 4.0, 3.0, 2.0],
    "category": ["a", "b", "a", "b"],
    "group": ["x", "x", "y", "y"],
}
MIN_SIZE_CHARTS: list[tuple[str, Callable[..., sp.Chart]]] = [
    ("lineplot", lambda **kw: sp.lineplot(SMALL, x="day", y="value", hue="group", **kw)),
    ("scatterplot", lambda **kw: sp.scatterplot(SMALL, x="day", y="value", size="weight", **kw)),
    ("barplot", lambda **kw: sp.barplot(SMALL, x="category", y="value", hue="group", **kw)),
    ("histplot", lambda **kw: sp.histplot(SMALL, x="value", bins=2, **kw)),
    ("areaplot", lambda **kw: sp.areaplot(SMALL, x="day", y="value", **kw)),
    ("pieplot", lambda **kw: sp.pieplot(SMALL, values="value", labels="category", **kw)),
    ("boxplot", lambda **kw: sp.boxplot(SMALL, x="group", y="value", **kw)),
    ("ecdfplot", lambda **kw: sp.ecdfplot(SMALL, x="value", hue="group", **kw)),
    ("violinplot", lambda **kw: sp.violinplot(DATA, x="group", y="value", **kw)),
    ("regplot", lambda **kw: sp.regplot(SMALL, x="day", y="value", **kw)),
    ("treemap", lambda **kw: sp.treemap(SMALL, values="value", labels="category", **kw)),
    ("gaugeplot", lambda **kw: sp.gaugeplot(GAUGE_DATA, value="value", labels="category", **kw)),
]


@pytest.mark.parametrize(("name", "build"), MIN_SIZE_CHARTS, ids=[name for name, _ in MIN_SIZE_CHARTS])
def test_nothing_is_drawn_outside_the_smallest_canvas(name: str, build: Callable[..., sp.Chart]) -> None:
    """The minimum size itself, where every clamp is engaged at once."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", sp.SvgplotWarning)
        svg = build(width=MIN_WIDTH, height=MIN_HEIGHT).to_string()

    assert _worst_overflow(svg, MIN_WIDTH, MIN_HEIGHT) == pytest.approx(0.0, abs=1e-6)


def test_a_legend_taller_than_the_canvas_is_refused_rather_than_clipped() -> None:
    """A legend that runs off the bottom is not a smaller legend, it is a missing one.
    ``heatmap``'s nine colour levels need 180 px of rows below the top margin, which a
    minimum-height canvas does not have."""
    with pytest.raises(ValueError, match="a legend of 9 entries needs"):
        sp.heatmap(DATA, x="day", y="group", values="value", width=400, height=MIN_HEIGHT)


def test_the_legend_guard_measures_ink_not_the_space_a_legend_claims() -> None:
    """``render_legend`` returns ``rows * _ROW_HEIGHT`` so a caller can stack under it, and
    that number is bigger than the legend's ink by the last row's own bottom padding. Guarding
    on it refuses legends that fit: on ``origin/main`` a 29-entry legend at 800x600 puts its
    lowest ink at y=594 and renders correctly. Read the boundary back from what is drawn."""
    svg = sp.heatmap(DATA, x="day", y="group", values="value", width=400, height=200).to_string()
    swatches = [tag for tag in re.finditer(r"<rect\b[^>]*/>", svg) if "level-" in tag.group()]
    inked_bottom = max(
        float(dict(_ATTR_RE.findall(tag.group()))["y"]) + float(dict(_ATTR_RE.findall(tag.group()))["height"])
        for tag in swatches
    )

    assert inked_bottom <= 200
    assert _worst_overflow(svg, 400, 200) == pytest.approx(0.0, abs=1e-6)
    with pytest.raises(ValueError, match="a legend of 9 entries needs"):
        sp.heatmap(DATA, x="day", y="group", values="value", width=400, height=197)


def test_a_second_legend_stacked_below_the_first_is_checked_too() -> None:
    """``scatterplot(hue=, size=)`` draws two legends, one under the other. Each looked fine
    on its own while the pair ran 46 px off a 400x180 canvas — the guard has to cover the
    stack, not the first legend."""
    # Six groups, not the fixture's two: the hue legend has to be long enough to push the
    # size legend past the edge while still fitting itself. That is the whole shape of the
    # bug, and it is why the shared fixture never caught it.
    groups = 6
    wide = {
        "x": [float(index) for index in range(2 * groups)],
        "y": [float(index % 5) for index in range(2 * groups)],
        "w": [1.0 + index for index in range(2 * groups)],
        "g": [chr(97 + index // 2) for index in range(2 * groups)],
    }
    with pytest.raises(ValueError, match="a size legend of"):
        sp.scatterplot(wide, x="x", y="y", hue="g", size="w", width=400, height=180)

    tall = sp.scatterplot(wide, x="x", y="y", hue="g", size="w", width=400, height=320).to_string()
    assert _worst_overflow(tall, 400, 320) == pytest.approx(0.0, abs=1e-6)


def test_the_default_canvas_refuses_a_legend_it_used_to_clip() -> None:
    """The boundary, pinned to the numbers rather than left to drift -- and pinned to the
    ones ``origin/main`` actually draws. An earlier version of this guard refused 29 groups on
    the strength of a claim that main clipped them, which measurement disproved: main puts the
    29th row's ink at y=594 on a 600px canvas. Thirty reaches 614 and really does overflow."""

    def build(groups: int) -> sp.Chart:
        rows = groups * 2
        return sp.lineplot(
            {
                "x": [float(index % 2) for index in range(rows)],
                "y": [float(index) for index in range(rows)],
                "g": [f"group-{index // 2}" for index in range(rows)],
            },
            x="x",
            y="y",
            hue="g",
        )

    assert build(29) is not None  # 594px of ink on a 600px canvas -- exactly what main drew
    with pytest.raises(ValueError, match="a legend of 30 entries needs"):
        build(30)


def test_a_taller_canvas_takes_the_same_legend() -> None:
    """The refusal is about the canvas, not the legend: nothing is wrong with nine levels."""
    assert sp.heatmap(DATA, x="day", y="group", values="value", width=400, height=300) is not None


def test_a_gauge_with_too_many_rows_for_a_small_canvas_names_its_own_limit() -> None:
    """A gauge's ring thickness is its own rule, older than this issue, and on a small
    canvas it binds before the canvas minimum does — with a message that names it."""
    with pytest.raises(ValueError, match="below the 3.0px that still reads as an arc"):
        sp.gaugeplot(DATA, value="value", labels="category", width=MIN_WIDTH, height=MIN_HEIGHT)


@pytest.mark.parametrize(("width", "height"), [(MIN_WIDTH, 2000), (2000, MIN_HEIGHT)])
def test_an_extreme_aspect_ratio_still_stays_inside_the_canvas(width: float, height: float) -> None:
    """A tall column and a wide banner are the two shapes a markdown layout actually asks
    for, and each clamps only one of the two margin pairs."""
    svg = sp.barplot(DATA, x="category", y="value", hue="group", width=width, height=height).to_string()

    assert _worst_overflow(svg, width, height) == pytest.approx(0.0, abs=1e-6)


# --- 4. the minimum, and where it comes from -------------------------------------------


def test_the_minimum_width_is_the_boundary_the_legend_gutter_gives() -> None:
    """``MIN_WIDTH``'s docstring derives 239.25 from the legend gutter rather than picking
    a round number. Recomputed here, so the constant cannot drift away from its own
    justification -- if the margin fraction or the legend geometry changes, this fails."""
    needed = minimum_legend_text_width(11.0)
    fitting = [
        width / 100
        for width in range(10_000, 60_000)
        if legend_text_room(fit_margin(MARGIN_WITH_LEGEND, width / 100, 600)[1] - LEGEND_X_OFFSET) >= needed
    ]
    assert fitting, "the boundary left the 100-600px search window; widen it rather than trusting min()"
    boundary = min(fitting)

    assert boundary == pytest.approx(239.25, abs=0.01)
    assert math.ceil(boundary) == MIN_WIDTH


def test_the_minimum_height_keeps_the_default_aspect_ratio() -> None:
    assert MIN_HEIGHT == MIN_WIDTH * DEFAULT_HEIGHT / DEFAULT_WIDTH


def test_the_minimum_canvas_still_holds_two_ticks_on_each_axis() -> None:
    """Two, spelled out — the name of this test is a promise about a number, not about
    whatever ``MIN_TICKS`` currently happens to be."""
    area = plot_area(MIN_WIDTH, MIN_HEIGHT, margin=fit_margin(MARGIN_WITH_LEGEND, MIN_WIDTH, MIN_HEIGHT))

    assert ticks_for(area.width, TICK_SPACING_X) == 2
    assert ticks_for(area.height, TICK_SPACING_Y) == 2


@pytest.mark.parametrize(("width", "height"), [(MIN_WIDTH - 1, MIN_HEIGHT), (MIN_WIDTH, MIN_HEIGHT - 1), (10, 10)])
def test_a_canvas_below_the_minimum_is_refused(width: float, height: float) -> None:
    """Refused rather than clamped: a caller who asked for 100 px and silently got 240
    would have a chart that does not fit where they meant to put it."""
    with pytest.raises(ValueError, match="canvas must be at least"):
        sp.lineplot(DATA, x="day", y="value", width=width, height=height)


def test_exactly_the_minimum_renders() -> None:
    assert _canvas(sp.lineplot(DATA, x="day", y="value", width=MIN_WIDTH, height=MIN_HEIGHT).to_string()) == ("240", "180")


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), "800", None if False else True, [800]])
def test_a_size_that_is_not_a_finite_number_is_refused(bad: object) -> None:
    with pytest.raises(ValueError, match="must be a finite number"):
        sp.lineplot(DATA, x="day", y="value", width=bad)


def test_zero_is_a_size_that_is_refused_not_a_missing_one() -> None:
    """``width or DEFAULT_WIDTH`` would quietly turn 0 into 800. ``None`` means "default";
    every other value, 0 included, is a size the caller asked for and has to answer for."""
    with pytest.raises(ValueError, match="canvas must be at least"):
        sp.lineplot(DATA, x="day", y="value", width=0)


def test_none_means_the_package_default_rather_than_an_error() -> None:
    assert resolve_size(None, None) == (DEFAULT_WIDTH, DEFAULT_HEIGHT)
    assert resolve_size(400.0, None) == (400.0, DEFAULT_HEIGHT)


# --- 5. tick density --------------------------------------------------------------------


def test_ticks_thin_out_as_the_canvas_shrinks() -> None:
    """The decision this issue asked to be made and documented: the tick *request* tracks
    the plot extent at the density the default size already uses."""
    counts = [
        ticks_for(plot_area(w, 600, margin=fit_margin(MARGIN_WITHOUT_LEGEND, w, 600)).width, TICK_SPACING_X)
        for w in (800, 600, 400, 300, MIN_WIDTH)
    ]

    assert counts == sorted(counts, reverse=True)
    assert counts[0] > counts[-1]


def test_the_tick_request_is_clamped_at_both_ends() -> None:
    """Literals, not the constants themselves. Asserting ``== MIN_TICKS`` restates the code
    and passes for any value it might drift to -- and both clamps really bite: the raw
    request at the minimum canvas is 1 on each axis, and at 3000x2400 it is 23."""
    assert (MIN_TICKS, MAX_TICKS) == (2, 10)
    assert ticks_for(1.0, TICK_SPACING_X) == 2
    assert ticks_for(100_000.0, TICK_SPACING_X) == 10
    assert (
        round(
            plot_area(MIN_WIDTH, MIN_HEIGHT, margin=fit_margin(MARGIN_WITHOUT_LEGEND, MIN_WIDTH, MIN_HEIGHT)).width
            / TICK_SPACING_X
        )
        == 1
    )  # the clamp is what turns this into an axis


def test_the_default_size_draws_exactly_the_ticks_it_always_drew() -> None:
    """Counting labels is not enough: a mutation that put the *horizontal* spacing on the y
    axis still leaves "fewer labels when narrower" true, while silently changing the axis
    every existing chart shows. So the labels themselves are pinned, both axes."""
    labels = _tick_labels(sp.lineplot(DATA, x="day", y="value").to_string(), 800, 600, MARGIN_WITHOUT_LEGEND)

    assert labels == (["1", "1.5", "2", "2.5", "3", "3.5", "4"], ["5", "10", "15", "20"])


def test_the_axis_split_survives_a_chart_whose_y_axis_starts_at_a_data_bound() -> None:
    """``_tick_labels`` splits on x because splitting on y misclassifies: ``render_y_axis``
    nudges its labels down by half the tick offset, so the label at the domain's minimum lands
    *below* ``area.bottom``. ``lineplot`` escapes it by having slack in its y domain, which is
    why every other test here passed under the broken rule — ``histplot``'s count axis starts
    at exactly zero and does not."""
    labels = _tick_labels(sp.histplot(DATA, x="value", bins=4).to_string(), 800, 600, MARGIN_WITHOUT_LEGEND)

    assert "0" in labels[1], labels
    assert "0" not in labels[0], labels


def test_the_overflow_detector_reads_arcs_without_transposing_them() -> None:
    """An ``A`` command takes seven numbers of which only two are a point. Splitting a ``d``
    on odd/even positions flips x and y for everything after the first arc, and this package's
    pie/donut/gauge paths are exactly ``M L A`` sequences -- so the detector guarding those
    charts was reading their coordinates sideways."""
    arc_then_line = '<svg width="800" height="200"><path d="M 10 50 A 20 20 0 0 1 30 50 L 100 250"/></svg>'

    assert _worst_overflow(arc_then_line, 800, 200) == pytest.approx(50.0)


def test_the_y_spacing_constant_is_pinned_to_a_value_not_just_a_role() -> None:
    """``TICK_SPACING_Y`` could drift from 104 to 96 with the whole suite still green: every
    size the other tests use rounds both to the same request. At 800x330 the plot area is
    250 px tall, where 104 asks for two ticks and 96 asks for three."""
    labels = _tick_labels(
        sp.lineplot(DATA, x="day", y="value", width=800, height=330).to_string(), 800, 330, MARGIN_WITHOUT_LEGEND
    )

    assert labels[1] == ["10", "20"]


def test_the_x_axis_thins_by_its_own_spacing_too() -> None:
    """The mirror of the test below, and the one that was missing. At 400x300 the plot area
    is 300 px wide: the horizontal spacing asks for two ticks and the vertical one would ask
    for three, and ``make_ticks`` answers those differently. Every other size in this file
    rounds both requests to the same number, so swapping the two constants the other way
    round left the whole suite green."""
    labels = _tick_labels(
        sp.lineplot(DATA, x="day", y="value", width=400, height=300).to_string(), 400, 300, MARGIN_WITHOUT_LEGEND
    )

    assert labels[0] == ["2", "4"]


def test_each_axis_thins_by_its_own_spacing() -> None:
    """The two axes have different spacings because their labels stack differently, and a
    chart has to hand each axis its own. At 800x360 the horizontal spacing would ask the y
    axis for two ticks where its own asks for three -- a difference invisible at the sizes
    the other tests use, where both requests happen to round to the same answer."""
    labels = _tick_labels(
        sp.lineplot(DATA, x="day", y="value", width=800, height=360).to_string(), 800, 360, MARGIN_WITHOUT_LEGEND
    )

    assert labels[1] == ["5", "10", "15", "20"]


def test_a_narrow_chart_draws_exactly_the_thinned_ticks() -> None:
    """``ticks_for`` is only a request -- ``make_ticks`` answers with nice round numbers
    near it. What is pinned here is the answer, not the request."""
    narrow = sp.lineplot(DATA, x="day", y="value", width=300, height=240).to_string()

    assert _tick_labels(narrow, 300, 240, MARGIN_WITHOUT_LEGEND) == (["2", "4"], ["10", "20"])


# --- 6. the neighbours -------------------------------------------------------------------


def test_sparkline_keeps_its_own_defaults_and_is_exempt_from_the_minimum() -> None:
    """It draws no axes, legend or labels, so none of the reasoning above applies to it."""
    assert _canvas(sp.sparkline(DATA, y="value").to_string()) == ("120", "24")
    assert _canvas(sp.sparkline(DATA, y="value", width=60, height=12).to_string()) == ("60", "12")


def test_apply_size_still_works_on_a_custom_canvas() -> None:
    """``apply_size`` reads the document's own dimensions, so responsive mode has to follow
    a chosen size rather than the package default."""
    chart = sp.apply_size(sp.lineplot(DATA, x="day", y="value", width=400, height=300), "responsive")
    svg = chart.to_string()

    assert 'viewBox="0 0 400 300"' in svg


def test_a_composition_of_custom_sized_charts_serializes(tmp_path) -> None:
    """Composition places children by their own documents' sizes; nothing in it assumed the
    default, and this pins that."""
    figure = sp.row(
        [
            sp.lineplot(DATA, x="day", y="value", width=300, height=240),
            sp.barplot(DATA, x="category", y="value", width=300, height=240),
        ]
    )
    path = tmp_path / "figure.svg"
    figure.save(str(path))

    # The composed canvas has to be built from the children's own sizes. Counting <svg>
    # elements cannot show that -- three of them come back for default-sized children too.
    root = re.search(r"<svg\b[^>]*>", path.read_text(encoding="utf-8"))
    assert root is not None
    attrs = dict(_ATTR_RE.findall(root.group()))
    assert (attrs["width"], attrs["height"]) == ("612", "240")


# --- the validation the review found uneven ---------------------------------------------


def test_a_numpy_size_is_a_size() -> None:
    """A canvas size very often arrives from the same array library the data did, and
    ``numpy.float32``/``numpy.int64`` are neither ``int`` nor ``float``."""
    numpy = pytest.importorskip("numpy")

    for value in (numpy.float32(400), numpy.int64(400), numpy.float64(400)):
        assert _canvas(sp.lineplot(DATA, x="day", y="value", width=value).to_string())[0] == "400"


def test_a_negative_margin_side_is_refused() -> None:
    """The pair's *sum* can sit under the budget while one side is -500, which put the plot
    area 500 px above the canvas. ``fit_margin`` documents itself as taking whatever margin
    it is given, and this is what makes that true rather than merely unchecked."""
    with pytest.raises(ValueError, match="must not be negative"):
        fit_margin((-500.0, 10.0, 400.0, 10.0), 800, 400)


@pytest.mark.parametrize("bad", ["120", float("nan"), float("inf"), True])
def test_sparkline_refuses_an_unusable_size_by_name(bad: object) -> None:
    """It is exempt from the *minimum*, not from the validation: these used to surface as a
    ``TypeError`` about ``str`` minus ``float``, or as one about an SVG literal, neither
    naming the argument."""
    with pytest.raises(ValueError, match="must be a finite number"):
        sp.sparkline(DATA, y="value", width=bad)


def test_every_sized_chart_documents_the_two_new_arguments() -> None:
    """They are public parameters; README and CHANGELOG are not where a caller looks first."""
    functions = [
        sp.lineplot,
        sp.scatterplot,
        sp.barplot,
        sp.histplot,
        sp.areaplot,
        sp.pieplot,
        sp.boxplot,
        sp.ecdfplot,
        sp.kdeplot,
        sp.violinplot,
        sp.regplot,
        sp.heatmap,
        sp.radarplot,
        sp.treemap,
        sp.gaugeplot,
    ]

    undocumented = [function.__name__ for function in functions if "240x180" not in (function.__doc__ or "")]
    assert undocumented == []


def test_the_heatmap_legend_boundary_is_where_its_ink_ends() -> None:
    """The figure README and CHANGELOG quote, pinned. Nine entries put ``legend_ink_height(9)``
    = 168px of ink below the top margin at y=30, so the shortest canvas that holds them is
    198 — not the 210 the claimed-space rule gives, which is what those two documents said
    until this was measured."""
    data = {
        "r": [f"r{index}" for index in range(3)] * 3,
        "c": [f"c{index}" for index in range(3) for _ in range(3)],
        "v": [float(index) for index in range(9)],
    }

    assert legend_ink_height(9) == 168.0
    with pytest.raises(ValueError, match="needs 168px below y=30"):
        sp.heatmap(data, x="r", y="c", values="v", width=400, height=197)
    assert sp.heatmap(data, x="r", y="c", values="v", width=400, height=198) is not None
