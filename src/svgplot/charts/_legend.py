"""Legend rendering shared by every chart type whose hue=/grouping produces
multiple series: one color swatch + label per entry.

A label longer than the room to the canvas edge used to run straight past it and out of the
``viewBox``, where nothing renders it -- 118px of room on the default canvas, which is about
18 Latin characters or **10 CJK** at ``legend_font_size``, by this module's own estimate. In a Korean-first package eleven
characters is an ordinary label. Labels are now shortened to fit (see
``charts/_textwidth``), with the full text kept in a ``<title>`` so the shortening costs
presentation rather than information.

Private/internal — not re-exported from ``svgplot.charts``.
"""

from __future__ import annotations

from svgplot._svg import SvgDocument
from svgplot.charts._layout import format_coord
from svgplot.charts._textwidth import needs_full_text, truncate_to_width

_SWATCH_WIDTH = 16.0
_LABEL_GAP = 6.0
_ROW_HEIGHT = 20.0
_TEXT_BASELINE_OFFSET = 4.0


_SWATCH_HEIGHT = 10.0


def render_legend(
    document: SvgDocument,
    entries: list[tuple[str, str]],
    *,
    x: float,
    y: float,
    mark_style: str = "stroke",
    font_size: float,
) -> float:
    """Draw a vertical legend starting at ``(x, y)``, one row per ``entries`` item,
    and return the y coordinate just past the last row.

    Returning the consumed height keeps row spacing owned by this module: a caller
    stacking something beneath the legend (e.g. ``charts.scatter``'s size legend)
    derives its offset from this value instead of re-deriving it from a copy of
    ``_ROW_HEIGHT``, which would silently overlap if that constant ever changed.

    Each entry is ``(label, css_class)`` — ``css_class`` is reused as-is (e.g. the
    same class a series' ``<path>`` already carries), so this function only
    positions a swatch + text per entry; it never chooses or emits any color
    itself — that's ``theme.css.render_theme_style``'s job, which already styles
    ``css_class`` via its ``<style>`` block. ``mark_style`` must match whatever was
    passed to ``render_theme_style`` for these same classes (``"stroke"``, the
    default, draws a ``<line>`` swatch matching a stroked mark like a line chart's
    path; ``"fill"`` draws a small ``<rect>`` swatch matching a filled mark like a
    bar/area/pie slice) — a mismatch doesn't error, but the swatch shape/CSS
    property pairing would look wrong (e.g. a ``<line>`` swatch has no visible
    color under a ``fill``-only CSS rule).

    The room a label has is read off ``document.width`` and ``x`` rather than hardcoded. 800
    is right for every chart today only because every one of them uses the default canvas, and
    all twelve would be wrong together the moment a chart could be given a size (#120). It is
    the same reason the returned height exists.

    A label estimated not to fit is shortened with an ellipsis, and its full text kept in a
    ``<title>`` child -- which both browsers and assistive technology read. The full text is
    also kept for a label merely *close* to the budget, because the width estimate can be
    wrong in the direction that says "this fits", and that is the case with no fallback.

    Raises:
            ValueError: if ``mark_style`` isn't ``"stroke"`` or ``"fill"``.
    """
    if mark_style not in ("stroke", "fill"):
        raise ValueError(f"mark_style must be 'stroke' or 'fill', got {mark_style!r}")
    for index, (label, css_class) in enumerate(entries):
        row_y = y + index * _ROW_HEIGHT
        if mark_style == "stroke":
            document.add_node(
                None,
                "line",
                attrib={
                    "x1": format_coord(x),
                    "y1": format_coord(row_y),
                    "x2": format_coord(x + _SWATCH_WIDTH),
                    "y2": format_coord(row_y),
                },
                classes=[css_class],
            )
        else:
            document.add_node(
                None,
                "rect",
                attrib={
                    "x": format_coord(x),
                    "y": format_coord(row_y - _SWATCH_HEIGHT / 2),
                    "width": format_coord(_SWATCH_WIDTH),
                    "height": format_coord(_SWATCH_HEIGHT),
                },
                classes=[css_class],
            )
        room = document.width - (text_x := x + _SWATCH_WIDTH + _LABEL_GAP)
        shown = truncate_to_width(label, font_size, room)
        text_node = document.add_text(
            None,
            shown,
            tag="text",
            attrib={"x": format_coord(text_x), "y": format_coord(row_y + _TEXT_BASELINE_OFFSET)},
            classes=["legend-text"],
        )
        if shown != label or needs_full_text(label, font_size, room):
            # Not only when something was cut. The width model can be wrong in the
            # direction that says "this fits" -- and that is the case with no fallback,
            # because the tail is outside the viewBox and nowhere in the file. Anything
            # close to the budget keeps its full text; short labels, which are most of
            # them, still get no <title> and the markup stays hand-editable.
            document.add_text(text_node, label, tag="title")
    return y + len(entries) * _ROW_HEIGHT
