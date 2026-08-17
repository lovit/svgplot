"""Accessibility defaults for rendered SVG charts.

Adds ``role="img"``/``aria-label`` and ``<title>``/``<desc>`` to every chart
root by default (not opt-in) — see docs/research/12-aesthetics.md §4 and
docs/research/10-feature-matrix.md A9. WCAG contrast checking (2차) belongs
in this same file when it's added.

Not yet wired into ``chart.base.Chart``'s render path — that requires
``Chart``'s real implementation (issue #4), which isn't merged into ``main``
yet at the time this module was written. Once it lands, the render path
should call ``add_accessibility(document, title=self._title or "Chart",
desc=...)`` before serialization.
"""

from __future__ import annotations

from svgplot._svg import SvgDocument


def add_accessibility(document: SvgDocument, title: str, desc: str | None = None) -> None:
    """Attach role/aria/title/desc to an SVG document's root node.

    ``role="img"`` and ``aria-label`` are set directly on the root ``<svg>`` —
    the primary, order-independent accessible-name mechanism for ARIA-aware
    assistive technology. ``<title>``/``<desc>`` child elements are also added
    (useful when the SVG is opened as a standalone file, or read by tools that
    don't consult ARIA attributes); this function doesn't try to make them the
    *first* children of the root, since ``aria-label`` alone is sufficient and
    order-independent for ARIA-aware assistive technology.

    ``title`` is required — callers (e.g. ``Chart``) are expected to supply a
    reasonable fallback (e.g. ``"Chart"``) when the user hasn't set one via
    ``set_title()``. ``desc`` defaults to a short generic sentence mentioning
    ``title`` when omitted.
    """
    resolved_desc = desc if desc is not None else f'A chart titled "{title}".'
    document.set_attribute(document.root, "role", "img")
    document.set_attribute(document.root, "aria-label", title)
    document.add_text(None, title, tag="title")
    document.add_text(None, resolved_desc, tag="desc")
