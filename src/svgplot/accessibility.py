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

    Meant to be called once per document. Calling it again on the same
    document adds a second ``<title>``/``<desc>`` (ARIA readers still see only
    the latest ``aria-label``, since that's an attribute, not an appended
    element) — this isn't guarded against, since ``Chart`` is expected to call
    it exactly once per render.

    Raises:
        ValueError: if ``title`` is empty/whitespace-only (an empty
            ``aria-label``/``<title>`` is worse than none — assistive tech
            reads the ``role="img"`` with no usable name at all), or if
            ``title``/``desc`` contain characters XML 1.0 forbids. Validated
            *before* touching ``document``, so a rejected call never leaves it
            with a ``role``/``aria-label`` but no matching ``<title>``/``<desc>``.
    """
    if not title.strip():
        raise ValueError(f"title must not be empty: {title!r}")
    resolved_desc = desc if desc is not None else f'A chart titled "{title}".'
    _validate_accessibility_text(title, resolved_desc)

    document.set_attribute(document.root, "role", "img")
    document.set_attribute(document.root, "aria-label", title)
    document.add_text(None, title, tag="title")
    document.add_text(None, resolved_desc, tag="desc")


def _validate_accessibility_text(title: str, desc: str) -> None:
    """Raise ``ValueError`` if ``title``/``desc`` would be rejected, without
    mutating the real document — checked on a throwaway one instead, since
    ``SvgDocument``'s validation lives behind its public API, not exposed for
    direct reuse (this module isn't the escape chokepoint; ``_svg.py`` is).
    """
    scratch = SvgDocument()
    scratch.set_attribute(scratch.root, "aria-label", title)
    scratch.add_text(None, title, tag="title")
    scratch.add_text(None, desc, tag="desc")
