"""Tests for the low-level SVG document builder."""

from __future__ import annotations

import xml.etree.ElementTree as ET

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


def test_format_number_normalizes_uncoercible_input_to_value_error() -> None:
    with pytest.raises(ValueError, match="cannot format value"):
        _format_number(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="cannot format value"):
        _format_number("not-a-number")  # type: ignore[arg-type]


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

    with pytest.raises(ValueError, match=r"XML 1\.0"):
        doc.add_text(None, "label\x00evil")


def test_add_node_rejects_class_name_containing_whitespace() -> None:
    doc = SvgDocument()

    with pytest.raises(ValueError, match="class"):
        doc.add_node(None, "g", classes=["evil hidden"])


def test_add_node_rejects_class_name_with_control_characters() -> None:
    doc = SvgDocument()

    with pytest.raises(ValueError, match=r"XML 1\.0"):
        doc.add_node(None, "g", classes=["bar\x00evil"])


def test_add_node_rejects_tag_name_with_trailing_newline() -> None:
    """re.match + '$' allows a trailing newline; fullmatch is required to actually reject it."""
    doc = SvgDocument()

    with pytest.raises(ValueError, match="tag"):
        doc.add_node(None, "g\n")


def test_add_node_rejects_style_and_event_handler_attribute_names() -> None:
    doc = SvgDocument()

    with pytest.raises(ValueError, match="style/event handlers"):
        doc.add_node(None, "rect", attrib={"style": "fill:red"})
    with pytest.raises(ValueError, match="style/event handlers"):
        doc.add_node(None, "rect", attrib={"onclick": "alert(1)"})


def test_add_node_accepts_namespaced_attribute_name() -> None:
    doc = SvgDocument()
    doc.add_node(None, "use", attrib={"xlink:href": "#icon"})

    output = doc.to_string()

    assert 'xlink:href="#icon"' in output


def test_add_node_rejects_non_ascii_tag_name() -> None:
    """The name regex must stay ASCII-only or a non-well-formed document can slip through."""
    doc = SvgDocument()

    with pytest.raises(ValueError, match="tag"):
        doc.add_node(None, "a²")


def test_failed_validation_leaves_no_orphan_node_in_tree() -> None:
    doc = SvgDocument()
    group = doc.add_node(None, "g")

    with pytest.raises(ValueError):
        doc.add_node(group, "rect", attrib={"onclick": "alert(1)"})
    with pytest.raises(ValueError):
        doc.add_text(group, "bad\x00text")

    assert list(group) == []


def test_add_node_attribute_value_not_pre_formatted_is_passed_through_verbatim() -> None:
    """Documents the contract: add_node does not call _format_number for callers."""
    doc = SvgDocument()
    doc.add_node(None, "circle", attrib={"cx": 0.1 + 0.2})

    output = doc.to_string()

    assert 'cx="0.30000000000000004"' in output


def test_to_string_round_trips_through_xml_parser_and_utf8_encoding() -> None:
    doc = SvgDocument()
    doc.add_text(None, 'a\nb\tc"d<e&f')
    doc.add_node(None, "rect", classes=["series-1"], attrib={"data-label": 'quote" and <tag>'})

    for pretty in (True, False):
        output = doc.to_string(pretty=pretty)
        ET.fromstring(output)  # raises ParseError if not well-formed
        output.encode("utf-8")  # raises UnicodeEncodeError on stray surrogates


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


def test_add_text_accepts_custom_tag() -> None:
    doc = SvgDocument()
    doc.add_text(None, "My Chart", tag="title")

    output = doc.to_string()

    assert "<title>My Chart</title>" in output


def test_add_text_default_tag_is_still_text() -> None:
    doc = SvgDocument()
    doc.add_text(None, "label")

    assert "<text>label</text>" in doc.to_string()


