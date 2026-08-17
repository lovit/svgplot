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
too). Markdown output additionally escapes the literal ``|`` column
separator so a value can't break the table structure.
"""

from __future__ import annotations

import html

from svgplot.data._columns import column_length, extract_columns
from svgplot.labels.spec import LabelSpec, render_value

TABLE_FORMATS = ("markdown", "html")


def _escape_markdown_cell(text: str) -> str:
    return html.escape(text, quote=True).replace("|", "\\|")


def render_table(data: object, spec: LabelSpec, format: str = "markdown") -> str:
    """Render ``spec`` applied to ``data`` as a footnote-style table (pygal's ``render_table`` precedent).

    Args:
        data: a pandas DataFrame (duck-typed), a dict of column name -> sequence,
            or a list of dict records (same shapes ``data.ingest_longform`` accepts).
        spec: which fields to include as columns, and how to format each.
        format: ``"markdown"`` (GitHub-flavored table) or ``"html"`` (a ``<table>`` element).

    Raises:
        ValueError: if ``format`` isn't one of :data:`TABLE_FORMATS`.
        KeyError: if a field named in ``spec`` isn't a column in ``data``.
    """
    if format not in TABLE_FORMATS:
        raise ValueError(f"unsupported table format: {format!r} (expected one of {TABLE_FORMATS})")

    columns = extract_columns(data)
    for field in spec:
        if field.field not in columns:
            raise KeyError(f"field not found in data: {field.field!r}")
    row_count = column_length(columns)

    headers = [field.label for field in spec]
    rows = [[render_value(field, columns[field.field][row_index]) for field in spec] for row_index in range(row_count)]

    if format == "html":
        return _render_html(headers, rows)
    return _render_markdown(headers, rows)


def _render_html(headers: list[str], rows: list[list[str]]) -> str:
    head_cells = "".join(f"<th>{html.escape(header, quote=True)}</th>" for header in headers)
    body_rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(cell, quote=True)}</td>" for cell in row) + "</tr>" for row in rows
    )
    return f"<table><thead><tr>{head_cells}</tr></thead><tbody>{body_rows}</tbody></table>"


def _render_markdown(headers: list[str], rows: list[list[str]]) -> str:
    header_line = "| " + " | ".join(_escape_markdown_cell(header) for header in headers) + " |"
    divider_line = "| " + " | ".join("---" for _ in headers) + " |"
    row_lines = ["| " + " | ".join(_escape_markdown_cell(cell) for cell in row) + " |" for row in rows]
    return "\n".join([header_line, divider_line, *row_lines])
