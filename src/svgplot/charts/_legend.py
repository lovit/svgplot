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

import math

from svgplot._svg import SvgDocument
from svgplot.charts._layout import corner_radius_attr, format_coord
from svgplot.charts._textwidth import needs_full_text, truncate_to_width
from svgplot.charts._tooltip import add_tooltip

_SWATCH_WIDTH = 16.0
_LABEL_GAP = 6.0
_ROW_HEIGHT = 20.0
_TEXT_BASELINE_OFFSET = 4.0


_SWATCH_HEIGHT = 10.0


_SHORTENING_FLOOR_EMS = 2.4
"""What the legend gutter is checked against — the room below which shortening stops helping.

Not a font measurement of its own. ``charts/_textwidth.py`` owns that, and it is a *measured*
model: each character is charged the worst advance of its Unicode class in Arial, verified
against the font's ``hmtx`` table. An earlier version of this module carried its own estimate
of 0.55 em per character on the premise that "a label's real width is unknowable here", which
is no longer true and was never conservative — 0.55 sits below a digit's own 0.556, so six
digits cost more than it charged.

The floor is a floor rather than a full label because a label that does not fit is **not** a
failure: ``render_legend`` shortens it with an ellipsis and keeps the full text in a
``<title>`` that assistive technology reads. What a gutter has to guarantee is that
shortening still leaves something, which is the same 2.4 em ``charts/_axes.py`` uses for the
same decision.
"""


def minimum_legend_text_width(font_size: float) -> float:
    """The narrowest gutter a legend label can be shortened into and still say anything."""
    return _SHORTENING_FLOOR_EMS * font_size


def legend_ink_height(rows: int) -> float:
    """How far below ``y`` a legend of ``rows`` rows actually puts ink.

    Not ``rows * _ROW_HEIGHT``. That is the space the legend *claims* — what
    :func:`render_legend` returns so a caller can stack under it — and it includes the last
    row's own bottom padding, which nothing is drawn in. Guarding on the claimed space refuses
    legends that fit: measured on ``origin/main``, a 29-entry legend on an 800x600 canvas puts
    its lowest ink at y=594 and renders correctly, while the claim-space rule would have
    rejected it. Thirty entries reach y=614 and really do overflow.

    The allowance below the last baseline is the same ``_TEXT_BASELINE_OFFSET`` used above it:
    the offset centres the row's text, and a descender reaches about as far below the baseline
    as the centring lifted it.
    """
    return max(rows - 1, 0) * _ROW_HEIGHT + 2 * _TEXT_BASELINE_OFFSET


def size_legend_ink_height(radii: list[float], row_padding: float, baseline_offset: float) -> float:
    """The same measurement for a size legend, whose rows are as tall as their own markers.

    Two differences from :func:`legend_ink_height`, and both come from the rows not being a
    fixed height. The padding between rows is counted ``n - 1`` times rather than ``n``, for
    the same reason as above -- the last row's padding has nothing drawn in it. And the last
    row's own extent is whichever reaches lower, the bottom of its circle or the descender
    under its label: a small marker with a big number beside it is limited by the text, a big
    marker by the circle.
    """
    if not radii:
        return 0.0
    above = sum(2 * radius + row_padding for radius in radii[:-1])
    last = radii[-1]
    return above + max(2 * last, last + baseline_offset + 2 * _TEXT_BASELINE_OFFSET)


def require_room(document: SvgDocument, y: float, needed: float, *, what: str) -> None:
    """Refuse to start drawing ``needed`` pixels of legend at ``y`` on a shorter canvas.

    ``needed`` is ink, not claimed space — see :func:`legend_ink_height`. A second legend
    stacked below the first starts at the *claimed* end of it, so it is checked from there
    and against its own ink. That pairing is what catches ``scatterplot(hue=, size=)``, where
    each legend on its own looks fine: measured at 400x180 with both guards removed, three
    hue groups fit (lowest ink y=175) and the fourth is the first to overflow, by 15px, with
    every further group adding 20px — 75px at seven, and unbounded after that.

    An earlier version of this paragraph said 46px, which no number of groups produces. The
    figures above were measured by rendering with the guards disabled and reading the lowest
    ink out of the document.
    """
    if y + needed > document.height:
        raise ValueError(
            f"{what} needs {format_coord(needed)}px below y={format_coord(y)}, "
            f"but the canvas is only {format_coord(document.height)}px tall; "
            f"use a taller canvas or fewer groups"
        )


