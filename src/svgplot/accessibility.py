"""Accessibility defaults for rendered SVG charts.

Adds ``role="img"``/``aria-label`` and ``<title>``/``<desc>`` to every chart
root by default (not opt-in) — see docs-research/12-aesthetics.md §4 and
docs-research/10-feature-matrix.md A9. WCAG contrast checking (2차) belongs
in this same file when it's added.

Wired into ``chart.base.Chart``'s render path (issue #29): every serialization
(``to_string``/``save``/``_repr_svg_``) applies this to a *copy* of the chart's
document, so repeated renders never stack duplicate ``<title>``/``<desc>`` pairs
and a late ``set_title()`` still takes effect. ``chart.composition.Composition``
does the same on its own serialization paths (issue #55), but only on the *outer*
document: a composed figure needs one accessible name of its own, not one per
nested child, and children are nested from their raw pre-accessibility documents
precisely so this function is never applied per panel.
"""

from __future__ import annotations

from svgplot._svg import SvgDocument, validate_element_id


def add_accessibility(document: SvgDocument, title: str, desc: str | None = None, *, describedby: str | None = None) -> None:
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
    ``title`` when omitted; every chart type supplies its own (see
    ``charts/_describe.py``), so the fallback is what a hand-built document gets.

    ``describedby`` sets ``aria-describedby`` to that element id, for the case where
    the same information is also on the page as a data table (``info=``). **It is a
    reference into the host document, so it only resolves in an HTML context** where an
    element with that id is present — see ``chart.base.Chart.to_html_table``. In a
    standalone ``.svg`` file, or anywhere the id is absent, the reference is simply
    ignored and the ``<desc>`` below is what gets announced; that is why ``<desc>`` is
    still written in full rather than deferred to the table.

    Meant to be called once per document. Calling it again on the same
    document adds a second ``<title>``/``<desc>`` (ARIA readers still see only
    the latest ``aria-label``, since that's an attribute, not an appended
    element) — this isn't guarded against, since ``Chart`` is expected to call
    it exactly once per render.

    Raises:
        ValueError: if ``title`` is empty/whitespace-only (an empty
            ``aria-label``/``<title>`` is worse than none — assistive tech
            reads the ``role="img"`` with no usable name at all), or if
            ``title``/``desc`` contain characters XML 1.0 forbids, or if
            ``describedby`` is empty or contains whitespace (which would smuggle a
            second id into the reference list). Validated *before* touching
            ``document``, so a rejected call never leaves it with a
            ``role``/``aria-label`` but no matching ``<title>``/``<desc>``.
    """
    if not title.strip():
        raise ValueError(f"title must not be empty: {title!r}")
    if describedby is not None:
        validate_element_id(describedby, parameter="describedby")
    resolved_desc = desc if desc is not None else f'A chart titled "{title}".'
    _validate_accessibility_text(title, resolved_desc)

    document.set_attribute(document.root, "role", "img")
    document.set_attribute(document.root, "aria-label", title)
    if describedby is not None:
        document.set_attribute(document.root, "aria-describedby", describedby)
    document.add_text(None, title, tag="title")
    document.add_text(None, resolved_desc, tag="desc")


def _validate_accessibility_text(title: str, desc: str) -> None:
    """Raise ``ValueError`` if any of these would be rejected, without mutating the real
    document — checked on a throwaway one instead, since ``SvgDocument``'s validation
    lives behind its public API, not exposed for direct reuse (this module isn't the
    escape chokepoint; ``_svg.py`` is).

    ``describedby`` is **not** re-checked here: ``_svg.validate_element_id`` already ran,
    before this function touched anything, and it applies the stricter of the SVG and HTML
    rules. A second copy of that check on the scratch document would be a branch no input
    can take — which a mutation run duly proved by deleting it and killing nothing.
    """
    scratch = SvgDocument()
    scratch.set_attribute(scratch.root, "aria-label", title)
    scratch.add_text(None, title, tag="title")
    scratch.add_text(None, desc, tag="desc")
