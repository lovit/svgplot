"""Tests for the low-level SVG document builder."""

from __future__ import annotations

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


def test_semantic_class_increments_per_prefix_not_random() -> None:
    doc = SvgDocument()

    assert doc.semantic_class("series") == "series-1"
    assert doc.semantic_class("series") == "series-2"
    assert doc.semantic_class("bar") == "bar-1"


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


def test_format_number_strips_floating_point_noise() -> None:
    assert _format_number(120.5) == "120.5"
    assert _format_number(30) == "30"
    assert _format_number(30.0) == "30"
    assert _format_number(0.1 + 0.2) == "0.3"
