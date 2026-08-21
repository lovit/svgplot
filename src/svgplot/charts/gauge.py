"""gaugeplot — a value's position within a fixed range, drawn as an arc (pygal's model).

The one chart here whose data model is a **scalar** rather than a comparison. It has no
x/y channels, so it takes a single ``value`` column the way ``pieplot`` does rather than
going through ``ingest_longform``, and it owns its own margin because there are no
cartesian axes to hand to ``charts/_axes``.

Needs no new scale type: ``LinearScale((vmin, vmax), (start_angle, end_angle))`` *is* the
angular scale, and ``make_ticks`` dispatches on it unchanged -- see ``charts/_polar``'s
module docstring for why there is no ``PolarScale``.

Several rows become concentric arcs (pygal's ``SolidGauge``), outermost first, over one
shared range: the point of a gauge is "how far along the same scale", so giving each row
its own range would make the rings incomparable and the tick ring a lie.
"""

from __future__ import annotations

import math

from svgplot._svg import SvgDocument
from svgplot.chart.base import Chart
from svgplot.charts._describe import describe, group, span
from svgplot.charts._layout import (
    LEGEND_X_OFFSET,
    MARGIN_WITH_SIDE_LEGEND,
    fit_margin,
    format_coord,
    format_value_label,
    new_canvas,
    resolve_size,
)
from svgplot.charts._legend import render_legend
from svgplot.charts._polar import label_anchor, polar_point, ring_path
from svgplot.charts._theme_resolve import resolve_theme
from svgplot.data._columns import column_length, extract_columns
from svgplot.data._missing import is_missing
from svgplot.scales import LinearScale, make_ticks
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style

_SWEEP = 4 * math.pi / 3
"""240 degrees, centred on 12 o'clock. The open third at the bottom is what makes a gauge
read as a gauge rather than a donut, and it is where the two ends of the scale go."""

_START_ANGLE = -math.pi / 2 - _SWEEP / 2
"""Lower left. Angles are radians in SVG's y-down system, so they advance clockwise."""

_END_ANGLE = _START_ANGLE + _SWEEP

_HOLE_FRACTION = 0.35
"""Innermost ring boundary, as a fraction of the outer radius. The hole is not decoration:
it is where the value text goes, and a gauge without its number printed is unreadable."""

_RING_GAP = 4.0
"""Blank pixels between two concentric rings, so adjacent arcs stay separable."""

_MIN_RING_THICKNESS = 3.0
"""Below this a ring is thinner than its own outline and stops reading as an arc."""

_TICK_LABEL_GAP = 10.0
"""Pixels from the end of a tick mark to its label."""

_LABEL_MARGIN = 28.0
"""Radial space reserved outside the outer ring for tick marks and their labels."""


_VALUE_LINE_HEIGHT = 18.0
"""Baseline-to-baseline distance for the value text stacked in the hole."""


def _resolve_bounds(values: list[float], vmin: float | None, vmax: float | None) -> tuple[float, float]:
    """Settle the gauge's range, defaulting to ``[0, max(values)]``.

    Zero anchors the low end because a gauge answers "how far along", and a bar that
    starts partway up the scale overstates every value on it -- the same reason
    ``barplot`` baselines at zero. A negative datum pulls the floor down to itself so the
    arc still has somewhere to sit.

    Raises:
        ValueError: if a supplied bound isn't a finite number, if the two are so far apart
            that their difference overflows, or if the resulting range is empty or inverted.
    """
    low = _require_finite_bound(vmin, field="vmin") if vmin is not None else min(0.0, *values)
    high = _require_finite_bound(vmax, field="vmax") if vmax is not None else max(values)
    if low >= high:
        raise ValueError(
            f"gauge range must be non-empty and increasing, got vmin={low!r} >= vmax={high!r}"
            + ("; pass vmax= explicitly" if vmax is None else "")
        )
    # After the ordering check, so an inverted pair whose span also overflows is reported
    # as inverted -- which is what the caller actually has to fix.
    if not math.isfinite(high - low):
        # Each bound can be finite while the span is not. Left alone, LinearScale rejects
        # it with a message about a domain span, naming neither argument -- the same reason
        # the value check above does not defer to format_coord.
        raise ValueError(f"gauge range is too wide to measure: vmax - vmin overflows for vmin={low!r}, vmax={high!r}")
    return low, high