def legend_text_room(gutter: float) -> float:
    """Pixels left for a legend label's glyphs, given the gutter between the plot area's
    right edge and the canvas edge."""
    return gutter - _SWATCH_WIDTH - _LABEL_GAP


_SWATCH_RADIUS_FRACTION = 0.25
"""How much of the swatch's short side its corner radius may take.

Half the short side is a full ellipse -- that is where SVG's own clamp lands -- so a quarter is
the midpoint of "visibly rounded" and "no longer a rectangle". The swatch has to keep reading as
the same *kind* of shape as the mark it names; matching the mark's radius in pixels does the
opposite once the two differ in size by an order of magnitude, which is what they do (#265).
"""


def _swatch_radius(corner_radius: float) -> float:
    """The mark's corner radius, expressed on a swatch.

    Proportional rather than absolute: a theme asking for a barely-rounded bar should get a
    barely-rounded swatch, and one asking for a lozenge should get one as far as a swatch can.
    The cap keeps an extreme radius from turning the swatch into an ellipse while the bars it
    names are still rectangles.

    Zero and negative need no guard -- ``min`` passes them through and
    :func:`~svgplot.charts._layout.corner_radius_attr` answers ``None`` for anything undrawable.
    ``inf`` does: ``min(inf, 2.5)`` is ``2.5``, a perfectly drawable number, so the cap turned a
    radius the mark itself refuses into one the swatch accepts -- a square bar beside a rounded
    swatch, which is this defect wearing its own fix inside out. Reachable only past ``Theme``'s
    constructor, and pinned there.
    """
    if not math.isfinite(corner_radius):
        return corner_radius
    return min(corner_radius, _SWATCH_HEIGHT * _SWATCH_RADIUS_FRACTION)


def render_legend(
    document: SvgDocument,
    entries: list[tuple[str, str]],
    *,
    x: float,
    y: float,
    mark_style: str = "stroke",
    font_size: float,
    corner_radius: float = 0.0,
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

    The rows must fit on the canvas. They always did at 800 x 600 for any legend this
    package produces, so nothing checked — but a caller-chosen canvas (issue #120) can be
    shorter than the legend is tall, and a legend that runs off the bottom is not a smaller
    legend, it is a missing one. ``heatmap``'s nine colour levels need 210 px of the 180 px
    a minimum-size canvas has, which is how this was found. Refused rather than clipped, for
    ``gaugeplot``'s reason: a silently unreadable chart is worse than a message naming the
    limit. A chart with more legend entries than an 800 x 600 canvas could ever hold (29 or
    more) now reports that instead of drawing them past the edge.

    Raises:
        ValueError: if ``mark_style`` isn't ``"stroke"`` or ``"fill"``, or if the legend's
            rows would extend past the bottom of ``document``.
    """
    if mark_style not in ("stroke", "fill"):
        raise ValueError(f"mark_style must be 'stroke' or 'fill', got {mark_style!r}")
    require_room(document, y, legend_ink_height(len(entries)), what=f"a legend of {len(entries)} entries")
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
                    # Scaled to the swatch, not copied from the mark. A key shaped differently
                    # from what it names reads as "not that one" (#265) -- but "the same radius"
                    # is not "the same shape" when the two rectangles are different sizes.
                    #
                    # An earlier version passed the radius through unchanged, arguing that SVG
                    # clamps ``rx`` at half the shorter side so anything big enough to round the
                    # swatch away had already done the same to the bars. Measured, that is false
                    # over a wide and ordinary range: a bar's short side is ~100px, a swatch's is
                    # 10, so at radius 8 the swatch is a full ellipse while the bar is plainly
                    # still a bar. The rounding *has* to be relative to the shape it is on.
                    **({"rx": rounding} if (rounding := corner_radius_attr(_swatch_radius(corner_radius))) else {}),
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
            add_tooltip(document, text_node, label)
    return y + len(entries) * _ROW_HEIGHT
