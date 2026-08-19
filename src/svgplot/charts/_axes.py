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
from svgplot.scales import CategoricalScale, Scale, make_ticks

_DEFAULT_TICK_LENGTH = 6.0
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


_DATE_FORMATS = ("%Y", "%Y-%m", "%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S")
"""Time-axis label formats for a domain spanning a day or more, coarsest first."""

_CLOCK_FORMATS = ("%H:%M", "%H:%M:%S", "%H:%M:%S.%f")
"""The same for ticks that all fall on one calendar date, where repeating that date on every
tick would spend the axis' width saying what the chart title already says.

One date, not one day's worth of hours: ticks running 12:00, 18:00, 00:00, 06:00 span
eighteen hours but two dates, and dropping the date there leaves a reader to guess which
midnight ``00:00`` is."""


def _time_format(ticks: list[datetime]) -> str:
    """The coarsest format that still tells the ticks apart.

    A fixed ``"%Y-%m-%d"`` is right for a domain of months and wrong either way outside it.
    Measured on a three-hour domain it labelled all five ticks ``2024-01-01``; on a three-year
    domain it spent eleven characters on a day nobody asked about. Both are the same bug --
    the resolution has to come from the domain, which is what matplotlib's locator/formatter
    pair does and what this is the small version of.

    Choosing by *distinctness* rather than by a span-to-format table is what makes the "no
    duplicate labels" property hold rather than be approximated: a table has to guess how many
    ticks will land in a span, and the ticks are right there.
    """
    ladder = _CLOCK_FORMATS if len({tick.date() for tick in ticks}) == 1 else _DATE_FORMATS
    for candidate in ladder:
        if len({tick.strftime(candidate) for tick in ticks}) == len(ticks):
            return candidate
    # Two ticks the finest format cannot separate are under a microsecond apart, which is
    # finer than ``datetime`` resolves -- so they are the same instant, and ``make_ticks``
    # returns one of them. Reaching here means something upstream produced ticks it should
    # not have; the finest format at least shows the most it can rather than raising.
    return ladder[-1]


def _tick_label_text(scale: Scale, tick: object, *, time_format: str) -> str:
    if isinstance(scale, CategoricalScale):
        return str(tick)
    if isinstance(tick, datetime):
        return tick.strftime(time_format)
    return format_coord(float(tick))


def render_x_axis(
    document: SvgDocument, scale: Scale, area: PlotArea, *, tick_count: int = 5, tick_length: float = _DEFAULT_TICK_LENGTH
) -> None:
    """Draw the bottom spine, vertical grid lines, tick marks, and tick labels for ``scale``.

    ``tick_length`` should come from the ``Theme`` being rendered with
    (``theme.tick_size``) so a theme's tick length actually takes visual effect —
    it defaults to a sane constant only for direct/standalone callers that don't
    have a ``Theme`` in scope.
    """
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
    label_offset = tick_length + _TICK_LABEL_OFFSET
    ticks = make_ticks(scale, count=tick_count)
    time_format = _time_format(ticks) if ticks and isinstance(ticks[0], datetime) else ""
    for tick in ticks:
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
                "y2": format_coord(area.bottom + tick_length),
            },
            classes=["tick-line"],
        )
        document.add_text(
            None,
            _tick_label_text(scale, tick, time_format=time_format),
            tag="text",
            attrib={"x": format_coord(x), "y": format_coord(area.bottom + label_offset), "text-anchor": "middle"},
            classes=["tick-label"],
        )


def render_y_axis(
    document: SvgDocument, scale: Scale, area: PlotArea, *, tick_count: int = 5, tick_length: float = _DEFAULT_TICK_LENGTH
) -> None:
    """Draw the left spine, horizontal grid lines, tick marks, and tick labels for ``scale``.

    ``tick_length`` should come from the ``Theme`` being rendered with
    (``theme.tick_size``) so a theme's tick length actually takes visual effect —
    it defaults to a sane constant only for direct/standalone callers that don't
    have a ``Theme`` in scope.
    """
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
    label_x_offset = tick_length + 2
    ticks = make_ticks(scale, count=tick_count)
    time_format = _time_format(ticks) if ticks and isinstance(ticks[0], datetime) else ""
    for tick in ticks:
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
                "x1": format_coord(area.left - tick_length),
                "y1": format_coord(y),
                "x2": format_coord(area.left),
                "y2": format_coord(y),
            },
            classes=["tick-line"],
        )
        document.add_text(
            None,
            _tick_label_text(scale, tick, time_format=time_format),
            tag="text",
            attrib={
                "x": format_coord(area.left - label_x_offset),
                "y": format_coord(y + _Y_TICK_LABEL_OFFSET / 2),
                "text-anchor": "end",
            },
            classes=["tick-label"],
        )
