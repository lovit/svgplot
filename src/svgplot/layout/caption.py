"""Composition-level captions and the Tabs-replacement heading-per-chart pattern
(docs/research/16-layout-vocabulary.md, "Tabs 대체 관용구" 기본안).

The per-chart heading half of that pattern lives in ``layout.grid`` (the
``titles=`` parameter), since headings are positioned as part of cell layout.
This module handles the composition-wide caption — the static stand-in for the
visual unity Bokeh got from a shared toolbar.
"""

from __future__ import annotations

from svgplot.chart.composition import CAPTION_HEIGHT, Composition, composition_document
from svgplot.charts._layout import format_coord

_CAPTION_CLASS = "composition-caption"
_CAPTION_LOCATIONS = ("above", "below")
_CAPTION_BASELINE_INSET = CAPTION_HEIGHT / 3


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
    always wins.

    Raises:
        ValueError: if ``location`` isn't ``"above"`` or ``"below"``, or if ``text``
            is empty/whitespace-only (an empty caption band is just dead space).
    """
    if location not in _CAPTION_LOCATIONS:
        raise ValueError(f"location must be one of {_CAPTION_LOCATIONS}, got {location!r}")
    if not text.strip():
        raise ValueError(f"caption text must not be empty: {text!r}")

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
    document.add_text(
        None,
        text,
        tag="text",
        attrib={"x": format_coord(width / 2), "y": format_coord(caption_y), "text-anchor": "middle"},
        classes=[_CAPTION_CLASS],
    )
    if not composition._title:
        composition.set_title(text)
    return composition
