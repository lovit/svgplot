"""Footnote-style data table renderer (pygal ``render_table`` precedent, docs/research/17-static-hover-alternative.md (d)).

Security note (PR #23 security review): returns an HTML string. Every cell
value must be escaped (see svgplot._svg escape chokepoint) before being
embedded — this table is meant to sit next to markdown-embedded SVG, so
unescaped user data here is an XSS vector.

``svgplot._svg``'s escape chokepoint is specific to XML/SVG serialization
(it leans on ``xml.etree.ElementTree``'s automatic escaping); a standalone
HTML/markdown table string isn't produced through that path, so this module
escapes independently via the stdlib's ``html.escape`` instead — every cell
value AND every spec-supplied display label goes through it, in both the
HTML and the markdown renderer (GitHub-flavored markdown still renders
inline HTML, so an unescaped ``<script>`` in a markdown cell is exploitable
too). Markdown output additionally neutralizes GFM table-structure syntax: a
literal backslash is doubled first (so it can't combine with characters this
function inserts later to form an unintended escape), a literal ``|`` column
separator is then backslash-escaped, and a literal newline (which would
otherwise terminate the row early and desynchronize the table) is collapsed
to a space — that order matters, see :func:`_escape_markdown_cell`.
"""

from __future__ import annotations

import html

from svgplot.data._columns import column_length, extract_columns
from svgplot.data._missing import is_missing
from svgplot.labels.spec import LabelField, LabelSpec, render_value

TABLE_FORMATS = ("markdown", "html")

MISSING_TEXT = "—"
"""What a chart-driven table shows for a cell the chart never consulted (an em dash, the
conventional "no value here" mark in printed tables). Only used when a caller opts in via
``render_table(missing=...)``."""


def _collapse_newlines(text: str) -> str:
    """Flatten a cell onto one line, for *both* output formats.

    A raw newline splits a GFM table row and desynchronises the table (round-2 security
    review). The HTML renderer needs the same treatment for a different reason: a blank
    line inside a cell ends the surrounding CommonMark HTML block, so the rest of the
    ``<table>`` markup spills into the document as markdown. Both tables are meant to sit
    beside markdown-embedded SVG, so neither can carry a line break through.
    """
    return text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")


def _escape_markdown_cell(text: str) -> str:
    # Order matters: double existing backslashes BEFORE inserting the "\|" escape below,
    # so a user-supplied "\" can never combine with our inserted "\" to change meaning.
    text = _collapse_newlines(text)
    text = text.replace("\\", "\\\\")
    return html.escape(text, quote=True).replace("|", "\\|")


def _escape_html_cell(text: str) -> str:
    return html.escape(_collapse_newlines(text), quote=True)


def render_table(data: object, spec: LabelSpec, format: str = "markdown", *, missing: str | None = None) -> str:
    """Render ``spec`` applied to ``data`` as a footnote-style table (pygal's ``render_table`` precedent).

    Args:
        data: a pandas DataFrame (duck-typed), a dict of column name -> sequence,
            or a list of dict records (same shapes ``data.ingest_longform`` accepts).
        spec: which fields to include as columns, and how to format each.
        format: ``"markdown"`` (GitHub-flavored table) or ``"html"`` (a ``<table>`` element).
        missing: what to show for a missing cell instead of raising. ``None`` -- the
            default -- keeps :func:`~svgplot.labels.spec.render_value`'s refusal to invent
            a rendering for a value that isn't there, which is the right behaviour when a
            caller hands this function a table's worth of data directly. Chart-driven
            tables pass :data:`MISSING_TEXT`, because they have already decided which rows
            to keep and a column the chart never consulted may legitimately have holes.

    Raises:
        ValueError: if ``format`` isn't one of :data:`TABLE_FORMATS`, or if ``missing``
            is neither a string nor ``None``.
        KeyError: if a field named in ``spec`` isn't a column in ``data``.
    """
    if format not in TABLE_FORMATS:
        raise ValueError(f"unsupported table format: {format!r} (expected one of {TABLE_FORMATS})")
    # Caught here rather than surfacing as an AttributeError from inside an escaper,
    # matching how ``format`` above is rejected.
    if missing is not None and not isinstance(missing, str):
        raise ValueError(f"missing must be a string or None, got {missing!r}")

    columns = extract_columns(data)
    for field in spec:
        if field.field not in columns:
            raise KeyError(f"field not found in data: {field.field!r}")
    row_count = column_length(columns)

    def cell(field: LabelField, value: object) -> str:
        # The substitute is produced *here*, upstream of both renderers, so it flows
        # through the same html.escape/markdown-neutralising path every other cell does.
        # Injecting it after escaping would make `missing=` an escaping bypass.
        if missing is not None and is_missing(value):
            return missing
        return render_value(field, value)

    headers = [field.label for field in spec]
    rows = [[cell(field, columns[field.field][row_index]) for field in spec] for row_index in range(row_count)]

    if format == "html":
        return _render_html(headers, rows)
    return _render_markdown(headers, rows)


def _render_html(headers: list[str], rows: list[list[str]]) -> str:
    head_cells = "".join(f"<th>{_escape_html_cell(header)}</th>" for header in headers)
    body_rows = "".join("<tr>" + "".join(f"<td>{_escape_html_cell(cell)}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head_cells}</tr></thead><tbody>{body_rows}</tbody></table>"


def _render_markdown(headers: list[str], rows: list[list[str]]) -> str:
    header_line = "| " + " | ".join(_escape_markdown_cell(header) for header in headers) + " |"
    divider_line = "| " + " | ".join("---" for _ in headers) + " |"
    row_lines = ["| " + " | ".join(_escape_markdown_cell(cell) for cell in row) + " |" for row in rows]
    return "\n".join([header_line, divider_line, *row_lines])
