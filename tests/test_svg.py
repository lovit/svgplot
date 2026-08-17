"""Tests for the low-level SVG document builder."""

from __future__ import annotations

import pytest

from svgplot._svg import SvgDocument, _format_number


def test_add_node_and_text_appear_in_output() -> None:
    doc = SvgDocument(width=400, height=300)
    group = doc.add_node(None, "g", classes=["plot-area"])
    doc.add_node(group, "rect", attrib={"x": "10", "y": "20", "width": "5", "height": "8"}, classes=["bar", "series-1"])
    doc.add_text(group, "Hello", classes=["label"])

    output = doc.to_string()

    assert '<g class="plot-area">' in output
    assert 'class="bar series-1"' in output
    assert '<text class="label">Hello</text>' in output


def test_to_string_pretty_is_indented_and_multiline() -> None:
    doc = SvgDocument(width=100, height=100)
    group = doc.add_node(None, "g")
    doc.add_node(group, "circle")

    output = doc.to_string(pretty=True)

    lines = output.splitlines()
    assert len(lines) > 1
    assert any(line.startswith("  ") for line in lines)


def test_to_string_compact_is_single_line() -> None:
    doc = SvgDocument(width=100, height=100)
    group = doc.add_node(None, "g")
    doc.add_node(group, "circle")

    output = doc.to_string(pretty=False)

    assert "\n" not in output


def test_to_string_compact_stays_single_line_after_pretty_call() -> None:
    """ET.indent must not mutate the tree, or a later compact call inherits stale whitespace."""
    doc = SvgDocument(width=100, height=100)
    group = doc.add_node(None, "g")
    doc.add_node(group, "circle")

    doc.to_string(pretty=True)
    compact = doc.to_string(pretty=False)

    assert "\n" not in compact


def test_to_string_pretty_is_repeatable_and_reflects_later_additions() -> None:
    doc = SvgDocument(width=100, height=100)
    group = doc.add_node(None, "g")

    first = doc.to_string(pretty=True)
    doc.add_node(group, "circle")
    second = doc.to_string(pretty=True)

    assert "<circle" not in first
    assert "<circle" in second


def test_semantic_class_increments_per_prefix_not_random() -> None:
    doc = SvgDocument()

    assert doc.semantic_class("series") == "series-1"
    assert doc.semantic_class("bar") == "bar-1"
    assert doc.semantic_class("series") == "series-2"
    assert doc.semantic_class("bar") == "bar-2"


def test_root_uses_literal_coordinates_not_style_attribute() -> None:
    doc = SvgDocument(width=120.5, height=30)

    output = doc.to_string()

    assert 'width="120.5"' in output
    assert 'height="30"' in output
    assert 'viewBox="0 0 120.5 30"' in output
    assert "style=" not in output


def test_text_content_is_escaped_on_serialization() -> None:
    doc = SvgDocument()
    doc.add_text(None, "<script>alert(1)</script>")

    output = doc.to_string()

    assert "<script>" not in output
    assert "&lt;script&gt;" in output


def test_attribute_value_quote_cannot_break_out_of_attribute() -> None:
    doc = SvgDocument()
    doc.add_node(None, "rect", attrib={"data-label": '5" onload="alert(1)'})

    output = doc.to_string()

    assert 'onload="alert(1)"' not in output
    assert "&quot;" in output


def test_format_number_strips_floating_point_noise() -> None:
    assert _format_number(120.5) == "120.5"
    assert _format_number(30) == "30"
    assert _format_number(30.0) == "30"
    assert _format_number(0.1 + 0.2) == "0.3"


@pytest.mark.parametrize("bad_value", [float("inf"), float("-inf"), float("nan")])
def test_format_number_rejects_non_finite_values(bad_value: float) -> None:
    with pytest.raises(ValueError, match="non-finite"):
        _format_number(bad_value)


def test_add_node_rejects_invalid_tag_name() -> None:
    doc = SvgDocument()

    with pytest.raises(ValueError, match="tag"):
        doc.add_node(None, "g><script>alert(1)</script><g")


def test_add_node_rejects_invalid_attribute_name() -> None:
    doc = SvgDocument()

    with pytest.raises(ValueError, match="attribute"):
        doc.add_node(None, "rect", attrib={'x="1" onload="alert(1)': "1"})


def test_add_text_rejects_xml_invalid_control_characters() -> None:
    doc = SvgDocument()

    with pytest.raises(ValueError, match="XML 1.0"):
        doc.add_text(None, "label\x00evil")


def test_add_node_rejects_class_name_containing_whitespace() -> None:
    doc = SvgDocument()

    with pytest.raises(ValueError, match="class"):
        doc.add_node(None, "g", classes=["evil hidden"])


def test_add_node_classes_overrides_class_key_in_attrib() -> None:
    doc = SvgDocument()
    doc.add_node(None, "g", attrib={"class": "from-attrib"}, classes=["from-classes"])

    output = doc.to_string()

    assert 'class="from-classes"' in output
    assert "from-attrib" not in output


def test_zero_and_negative_dimensions_serialize_without_error() -> None:
    """This module doesn't validate chart-level semantics — that's a higher layer's job."""
    zero = SvgDocument(width=0, height=0)
    negative = SvgDocument(width=-10, height=5)

    assert 'viewBox="0 0 0 0"' in zero.to_string()
    assert 'viewBox="0 0 -10 5"' in negative.to_string()
