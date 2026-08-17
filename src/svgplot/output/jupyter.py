"""Jupyter rich-display integration (``_repr_svg_``)."""

from __future__ import annotations


def repr_svg(document: object) -> str:
    """Return the SVG string Jupyter uses to render a Chart/Composition inline."""
    raise NotImplementedError
