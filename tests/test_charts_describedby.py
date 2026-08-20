"""Linking the ``info=`` table to the chart with ``aria-describedby`` (issue #118).

The research note this issue quotes names pygal's weakness exactly: a ``render_table``
that exists but is not connected to the chart for assistive technology. These tests are
about that connection actually being there -- and, just as much, about it *not* being
claimed where it cannot hold.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import svgplot as sp
from svgplot.labels.spec import LabelSpec
from svgplot.labels.table import render_table

DATA = {"day": [1.0, 2.0, 3.0], "sales": [1200.0, 3400.0, 2500.0], "note": ["a", "b", "c"]}
SPEC = [("Day", "@day{0.0}"), ("Sales", "@sales{0,0}")]
PARSED_SPEC = LabelSpec.parse(SPEC)


def _chart(**kwargs: object) -> sp.Chart:
    return sp.lineplot(DATA, x="day", y="sales", **kwargs)


def _describedby(svg: str) -> str | None:
    """The ``aria-describedby`` of the **root ``<svg>``**, or ``None``.

    Read off the parsed root rather than found anywhere in the string. Assistive
    technology resolves the attribute from the element carrying ``role="img"`` — nowhere
    else — so a helper that searched the whole document would keep passing if a regression
    moved the attribute onto a child, and all 29 tests here would go on asserting nothing.
    A reviewer demonstrated exactly that by attaching it to a stray ``<g>``.

    Markdown output is not a bare SVG, so the SVG block is extracted first; the point of
    the assertion there is that the attribute is absent, and finding it *anywhere* in that
    file would be a failure either way.
    """
    if not svg.lstrip().startswith(("<?xml", "<svg")):
        match = re.search(r"<svg\b.*?</svg>", svg, re.S)
        if match is None:
            return None
        svg = match.group()
    return ET.fromstring(svg).get("aria-describedby")


def test_a_chart_with_info_points_at_its_table() -> None:
    assert _describedby(_chart(info=SPEC).to_string()) == sp.Chart.DEFAULT_TABLE_ID


def test_a_chart_without_info_points_at_nothing() -> None:
    """There is no table, so a reference would resolve to nothing -- which assistive tech
    reads as "no description", silently losing the ``<desc>`` that is there."""
    assert _describedby(_chart().to_string()) is None
    assert _chart().table_id is None


def test_the_html_table_carries_the_id_the_svg_names() -> None:
    """The two halves have to agree, or the link is decorative."""
    chart = _chart(info=SPEC)

    assert chart.table_id is not None
    assert f'<table id="{chart.table_id}">' in chart.to_html_table()
    assert _describedby(chart.to_string()) == chart.table_id


def test_the_html_table_holds_the_same_rows_the_chart_drew() -> None:
    """A description that points at a *different* dataset is worse than none."""
    table = _chart(info=SPEC).to_html_table()

    assert "<th>Day</th><th>Sales</th>" in table
    assert "<td>1.0</td><td>1,200</td>" in table
    assert table.count("<tr>") == 4  # one header row plus three data rows


def test_there_is_no_html_table_without_info() -> None:
    assert _chart().to_html_table() is None


def test_two_charts_on_one_page_can_be_given_distinct_ids() -> None:
    """Duplicate ids make ``aria-describedby`` resolve to whichever came first, so the
    second chart would be described by the first chart's data."""
    first = _chart(info=SPEC).set_table_id("sales-table")
    second = _chart(info=SPEC).set_table_id("returns-table")

    assert _describedby(first.to_string()) == "sales-table"
    assert _describedby(second.to_string()) == "returns-table"
    assert '<table id="returns-table">' in second.to_html_table()


def test_set_table_id_chains() -> None:
    chart = _chart(info=SPEC)
    assert chart.set_table_id("x") is chart


@pytest.mark.parametrize("bad", ["", "two ids", "trailing ", "\ttab", "line\nbreak"])
def test_an_id_that_would_smuggle_a_second_reference_is_refused(bad: str) -> None:
    """``aria-describedby`` is a space-separated *list*, so whitespace in an id silently
    turns one reference into two."""
    with pytest.raises(ValueError, match="table_id"):
        _chart(info=SPEC).set_table_id(bad)


@pytest.mark.parametrize(
    "bad", ["id\x00x", "id\ud800x", "id\uffffx", "id\x0ex"], ids=["nul", "surrogate", "noncharacter", "so"]
)
def test_an_id_xml_forbids_is_refused_at_the_setter_not_at_render_time(bad: str) -> None:
    """These pass a whitespace-only check and then break *later*, differently in each
    output: ``to_html_table()`` emits an id that is not well-formed XML (and, for a lone
    surrogate, cannot be written to a UTF-8 file at all), while ``to_string()`` raises —
    at render time, far from the call that caused it. One rule, the stricter one, applied
    at the setter."""
    with pytest.raises(ValueError, match="not allowed in XML 1.0"):
        _chart(info=SPEC).set_table_id(bad)


def test_the_two_halves_agree_on_which_ids_are_usable() -> None:
    """The SVG attribute and the HTML table are written by different code down different
    paths. An id either reaches both or neither -- a table published under an id the SVG
    would refuse is a reference that can never resolve."""
    for candidate in ("ok-id", "id\x00x", "two ids", ""):
        chart = _chart(info=SPEC)
        try:
            chart.set_table_id(candidate)
        except ValueError:
            with pytest.raises(ValueError):
                render_table(DATA, PARSED_SPEC, format="html", table_id=candidate)
            continue
        assert f'<table id="{candidate}">' in chart.to_html_table()
        assert _describedby(chart.to_string()) == candidate


