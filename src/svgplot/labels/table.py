"""Footnote-style data table renderer (pygal ``render_table`` precedent, docs/research/17-static-hover-alternative.md (d))."""

from __future__ import annotations

from svgplot.labels.spec import LabelSpec


def render_table(data: object, spec: LabelSpec) -> str:
    """Render a LabelSpec against data as an HTML/markdown table."""
    raise NotImplementedError
