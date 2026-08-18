from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import svgplot.chart.base as sp_chart_module
from svgplot._svg import SvgDocument
from svgplot.charts.bar import barplot
from svgplot.layout import row
from svgplot.output.markdown import MARKDOWN_SUFFIXES, _reject_blank_lines, save_markdown, to_markdown

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


def test_the_block_opens_with_a_bare_div_on_its_own_line() -> None:
    """A block-level tag alone on a line is what makes the whole thing a CommonMark HTML
    block, passed through verbatim. ``<div>`` rather than ``<svg>`` because
    Python-Markdown (MkDocs' default engine) has no ``svg`` in its block-level tag list
    and would treat a multi-line one as an inline paragraph -- inserting a ``<br/>`` and a
    paragraph break that lift the ``<style>`` element out of the SVG subtree."""
    lines = to_markdown(_document()).splitlines()

    assert lines[0] == "<div>"
    assert lines[1].startswith("<svg ")


def test_the_div_closes_after_the_svg() -> None:
    lines = to_markdown(_document()).splitlines()

    assert lines[lines.index("</svg>") + 1] == "</div>"


def test_exactly_one_blank_line_separates_the_svg_from_the_table() -> None:
    """The blank line is the boundary that *closes* the HTML block, so the table that
    follows is parsed as markdown rather than swallowed into the block."""
    lines = to_markdown(_document(), TABLE).splitlines()
    closing = lines.index("</div>")

    assert lines[closing + 1] == ""
    assert lines[closing + 2] == "| X | Y |"


def test_a_chart_without_a_table_is_still_markdown() -> None:
    """Not an error: markdown is a *format*, not a feature flag, and a typo'd field name
    is already caught at plot time.

    The trailing newline is asserted rather than stripped -- this repo enforces
    end-of-file newlines with a hook, so the files it *writes* should have one too."""
    assert to_markdown(_document()).endswith("</div>\n")


def test_an_empty_table_does_not_leave_trailing_blank_lines() -> None:
    """``render_table`` of an empty selection is still a string. Falling into the table
    branch with it would append a blank line and nothing else."""
    assert to_markdown(_document(), "") == to_markdown(_document())
    assert to_markdown(_document(), "   \n\n") == to_markdown(_document())


def test_the_table_is_not_followed_by_stray_blank_lines() -> None:
    assert to_markdown(_document(), TABLE + "\n\n\n").endswith("| a | 1.0 |\n")


# ---------------------------------------------------------------------------
# the blank-line guard
# ---------------------------------------------------------------------------


def test_the_guard_refuses_a_blank_line_and_names_the_cause() -> None:
    """``_svg`` now folds newlines out of text content, so no chart can reach this guard.
    It stays as the last line of defence -- a future ``add_text`` caller with a new
    multi-line tag, or a document assembled by hand -- and is exercised directly rather
    than through a chart, because going through a chart would now silently test nothing."""
    svg = '<svg xmlns="http://www.w3.org/2000/svg">\n  <text>first\n\nsecond</text>\n</svg>'

    with pytest.raises(ValueError, match="blank line"):
        _reject_blank_lines(svg)


def test_the_refusal_points_at_the_data_rather_than_the_serializer() -> None:
    """The fix is in the caller's data, so the message has to point there rather than
    reporting an opaque serialization failure."""
    svg = "<svg>\n  <text>a\n\nb</text>\n</svg>"

    with pytest.raises(ValueError, match="newline inside a label or title"):
        _reject_blank_lines(svg)


def test_the_refusal_reports_the_offending_line_number() -> None:
    """The line number is the whole diagnostic value of the message -- without it the
    caller is told only that a blank line exists somewhere in a few hundred lines."""
    svg = "<svg>\n  <text>a\n\nb</text>\n</svg>"

    with pytest.raises(ValueError, match=r"line 3\b"):
        _reject_blank_lines(svg)


def test_a_whitespace_only_line_counts_as_blank() -> None:
    """CommonMark ends an HTML block on a line containing only whitespace, not just on an
    empty one, so checking ``line == ""`` would let the break through."""
    with pytest.raises(ValueError, match="blank line"):
        _reject_blank_lines("<svg>\n  <text>a\n   \nb</text>\n</svg>")


def test_a_document_with_no_blank_line_passes_the_guard() -> None:
    """Otherwise the three tests above would pass against a guard that rejected
    everything."""
    assert _reject_blank_lines("<svg>\n  <text>a b</text>\n</svg>") is None


