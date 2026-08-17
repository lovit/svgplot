"""Footnote-style data table renderer (pygal ``render_table`` precedent, docs/research/17-static-hover-alternative.md (d)).

Security note (PR #23 security review): returns an HTML string. Every cell
value must be escaped (see svgplot._svg escape chokepoint) before being
embedded — this table is meant to sit next to markdown-embedded SVG, so
unescaped user data here is an XSS vector.
"""

from __future__ import annotations

from svgplot.labels.spec import LabelSpec


def render_table(data: object, spec: LabelSpec) -> str:
    """Render a LabelSpec against data as an HTML/markdown table."""
    raise NotImplementedError
