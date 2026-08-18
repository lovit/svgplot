"""Axis rendering shared by every chart type: spine line, grid lines, tick marks,
and tick label text for a linear/categorical/time scale.

Static axis elements (spine/grid-line/tick-line/tick-label) all share one CSS
class per element *type*, not a ``document.semantic_class``-per-instance name
— ``theme.css``'s ``<style>`` block targets ``.spine``/``.grid-line``/etc. once
and every matching element picks it up uniformly. Only per-series/per-legend
elements (see ``charts/line.py``, ``charts/_legend.py``) need unique classes.

Private/internal — not re-exported from ``svgplot.charts``.
"""

from __future__ import annotations

from datetime import datetime

from svgplot._svg import SvgDocument
from svgplot.charts._layout import PlotArea, format_coord
from svgplot.scales import CategoricalScale, LinearScale, TimeScale, make_ticks

Scale = LinearScale | CategoricalScale | TimeScale

_TICK_LENGTH = 6.0
_TICK_LABEL_OFFSET = 18.0
_Y_TICK_LABEL_OFFSET = 8.0


def _tick_position(scale: Scale, tick: object) -> float:
    """A ``CategoricalScale`` tick should sit at its band's center, not its band's
    start — every other scale type's ``__call__`` already returns the position a
    tick belongs at.
    """
    if isinstance(scale, CategoricalScale):
        return scale.center(str(tick))
    return scale(tick)


def _tick_label_text(scale: Scale, tick: object) -> str:
    if isinstance(scale, CategoricalScale):
        return str(tick)
    if isinstance(tick, datetime):
        return tick.strftime("%Y-%m-%d")
    return format_coord(float(tick))


def render_x_axis(document: SvgDocument, scale: Scale, area: PlotArea, *, tick_count: int = 5) -> None:
    """Draw the bottom spine, vertical grid lines, tick marks, and tick labels for ``scale``."""
    document.add_node(
        None,
        "line",
        attrib={
            "x1": format_coord(area.left),
            "y1": format_coord(area.bottom),
            "x2": format_coord(area.right),
            "y2": format_coord(area.bottom),
        },
        classes=["spine"],
    )
    for tick in make_ticks(scale, count=tick_count):
        x = _tick_position(scale, tick)
        document.add_node(
            None,
            "line",
            attrib={
                "x1": format_coord(x),
                "y1": format_coord(area.top),
                "x2": format_coord(x),
                "y2": format_coord(area.bottom),
            },
            classes=["grid-line"],
        )
        document.add_node(
            None,
            "line",
            attrib={
                "x1": format_coord(x),
                "y1": format_coord(area.bottom),
                "x2": format_coord(x),
                "y2": format_coord(area.bottom + _TICK_LENGTH),
            },
            classes=["tick-line"],
        )
        document.add_text(
            None,
            _tick_label_text(scale, tick),
            tag="text",
            attrib={"x": format_coord(x), "y": format_coord(area.bottom + _TICK_LABEL_OFFSET), "text-anchor": "middle"},
            classes=["tick-label"],
        )


def render_y_axis(document: SvgDocument, scale: Scale, area: PlotArea, *, tick_count: int = 5) -> None:
    """Draw the left spine, horizontal grid lines, tick marks, and tick labels for ``scale``."""
    document.add_node(
        None,
        "line",
        attrib={
            "x1": format_coord(area.left),
            "y1": format_coord(area.top),
            "x2": format_coord(area.left),
            "y2": format_coord(area.bottom),
        },
        classes=["spine"],
    )
    for tick in make_ticks(scale, count=tick_count):
        y = _tick_position(scale, tick)
        document.add_node(
            None,
            "line",
            attrib={
                "x1": format_coord(area.left),
                "y1": format_coord(y),
                "x2": format_coord(area.right),
                "y2": format_coord(y),
            },
            classes=["grid-line"],
        )
        document.add_node(
            None,
            "line",
            attrib={
                "x1": format_coord(area.left - _TICK_LENGTH),
                "y1": format_coord(y),
                "x2": format_coord(area.left),
                "y2": format_coord(y),
            },
            classes=["tick-line"],
        )
        document.add_text(
            None,
            _tick_label_text(scale, tick),
            tag="text",
            attrib={
                "x": format_coord(area.left - _TICK_LENGTH - 2),
                "y": format_coord(y + _Y_TICK_LABEL_OFFSET / 2),
                "text-anchor": "end",
            },
            classes=["tick-label"],
        )
