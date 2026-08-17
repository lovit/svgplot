"""Accessibility defaults for rendered SVG charts.

Adds ``role="img"``/``aria-label`` and ``<title>``/``<desc>`` to every chart
root by default (not opt-in) — see docs/research/12-aesthetics.md §4 and
docs/research/10-feature-matrix.md A9. WCAG contrast checking (2차) belongs
in this same file when it's added.
"""

from __future__ import annotations

from svgplot._svg import SvgDocument


def add_accessibility(document: SvgDocument, title: str, desc: str | None = None) -> None:
    """Attach role/aria/title/desc to an SVG document's root node."""
    raise NotImplementedError
