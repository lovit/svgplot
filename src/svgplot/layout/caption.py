"""Composition-level captions and the Tabs-replacement heading-per-chart pattern
(docs-research/16-layout-vocabulary.md, "Tabs 대체 관용구" 기본안).

The per-chart heading half of that pattern lives in ``layout.grid`` (the
``titles=`` parameter), since headings are positioned as part of cell layout.
This module handles the composition-wide caption — the static stand-in for the
visual unity Bokeh got from a shared toolbar.
"""

from __future__ import annotations

from svgplot._svg import SvgDocument
from svgplot.chart.composition import CAPTION_HEIGHT, Composition, composition_document, composition_title
from svgplot.charts._layout import format_coord

_CAPTION_CLASS = "composition-caption"
_CAPTION_LOCATIONS = ("above", "below")
_CAPTION_BASELINE_INSET = CAPTION_HEIGHT / 3


def _caption_node_kwargs(x: float, y: float) -> dict[str, object]:
    """The node arguments shared by the validation probe and the real write.

    Built in one place so the probe cannot quietly become weaker than the write it stands
    in for -- today only ``text`` carries caller data, but the moment a caption node grows
    a user-derived attribute, a probe that had been assembled separately would stop
    covering it and nothing would fail.
    """
    return {
        "tag": "text",
        "attrib": {"x": format_coord(x), "y": format_coord(y), "text-anchor": "middle"},
        "classes": [_CAPTION_CLASS],
    }


def _validate_caption_text(text: str) -> None:
    """Raise ``ValueError`` if ``text`` would be rejected as a caption node, without
    touching the real document -- checked on a throwaway one instead.

    ``text`` is probed exactly as given. Stripping it first would look tidier next to the
    emptiness check above and would silently reopen this function's own bug: ``\x0b``,
    ``\x0c`` and ``\x1c``-``\x1f`` are characters ``str.strip()`` removes *and* XML 1.0
    forbids, so a stripped probe accepts a caption the real write then rejects -- after the
    canvas has already grown.

    Every mutation below this point is unconditional, so a caption rejected *after* them
    left the canvas permanently taller with no caption in it, and a retry grew it again.
    ``accessibility._validate_accessibility_text`` solves the same problem the same way:
    ``SvgDocument``'s validation lives behind its public API rather than being exposed for
    direct reuse, because ``_svg.py`` is the escape chokepoint and this module is not.
    """
    scratch = SvgDocument()
    scratch.add_text(None, text, **_caption_node_kwargs(0.0, 0.0))


def add_caption(composition: Composition, text: str, location: str = "below") -> Composition:
    """Attach a shared caption/title to a Composition (replaces Bokeh's shared-toolbar unity cue).

    Grows the canvas by one caption band and writes ``text`` into it. With
    ``location="above"`` every existing child is shifted down to make room, so
    the caption never overlaps the charts.

    Mutates ``composition`` in place and returns it, matching
    :meth:`svgplot.chart.base.Chart.set_title`'s chaining convention.

    Also adopts ``text`` as the composition's accessible name unless one was already
    set explicitly — a caption *is* the figure's name, so announcing the generic
    default while a visible caption reads "Figure 3. Quarterly revenue" would be
    strictly worse. An explicit :meth:`~svgplot.chart.composition.Composition.set_title`
    always wins, whether it was called before or after this. Adding a *second* caption
    likewise leaves the name alone: both bands render, but the first caption stays the
    figure's name, since a later band is an addition to the figure rather than a
    correction of what it is called.

    Raises:
        ValueError: if ``location`` isn't ``"above"`` or ``"below"``, if ``text`` is
            empty/whitespace-only (an empty caption band is just dead space), or if
            ``text`` holds a character XML 1.0 forbids. A rejected caption leaves the
            composition exactly as it was.
    """
    if location not in _CAPTION_LOCATIONS:
        raise ValueError(f"location must be one of {_CAPTION_LOCATIONS}, got {location!r}")
    if not text.strip():
        raise ValueError(f"caption text must not be empty: {text!r}")
    _validate_caption_text(text)

    document = composition_document(composition)
    width, height = float(document.width), float(document.height)
    new_height = height + CAPTION_HEIGHT

    if location == "above":
        # Shift every already-placed child (nested <svg>) and heading (<text>) down.
        for element in list(document.root):
            if element.tag == "svg" or element.tag == "text":
                document.set_attribute(element, "y", format_coord(float(element.get("y", "0")) + CAPTION_HEIGHT))
        caption_y = CAPTION_HEIGHT - _CAPTION_BASELINE_INSET
    else:
        caption_y = new_height - _CAPTION_BASELINE_INSET

    document.height = new_height
    document.set_attribute(document.root, "height", format_coord(new_height))
    document.set_attribute(document.root, "viewBox", f"0 0 {format_coord(width)} {format_coord(new_height)}")
    document.add_text(None, text, **_caption_node_kwargs(width / 2, caption_y))
    if composition_title(composition) is None:
        composition.set_title(text)
    return composition