def test_add_text_custom_tag_is_validated() -> None:
    doc = SvgDocument()

    with pytest.raises(ValueError, match="tag"):
        doc.add_text(None, "hi", tag="bad tag")


def test_set_attribute_sets_validated_attribute_on_existing_node() -> None:
    doc = SvgDocument()
    doc.set_attribute(doc.root, "aria-label", "My Chart")

    assert 'aria-label="My Chart"' in doc.to_string()


def test_set_attribute_escapes_value() -> None:
    doc = SvgDocument()
    doc.set_attribute(doc.root, "aria-label", 'quote" and <tag>')

    output = doc.to_string()

    assert "&quot;" in output
    assert "&lt;tag&gt;" in output


def test_set_attribute_rejects_invalid_attribute_name() -> None:
    doc = SvgDocument()

    with pytest.raises(ValueError, match="attribute"):
        doc.set_attribute(doc.root, "onclick", "alert(1)")


def test_set_attribute_rejects_control_characters_in_value() -> None:
    doc = SvgDocument()

    with pytest.raises(ValueError, match=r"XML 1\.0"):
        doc.set_attribute(doc.root, "aria-label", "bad\x00value")


def test_set_attribute_works_on_non_root_node() -> None:
    doc = SvgDocument()
    circle = doc.add_node(None, "circle")

    doc.set_attribute(circle, "aria-hidden", "true")

    assert 'aria-hidden="true"' in doc.to_string()


def test_set_attribute_overwrite_uses_latest_value() -> None:
    doc = SvgDocument()
    doc.set_attribute(doc.root, "aria-label", "First")
    doc.set_attribute(doc.root, "aria-label", "Second")

    output = doc.to_string()

    assert 'aria-label="Second"' in output
    assert "First" not in output


def test_set_attribute_class_accepts_space_separated_multiple_classes() -> None:
    """Unlike add_node's classes=[...] (a list of atomic entries), this is the final
    attribute value, so a space-separated string legitimately sets several classes.
    """
    doc = SvgDocument()
    node = doc.add_node(None, "g")

    doc.set_attribute(node, "class", "series-1 highlighted")

    assert 'class="series-1 highlighted"' in doc.to_string()


def test_set_attribute_class_rejects_empty_value() -> None:
    doc = SvgDocument()
    node = doc.add_node(None, "g")

    with pytest.raises(ValueError, match="class"):
        doc.set_attribute(node, "class", "")


def test_set_attribute_class_rejects_control_character_in_a_class_token() -> None:
    doc = SvgDocument()
    node = doc.add_node(None, "g")

    with pytest.raises(ValueError, match=r"XML 1\.0"):
        doc.set_attribute(node, "class", "a\x00b")


def test_add_text_rejects_script_tag() -> None:
    """ "script" must never be allowed here, unlike "style" (issue #12 added "style"
    to the allow-list — see this module's "Security note (issue #12)" — because it
    has a sanctioned, self-validating caller; "script" has no such caller and never
    should, since this package emits no JS.
    """
    doc = SvgDocument()

    with pytest.raises(ValueError, match="text-bearing tags"):
        doc.add_text(None, "fetch('//evil/')", tag="script")


def test_add_node_rejects_script_tag_directly() -> None:
    """Post-merge security review: add_text's allow-list alone isn't a structural
    guarantee — a caller could create a <script> node via add_node and set .text
    directly on the returned element, bypassing add_text entirely. add_node must
    reject "script" itself so the guarantee holds regardless of which method is used.
    """
    doc = SvgDocument()

    with pytest.raises(ValueError, match="script"):
        doc.add_node(None, "script")


@pytest.mark.parametrize("tag", ["text", "tspan", "title", "desc", "textPath", "style"])
def test_add_text_allows_every_text_bearing_tag(tag: str) -> None:
    doc = SvgDocument()

    doc.add_text(None, "hi", tag=tag)

    assert f"<{tag}>hi</{tag}>" in doc.to_string()
