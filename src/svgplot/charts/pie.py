"""pieplot — pie/donut charts (donut via inner_radius).

Unlike the other chart types, a pie has no axes and no ``x=``/``y=``/``hue=``
column roles — it takes a single ``values=`` column (mapped to slice angle)
and an optional ``labels=`` column (mapped to legend text). Data access uses
``data._columns.extract_columns``/``column_length`` rather than
``data.ingest.ingest_longform``, since the latter is x/y-shaped and doesn't
fit a single-column input.
"""

from __future__ import annotations

import math

from svgplot._svg import SvgDocument
from svgplot.chart.base import Chart
from svgplot.charts._layout import DEFAULT_HEIGHT, DEFAULT_WIDTH, LEGEND_X_OFFSET, format_coord, plot_area
from svgplot.charts._legend import render_legend
from svgplot.charts._polar import FULL_CIRCLE_TOLERANCE, full_ring_path, polar_point, ring_path
from svgplot.charts._theme_resolve import resolve_theme
from svgplot.data._columns import column_length, extract_columns
from svgplot.data._missing import is_missing
from svgplot.labels._source import collect_label_data
from svgplot.labels.spec import LabelSpec
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style

_MARGIN = (30.0, 180.0, 30.0, 30.0)  # top, right, bottom, left -- right reserves legend space
_LABEL_RADIUS_FRACTION = 0.65  # value-label distance from center, as a fraction between inner/outer radius


def _format_value_label(value: float) -> str:
    """Render a data value as label text, shortest-round-trip.

    Not ``format_coord``: that rounds to 6 decimals because it formats *coordinates*,
    which silently rewrites the data it is labelling (``1e-7`` -> ``"0"``,
    ``0.123456789`` -> ``"0.123457"``). Integral values still lose the ``.0`` so the
    common case reads as ``30``, not ``30.0``.
    """
    return str(int(value)) if value.is_integer() else str(value)


def pieplot(
    data: object,
    values: str,
    labels: str | None = None,
    *,
    inner_radius: float = 0.0,
    info: LabelSpec | list[tuple[str, str]] | None = None,
    theme: Theme | str | None = None,
) -> Chart:
    """Draw a pie chart from ``values`` (slice angle) and, optionally, ``labels``
    (legend text; defaults to 1-based slice position when omitted).

    ``inner_radius`` is a fraction of the outer radius in ``[0, 1)`` (not an
    absolute pixel length) -- ``0.0`` (the default) draws a full pie, any value
    above ``0.0`` draws a donut with a hole that size relative to the pie.
    Each slice's value is drawn as a label directly on the slice; ``labels``
    (when given) drives the legend instead, matching the fact that a slice's
    angle is only meaningful relative to its own numeric value.

    Raises:
        KeyError: if ``values``/``labels`` isn't a column in ``data``, or if
            ``theme`` is a string that isn't a registered preset name.
        TypeError: if ``theme`` is neither a ``Theme``, a preset name, nor ``None``.
        ValueError: if ``data`` has no rows, if no rows remain after dropping
            missing values, if any value is negative, if all values are zero,
            or if ``inner_radius`` isn't finite and in ``[0, 1)``.
    """
    resolved_theme = resolve_theme(theme)
    columns = extract_columns(data)
    if values not in columns:
        raise KeyError(f"values column not found in data: {values!r}")
    if labels is not None and labels not in columns:
        raise KeyError(f"labels column not found in data: {labels!r}")
    length = column_length(columns)
    if length == 0:
        raise ValueError("data must contain at least one row")

    if not (isinstance(inner_radius, int | float) and not isinstance(inner_radius, bool) and math.isfinite(inner_radius)):
        raise ValueError(f"inner_radius must be a finite number, got {inner_radius!r}")
    if not (0.0 <= inner_radius < 1.0):
        raise ValueError(f"inner_radius must be a fraction of the outer radius in [0, 1), got {inner_radius!r}")

    raw_values = columns[values]
    raw_labels = columns[labels] if labels is not None else [str(index + 1) for index in range(length)]
    pairs = [
        (str(label), float(value))
        for label, value in zip(raw_labels, raw_values, strict=True)
        if not is_missing(label) and not is_missing(value)
    ]
    if not pairs:
        raise ValueError("no rows with both a non-missing label and value present after dropping missing values")
    for label, value in pairs:
        # Checked here rather than left to format_coord: an inf/-inf survives the
        # negative check, becomes nan inside the trig, and only then fails -- with a
        # message about a coordinate, naming neither the offending value nor its row.
        if not math.isfinite(value):
            raise ValueError(f"pie values must be finite, got {value!r} for label {label!r}")
        if value < 0:
            raise ValueError(f"pie values must be non-negative, got {value!r} for label {label!r}")
    total = sum(value for _, value in pairs)
    if total == 0:
        raise ValueError("pie values must not all be zero (sum is 0)")

    # After the checks above, so a bad column still reports the chart's own error first.
    label_data = collect_label_data(data, info, required=(values, labels))

    document = SvgDocument(width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT)
    area = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=_MARGIN)
    document.add_node(
        None,
        "rect",
        attrib={"x": 0, "y": 0, "width": format_coord(DEFAULT_WIDTH), "height": format_coord(DEFAULT_HEIGHT)},
        classes=["plot-background"],
    )

    cx, cy = area.left + area.width / 2, area.top + area.height / 2
    outer_radius = min(area.width, area.height) / 2
    inner_radius_px = outer_radius * inner_radius
    label_radius = inner_radius_px + (outer_radius - inner_radius_px) * _LABEL_RADIUS_FRACTION

    series_classes: list[str] = []
    legend_entries: list[tuple[str, str]] = []
    cumulative = 0.0
    for label, value in pairs:
        series_class = document.semantic_class("series")
        series_classes.append(series_class)
        legend_entries.append((label, series_class))

        start_angle = -math.pi / 2 + (cumulative / total) * 2 * math.pi
        cumulative += value
        end_angle = -math.pi / 2 + (cumulative / total) * 2 * math.pi
        is_full_circle = math.isclose(end_angle - start_angle, 2 * math.pi, abs_tol=FULL_CIRCLE_TOLERANCE)

        path_data = (
            full_ring_path(cx, cy, outer_radius, inner_radius_px)
            if is_full_circle
            else ring_path(cx, cy, outer_radius, inner_radius_px, start_angle, end_angle)
        )
        attrib: dict[str, str | int | float] = {"d": path_data}
        if inner_radius_px > 0:
            attrib["fill-rule"] = "evenodd"
        document.add_node(None, "path", attrib=attrib, classes=[series_class])

        mid_angle = (start_angle + end_angle) / 2
        label_x, label_y = polar_point(cx, cy, label_radius, mid_angle)
        document.add_text(
            None,
            _format_value_label(value),
            tag="text",
            attrib={"x": format_coord(label_x), "y": format_coord(label_y), "text-anchor": "middle"},
            classes=["legend-text"],
        )

    render_legend(document, legend_entries, x=area.right + LEGEND_X_OFFSET, y=area.top, mark_style="fill")
    render_theme_style(document, resolved_theme, series_classes, mark_style="fill")

    return Chart(document, label_data)
