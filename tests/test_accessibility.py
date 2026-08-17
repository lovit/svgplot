"""Tests for svgplot.accessibility."""

from __future__ import annotations

import pytest

from svgplot._svg import SvgDocument
from svgplot.accessibility import add_accessibility


def test_add_accessibility_sets_role_and_aria_label() -> None:
    document = SvgDocument()

    add_accessibility(document, title="Sales by Quarter")

    output = document.to_string()
    assert 'role="img"' in output
    assert 'aria-label="Sales by Quarter"' in output


def test_add_accessibility_adds_title_and_explicit_desc() -> None:
    document = SvgDocument()

    add_accessibility(document, title="Sales by Quarter", desc="Quarterly revenue in USD.")

    output = document.to_string()
    assert "<title>Sales by Quarter</title>" in output
    assert "<desc>Quarterly revenue in USD.</desc>" in output


def test_add_accessibility_generates_default_desc_when_omitted() -> None:
    document = SvgDocument()

    add_accessibility(document, title="Sales by Quarter")

    output = document.to_string()
    assert "<desc>" in output
    assert "Sales by Quarter" in output


def test_add_accessibility_escapes_title_used_in_multiple_places() -> None:
    document = SvgDocument()

    add_accessibility(document, title="<script>alert(1)</script>")

    output = document.to_string()
    assert "<script>alert(1)</script>" not in output
    assert "&lt;script&gt;" in output


def test_add_accessibility_does_not_disturb_existing_marks() -> None:
    document = SvgDocument()
    document.add_node(None, "circle", attrib={"cx": "50", "cy": "50", "r": "10"}, classes=["series-1"])

    add_accessibility(document, title="My Chart")

    output = document.to_string()
    assert "<circle" in output
    assert 'class="series-1"' in output
    assert 'role="img"' in output


@pytest.mark.parametrize("title", ["", "   "])
def test_add_accessibility_rejects_empty_title(title: str) -> None:
    document = SvgDocument()

    with pytest.raises(ValueError, match="empty"):
        add_accessibility(document, title=title)


def test_add_accessibility_rejected_call_leaves_document_untouched() -> None:
    """A rejected call must never leave role="img" set with no matching aria-label/
    title/desc — that's worse for accessibility than not calling this at all.
    """
    document = SvgDocument()

    with pytest.raises(ValueError):
        add_accessibility(document, title="Good Title", desc="bad\x00desc")

    output = document.to_string()
    assert "role=" not in output
    assert "aria-label=" not in output
    assert "<title>" not in output
    assert "<desc>" not in output


def test_add_accessibility_invalid_title_also_leaves_document_untouched() -> None:
    document = SvgDocument()

    with pytest.raises(ValueError):
        add_accessibility(document, title="bad\x00title")

    assert "role=" not in document.to_string()