def test_a_label_with_newlines_no_longer_reaches_the_guard_at_all() -> None:
    """The real fix for the risk this guard was written around: the newlines are gone
    before serialization, so the markdown output is produced rather than refused."""
    document = _document()
    document.add_text(None, "first\n\nsecond", attrib={"x": "1", "y": "1"})

    assert ">first second<" in to_markdown(document)


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
    """Compared through the *compact* form as well: ``ET.indent`` is idempotent, so two
    pretty renders agree even when the indentation was applied to the stored tree."""
    document = _document()
    before_pretty = hashlib.sha256(document.to_string().encode()).hexdigest()
    before_compact = hashlib.sha256(document.to_string(pretty=False).encode()).hexdigest()

    to_markdown(document)

    assert hashlib.sha256(document.to_string().encode()).hexdigest() == before_pretty
    assert hashlib.sha256(document.to_string(pretty=False).encode()).hexdigest() == before_compact


# ---------------------------------------------------------------------------
# save() dispatch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("suffix", [*MARKDOWN_SUFFIXES, ".MD", ".Markdown"])
def test_save_routes_every_markdown_extension(tmp_path: Path, suffix: str) -> None:
    """A file extension's case is an accident of the filesystem, not an intent."""
    path = tmp_path / f"chart{suffix}"
    _chart().save(str(path))

    assert path.read_text(encoding="utf-8").startswith("<div>\n<svg ")


def test_save_markdown_writes_utf8(tmp_path: Path) -> None:
    path = tmp_path / "chart.md"
    save_markdown(_document(), "| — |", str(path))

    assert "—".encode() in path.read_bytes()


def test_save_markdown_pins_the_encoding_and_line_endings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Asserted on the *call*, not on the resulting bytes, because neither argument has an
    observable effect on this platform: ``os.linesep`` is already "\n" and the default
    encoding is already UTF-8. Both matter on Windows -- and ``newline`` matters for
    correctness, not tidiness: the default rewrites every "\n" to ``os.linesep``, so a
    label holding a CRLF passes ``_reject_blank_lines`` in memory and still lands CR +
    CRLF -- a real blank line -- on disk, reopening the injection this module refuses."""
    captured: dict[str, object] = {}
    original = Path.write_text

    def spy(self: Path, data: str, **kwargs: object) -> int:
        captured.update(kwargs)
        return original(self, data, encoding="utf-8")

    monkeypatch.setattr(Path, "write_text", spy)
    save_markdown(_document(), None, str(tmp_path / "chart.md"))

    assert captured["encoding"] == "utf-8"
    assert captured["newline"] == "\n"


def test_a_crlf_label_cannot_produce_a_blank_line_on_disk(tmp_path: Path) -> None:
    """The end-to-end companion to the check above, on platforms where it can be observed."""
    document = _document()
    document.add_text(None, "row1\r\nrow2", attrib={"x": "1", "y": "1"})
    path = tmp_path / "chart.md"
    save_markdown(document, None, str(path))

    raw = path.read_bytes()
    assert b"\r\n\r\n" not in raw
    assert b"\n\n" not in raw


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


@pytest.mark.parametrize("suffix", [*MARKDOWN_SUFFIXES, ".MD"])
def test_composition_supports_markdown_too(tmp_path: Path, suffix: str) -> None:
    """``Composition`` documents that it exposes the same serialization surface as
    ``Chart``; supporting markdown on only one of them would break that invariant."""
    path = tmp_path / f"composition{suffix}"
    composition = row([_chart(), _chart()])
    composition.save(str(path))

    assert path.read_text(encoding="utf-8") == composition.to_markdown()
    assert "<?xml" not in composition.to_markdown()


def test_composition_markdown_carries_no_table_yet() -> None:
    """Gathering the children's tables is a follow-up; the format still works without."""
    assert row([_chart(), _chart()]).to_markdown().endswith("</div>\n")


def test_composition_unknown_extension_lists_the_markdown_options(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"\.md"):
        row([_chart(), _chart()]).save(str(tmp_path / "composition.txt"))


# ---------------------------------------------------------------------------
# the _label_table hook
# ---------------------------------------------------------------------------


class _LabelledChart(sp_chart_module.Chart):
    """A chart that has a table, standing in for what issue #69 wires up.

    The hook returns ``None`` for every real chart today, so without a subclass the
    "with a table" branch of both output paths is unreachable and untested — the wiring
    would be a claim nobody checks.
    """

    def _label_table(self) -> str | None:
        return TABLE


def test_to_markdown_emits_the_hook_s_table() -> None:
    chart = _LabelledChart(_document())

    assert chart.to_markdown().splitlines()[-3:] == ["| X | Y |", "| --- | --- |", "| a | 1.0 |"]


def test_save_writes_the_hook_s_table_too(tmp_path: Path) -> None:
    """``save()`` builds its own arguments rather than calling ``to_markdown``, so the two
    paths can drift apart."""
    path = tmp_path / "chart.md"
    chart = _LabelledChart(_document())
    chart.save(str(path))

    assert path.read_text(encoding="utf-8") == chart.to_markdown()
    assert "| a | 1.0 |" in path.read_text(encoding="utf-8")
