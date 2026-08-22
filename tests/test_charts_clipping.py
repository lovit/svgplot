"""What a narrowing ``xlim=``/``ylim=`` may draw, for every chart that takes one.

``apply_limit`` says a caller who asks for ``(0, 100)`` on data spanning 0..300 "means to clip
the view" (``chart/_domain.py``). Nothing clipped it. Every one of the ten charts below drew
its marks at whatever pixel the replaced domain mapped them to -- over the axis, through the
tick labels, off the canvas -- and each chart's own tests stayed green because none of them
asked where the ink landed. ``layout/facet.py`` had already recorded the symptom from the
other side: a bar drawn 57.8px above the plot area, which nothing cut and nothing warned about.
(That note is in this diff too -- the half of its sentence describing the absence of a clip is
no longer true and had to go.)

The two tests here are halves of one statement: with a limit, no mark outside the plot area;
without one, the same bytes as before any of this existed.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest

import svgplot as sp
from _svg_probe import CLIP_CLASS

_SVG_NS = "http://www.w3.org/2000/svg"

DATA = {
    # Ten rows per group, not two: ``boxplot`` computes no outliers from a pair, and an outlier
    # is a mark drawn by a code path of its own. ``CHARTS["boxplot"]`` splits on ``group``, and
    # 46.0 sits nine units past group a's upper fence (q1 14.5, q3 23.5, fence 37.0) -- units on
    # ``y``, not pixels; nothing here is rendered yet -- so group a draws exactly one outlier
    # and group b none.
    "x": [1.0, 2.0, 3.0, 4.0] * 5,
    "y": [
        10.0,
        12.0,
        14.0,
        16.0,
        18.0,
        20.0,
        22.0,
        24.0,
        26.0,
        46.0,
        11.0,
        13.0,
        15.0,
        17.0,
        19.0,
        21.0,
        23.0,
        25.0,
        27.0,
        9.0,
    ],
    "category": ["가", "나", "다", "라"] * 5,
    "group": ["a"] * 10 + ["b"] * 10,
    "weight": [1.0, 2.0, 3.0, 4.0, 5.0] * 4,
}

WINDOWS = {
    "barplot": (19.0, 21.0),
    "ecdfplot": (0.1, 0.5),
    "histplot": (0.2, 0.8),
    "kdeplot": (0.005, 0.02),
}
"""Per-chart ``ylim=`` windows, where ``(15, 25)`` would not bite on both sides.

Everything else measures ``y`` (9..46) and takes ``(15, 25)``: inside the data on both sides,
so there is ink to lose above *and* below. ``barplot`` aggregates, so what it draws is four
category means -- 18.4, 24.0, 18.6, 16.6 -- rather than the twenty rows, and ``(15, 25)``
contains every one of them, so only the baseline would escape.

``ecdfplot``'s y is a proportion and ``kdeplot``'s a density, and a window outside *their*
range would leave the whole curve on one side of the clip
-- which still clips, and would still pass a test that only asked whether anything was cut.
Every window is checked for biting rather than trusted -- in both directions except for
``histplot``, which draws each bar from its top down to ``area.bottom`` literally rather than
to the pixel its zero maps to, so a bar can leave the plot area upward but never downward. That
is the one chart whose floor was already where a clip would have put it.
"""

DEFAULT_WINDOW = (15.0, 25.0)

ESCAPES = dict.fromkeys(
    ("areaplot", "barplot", "boxplot", "ecdfplot", "kdeplot", "lineplot", "regplot", "scatterplot", "violinplot"),
    (True, True),
) | {"histplot": (True, False)}
"""``(above, below)``: which side of the plot area each chart's ink reaches past, measured.

