from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from svgplot._svg import SvgDocument
from svgplot.charts.bar import barplot
from svgplot.layout import row
from svgplot.output.markdown import MARKDOWN_SUFFIXES, save_markdown, to_markdown

DATA = {"x": ["a", "b", "c"], "y": [1.0, 2.0, 3.0]}
TABLE = "| X | Y |\n| --- | --- |\n| a | 1.0 |"


def _chart():
    return barplot(DATA, x="x", y="y")


def _document() -> SvgDocument:
    document = SvgDocument(width=120, height=80)
    document.add_node(None, "rect", attrib={"x": 0, "y": 0, "width": "120", "height": "80"}, classes=["plot-background"])
    return document


# ---------------------------------------------------------------------------
# document shape
# ---------------------------------------------------------------------------


def test_markdown_carries_no_xml_declaration() -> None:
    """A prolog renders as literal text mid-document, which is why ``to_string`` grew a
    ``declaration=`` switch rather than the caller stripping it."""
    assert "<?xml" not in to_markdown(_document())


def test_markdown_keeps_the_svg_indented() -> None:
    """Compact output can't be hand-edited, and hand-editability is the premise of the
    whole package -- so markdown drops the prolog but keeps the pretty printing."""
    body = to_markdown(_document())

    assert "\n  <rect" in body


def test_the_svg_opens_the_line_it_is_on() -> None:
    """``<svg ...>`` alone on a line is what makes the whole element a CommonMark type-7
    HTML block, passed through verbatim. Anything before it on that line would turn the
    block into a paragraph and the SVG source into visible text."""
    assert to_markdown(_document()).splitlines()[0].startswith("<svg ")


def test_exactly_one_blank_line_separates_the_svg_from_the_table() -> None:
    """The blank line is the boundary that *closes* the HTML block, so the table that
    follows is parsed as markdown rather than swallowed into the block."""
    lines = to_markdown(_document(), TABLE).splitlines()
    closing = lines.index("</svg>")

    assert lines[closing + 1] == ""
    assert lines[closing + 2] == "| X | Y |"


def test_a_chart_without_a_table_is_still_markdown() -> None:
    """Not an error: markdown is a *format*, not a feature flag, and a typo'd field name
    is already caught at plot time."""
    body = to_markdown(_document())

    assert body.startswith("<svg ")
    assert body.rstrip().endswith("</svg>")


def test_the_table_is_not_followed_by_stray_blank_lines() -> None:
    assert to_markdown(_document(), TABLE + "\n\n\n").endswith("| a | 1.0 |\n")


# ---------------------------------------------------------------------------
# the blank-line guard
# ---------------------------------------------------------------------------


def test_a_blank_line_inside_the_svg_is_refused() -> None:
    """The measured risk this format exists around. ``xml.etree`` escapes ``<`` and ``&``
    in a text node but passes newlines through, so a label containing a blank line ends
    the HTML block mid-document and the rest of the SVG is parsed as markdown."""
    document = _document()
    document.add_text(None, "first\n\nsecond", attrib={"x": "1", "y": "1"})

    with pytest.raises(ValueError, match="blank line"):
        to_markdown(document)


def test_the_refusal_names_the_cause() -> None:
    """The fix is in the caller's data, so the message has to point there rather than
    reporting an opaque serialization failure."""
    document = _document()
    document.add_text(None, "a\n\nb", attrib={"x": "1", "y": "1"})

    with pytest.raises(ValueError, match="newline inside a label or title"):
        to_markdown(document)


def test_a_whitespace_only_line_counts_as_blank() -> None:
    """CommonMark ends an HTML block on a line containing only whitespace, not just on an
    empty one, so checking ``line == ""`` would let the break through."""
    document = _document()
    document.add_text(None, "a\n   \nb", attrib={"x": "1", "y": "1"})

    with pytest.raises(ValueError, match="blank line"):
        to_markdown(document)


def test_a_single_newline_in_a_label_is_allowed() -> None:
    """One newline doesn't produce a blank line, so it doesn't break the block -- refusing
    it would reject legitimate multi-line labels."""
    document = _document()
    document.add_text(None, "first\nsecond", attrib={"x": "1", "y": "1"})

    assert "first\nsecond" in to_markdown(document)


# ---------------------------------------------------------------------------
# existing output is untouched
# ---------------------------------------------------------------------------


def test_the_default_serialization_is_byte_for_byte_unchanged() -> None:
    """``declaration=`` defaults to the old behaviour; the ``.svg`` path must not shift."""
    document = _document()

    assert document.to_string() == document.to_string(pretty=True, declaration=True)
    assert document.to_string().startswith('<?xml version="1.0" encoding="UTF-8"?>\n')


def test_declaration_false_changes_only_the_prolog() -> None:
    document = _document()

    with_prolog = document.to_string(pretty=True, declaration=True)
    without = document.to_string(pretty=True, declaration=False)

    assert with_prolog == '<?xml version="1.0" encoding="UTF-8"?>\n' + without


def test_declaration_is_moot_for_compact_output() -> None:
    """Compact output never emitted a prolog, so the flag must not start adding one."""
    document = _document()

    assert document.to_string(pretty=False, declaration=True) == document.to_string(pretty=False, declaration=False)


def test_serializing_for_markdown_does_not_mutate_the_document() -> None:
    document = _document()
    before = hashlib.sha256(document.to_string().encode()).hexdigest()

    to_markdown(document)

    assert hashlib.sha256(document.to_string().encode()).hexdigest() == before


# ---------------------------------------------------------------------------
# save() dispatch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("suffix", [*MARKDOWN_SUFFIXES, ".MD", ".Markdown"])
def test_save_routes_every_markdown_extension(tmp_path: Path, suffix: str) -> None:
    """A file extension's case is an accident of the filesystem, not an intent."""
    path = tmp_path / f"chart{suffix}"
    _chart().save(str(path))

    assert path.read_text(encoding="utf-8").startswith("<svg ")


def test_save_markdown_writes_utf8(tmp_path: Path) -> None:
    path = tmp_path / "chart.md"
    save_markdown(_document(), "| — |", str(path))

    assert "—" in path.read_text(encoding="utf-8")


def test_chart_to_markdown_matches_what_save_writes(tmp_path: Path) -> None:
    path = tmp_path / "chart.md"
    chart = _chart()
    chart.save(str(path))

    assert path.read_text(encoding="utf-8") == chart.to_markdown()


def test_an_unknown_extension_still_lists_the_markdown_options(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"\.md"):
        _chart().save(str(tmp_path / "chart.txt"))


# ---------------------------------------------------------------------------
# Composition parity
# ---------------------------------------------------------------------------


def test_composition_supports_markdown_too(tmp_path: Path) -> None:
    """``Composition`` documents that it exposes the same serialization surface as
    ``Chart``; supporting markdown on only one of them would break that invariant."""
    path = tmp_path / "composition.md"
    composition = row([_chart(), _chart()])
    composition.save(str(path))

    assert path.read_text(encoding="utf-8") == composition.to_markdown()
    assert "<?xml" not in composition.to_markdown()


def test_composition_markdown_carries_no_table_yet() -> None:
    """Gathering the children's tables is a follow-up; the format still works without."""
    assert row([_chart(), _chart()]).to_markdown().rstrip().endswith("</svg>")


def test_composition_unknown_extension_lists_the_markdown_options(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"\.md"):
        row([_chart(), _chart()]).save(str(tmp_path / "composition.txt"))
