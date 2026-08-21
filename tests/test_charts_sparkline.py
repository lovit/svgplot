from __future__ import annotations

import importlib
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

# ``gallery`` is repo-root source, not part of the installed package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gallery import interaction, page
from gallery.example import load
from gallery.interaction import resolve
from gallery.page import chart_page

from _svg_probe import style_rule
from svgplot.charts._layout import SPARKLINE_HEIGHT, SPARKLINE_WIDTH
from svgplot.charts.line import lineplot
from svgplot.charts.sparkline import sparkline
from svgplot.layout.grid import row
from svgplot.layout.sizing import apply_size

DATA = {"v": [1.0, 5.0, 2.0, 8.0, 3.0]}
SVG_NS = "{http://www.w3.org/2000/svg}"


def parse(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def elements(svg: str, tag: str) -> list[ET.Element]:
    """Every ``<tag>`` element in the document, by real XML tag.

    Parsed rather than string-matched on purpose: ``render_theme_style`` always emits
    CSS *rules* for ``.grid-line``/``.spine``/``.tick-label`` regardless of whether any
    such element exists, so a substring check would report chrome this chart never drew.
    """
    return list(parse(svg).iter(f"{SVG_NS}{tag}"))


def classes(svg: str) -> set[str]:
    """Every CSS class actually present on an element (not merely styled in <style>)."""
    return {name for element in parse(svg).iter() for name in (element.get("class") or "").split()}


# ---------------------------------------------------------------------------
# what a sparkline emits — and, more to the point, what it must not
# ---------------------------------------------------------------------------


def test_sparkline_emits_one_path_and_one_background_rect() -> None:
    svg = sparkline(DATA, "v").to_string()

    assert len(elements(svg, "path")) == 1
    rects = elements(svg, "rect")
    assert len(rects) == 1
    assert rects[0].get("class") == "plot-background"


@pytest.mark.parametrize("chrome_class", ["spine", "grid-line", "tick-line", "tick-label", "legend-text"])
def test_sparkline_draws_no_axis_or_legend_chrome(chrome_class: str) -> None:
    """The absence assertions are the substance of this chart: a sparkline that quietly
    grew an axis would still "render fine", so nothing else would catch it.

    Checked against classes present on elements, not against the raw SVG text — the
    <style> block names every one of these regardless of what was drawn.
    """
    assert chrome_class not in classes(sparkline(DATA, "v").to_string())


def test_sparkline_draws_no_line_or_text_elements_at_all() -> None:
    """Complements the per-class check above: catches axis/legend chrome that arrives
    under some *other* class name than the ones theme/css.py happens to style today.
    """
    svg = sparkline(DATA, "v").to_string()

    assert elements(svg, "line") == []
    # <title>/<desc> are accessibility markup added to every chart, so only <text>
    # (labels, tick labels, legend entries) is the chrome this chart must not draw.
    assert elements(svg, "text") == []


def test_sparkline_uses_its_own_canvas_size_not_the_chart_default() -> None:
    root = parse(sparkline(DATA, "v").to_string())

    assert root.get("width") == "120"
    assert root.get("height") == "24"
    assert (SPARKLINE_WIDTH, SPARKLINE_HEIGHT) == (120.0, 24.0)


def test_sparkline_canvas_size_is_overridable() -> None:
    root = parse(sparkline(DATA, "v", width=300.0, height=40.0).to_string())

    assert root.get("width") == "300"
    assert root.get("height") == "40"


# ---------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------


def _coords(svg: str) -> list[tuple[float, float]]:
    command = elements(svg, "path")[0].get("d") or ""
    parsed = []
    for token in command.replace("M ", "").split(" L "):
        x, y = token.strip().split(",")
        parsed.append((float(x), float(y)))
    return parsed


def test_sparkline_plots_one_vertex_per_row_spanning_the_canvas() -> None:
    coords = _coords(sparkline(DATA, "v").to_string())

    assert len(coords) == len(DATA["v"])
    xs = [x for x, _ in coords]
    assert xs == sorted(xs), "x must advance monotonically — a sparkline plots a sequence"
    assert xs[0] == pytest.approx(2.0)  # left inset
    assert xs[-1] == pytest.approx(SPARKLINE_WIDTH - 2.0)  # right inset


def test_sparkline_keeps_input_row_order_rather_than_sorting_by_value() -> None:
    """lineplot sorts by x; a sparkline has no x column, so reordering would
    misrepresent the sequence it exists to show."""
    coords = _coords(sparkline({"v": [3.0, 1.0, 2.0]}, "v").to_string())

    ys = [y for _, y in coords]
    # SVG y grows downward, so the largest value has the smallest y.
    assert ys[0] < ys[2] < ys[1]


def test_sparkline_maps_the_extremes_to_the_plot_area_edges() -> None:
    coords = _coords(sparkline(DATA, "v").to_string())

    ys = [y for _, y in coords]
    assert min(ys) == pytest.approx(2.0)  # max value -> top inset
    assert max(ys) == pytest.approx(SPARKLINE_HEIGHT - 2.0)  # min value -> bottom inset


def test_sparkline_places_a_single_point_at_the_left_edge() -> None:
    """A one-point series has no run to spread across; a degenerate index domain would
    otherwise resolve to the plot area's midpoint (see scales.LinearScale)."""
    coords = _coords(sparkline({"v": [7.0]}, "v").to_string())

    assert len(coords) == 1
    assert coords[0][0] == pytest.approx(2.0)


def test_sparkline_drops_rows_with_a_missing_value() -> None:
    coords = _coords(sparkline({"v": [1.0, None, 3.0]}, "v").to_string())

    assert len(coords) == 2


# ---------------------------------------------------------------------------
# composition and sizing
# ---------------------------------------------------------------------------


def test_sparkline_composes_into_a_row_with_its_classes_namespaced() -> None:
    """Composition rewrites every child's classes into a per-child namespace so two
    children can't restyle each other. A chart with a non-default canvas is the case
    most likely to be special-cased by mistake, so pin that it isn't.
    """
    composed = row([sparkline(DATA, "v"), lineplot({"x": [1, 2], "y": [1.0, 2.0]}, x="x", y="y")]).to_string()

    present = classes(composed)
    assert "c0-series-1" in present, "the sparkline's series class must be namespaced to child 0"
    assert "c1-series-1" in present, "the lineplot's series class must be namespaced to child 1"
    assert "series-1" not in present, "no un-namespaced class may survive composition"
    # Each child keeps its own <style>, rewritten to match its own namespace.
    styles = "".join(element.text or "" for element in parse(composed).iter(f"{SVG_NS}style"))
    assert ".c0-series-1 {" in styles
    assert ".c1-series-1 {" in styles


def test_sparkline_survives_responsive_sizing() -> None:
    chart = apply_size(sparkline(DATA, "v"), "responsive")
    root = parse(chart.to_string())

    assert root.get("viewBox") == "0 0 120 24"
    assert "svgplot-responsive" in (root.get("class") or "").split()


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


def test_sparkline_rejects_empty_data() -> None:
    with pytest.raises(ValueError, match="at least one row"):
        sparkline({"v": []}, "v")


def test_sparkline_rejects_data_with_no_usable_values() -> None:
    with pytest.raises(ValueError, match="no rows with a non-missing y value"):
        sparkline({"v": [None, None]}, "v")


def test_sparkline_rejects_an_unknown_column() -> None:
    with pytest.raises(KeyError, match="nope"):
        sparkline(DATA, "nope")


def test_sparkline_rejects_an_unknown_theme_preset() -> None:
    with pytest.raises(KeyError, match="unknown theme preset"):
        sparkline(DATA, "v", theme="not-a-preset")


# ---------------------------------------------------------------------------
# why this is the one gallery page that gets no interaction
# ---------------------------------------------------------------------------
#
# The page says so in prose, so the prose is run here. Each of these is a reason the page
# gives, and a reason nobody can check is a reason that quietly stops being true.


def _titled_marks(html: str) -> list[str]:
    """The tags of every element in ``html`` that has a ``<title>`` child and is not the root.

    Parsed rather than pattern-matched. The first version of this looked for ``"</title></"``,
    which never matches anything this package emits -- the serializer pretty-prints, so a
    titled mark is ``</title>\n  </text>``. Checked against ``docs/gallery/heatmap.html``,
    which really does carry one: the string form found 0, this finds it.
    """
    found = []
    for figure in re.findall(r"<svg\b.*?</svg>", html, re.S):
        root = ET.fromstring(figure)
        for parent in root.iter():
            if parent is root:
                continue
            if any(child.tag == f"{SVG_NS}title" for child in parent):
                found.append(parent.tag.removeprefix(SVG_NS))
    return found


def test_the_mark_tooltip_detector_sees_one_when_there_is_one() -> None:
    """The detector above is the whole of ``no mark tooltip``, so it gets its own case.

    A check that answers "none" whatever it is given is not evidence of none.
    """
    from svgplot.charts._tooltip import add_tooltip

    chart = sparkline(DATA, y="v")
    # Reaching past the public API on purpose: the point is to build the case the detector has
    # to see, and no chart offers a mark tooltip yet.
    document = chart._svg_document
    add_tooltip(document, next(node for node in document.root if node.tag.endswith("path")), "a value")

    assert _titled_marks(chart.to_string()) == ["path"]


def test_the_gallery_emitter_refuses_a_toggle_for_a_sparkline() -> None:
    """Not a judgement the page makes -- the machinery will not build one.

    A control needs a name and names come from the legend, and this chart draws none: one
    series, and its name is already in the sentence the picture sits in.
    """
    svg = sparkline(DATA, y="v").set_scope("svgplot-sparkline-1").to_string()

    with pytest.raises(ValueError, match="no legend entry"):
        resolve("svgplot-sparkline-1", "toggle", svg)


def test_the_sparkline_page_carries_no_control_no_hover_and_no_mark_tooltip() -> None:
    """The page opens by saying it has none of the three, and that is the sentence most likely
    to rot: sibling issues are putting exactly those on the other pages, one page at a time.

    The NOTE deliberately says nothing about *how many* of them have landed. An earlier version
    counted them, and the count was wrong within the day -- ``ecdfplot`` merged while this
    branch was open. A page that has to be edited whenever a sibling merges is a page that will
    be wrong between merges.

    Rendered here rather than read off ``docs/``, for ``test_gallery_interaction.py``'s reason
    -- reading the committed file measures whether it is stale, which the byte-diff already
    does, instead of measuring the generator.
    """
    html = chart_page(load(importlib.import_module("gallery.examples.sparkline"), "sparkline"))

    assert 'class="series-toggle"' not in html
    assert ":hover" not in html
    assert _titled_marks(html) == [], "a mark grew a <title>, which is the browser's own tooltip"


def test_the_control_row_is_taller_than_the_default_canvas() -> None:
    """The page argues from two CSS values, so both are read out of the CSS rather than typed
    into the assertion.

    The label's own rule, not ``CHROME`` as a whole: ``.interaction-note`` carries the same
    ``font-size: 0.9rem``, so a substring check over the whole block passes with the label's
    size deleted -- measured, and the same failure this file's ``stroke-width`` case was
    written to close.

    Only the line box is compared. An earlier version added the checkbox's ``0.75rem`` bottom
    margin on top, which is not how inline layout works: the checkbox is inline-level, so its
    margin box sits *inside* the line box rather than stacking below it. The line box alone is
    24.48px at a 16px root, which already clears the 24px canvas -- and no browser was run to
    get either number, so the claim is kept to the part that is arithmetic on the stylesheet.
    """
    # The toggle's own chrome. ``CHROME`` held it until ``focus`` arrived and the per-kind
    # blocks were split out of it; reading the whole of ``CHROME`` now finds no label rule at
    # all, which is a ``StopIteration`` rather than a wrong number -- loud, but it would have
    # been silent had the note carried a ``+ label`` selector.
    label_rule = next(line for line in interaction._CONTROL_CHROME[interaction.TOGGLE].splitlines() if "+ label {" in line)
    body_rule = page.STYLE[page.STYLE.index("body {") : page.STYLE.index("a {")]
    label_size = float(re.search(r"font-size: ([\d.]+)rem;", label_rule).group(1))
    line_height = float(re.search(r"line-height: ([\d.]+);", body_rule).group(1))

    assert label_size * line_height * 16 > SPARKLINE_HEIGHT


def test_the_line_is_two_pixels_of_a_twenty_four_pixel_picture() -> None:
    """Why there is no ``:hover`` either. The stroke is the whole hit target for the series --
    an unfilled path has no interior to catch a pointer -- and here it is 2px against a default
    canvas 24px tall.

    Compared as a whole rule, not by substring. ``"stroke-width: 2" in rule`` also passes on
    ``stroke-width: 25``, and this is not hypothetical: ``theme="print"`` really does emit
    ``2.5``, so the page names that preset rather than claiming one number for all of them.
    """
    assert style_rule(sparkline(DATA, y="v").to_string(), ".series-1") == (
        ".series-1 { stroke: #E69F00; fill: none; stroke-width: 2; opacity: 1; }"
    )
    assert style_rule(sparkline(DATA, y="v", theme="print").to_string(), ".series-1") == (
        ".series-1 { stroke: #E69F00; fill: none; stroke-width: 2.5; opacity: 1; }"
    )
    assert SPARKLINE_HEIGHT == 24.0


def test_one_path_per_series_is_why_a_tooltip_would_name_the_line_not_a_point() -> None:
    """A ``<title>`` belongs to an element, and this chart draws one element for the whole
    series -- so it could carry the series' name and never a single reading. Giving it point
    markers would change that, and would be changing the picture to suit the tooltip."""
    root = parse(sparkline({"v": [1.0, 5.0, 2.0, 8.0, 3.0, 9.0]}, y="v").to_string())

    assert len([node for node in root.iter() if node.tag == f"{SVG_NS}path"]) == 1