Pinned rather than asserted loosely, because "something escaped" is satisfied by a window that
only bites on one side -- and then the clip is only shown to work on that side."""


def _window(name: str) -> tuple[float, float]:
    return WINDOWS.get(name, DEFAULT_WINDOW)


CHARTS = {
    "areaplot": lambda **kwargs: sp.areaplot(DATA, x="x", y="y", **kwargs),
    "barplot": lambda **kwargs: sp.barplot(DATA, x="category", y="y", estimator="mean", **kwargs),
    "boxplot": lambda **kwargs: sp.boxplot(DATA, x="group", y="y", **kwargs),
    "ecdfplot": lambda **kwargs: sp.ecdfplot(DATA, x="y", **kwargs),
    "histplot": lambda **kwargs: sp.histplot(DATA, x="y", **kwargs),
    "kdeplot": lambda **kwargs: sp.kdeplot(DATA, x="y", **kwargs),
    "lineplot": lambda **kwargs: sp.lineplot(DATA, x="x", y="y", **kwargs),
    "regplot": lambda **kwargs: sp.regplot(DATA, x="x", y="y", **kwargs),
    "scatterplot": lambda **kwargs: sp.scatterplot(DATA, x="x", y="y", **kwargs),
    "violinplot": lambda **kwargs: sp.violinplot(DATA, x="group", y="y", **kwargs),
}


def test_the_registry_is_every_chart_that_takes_a_limit() -> None:
    """Derived from the signatures rather than trusted, so a chart that gains ``ylim=`` and no
    clip fails here instead of being missing from a sweep that still says it passed."""
    import inspect

    takes_a_limit = {
        name for name in sp.charts.__all__ if {"xlim", "ylim"} & set(inspect.signature(getattr(sp, name)).parameters)
    }

    assert takes_a_limit == set(CHARTS)


def _mark_extent(svg: str) -> tuple[float, float]:
    """Top and bottom of the ink a chart drew for its data, in canvas pixels.

    Only elements carrying a ``series-`` class, which is what a *mark* is here -- the axis,
    its ticks and the plot background have their own classes and are meant to live outside
    the plot area. A legend swatch carries a series class too and is meant to live outside it
    as well, so this walks the clip's own children when there is one: the question these tests
    ask is where the marks went, and after this change the marks are exactly what is inside.
    """
    root = ET.fromstring(svg)
    clips = [element for element in root.iter(f"{{{_SVG_NS}}}svg") if CLIP_CLASS in (element.get("class") or "").split()]
    scope = clips[0] if clips else root
    values: list[float] = []
    for element in scope.iter():
        if "series-" not in (element.get("class") or ""):
            continue
        tag = element.tag.removeprefix(f"{{{_SVG_NS}}}")
        if tag == "path":
            numbers = [float(token) for token in re.findall(r"-?\d+\.?\d*", element.get("d", ""))]
            values += numbers[1::2]
        elif tag == "rect":
            top = float(element.get("y", 0.0))
            values += [top, top + float(element.get("height", 0.0))]
        elif tag == "circle":
            centre, radius = float(element.get("cy", 0.0)), float(element.get("r", 0.0))
            values += [centre - radius, centre + radius]
        elif tag == "line":
            values += [float(element.get("y1", 0.0)), float(element.get("y2", 0.0))]
    assert values, "found no marks to measure"
    return min(values), max(values)


@pytest.mark.parametrize("name", sorted(CHARTS))
def test_a_narrowing_limit_leaves_no_mark_outside_the_plot_area(name: str) -> None:
    """The bug, as a measurement. Before the clip existed every one of these ten drew ink past
    the plot area: on the fixture below, with ``marks_viewport`` returning ``None``,
    ``violinplot`` spans -2071..1819 and ``areaplot`` -4910..1330 on a 600px canvas whose plot
    area is 30..550."""
    svg = CHARTS[name](ylim=_window(name)).to_string()
    root = ET.fromstring(svg)
    clips = [element for element in root.iter(f"{{{_SVG_NS}}}svg") if CLIP_CLASS in (element.get("class") or "").split()]

    assert len(clips) == 1, f"{name}: expected exactly one clip, got {len(clips)}"
    left, top = float(clips[0].get("x")), float(clips[0].get("y"))
    right, bottom = left + float(clips[0].get("width")), top + float(clips[0].get("height"))

    # All four sides, measured from the chart's own spines rather than recomputed from a margin
    # preset -- the left margin is *fitted* to the widest tick label and the right one to the
    # legend, so ``plot_area(800, 600, MARGIN_WITHOUT_LEGEND)`` is the plot area of a chart
    # nobody drew. The spines come from the axis renderer, which is handed the same rect the
    # clip is, and they are the one place the plot area appears twice in the output.
    #
    # Two of these four sides had no assertion at all until a review widened the clip by 20px on
    # each side and the suite stayed green -- a clip that leaks marks over the y-axis spine and
    # into the right margin. The ``viewBox`` check below cannot see that either: it compares the
    # attribute against the element's own rect, so a corruption moving both is self-consistent.
    assert (left, top, right, bottom) == _spine_rect(root), f"{name}: the clip is not the plot area"

    ink_top, ink_bottom = _mark_extent(svg)
    assert (ink_top < top, ink_bottom > bottom) == ESCAPES[name], (
        f"{name}: ink escapes {(ink_top < top, ink_bottom > bottom)}, pinned as {ESCAPES[name]} -- "
        "either the window stopped narrowing or a mark's baseline moved"
    )


@pytest.mark.parametrize("name", sorted(CHARTS))
def test_the_clip_does_not_move_what_it_holds(name: str) -> None:
    """A nested ``<svg>`` establishes a new coordinate system, and its ``viewBox`` is what says
    a coordinate inside means the same thing as outside. This has to be an assertion about the
    attribute rather than about the marks, because the marks do not move in the *markup* -- the
    charts go on writing the same pixels either way, and only a renderer sees the difference.

    Measured in a headless browser on ``lineplot(..., ylim=(5, 45))``: with the viewport's own
    rect the line's ink spans ``(60, 95)-(759, 485)``; with the obvious wrong answer, ``0 0 w
    h``, it spans ``(120, 158)-(759, 514)`` -- shifted by the plot area's origin and cut off at
    the right edge, from a document that is still valid and still clips.
    """
    svg = CHARTS[name](ylim=_window(name)).to_string()
    clip = next(
        element
        for element in ET.fromstring(svg).iter(f"{{{_SVG_NS}}}svg")
        if CLIP_CLASS in (element.get("class") or "").split()
    )

    rect = (clip.get("x"), clip.get("y"), clip.get("width"), clip.get("height"))
    assert clip.get("viewBox") == " ".join(rect), f"{name}: the clip's viewBox is not its own viewport rect"


@pytest.mark.parametrize("name", sorted(CHARTS))
def test_a_chart_given_no_limit_draws_no_clip(name: str) -> None:
    """The other half. A chart whose domain came from its own data covers that data, so there
    is nothing to cut -- and paying a wrapper element for it would rewrite every committed
    gallery page to say nothing.

    Named for what it asserts. The stronger claim -- that the *bytes* are unchanged -- is one
    the gallery already makes for every figure it holds
    (``test_the_committed_gallery_is_what_a_fresh_build_produces``), since not one of them
    passes a limit."""
    svg = CHARTS[name]().to_string()

    assert CLIP_CLASS not in svg
    assert svg.count("<svg") == 1, "a chart with no limit gained a nested viewport"


VARIANTS: dict[str, tuple[dict[str, object], ...]] = {
    "areaplot": ({}, {"hue": "group"}, {"hue": "group", "stacked": True}),
    "barplot": ({}, {"hue": "group"}, {"hue": "group", "stacked": True}, {"orient": "h", "xlim": DEFAULT_WINDOW}),
    "boxplot": ({}, {"hue": "group"}),
    "ecdfplot": ({}, {"hue": "group"}),
    "histplot": ({}, {"hue": "group"}),
    "kdeplot": ({}, {"hue": "group"}),
    "lineplot": ({}, {"hue": "group"}),
    "regplot": ({}, {"ci": None}, {"scatter": False}),
    "scatterplot": ({}, {"hue": "group"}, {"size": "weight"}),
    "violinplot": ({}, {"hue": "group"}, {"inner": None}),
}
"""Per chart, the option combinations that change *which marks exist* -- not how they look.