def _require_finite_bound(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError(f"{field} must be a finite number, got {value!r}")
    return float(value)


def _ring_radii(count: int, outer_radius: float) -> list[tuple[float, float]]:
    """``(outer, inner)`` for each concentric ring, first series outermost.

    Raises:
        ValueError: if the rings would come out thinner than :data:`_MIN_RING_THICKNESS`.
            Rendering them anyway would emit arcs too thin to see, and a silently
            unreadable chart is worse than a message naming the limit.
    """
    band = outer_radius * (1.0 - _HOLE_FRACTION)
    thickness = (band - (count - 1) * _RING_GAP) / count
    if thickness < _MIN_RING_THICKNESS:
        raise ValueError(
            f"{count} rows leave each gauge ring {thickness:.2f}px thick, "
            f"below the {_MIN_RING_THICKNESS}px that still reads as an arc"
        )
    step = thickness + _RING_GAP
    return [(outer_radius - index * step, outer_radius - index * step - thickness) for index in range(count)]


def gaugeplot(
    data: object,
    value: str,
    *,
    vmin: float | None = None,
    vmax: float | None = None,
    labels: str | None = None,
    width: float | None = None,
    height: float | None = None,
    theme: Theme | str | None = None,
) -> Chart:
    """Draw a gauge: one arc per row over a shared ``[vmin, vmax]`` range.

    An arc's sweep is proportional to where its value sits in the range -- ``vmin`` draws
    nothing, ``vmax`` draws the full 240-degree sweep, and everything between is monotone.
    **Values outside the range are clamped to its ends**, so an over-range value reads as a
    full arc rather than silently winding past the end and back around, which would render
    as a *smaller* arc than a value that merely reached the top.

    ``vmin`` defaults to zero (or to the smallest value, if that is negative) and ``vmax``
    to the largest value. ``labels`` names the legend column; without it, rows are numbered
    from 1, and a single unlabelled row gets no legend at all -- its number is already
    printed in the middle.

    ``width``/``height`` set the canvas in pixels; ``None`` (the default) means 800x600, so a
    call that does not mention them is byte-identical to one written before they existed. The
    margin presets shrink to keep the plot area the majority of a small canvas and the tick
    count follows the plot extent — see ``charts/_layout.py``. Canvases below 240x180 are
    refused rather than clamped, and a chart may refuse a larger one if its own legend does
    not fit.

    Raises:
        KeyError: if ``value``/``labels`` isn't a column in ``data``, or if ``theme`` is a
            string that isn't a registered preset name.
        TypeError: if ``theme`` is neither a ``Theme``, a preset name, nor ``None``.
        ValueError: if ``data`` has no rows, if no rows remain after dropping missing
            values, if a value isn't finite, if ``vmin``/``vmax`` isn't a finite number,
            if their difference overflows, if they don't form an increasing range, or if
            there are so many rows that the rings would be too thin to read.
    """
    resolved_theme = resolve_theme(theme)
    columns = extract_columns(data)
    if value not in columns:
        raise KeyError(f"value column not found in data: {value!r}")
    if labels is not None and labels not in columns:
        raise KeyError(f"labels column not found in data: {labels!r}")
    length = column_length(columns)
    if length == 0:
        raise ValueError("data must contain at least one row")

    raw_labels = columns[labels] if labels is not None else [str(index + 1) for index in range(length)]
    pairs = [
        (str(label), float(magnitude))
        for label, magnitude in zip(raw_labels, columns[value], strict=True)
        if not is_missing(label) and not is_missing(magnitude)
    ]
    if not pairs:
        raise ValueError("no rows with both a non-missing label and value present after dropping missing values")
    for label, magnitude in pairs:
        # Checked here rather than left to format_coord: an inf survives into the trig as a
        # nan and only then fails, with a message about a coordinate that names neither the
        # offending value nor its row.
        if not math.isfinite(magnitude):
            raise ValueError(f"gauge values must be finite, got {magnitude!r} for label {label!r}")

    low, high = _resolve_bounds([magnitude for _, magnitude in pairs], vmin, vmax)
    angle_of = LinearScale((low, high), (_START_ANGLE, _END_ANGLE))

    canvas_width, canvas_height = resolve_size(width, height)
    document, area = new_canvas(
        fit_margin(MARGIN_WITH_SIDE_LEGEND, canvas_width, canvas_height),
        width=canvas_width,
        height=canvas_height,
    )

    cx, cy = area.left + area.width / 2, area.top + area.height / 2
    outer_radius = min(area.width, area.height) / 2 - _LABEL_MARGIN
    radii = _ring_radii(len(pairs), outer_radius)

    _render_ticks(document, angle_of, cx, cy, outer_radius, tick_length=resolved_theme.tick_size)

    series_classes: list[str] = []
    legend_entries: list[tuple[str, str]] = []
    for (label, magnitude), (ring_outer, ring_inner) in zip(pairs, radii, strict=True):
        # The track first, so the value arc paints over it rather than under it.
        document.add_node(
            None,
            "path",
            attrib={"d": ring_path(cx, cy, ring_outer, ring_inner, _START_ANGLE, _END_ANGLE)},
            classes=["gauge-track", "spine"],
        )
        series_class = document.semantic_class("series")
        series_classes.append(series_class)
        legend_entries.append((label, series_class))
        # The max() half is defensive today: angle_of is increasing, so a value below low
        # already maps below _START_ANGLE and the guard below drops it either way. It stays
        # because the guard is what happens to enforce the documented lower clamp, not the
        # clamp itself -- relaxing that guard to >= would make this line load-bearing again.
        end_angle = angle_of(min(max(magnitude, low), high))
        if end_angle > _START_ANGLE:
            # A zero-length sweep would be an arc whose endpoints coincide, which the
            # renderer drops entirely (SVG spec F.6.2) -- so omit it rather than emit a
            # path that some renderers turn into a full circle.
            document.add_node(
                None,
                "path",
                attrib={"d": ring_path(cx, cy, ring_outer, ring_inner, _START_ANGLE, end_angle)},
                classes=[series_class, "gauge-value"],
            )

    _render_value_text(document, [magnitude for _, magnitude in pairs], cx, cy)

    if labels is not None or len(pairs) > 1:
        render_legend(
            document,
            legend_entries,
            x=area.right + LEGEND_X_OFFSET,
            y=area.top,
            # render_legend knows "stroke" (a line swatch) and "fill" (a rect) only; an
            # outlined arc reads as a filled swatch, and passing "outlined" through raises.
            mark_style="fill",
            font_size=resolved_theme.legend_font_size,
        )
    render_theme_style(document, resolved_theme, series_classes, mark_style="outlined")

    magnitudes = [magnitude for _, magnitude in pairs]
    description = describe(
        "Gauge",
        group([label for label, _ in pairs], "arc"),
        span("values", min(magnitudes), max(magnitudes)),
        span("range", low, high),
    )
    return Chart(document, description=description)


def _render_ticks(
    document: SvgDocument, angle_of: LinearScale, cx: float, cy: float, outer_radius: float, *, tick_length: float
) -> None:
    """Tick marks and labels around the outside of the outermost ring.

    Positions come from ``make_ticks`` on the angular scale itself, so a tick sits at the
    angle its own value maps to -- there is no second, hand-rolled placement rule that
    could drift from the one the arcs use.
    """
    for tick in make_ticks(angle_of):
        angle = angle_of(float(tick))
        inner_x, inner_y = polar_point(cx, cy, outer_radius, angle)
        outer_x, outer_y = polar_point(cx, cy, outer_radius + tick_length, angle)
        document.add_node(
            None,
            "line",
            attrib={
                "x1": format_coord(inner_x),
                "y1": format_coord(inner_y),
                "x2": format_coord(outer_x),
                "y2": format_coord(outer_y),
            },
            classes=["tick-line"],
        )
        label_x, label_y = polar_point(cx, cy, outer_radius + tick_length + _TICK_LABEL_GAP, angle)
        document.add_text(
            None,
            format_value_label(float(tick)),
            attrib={
                "x": format_coord(label_x),
                "y": format_coord(label_y),
                "text-anchor": label_anchor(angle),
                "dominant-baseline": "middle",
            },
            classes=["tick-label"],
        )


def _render_value_text(document: SvgDocument, magnitudes: list[float], cx: float, cy: float) -> None:
    """The values themselves, stacked in the hole and centred on it as a block.

    Printed rather than left to the arcs: an arc's angle is only readable against the tick
    ring, and reading a number off a curve is exactly what a reader should not have to do.
    """
    top = cy - (len(magnitudes) - 1) * _VALUE_LINE_HEIGHT / 2
    for index, magnitude in enumerate(magnitudes):
        document.add_text(
            None,
            format_value_label(magnitude),
            attrib={
                "x": format_coord(cx),
                "y": format_coord(top + index * _VALUE_LINE_HEIGHT),
                "text-anchor": "middle",
                "dominant-baseline": "middle",
            },
            # See ``pie-value`` in charts/pie.py. The dial's numbers sit in the hole at the
            # centre, over nothing -- but the arcs reach the hole's edge, so the outermost line
            # of numbers overlaps them.
            classes=["gauge-value", "legend-text"],
        )
