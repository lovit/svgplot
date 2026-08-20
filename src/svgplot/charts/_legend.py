"""Legend rendering shared by every chart type whose hue=/grouping produces
multiple series: one color swatch + label per entry.

Private/internal — not re-exported from ``svgplot.charts``.
"""

from __future__ import annotations

from svgplot._svg import SvgDocument
from svgplot.charts._layout import format_coord

_SWATCH_WIDTH = 16.0
_LABEL_GAP = 6.0
_ROW_HEIGHT = 20.0
_TEXT_BASELINE_OFFSET = 4.0


_SWATCH_HEIGHT = 10.0


_ESTIMATED_CHAR_WIDTH_EM = 0.55
_MIN_READABLE_CHARS = 6.0
"""What the legend gutter is checked against, and the two things that check is *not*.

It is not a measurement: this package has no font renderer, so a label's real width is
unknowable here. 0.55 em is the average advance of a lower-case Latin string in the
sans-serif families the themes name, which is the closest honest stand-in. And it is not a
promise about any particular label — a six-character label is simply the shortest thing
that still distinguishes one series from another, so a gutter that cannot hold six
characters cannot hold a useful legend for *any* data.

Six characters at ``legend_font_size`` 11 is about 36 px of text. Everything else in a
legend row is fixed geometry (a 16 px swatch plus a 6 px gap), so the gutter has to be
about 58 px wide once :data:`charts._layout.LEGEND_X_OFFSET` is counted."""


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


def require_room(document: SvgDocument, y: float, needed: float, *, what: str) -> None:
    """Refuse to start drawing ``needed`` pixels of legend at ``y`` on a shorter canvas.

    ``needed`` is ink, not claimed space — see :func:`legend_ink_height`. A second legend
    stacked below the first starts at the *claimed* end of it, so it is checked from there
    and against its own ink: that pairing is what stops ``scatterplot(hue=, size=)`` drawing
    46px outside a 400x180 canvas with each legend individually looking fine.
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


def minimum_legend_text_width(font_size: float) -> float:
    """The room :data:`_MIN_READABLE_CHARS` characters need at ``font_size`` — see that
    constant for what this estimate is and is not."""
    return _MIN_READABLE_CHARS * _ESTIMATED_CHAR_WIDTH_EM * font_size


def render_legend(
    document: SvgDocument, entries: list[tuple[str, str]], *, x: float, y: float, mark_style: str = "stroke"
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
                },
                classes=[css_class],
            )
        document.add_text(
            None,
            label,
            tag="text",
            attrib={"x": format_coord(x + _SWATCH_WIDTH + _LABEL_GAP), "y": format_coord(row_y + _TEXT_BASELINE_OFFSET)},
            classes=["legend-text"],
        )
    return y + len(entries) * _ROW_HEIGHT
