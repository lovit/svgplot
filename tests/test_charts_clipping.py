"""What a narrowing ``xlim=``/``ylim=`` may draw, for every chart that takes one.

``apply_limit`` says a caller who asks for ``(0, 100)`` on data spanning 0..300 "means to clip
the view" (``chart/_domain.py``). Nothing clipped it. Every one of the ten charts below drew
its marks at whatever pixel the replaced domain mapped them to -- over the axis, through the
tick labels, off the canvas -- and each chart's own tests stayed green because none of them
asked where the ink landed. ``layout/facet.py`` had already recorded the symptom from the
other side: a bar 57.8px above the plot area "with nothing clipping it and no warning".

The two tests here are halves of one statement: with a limit, no mark outside the plot area;
without one, the same bytes as before any of this existed.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest

import svgplot as sp
from _svg_probe import CLIP_CLASS
from svgplot.charts._layout import MARGIN_WITH_LEGEND, MARGIN_WITHOUT_LEGEND, plot_area

_SVG_NS = "http://www.w3.org/2000/svg"

DATA = {
    "x": [1.0, 2.0, 3.0, 4.0],
    "y": [10.0, 20.0, 30.0, 40.0],
    "category": ["가", "나", "다", "라"],
    "group": ["a", "a", "b", "b"],
}

WINDOWS = {
    "ecdfplot": (0.1, 0.5),
    "histplot": (0.2, 0.8),
    "kdeplot": (0.005, 0.02),
}
"""Per-chart ``ylim=`` windows, where a chart's y axis is not the ``y`` column.

Everything else measures ``y`` (10..40) and takes ``(15, 25)``: inside the data on both sides,
so there is ink to lose above *and* below. ``ecdfplot``'s y is a proportion and ``kdeplot``'s a
density, and a window outside their range would leave the whole curve on one side of the clip
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
    "barplot": lambda **kwargs: sp.barplot(DATA, x="category", y="y", **kwargs),
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
    the plot area -- ``violinplot`` reached 1770px on a 600px canvas, ``areaplot`` 1330px."""
    svg = CHARTS[name](ylim=_window(name)).to_string()
    root = ET.fromstring(svg)
    clips = [element for element in root.iter(f"{{{_SVG_NS}}}svg") if CLIP_CLASS in (element.get("class") or "").split()]

    assert len(clips) == 1, f"{name}: expected exactly one clip, got {len(clips)}"
    top, bottom = float(clips[0].get("y")), float(clips[0].get("y")) + float(clips[0].get("height"))
    area = plot_area(800.0, 600.0, MARGIN_WITH_LEGEND if "legend-text" in svg else MARGIN_WITHOUT_LEGEND)
    assert (top, bottom) == (area.top, area.bottom), f"{name}: the clip is not the plot area"

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
def test_a_chart_given_no_limit_is_byte_identical(name: str) -> None:
    """The other half. A chart whose domain came from its own data covers that data, so there
    is nothing to cut -- and paying a wrapper element for it would rewrite every committed
    gallery page to say nothing. ``plot-clip`` appearing here at all is the failure."""
    svg = CHARTS[name]().to_string()

    assert CLIP_CLASS not in svg
    assert svg.count("<svg") == 1, "a chart with no limit gained a nested viewport"


@pytest.mark.parametrize("name", sorted(CHARTS))
def test_the_marks_are_inside_the_clip_and_the_legend_is_not(name: str) -> None:
    """A clip that swallowed the legend would hide it: the legend sits to the right of the plot
    area, which is precisely what the clip cuts away. Charts here are drawn with ``hue=`` so
    there is a legend to lose, and its swatch carries the same ``series-`` class as a mark --
    class alone cannot tell them apart, only where they sit."""
    import inspect

    if "hue" not in inspect.signature(getattr(sp, name)).parameters:
        pytest.skip(f"{name} draws one series and has no legend to lose")
    root = ET.fromstring(CHARTS[name](hue="group", ylim=_window(name)).to_string())
    clip = next(element for element in root.iter(f"{{{_SVG_NS}}}svg") if CLIP_CLASS in (element.get("class") or "").split())

    in_clip = [element for element in clip.iter() if "series-" in (element.get("class") or "")]
    at_root = [element for element in root if "series-" in (element.get("class") or "")]

    assert in_clip, f"{name}: the clip holds no marks"
    assert at_root, f"{name}: no legend swatch stayed outside the clip"
    assert all(
        element.tag in (f"{{{_SVG_NS}}}line", f"{{{_SVG_NS}}}rect") for element in at_root
    ), f"{name}: something other than a legend swatch was left outside the clip"


def test_a_lone_chart_has_no_placed_panels() -> None:
    """``_svg_probe.placed_panels`` skips a clip by name as well as by position, and the
    position alone is enough *inside a composition* -- a clip is a grandchild there. A chart
    on its own is where the two differ: its clip is a direct child of the root, so without the
    name the probe would report a one-panel composition that is really one chart."""
    from _svg_probe import placed_panels

    lone = sp.lineplot(DATA, x="x", y="y", ylim=DEFAULT_WINDOW).to_string()

    assert CLIP_CLASS in lone, "this fixture is meant to carry a clip"
    assert placed_panels(lone) == []