def test_a_rejected_id_leaves_the_previous_one_in_place() -> None:
    chart = _chart(info=SPEC).set_table_id("good")
    with pytest.raises(ValueError):
        chart.set_table_id("bad id")

    assert _describedby(chart.to_string()) == "good"
    assert '<table id="good">' in chart.to_html_table()


def test_an_id_is_escaped_into_the_table_rather_than_closing_the_attribute() -> None:
    chart = _chart(info=SPEC).set_table_id('a"><script>alert(1)</script>')

    table = chart.to_html_table()
    assert "<script>" not in table
    assert "&quot;&gt;&lt;script&gt;" in table


def test_the_svg_attribute_is_escaped_too() -> None:
    output = _chart(info=SPEC).set_table_id('a"b').to_string()

    assert 'aria-describedby="a&quot;b"' in output


# --- where the reference is deliberately absent -------------------------------------------


def test_markdown_output_makes_no_claim_it_cannot_keep() -> None:
    """``.md`` renders a GitHub-flavored table, which is rows of pipes with no element to
    carry an id. Emitting the attribute anyway would point at nothing in the one output
    format that actually puts both halves in one file."""
    markdown = _chart(info=SPEC).to_markdown()

    assert _describedby(markdown) is None
    assert "| Day | Sales |" in markdown


def test_saving_markdown_matches_to_markdown(tmp_path: Path) -> None:
    path = tmp_path / "chart.md"
    _chart(info=SPEC).save(str(path))

    assert path.read_text(encoding="utf-8") == _chart(info=SPEC).to_markdown()
    assert "aria-describedby" not in path.read_text(encoding="utf-8")


def test_saving_svg_keeps_the_reference(tmp_path: Path) -> None:
    path = tmp_path / "chart.svg"
    _chart(info=SPEC).save(str(path))

    assert _describedby(path.read_text(encoding="utf-8")) == sp.Chart.DEFAULT_TABLE_ID


def test_the_jupyter_repr_makes_no_claim_either() -> None:
    """The hook returns the SVG alone into a cell with no table beside it."""
    assert _describedby(_chart(info=SPEC)._repr_svg_()) is None


def test_a_composition_does_not_inherit_a_child_s_reference() -> None:
    """Children are nested from their raw pre-accessibility documents, so a composed
    figure announces one name of its own -- and must not carry a dangling id from a panel.
    """
    composed = sp.row([_chart(info=SPEC), _chart(info=SPEC)])

    assert _describedby(composed.to_string()) is None


# --- render_table's half ------------------------------------------------------------------


def test_render_table_puts_the_id_on_the_table_element() -> None:
    assert render_table(DATA, PARSED_SPEC, format="html", table_id="t").startswith('<table id="t">')


def test_render_table_leaves_the_element_bare_without_an_id() -> None:
    assert render_table(DATA, PARSED_SPEC, format="html").startswith("<table><thead>")


def test_render_table_refuses_an_id_it_has_nowhere_to_put() -> None:
    """Dropping it silently would leave the caller with a reference to an id that never
    got written."""
    with pytest.raises(ValueError, match="format='html'"):
        render_table(DATA, PARSED_SPEC, format="markdown", table_id="t")


@pytest.mark.parametrize("bad", ["", "two ids", "\ttab"])
def test_render_table_refuses_an_unusable_id(bad: str) -> None:
    with pytest.raises(ValueError, match="table_id"):
        render_table(DATA, PARSED_SPEC, format="html", table_id=bad)


# --- add_accessibility's half -------------------------------------------------------------


def test_add_accessibility_refuses_a_whitespace_id_before_touching_the_document() -> None:
    from svgplot._svg import SvgDocument
    from svgplot.accessibility import add_accessibility

    document = SvgDocument()
    with pytest.raises(ValueError, match="describedby"):
        add_accessibility(document, title="Chart", describedby="a b")

    assert document.root.get("role") is None
    assert document.root.get("aria-label") is None


def test_add_accessibility_refuses_an_xml_forbidden_id_before_touching_the_document() -> None:
    """``\\S+`` matches ``"\\x00"`` happily; ``set_attribute`` is what refuses it, and by
    then ``role``/``aria-label`` would already be written."""
    from svgplot._svg import SvgDocument
    from svgplot.accessibility import add_accessibility

    document = SvgDocument()
    with pytest.raises(ValueError, match="not allowed in XML 1.0"):
        add_accessibility(document, title="Chart", describedby="a\x00b")

    assert document.root.get("role") is None
    assert "<desc>" not in document.to_string()


def test_add_accessibility_writes_no_attribute_when_no_id_is_given() -> None:
    from svgplot._svg import SvgDocument
    from svgplot.accessibility import add_accessibility

    document = SvgDocument()
    add_accessibility(document, title="Chart")

    assert document.root.get("aria-describedby") is None


def test_an_unusable_id_is_reported_even_when_the_format_is_also_wrong() -> None:
    """The two checks run in a deliberate order and nothing pinned it. A caller who passed a
    markdown format *and* an id with a space in it should hear about the id — that is the
    harder mistake to see, and swapping the order sends them to fix the easy one first and
    then hit the other. The two existing cases pair markdown with a *valid* id and html with
    an invalid one, so neither crosses the two."""
    with pytest.raises(ValueError, match="table_id must be a non-empty id with no whitespace"):
        render_table(DATA, PARSED_SPEC, format="markdown", table_id="a b")
