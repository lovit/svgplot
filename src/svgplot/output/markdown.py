"""Markdown export: inline SVG followed by an optional footnote table.

Written in the same register as ``output/svg.py`` -- document plus strings in, string out.
Assembling the table belongs to ``Chart``/``Composition``, not here.

Layout
======

The file is the pretty-printed SVG with its XML prolog dropped, one blank line, then the
table. That shape is load-bearing rather than cosmetic: a ``<svg ...>`` alone on its own
line opens a CommonMark **type-7 HTML block**, which passes through verbatim and ends at
the first blank line -- exactly the boundary the table needs in front of it.

A single file with both is the requirement, so neither an ``<img>`` reference nor a
sidecar ``.svg`` will do, and a ``data:`` URI would give up the hand-editability this
package exists for.

Renderer support
================

**GitHub strips inline SVG** from rendered markdown (its sanitizer removes the element
entirely), so a ``.md`` written here shows the table but not the chart on github.com.
MkDocs, Sphinx, VS Code's preview, and most static-site pipelines render it fine. For
GitHub specifically, write the chart with ``save("x.svg")`` and reference it as an image
instead -- at the cost of the two-file split this format exists to avoid.
"""

from __future__ import annotations

from pathlib import Path

from svgplot._svg import SvgDocument

MARKDOWN_SUFFIXES = (".md", ".markdown")
"""Extensions ``save()`` routes here. Compared against a lower-cased suffix, so ``.MD``
works too — a file extension's case is an accident of the filesystem, not an intent."""


def _reject_blank_lines(svg: str) -> None:
    """Refuse an SVG that would terminate its own HTML block early.

    A CommonMark type-7 HTML block ends at the first blank line. ``xml.etree`` escapes
    ``<`` and ``&`` in a text node but passes newlines through untouched, so a label
    containing a blank line -- legal input that every chart accepts today -- splits the
    block mid-document and the rest of the SVG source is then parsed as markdown.

    This is not XSS: angle brackets are already entity-escaped and ``_svg`` blocks
    ``script``/``on*``/``style``. It is a content/layout injection specific to this output
    path. Rewriting the text node here would put an edit outside ``_svg``'s escape
    chokepoint, so this refuses instead and names the cause.
    """
    for number, line in enumerate(svg.splitlines(), start=1):
        if not line.strip():
            raise ValueError(
                f"the serialized SVG contains a blank line (line {number}), which would end its markdown "
                "HTML block early and leave the rest of the SVG to be parsed as markdown — this comes from "
                "a newline inside a label or title, so strip it from the data before plotting"
            )


def to_markdown(document: SvgDocument, table: str | None = None) -> str:
    """Render ``document`` as inline markdown, optionally followed by ``table``.

    Args:
        document: the chart to inline.
        table: a pre-rendered table (see :func:`svgplot.labels.render_table`), or ``None``
            for the SVG alone. ``None`` is not an error: markdown is a *format*, not a
            feature flag, and a chart without labels is a perfectly good markdown file.

    Raises:
        ValueError: if the serialized SVG contains a blank line -- see
            :func:`_reject_blank_lines`.
    """
    svg = document.to_string(pretty=True, declaration=False).rstrip("\n")
    _reject_blank_lines(svg)
    if table is None:
        return f"{svg}\n"
    return f"{svg}\n\n{table.rstrip(chr(10))}\n"


def save_markdown(document: SvgDocument, table: str | None, path: str) -> None:
    """Write :func:`to_markdown`'s output to a file.

    ``path`` is a filesystem path chosen by the caller — this is a library function, not a
    web endpoint. Callers embedding user-supplied filenames (e.g. in a web service) are
    responsible for validating/resolving them.
    """
    Path(path).write_text(to_markdown(document, table), encoding="utf-8")
