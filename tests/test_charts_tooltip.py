"""``<title>`` on a mark: what it guarantees, and what it refuses.

Five places already emitted one before this module existed -- three tick-label sites in
``_axes.py``, one in ``_legend.py``, one in ``treemap.py`` -- each with its own copy of the
call and its own copy of the reasoning. The rules here are the ones any of the five could have
broken without the other four noticing.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest

from _svg_probe import every_tag, tags
from svgplot._svg import SvgDocument
from svgplot.charts._tooltip import add_tooltip
from svgplot.charts.bar import barplot
from svgplot.charts.kde import kdeplot
from svgplot.charts.treemap import treemap


def _mark() -> tuple[SvgDocument, ET.Element]:
    document = SvgDocument(width=100.0, height=100.0)
    return document, document.add_node(None, "rect", attrib={"x": "0"}, classes=["series-1"])


def test_a_tooltip_is_the_marks_first_child() -> None:
    """Both the browser tooltip and the accessible name are defined in terms of the element's
    *first* ``<title>``. Every call site today adds one to a mark with no other children, where
    first and last are the same thing -- which is why nobody would notice the day one of them
    stopped being true."""
    document, mark = _mark()
    document.add_text(mark, "under", tag="text")

    add_tooltip(document, mark, "the tooltip")

    assert [child.tag for child in mark] == ["title", "text"]


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("", id="empty"),
        pytest.param("   ", id="spaces"),
        pytest.param("\t", id="tab"),
        pytest.param("\u00a0", id="no-break-space"),
        pytest.param("\u200b", id="zero-width-space"),
        pytest.param("\u2060", id="word-joiner"),
    ],
)
def test_text_that_draws_nothing_gets_no_title_at_all(text: str) -> None:
    """An empty ``<title>`` gives the mark an empty *accessible name*, which is worse than
    having none: assistive technology stops falling back to anything else. Before this module
    all five call sites emitted exactly that.

    Skipped rather than refused -- see :func:`test_a_label_that_draws_nothing_does_not_kill_the_chart`.

    ``str.strip()`` was the first rule and stops one character short: it catches U+00A0, a
    *space*, and passes U+200B, which draws exactly as much. There is no principle separating
    them.
    """
    document, mark = _mark()

    assert add_tooltip(document, mark, text) is None
    assert list(mark) == []


def test_a_label_that_draws_nothing_does_not_kill_the_chart() -> None:
    """The reason the rule above skips instead of raising.

    Everything reaching ``add_tooltip`` is a label out of somebody's file, and all five call
    sites hand over the *whole* label. A category named with a single tab is an ordinary thing
    to find in a CSV, and ``needs_full_text`` sends any unmeasured script straight down this
    path -- so one tab is enough, no 40-character contrivance needed.

    Measured on ``origin/main``: this rendered, and emitted ``<title>\t</title>`` -- the empty
    accessible name. An earlier version of this branch raised instead, which was worse than
    either.
    """
    svg = barplot({"c": ["\t", "b"], "v": [1.0, 2.0]}, x="c", y="v").to_string()

    assert "<title>\t</title>" not in svg
    assert svg.count("<title>") == 1, "only the chart's own title should be left"


def test_a_second_tooltip_on_one_mark_is_refused() -> None:
    """Only the first ``<title>`` is used, so a second is markup that renders, validates and
    says nothing. Reachable the moment a chart both shortens a label and describes a value on
    the same node."""
    document, mark = _mark()
    add_tooltip(document, mark, "first")

    with pytest.raises(ValueError, match="only the first is used"):
        add_tooltip(document, mark, "second")


def test_a_title_that_is_not_the_first_child_still_counts_as_one() -> None:
    """The check reads *every* child, and only this reaches that.

    Narrowing it to ``node[0].tag`` survived the whole suite, because the other case always
    puts the first ``<title>`` at index 0 through this same function. What the wider form is
    for is a ``<title>`` that arrived another way -- ``add_text(..., tag="title")`` directly,
    which ``accessibility.py`` still does -- and landed behind another child.
    """
    document, mark = _mark()
    document.add_text(mark, "under", tag="text")
    document.add_text(mark, "smuggled", tag="title")

    assert [child.tag for child in mark] == ["text", "title"], "the fixture stopped being the not-first case"
    with pytest.raises(ValueError, match="only the first is used"):
        add_tooltip(document, mark, "second")


def test_a_tooltip_survives_serialization_as_text_not_markup() -> None:
    """The content is escaped on the way out, so a label containing markup is a label rather
    than a hole in the document."""
    document, mark = _mark()
    add_tooltip(document, mark, "R&D <b>")

    assert "<title>R&amp;D &lt;b&gt;</title>" in document.to_string()


def test_a_mark_carrying_a_tooltip_is_still_found_by_the_probe() -> None:
    """The reason ``test_charts_ecdf/kde/scatter`` moved onto ``_svg_probe`` in this issue.

    A ``<rect …/>`` becomes ``<rect …>…</rect>`` the moment it gains a ``<title>``, and the
    ``/>``-only patterns those three modules used simply stopped seeing it. Asserted on the
    same document with and without the tooltip, so it is the tooltip being tested and not the
    probe's opinion of one particular chart.
    """
    plain, _ = _mark()
    tipped, tipped_mark = _mark()
    add_tooltip(tipped, tipped_mark, "a value")
    plain_svg, tipped_svg = plain.to_string(), tipped.to_string()

    # The premise: the tooltip is what changed the tag's shape.
    assert '<rect x="0" class="series-1" />' in plain_svg
    assert '<rect x="0" class="series-1" />' not in tipped_svg

    # The pattern the three modules used, spelled out rather than named, because the point is
    # what it does to a mark that grew a child.
    assert re.findall(r"<rect\b[^>]*/>", plain_svg)
    assert not re.findall(r"<rect\b[^>]*/>", tipped_svg)

    # The probe sees both.
    assert len(tags(plain_svg, "rect", "series-1")) == 1
    assert len(tags(tipped_svg, "rect", "series-1")) == 1
    assert len(every_tag(tipped_svg, "rect")) == len(every_tag(plain_svg, "rect"))


def test_the_existing_callers_still_emit_what_they_did() -> None:
    """The migration had to be invisible, and it touched all three kinds of caller.

    ``treemap`` shortens a tile label it cannot fit; ``_legend`` does the same for a long
    group name; ``_axes`` for a long tick label. Checked here rather than only by the gallery
    byte-diff, which fires for any output change at all and so can never say which one moved.
    """
    long_name = "온라인 채널 " * 6
    tiles = treemap({"이름": [long_name, "나"], "값": [9.0, 1.0]}, labels="이름", values="값").to_string()
    legend = kdeplot({"v": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0], "g": [long_name] * 3 + ["나"] * 3}, x="v", hue="g").to_string()
    ticks = barplot({"c": [long_name, "나"], "v": [1.0, 2.0]}, x="c", y="v").to_string()

    for source, svg in (("treemap tile", tiles), ("legend row", legend), ("tick label", ticks)):
        assert "…" in svg, f"the {source} fixture stopped being the shortened case"
        assert f"<title>{long_name}</title>" in svg, f"the {source} lost its full text"
