"""Markdown export: inline SVG followed by an optional footnote table.

Written in the same register as ``output/svg.py`` -- document plus strings in, string out.
Assembling the table belongs to ``Chart``/``Composition``, not here.

Layout
======

The file is the pretty-printed SVG wrapped in a bare ``<div>``, one blank line, then the
table. That shape is load-bearing rather than cosmetic: a block-level tag alone on its own
line opens a CommonMark **HTML block**, which passes through verbatim and ends at the
first blank line -- exactly the boundary the table needs in front of it.

The ``<div>`` is why the wrapper exists rather than emitting ``<svg>`` directly. Under
CommonMark either works (``svg`` opens a type-7 block, ``div`` a type-6), but
Python-Markdown -- what MkDocs runs by default -- has no ``svg`` in its block-level tag
list, so a multi-line ``<svg>`` is treated as an *inline* HTML paragraph: it inserts a
``<br/>`` before the ``<style>`` line and splits the paragraph at ``</style>``. Both tags
break out of foreign content in the HTML parser, which lifts the ``<style>`` block --
every colour in the chart -- out of the ``<svg>`` subtree. Wrapping in ``<div>`` makes the
whole thing verbatim in both engines, and keeps the "ends at the first blank line"
contract this module's guard depends on.

A single file with both is the requirement, so neither an ``<img>`` reference nor a
sidecar ``.svg`` will do, and a ``data:`` URI would give up the hand-editability this
package exists for.

Renderer support
================

**GitHub strips inline SVG** from rendered markdown (its sanitizer removes the element
entirely), so a ``.md`` written here shows the table but not the chart on github.com. For
GitHub specifically, write the chart with ``save("x.svg")`` and reference it as an image
instead -- at the cost of the two-file split this format exists to avoid.

Verified to pass through verbatim under markdown-it-py (VS Code's preview, MyST/Sphinx)
and under Python-Markdown with MkDocs' default extensions.
"""

from __future__ import annotations

from pathlib import Path

from svgplot._svg import SvgDocument
from svgplot.output.svg import to_string

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
            feature flag, and a chart without labels is a perfectly good markdown file. A
            blank string is treated the same way, so an empty table cannot leave a
            trailing run of blank lines behind the chart.

    Raises:
        ValueError: if the serialized SVG contains a blank line -- see
            :func:`_reject_blank_lines`.
    """
    svg = to_string(document, pretty=True, declaration=False).rstrip("\n")
    _reject_blank_lines(svg)
    block = f"<div>\n{svg}\n</div>"
    if table is None or not table.strip():
        return f"{block}\n"
    return f"{block}\n\n{table.rstrip(chr(10))}\n"


def save_markdown(document: SvgDocument, table: str | None, path: str) -> None:
    """Write :func:`to_markdown`'s output to a file.

    ``path`` is a filesystem path chosen by the caller — this is a library function, not a
    web endpoint. Callers embedding user-supplied filenames (e.g. in a web service) are
    responsible for validating/resolving them.
    """
    # newline="\n" is not cosmetic: the default translates every "\n" to os.linesep, so on
    # Windows a label holding a CRLF would pass the in-memory guard above and still land a
    # real blank line on disk -- reopening the very injection this module refuses.
    Path(path).write_text(to_markdown(document, table), encoding="utf-8", newline="\n")
