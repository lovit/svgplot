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

from svgplot.chart.base import Chart
from svgplot.charts._describe import describe, group, number, span
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
from svgplot.charts._polar import FULL_CIRCLE_TOLERANCE, full_ring_path, polar_point, ring_path
from svgplot.charts._theme_resolve import resolve_theme
from svgplot.charts._tooltip import add_tooltip, clause, format_label, format_number
from svgplot.data._columns import column_length, extract_columns
from svgplot.data._missing import is_missing
from svgplot.labels._source import collect_label_data
from svgplot.labels.spec import LabelSpec
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style

_LABEL_RADIUS_FRACTION = 0.65  # value-label distance from center, as a fraction between inner/outer radius


def _slice_tooltip(*, values: str, label: str, value: float, cumulative: float, total: float) -> str:
    """What one slice's ``<title>`` says: its name, its value, its share, and the share of
    everything up to and including it.

    **The running share is in the picture and written nowhere.** A pie is read clockwise from
    twelve o'clock, so where a slice *ends* is already a statement about the whole -- "these
    four together are most of it" is the question a pie is usually asked, and answering it by
    eye means adding the slices back up. The chart draws each slice's value in the middle of it
    and the legend names them; neither says how far round the reader has got.

    Rounded to one decimal like ``treemap``'s share: a proportion of a total the reader can also
    see is not a measurement, and seventeen digits of one would be the longest clause here.
    The *value* beside it is spelled exactly, because that one came out of somebody's file.
    """
    parts = []
    if (shown := format_label(label)) is not None:
        parts.append(shown)
    parts.append(clause(values, format_number(value)))
    parts.append(f"{value / total * 100:.1f}%")
    parts.append(f"{cumulative / total * 100:.1f}% cumulative")
    return " · ".join(parts)


def pieplot(
    data: object,
    values: str,
    labels: str | None = None,
    *,
    tooltip: bool = False,
    inner_radius: float = 0.0,
    info: LabelSpec | list[tuple[str, str]] | None = None,
    width: float | None = None,
    height: float | None = None,
    theme: Theme | str | None = None,
) -> Chart:
    """Draw a pie chart from ``values`` (slice angle) and, optionally, ``labels``
    (legend text; defaults to 1-based slice position when omitted).

    ``tooltip=True`` gives every slice a ``<title>`` naming it, its value, its share, and the
    share of **everything up to and including it**. That last part is in the picture and written
    nowhere: a pie is read clockwise from twelve o'clock, so where a slice ends is already a
    statement about the whole -- "these four together are most of it" is the question a pie is
    usually asked, and answering it by eye means adding the slices back up. The chart draws each
    slice's value in the middle of it and the legend names them; neither says how far round the
    reader has got.

    Turning it on also gives the value labels ``pointer-events: none``. A label sits *on top of*
    its own slice, so without that it takes the pointer at the one place the reader aims for.
    With ``tooltip=False`` there is nothing to put in its place, which is why the rule is
    conditional.

    ``tooltip=False`` is the default; off, the file is what it was.

    ``inner_radius`` is a fraction of the outer radius in ``[0, 1)`` (not an
    absolute pixel length) -- ``0.0`` (the default) draws a full pie, any value
    above ``0.0`` draws a donut with a hole that size relative to the pie.
    Each slice's value is drawn as a label directly on the slice; ``labels``
    (when given) drives the legend instead, matching the fact that a slice's
    angle is only meaningful relative to its own numeric value.

    ``width``/``height`` set the canvas in pixels; ``None`` (the default) means 800x600, so a
    call that does not mention them is byte-identical to one written before they existed. The
    margin presets shrink to keep the plot area the majority of a small canvas and the tick
    count follows the plot extent — see ``charts/_layout.py``. Canvases below 240x180 are
    refused rather than clamped, and a chart may refuse a larger one if its own legend does
    not fit.

    ``info=`` publishes a footnote table beside the chart -- ``[("label", "@column")]``, or a
    :class:`~svgplot.labels.spec.LabelSpec`. Available here because one input row is one slice.
    The table lists the rows this chart actually drew, which for a pie means the rows with both
    ``values`` and ``labels`` present -- a row missing some *other* column is still drawn and
    still listed. ``chart.to_html_table()`` renders it, ``chart.save("x.md")`` writes it beneath
    the figure, and the SVG points at it with ``aria-describedby`` -- so two ``info=`` charts on
    one page need :meth:`~svgplot.chart.base.Chart.set_table_id` to tell their tables apart.

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

    canvas_width, canvas_height = resolve_size(width, height)
    document, area = new_canvas(
        fit_margin(MARGIN_WITH_SIDE_LEGEND, canvas_width, canvas_height),
        width=canvas_width,
        height=canvas_height,
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
        wedge = document.add_node(None, "path", attrib=attrib, classes=[series_class])
        if tooltip:
            add_tooltip(
                document,
                wedge,
                _slice_tooltip(values=values, label=label, value=value, cumulative=cumulative, total=total),
            )

        mid_angle = (start_angle + end_angle) / 2
        label_x, label_y = polar_point(cx, cy, label_radius, mid_angle)
        document.add_text(
            None,
            format_value_label(value),
            tag="text",
            attrib={"x": format_coord(label_x), "y": format_coord(label_y), "text-anchor": "middle"},
            # ``legend-text`` is what styles it -- kept, so no new rule is needed in
            # ``theme/css.py``, whose rule list every chart emits, and the *other thirteen*
            # charts' <style> is untouched. This chart's own <style> depends on how it was
            # scoped: the gallery names its scopes, so those blocks are unchanged, while a bare
            # ``to_string()`` derives the token from a hash of the document and adding a class
            # moves it. ``pie-value`` is a hook for the page around
            # the chart: a value label sits on top of its slice, so a reader hovering the number
            # gets no tooltip from the slice underneath unless the page can say
            # ``pointer-events: none`` about this element and not about every legend label.
            classes=["pie-value", "legend-text"],
        )

    render_legend(
        document,
        legend_entries,
        x=area.right + LEGEND_X_OFFSET,
        y=area.top,
        mark_style="fill",
        font_size=resolved_theme.legend_font_size,
    )
    render_theme_style(
        document,
        resolved_theme,
        series_classes,
        mark_style="fill",
        # A value label sits *on top of* its own slice, so it takes the pointer at the one place
        # the reader aims for. Only when the slices have something to say, for ``treemap``'s
        # reason: with tooltips off there is nothing to put in the label's place.
        transparent_to_pointer=("pie-value",) if tooltip else (),
    )

    magnitudes = [value for _, value in pairs]
    description = describe(
        "Donut chart" if inner_radius > 0 else "Pie chart",
        group([label for label, _ in pairs], "slice"),
        span("values", min(magnitudes), max(magnitudes)),
        f"total {number(total)}",
    )
    return Chart(document, label_data, description=description)
