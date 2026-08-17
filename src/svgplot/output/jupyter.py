"""Jupyter rich-display integration (``_repr_svg_``)."""

from __future__ import annotations

from svgplot._svg import SvgDocument
from svgplot.output.svg import to_string


def repr_svg(document: SvgDocument) -> str:
    """Return the SVG string Jupyter uses to render a Chart/Composition inline.

    Compact (``pretty=False``) since this is for inline display, not a
    hand-editable file — see ``SvgDocument.to_string``'s docstring.
    """
    return to_string(document, pretty=False)
