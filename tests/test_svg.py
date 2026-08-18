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


@pytest.mark.parametrize("tag", ["SCRIPT", "Script", "sCrIpT", "svg:script", "svg:SCRIPT"])
def test_add_node_rejects_script_tag_regardless_of_case_or_namespace(tag: str) -> None:
    """Round-2 security review: the first fix only checked `tag in _BLOCKED_TAGS`
    with an exact-match, case-sensitive comparison — "SCRIPT"/"svg:script" slipped
    through. That matters here specifically because this package's actual use case
    is inline embedding in markdown/HTML, where an HTML tokenizer lowercases tag
    names before it ever cares about XML case-sensitivity — a "SCRIPT" that a strict
    XML parser would treat as a distinct, harmless tag becomes a live <script>
    element the moment the same markup is parsed as HTML.
    """
    doc = SvgDocument()

    # match="not allowed", not "script": the error message preserves tag's original
    # case/namespace (e.g. "'SCRIPT'"), only the *comparison* is normalized.
    with pytest.raises(ValueError, match="not allowed"):
        doc.add_node(None, tag)


@pytest.mark.parametrize("tag", ["text", "tspan", "title", "desc", "textPath", "style"])
def test_add_text_allows_every_text_bearing_tag(tag: str) -> None:
    doc = SvgDocument()

    doc.add_text(None, "hi", tag=tag)

    assert f"<{tag}>hi</{tag}>" in doc.to_string()


# ---------------------------------------------------------------------------
# newlines in text content
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a\n\nb", "a b"),
        ("a\x85b", "a b"),
        ("a\u2028\u2029b", "a b"),
        ("a\n\x85\u2028b", "a b"),
        ("a\nb", "a b"),
        ("a\r\n\r\nb", "a b"),
        ("a\rb", "a b"),
        ("a\n\n\n\n\nb", "a b"),  # one space per run, not one per newline
        ("\na", " a"),
        ("a\n", "a "),
    ],
)
def test_a_newline_run_in_text_content_becomes_one_space(raw: str, expected: str) -> None:
    """A blank line inside a text node ends the SVG's markdown HTML block at that point and
    leaves the rest of its own source to be parsed as prose. No renderer draws a newline in
    a text node as a line break anyway, so folding costs nothing visible."""
    doc = SvgDocument()

    doc.add_text(None, raw, tag="text")

    assert f"<text>{expected}</text>" in doc.to_string()


def test_the_folded_set_matches_what_splitlines_calls_a_line_ending() -> None:
    """The two definitions have to be the same set. ``output/markdown``'s blank-line guard
    counts lines with ``splitlines``, so folding a narrower set leaves a label that passes
    the fold and then has its own chart refused when it is saved as markdown."""
    doc = SvgDocument()

    for character in "\r\n\x85\u2028\u2029":
        assert len(f"a{character}b".splitlines()) == 2, f"{character!r} is not a line ending"
    doc.add_text(None, "a\r\n\x85\u2028\u2029b", tag="text")

    assert "<text>a b</text>" in doc.to_string()


@pytest.mark.parametrize("raw", ["a  b", "a\tb", "a \t b", "  a  "])
def test_only_line_endings_are_folded_not_whitespace_in_general(raw: str) -> None:
    """Widening the pattern to ``\\s+`` would also collapse runs of spaces and tabs, which
    is data the caller wrote and nothing in the markdown problem asks to be touched. The
    fold exists to stop a *line* from ending, not to normalise spacing."""
    doc = SvgDocument()

    doc.add_text(None, raw, tag="text")

    assert f"<text>{raw}</text>" in doc.to_string()


def test_a_style_block_keeps_its_line_breaks() -> None:
    """One CSS rule per line is what makes a nine-line hand edit possible, and it is the
    one text-bearing tag whose content this package writes itself rather than accepting
    from a caller."""
    doc = SvgDocument()

    doc.add_text(None, ".a { fill: red; }\n.b { fill: blue; }", tag="style")

    assert ".a { fill: red; }\n.b { fill: blue; }" in doc.to_string()


def test_the_style_exemption_can_still_produce_a_blank_line_if_a_caller_supplies_one() -> None:
    """The exemption is safe only because rule text never contains one -- no sanctioned
    ``<style>`` producer joins an empty rule. This records that obligation rather than
    pretending the exemption is unconditional: the assertion below is that the hole is
    real, not that it is closed."""
    doc = SvgDocument()

    doc.add_text(None, ".a { fill: red; }\n\n.b { fill: blue; }", tag="style")

    assert "\n\n" in doc.to_string()


@pytest.mark.parametrize("bad", ["a\x0b\nb", "a\n\x0cb", "\n\x00\n", "a\r\x1fb"])
def test_folding_never_launders_an_xml_forbidden_character(bad: str) -> None:
    """Neither order can change the *verdict* -- every folded character is legal XML, and
    the fold inserts a space rather than deleting, so it can neither remove a forbidden
    character nor join two into a new one. The orders are not fully interchangeable though:
    validating first is what makes the error quote the string the caller actually passed
    (``'a\\n\\x00\\nb'``) rather than the folded one (``'a \\x00 b'``), which is pinned
    below."""
    doc = SvgDocument()

    with pytest.raises(ValueError, match="not allowed in XML 1.0"):
        doc.add_text(None, bad)


def test_the_rejection_message_quotes_what_the_caller_passed() -> None:
    """Folding before validating would report ``'a \\x00 b'`` -- a string the caller never
    wrote, sending them looking for a space that is not in their data."""
    doc = SvgDocument()

    with pytest.raises(ValueError, match=r"'a\\n\\x00\\nb'"):
        doc.add_text(None, "a\n\x00\nb")


def test_a_text_node_of_only_newlines_does_not_vanish() -> None:
    """Folding to the empty string would leave ``<text/>``, which is a different element
    from one holding a space and would silently drop a (pathological) label."""
    doc = SvgDocument()

    doc.add_text(None, "\n\n\n", tag="text")

    assert "<text> </text>" in doc.to_string()


@pytest.mark.parametrize("raw", ["a\n\nb", "a\r\rb", "a\x85\x85b", "a\u2028\u2029b"])
def test_attribute_values_are_folded_too(raw: str) -> None:
    """``xml.etree`` escapes ``\r`` and ``\n`` in an attribute value, so those never took a
    line of their own -- but it says nothing about NEL or the Unicode separators, which
    reach the file literally and do. Assuming the escaping covered all of them is what let
    an ``aria-label`` carrying one still split the document."""
    doc = SvgDocument()

    doc.add_node(None, "rect", attrib={"data-note": raw})
    output = doc.to_string()

    assert 'data-note="a b"' in output
    assert not any(line.strip() == "" for line in output.splitlines())


def test_a_title_reads_the_same_in_both_places_it_is_written() -> None:
    """A title reaches ``aria-label`` (an attribute) and ``<title>`` (text content). Folding
    only one of them left the two disagreeing about what the caller wrote."""
    doc = SvgDocument()
    doc.set_attribute(doc.root, "aria-label", "a\n\nb")
    doc.add_text(None, "a\n\nb", tag="title")
    output = doc.to_string()

    assert 'aria-label="a b"' in output
    assert "<title>a b</title>" in output