A defaults-only sweep leaves whole code paths unvisited, and an escaped mark on one of them is
invisible: reparenting one mark at a time to the document root, thirteen of the twenty-one
mutations survived the entire suite before this table existed -- every ``boxplot`` mark, all
three ``regplot`` marks, both ``violinplot`` inner marks, and ``areaplot``'s stacked band.

So: ``regplot`` without its band and without its points, ``violinplot`` without its inner box
and median tick, ``scatterplot`` with the size legend that ``_render_size_legend`` draws as
circles at the document root, stacked bands and bars, and ``hue=`` everywhere it is taken
(which is what puts a legend beside the marks). ``boxplot``'s outliers need no variant -- the
fixture draws one. Options that only restyle an existing mark (``interpolate=``, ``bins=``,
``mode=``, ``fill=``, ``complementary=``, a different ``ci=``) are deliberately absent: they
add no element for a clip to miss, and the widened fixture repeats its x values, which
``interpolate="cubic"`` refuses outright.

``barplot(orient="h")`` carries its own ``xlim=``: a horizontal bar's values run along x, so
that is the limit the chart applies and the one it clips on.
"""


def _spine_rect(root: ET.Element) -> tuple[float, float, float, float]:
    """``(left, top, right, bottom)`` of the plot area, read back from the two axis spines.

    ``render_x_axis`` draws its spine along the bottom from ``area.left`` to ``area.right`` and
    ``render_y_axis`` draws its own down the left from ``area.top`` to ``area.bottom``, so the
    union of their endpoints is the rect both were handed.
    """
    spines = [element for element in root.iter(f"{{{_SVG_NS}}}line") if "spine" in (element.get("class") or "").split()]
    assert len(spines) == 2, f"expected two spines to measure the plot area, found {len(spines)}"
    xs = [float(spine.get(key)) for spine in spines for key in ("x1", "x2")]
    ys = [float(spine.get(key)) for spine in spines for key in ("y1", "y2")]
    return min(xs), min(ys), max(xs), max(ys)


def _limited(name: str, options: dict[str, object]) -> dict[str, object]:
    """``options`` plus the limit that makes a clip, unless the variant brought its own."""
    if {"xlim", "ylim"} & set(options):
        return options
    return options | {"ylim": _window(name)}


def _root_marks(root: ET.Element) -> list[ET.Element]:
    return [element for element in root if "series-" in (element.get("class") or "")]


@pytest.mark.parametrize("name", sorted(CHARTS))
def test_every_mark_a_chart_draws_is_inside_the_clip(name: str) -> None:
    """The property the whole change is for, asserted directly rather than through a sample.

    A mark left at the document root is exactly the bug -- it is drawn past the plot area again
    -- but the root is also where the legend lives, and a legend swatch carries the same
    ``series-`` class as a mark. So the count is the test: ``render_legend`` writes one swatch
    and one label per entry, and ``scatterplot``'s size legend does the same, so the number of
    ``series-`` elements at the root equals the number of ``legend-text`` elements exactly when
    nothing but the legend is there. A chart with no legend must have none.
    """
    for options in VARIANTS[name]:
        root = ET.fromstring(CHARTS[name](**_limited(name, options)).to_string())
        labels = [element for element in root.iter() if "legend-text" in (element.get("class") or "")]

        assert len(_root_marks(root)) == len(labels), (
            f"{name}{options}: {len(_root_marks(root))} series elements at the root against "
            f"{len(labels)} legend entries -- a mark escaped the clip"
        )


@pytest.mark.parametrize("name", sorted(CHARTS))
def test_the_clip_holds_something_on_every_variant(name: str) -> None:
    """The other half of the count above, which a chart drawing *nothing* would also satisfy."""
    for options in VARIANTS[name]:
        root = ET.fromstring(CHARTS[name](**_limited(name, options)).to_string())
        clip = next(
            element for element in root.iter(f"{{{_SVG_NS}}}svg") if CLIP_CLASS in (element.get("class") or "").split()
        )

        assert [
            element for element in clip.iter() if "series-" in (element.get("class") or "")
        ], f"{name}{options}: the clip is empty"


def test_a_lone_chart_has_no_placed_panels() -> None:
    """``_svg_probe.placed_panels`` skips a clip by name as well as by position, and the
    position alone is enough *inside a composition* -- a clip is a grandchild there. A chart
    on its own is where the two differ: its clip is a direct child of the root, so without the
    name the probe would report a one-panel composition that is really one chart."""
    from _svg_probe import placed_panels

    lone = sp.lineplot(DATA, x="x", y="y", ylim=DEFAULT_WINDOW).to_string()

    assert CLIP_CLASS in lone, "this fixture is meant to carry a clip"
    assert placed_panels(lone) == []


def test_a_limit_a_chart_discards_draws_no_clip() -> None:
    """``barplot`` reads its value limit off the axis the values run along: ``xlim=`` when
    ``orient="h"``, ``ylim=`` otherwise. The other one names the *category* axis and is thrown
    away by ``apply_limit`` -- so clipping on it would wrap the bars in a viewport because of an
    argument that changed nothing, and the output would stop being byte-identical to the same
    call without it.

    Its own variant in ``VARIANTS`` passes the limit the chart uses, so it cannot see this. The
    predicate before the fix (``xlim is not None or ylim is not None``) survived all 3,828 tests.
    """
    horizontal = {"orient": "h"}
    for options, used, discarded in ((horizontal, "xlim", "ylim"), ({}, "ylim", "xlim")):
        plain = CHARTS["barplot"](**options).to_string()
        with_discarded = CHARTS["barplot"](**options, **{discarded: DEFAULT_WINDOW}).to_string()
        with_used = CHARTS["barplot"](**options, **{used: DEFAULT_WINDOW}).to_string()

        assert with_discarded == plain, f"{options}: {discarded}= is discarded but changed the output"
        assert CLIP_CLASS not in with_discarded, f"{options}: {discarded}= is discarded but drew a clip"
        assert CLIP_CLASS in with_used, f"{options}: {used}= is the limit this chart applies and drew no clip"
