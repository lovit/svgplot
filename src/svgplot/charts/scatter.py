"""scatterplot — point charts with hue/size semantic channel mapping.

Follows ``charts/line.py``'s reference structure (issue #12): same shared
rendering infrastructure (``_layout``/``_axes``/``_legend``/``theme.css``),
adapted for unconnected point marks instead of a connected path.
"""

from __future__ import annotations

from collections.abc import Callable

from svgplot._svg import SvgDocument
from svgplot.chart._domain import Domains, apply_limit
from svgplot.chart.base import Chart
from svgplot.charts._axes import fit_left_margin, render_x_axis, render_y_axis
from svgplot.charts._describe import describe, fits, over, plural, span
from svgplot.charts._layout import (
    LEGEND_X_OFFSET,
    MARGIN_WITH_LEGEND,
    MARGIN_WITHOUT_LEGEND,
    TICK_SPACING_X,
    TICK_SPACING_Y,
    fit_margin,
    format_coord,
    new_canvas,
    resolve_axis_scale,
    resolve_size,
    ticks_for,
    value_scale,
)
from svgplot.charts._legend import render_legend, require_room, size_legend_ink_height
from svgplot.charts._series import series_items as build_series
from svgplot.charts._theme_resolve import resolve_theme
from svgplot.charts._tooltip import add_tooltip, format_label, format_number, has_visible_text
from svgplot.data._missing import numeric_or_none
from svgplot.data.ingest import ingest_longform
from svgplot.labels._source import collect_label_data
from svgplot.labels.spec import LabelSpec
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style

_SIZE_LEGEND_GAP = 24.0  # vertical gap between the hue legend and the size legend
_SIZE_LEGEND_ROW_PADDING = 8.0  # vertical breathing room between size-legend rows
_SIZE_LEGEND_LABEL_GAP = 6.0
_SIZE_LEGEND_BASELINE = 4.0  # how far a row's label sits below its marker's centre

# A point's radius ranges from 0.5x to 2.5x the theme's base marker size when size=
# is mapped from data — wide enough to read as "varying," not so wide that the
# smallest points vanish or the largest overwhelm the plot area. Chosen empirically,
# not from a formula; documented here so a future reviewer knows it's a deliberate
# (if arbitrary) choice, not an accident.
_SIZE_RADIUS_MIN_FACTOR = 0.5
_SIZE_RADIUS_MAX_FACTOR = 2.5


def _radius_mapper(size_values: list[float], base_radius: float) -> Callable[[float], float]:
    """Return a function mapping a raw size value to a pixel radius, linearly
    scaled across ``size_values``'s ``[min, max]`` into
    ``[base_radius * _SIZE_RADIUS_MIN_FACTOR, base_radius * _SIZE_RADIUS_MAX_FACTOR]``.
    A constant size column (min == max) maps every value to ``base_radius``,
    since a 0-width domain has no meaningful ratio to scale by.
    """
    low, high = min(size_values), max(size_values)
    min_radius = base_radius * _SIZE_RADIUS_MIN_FACTOR
    max_radius = base_radius * _SIZE_RADIUS_MAX_FACTOR
    if high == low:
        return lambda _value: base_radius
    return lambda value: min_radius + (value - low) / (high - low) * (max_radius - min_radius)


def _render_size_legend(
    document: SvgDocument,
    size_values: list[float],
    radius_of: Callable[[float], float],
    *,
    x: float,
    y: float,
    marker_class: str,
) -> None:
    """Draw 3 representative samples (min/mid/max of ``size_values``) as circles
    of their mapped radius plus a value label each — a size legend can't reuse
    ``charts._legend.render_legend`` (uniform swatch shape), so this stays local
    to ``scatter.py`` rather than becoming a shared module for a single caller.

    ``marker_class`` reuses an already-``theme.css``-styled series class (rather
    than introducing an unstyled class this module has no way to color, since
    that would require a change to the shared ``theme/css.py`` this issue
    intentionally avoids touching) — every size sample renders in that one
    series' color, which stays theme-aware even when it isn't a perfect visual
    match for every hue group.
    """
    low, high = min(size_values), max(size_values)
    samples = sorted({low, (low + high) / 2, high})
    # Checked before the first circle, and against the same rule the hue legend uses: **ink**,
    # not the space claimed. This legend is drawn *below* the hue legend, starting at the space
    # that one claimed, so each can look fine alone while the pair runs off the bottom -- with
    # both guards removed at 400x180, three hue groups fit (lowest ink y=175) and the fourth is
    # the first to overflow, by 15px, every further group adding 20.
    #
    # Summing ``2r + padding`` over every sample would count the last row's bottom padding,
    # which nothing is drawn in, and that refuses legends that fit: ``scatterplot(hue=3, size=)``
    # at 400x180 was rejected while its lowest ink sat at 175 on a 180px canvas.
    require_room(
        document,
        y,
        size_legend_ink_height([radius_of(sample) for sample in samples], _SIZE_LEGEND_ROW_PADDING, _SIZE_LEGEND_BASELINE),
        what=f"a size legend of {len(samples)} samples",
    )
    # Rows advance by each sample's own diameter (plus padding), not a fixed height:
    # the largest sample's radius scales with theme.marker_size, so a fixed row height
    # lets big markers overlap the row above at perfectly ordinary theme settings.
    row_y = y
    for sample in samples:
        radius = radius_of(sample)
        row_y += radius
        document.add_node(
            None,
            "circle",
            attrib={"cx": format_coord(x + radius), "cy": format_coord(row_y), "r": format_coord(radius)},
            classes=[marker_class],
        )
        document.add_text(
            None,
            format_coord(sample),
            tag="text",
            attrib={
                "x": format_coord(x + 2 * (max(radius_of(high), radius_of(low))) + _SIZE_LEGEND_LABEL_GAP),
                "y": format_coord(row_y + _SIZE_LEGEND_BASELINE),
            },
            classes=["legend-text"],
        )
        row_y += radius + _SIZE_LEGEND_ROW_PADDING


def _size_clause(size: str | None) -> str | None:
    """The ``size=`` clause, with the column name capped like every other caller string.

    This is the one clause in the package that names something the caller typed rather
    than something the data contains, and it was the only uncapped path into a ``<desc>``:
    a 500,000-character column name produced a 500,064-character description. A name too
    long to read out is dropped rather than truncated, for the same reason a category name
    is — half a column name is a different column name.
    """
    if size is None:
        return None
    return f'marker size from "{size}"' if fits(size) else "marker size from another column"


def _clause(name: str, value: str) -> str:
    """``"name: value"``, or the value alone when the name is not worth repeating.

    Column names are caller strings, and here one of them is repeated **once per point** --
    an unreadably long name would be the largest thing in the file. Dropped rather than
    truncated, for ``_size_clause``'s reason: half a column name is a different column name.
    ``has_visible_text`` for the same job in the other direction -- a name of one tab is
    short enough to fit and still reads as ``"\t: 45"``.
    """
    return f"{name}: {value}" if fits(name) and has_visible_text(name) else value


def _point_tooltip(*, x: str, y: str, size: str | None, hue: str | None, row: tuple, label: object) -> str:
    """What one point's ``<title>`` says: its own values, named by the columns they came from.

    **Everything here is bounded, and that is the whole design constraint.** Each clause is
    written once per point, so anything unbounded is multiplied by the number of marks: before
    the label went through :func:`format_label`, a 100,000-character hue value took a
    1,000-point chart from 185 KB to 100 MB. The numbers are bounded by
    :func:`format_number`, because a ``<title>`` is the mark's *accessible name* and ``1e308``
    spelled as a decimal literal is 309 digits read out one at a time.

    The clauses are joined with ``" · "``, which a label containing that sequence can imitate
    -- ``"a · b"`` as a group name reads as two clauses. Escaping it would make the common case
    unreadable to buy an unambiguous parse nobody performs; the tooltip is prose for a person,
    not a record.
    """
    parts = [_clause(x, format_number(row[0])), _clause(y, format_number(row[1]))]
    if size is not None:
        # ``row[2]`` cannot be None here: the row loop drops any row with a missing size when
        # ``size=`` was given, so surviving rows always carry one.
        parts.append(_clause(size, format_number(row[2])))
    if hue is not None and (shown := format_label(label)) is not None:
        parts.append(_clause(hue, shown))
    return " · ".join(parts)


def scatterplot(
    data: object,
    x: str,
    y: str,
    hue: str | None = None,
    size: str | None = None,
    *,
    info: LabelSpec | list[tuple[str, str]] | None = None,
    tooltip: bool = False,
    width: float | None = None,
    height: float | None = None,
    theme: Theme | str | None = None,
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
    xscale: str = "linear",
    yscale: str = "linear",
) -> Chart:
    """Draw a scatter plot from long-form data.

    With ``hue=``, points are colored by distinct hue value (colors cycling
    through the theme's palette) with an auto-generated legend. With ``size=``,
    marker radius is linearly mapped from that numeric column's range (theme's
    ``marker_size`` as the anchor), with its own auto-generated legend showing
    representative min/mid/max samples. ``hue=`` and ``size=`` can be combined.

    ``tooltip=True`` gives every point a ``<title>`` naming its own values -- the x and y
    columns, plus ``size=`` and ``hue=`` where they were given. A browser shows that as the
    ordinary hover tooltip, and it is also the point's accessible name, so the marks become
    named nodes rather than one anonymous cloud. It works only where the SVG is *inlined* into
    the page: inside an ``<img>`` the file is a separate document and the browser draws it
    without interaction.

    ``tooltip=False`` is the default, and not as a matter of taste. A ``<title>`` per point is
    an element per point, so turning it on for a thousand-point chart adds a thousand elements
    -- and every existing caller's output would change bytes for a feature they did not ask
    for. Off, the file is what it was.

    ``xlim=``/``ylim=`` replace the domain this chart would compute from its own data. They
    exist so several charts can be made to agree -- see :func:`~svgplot.layout.facet.facet`,
    which uses them to give faceted panels one axis -- and replace rather than widen, so a
    caller asking for a narrower view gets one.

    ``width``/``height`` set the canvas in pixels; ``None`` (the default) means 800x600, so a
    call that does not mention them is byte-identical to one written before they existed. The
    margin presets shrink to keep the plot area the majority of a small canvas and the tick
    count follows the plot extent — see ``charts/_layout.py``. Canvases below 240x180 are
    refused rather than clamped, and a chart may refuse a larger one if its own legend does
    not fit.

    ``xscale=``/``yscale=`` choose that axis' scale: ``"linear"`` (the default) or ``"log"``.
    A log axis is what makes response times, file sizes or populations legible -- on a linear
    axis the small values collapse into one pixel. Values at or below zero are **refused by
    column name** rather than masked or clipped: a logarithm is undefined there, and both of
    the alternatives silently draw a different chart than the data describes.

    ``info=`` publishes a footnote table beside the chart -- ``[("label", "@column")]``, or a
    :class:`~svgplot.labels.spec.LabelSpec`. Available here because one input row is one point,
    so a table row and a mark correspond; the charts that fold rows into a mark do not take it.
    The table lists the rows this chart actually drew: a row missing ``x``, ``y``, ``hue`` or
    ``size`` is dropped from both. ``chart.to_html_table()`` renders it, ``chart.save("x.md")``
    writes it beneath the figure, and the SVG points at it with ``aria-describedby`` -- so two
    ``info=`` charts on one page need :meth:`~svgplot.chart.base.Chart.set_table_id` to tell
    their tables apart.

    Raises:
        KeyError: if ``x``/``y``/``hue``/``size`` isn't a column in ``data``, or if
            ``theme`` is a string that isn't a registered preset name.
        TypeError: if ``theme`` is neither a ``Theme``, a preset name, nor ``None``.
        ValueError: if ``data`` has no rows, or no rows remain after dropping rows
            with a missing x/y/size value.
    """
    resolved_theme = resolve_theme(theme)
    longform = ingest_longform(data, x, y)
    if len(longform) == 0:
        raise ValueError("data must contain at least one row")
    if size is not None and size not in longform.columns:
        raise KeyError(f"size column not found in data: {size!r}")

    series_items = build_series(data, longform.columns, hue)

    # (label, x, y, size_or_None) per surviving row, grouped by hue label.
    series_rows: list[tuple[object, list[tuple[float, float, float | None]]]] = []
    for label, columns in series_items:
        rows = []
        for xv, yv, sv in zip(
            columns[x], columns[y], columns[size] if size is not None else [None] * len(columns[x]), strict=True
        ):
            xn, yn = numeric_or_none(xv), numeric_or_none(yv)
            sn = numeric_or_none(sv) if size is not None else None
            if xn is None or yn is None or (size is not None and sn is None):
                continue
            rows.append((xn, yn, sn))
        series_rows.append((label, rows))

    all_rows = [row for _, rows in series_rows for row in rows]
    if not all_rows:
        raise ValueError("no rows with usable x/y (and size=, if given) values after dropping missing values")
    all_x = [row[0] for row in all_rows]
    all_y = [row[1] for row in all_rows]
    x_domain = (min(all_x), max(all_x))
    y_domain = (min(all_y), max(all_y))
    x_domain = apply_limit(x_domain, xlim)
    y_domain = apply_limit(y_domain, ylim)

    has_legend = hue is not None or size is not None
    # After the checks above, so a bad column still reports the chart's own error first.
    label_data = collect_label_data(data, info, required=(x, y, hue, size))

    resolved_xscale = resolve_axis_scale(xscale, parameter="xscale")
    resolved_yscale = resolve_axis_scale(yscale, parameter="yscale")
    canvas_width, canvas_height = resolve_size(width, height)
    document, area = new_canvas(
        fit_margin(
            fit_left_margin(
                MARGIN_WITH_LEGEND if has_legend else MARGIN_WITHOUT_LEGEND,
                y_domain,
                width=canvas_width,
                font_size=resolved_theme.tick_label_font_size,
            ),
            canvas_width,
            canvas_height,
        ),
        width=canvas_width,
        height=canvas_height,
    )

    pixel_x_scale = value_scale(resolved_xscale, x_domain, (area.left, area.right), column=x, values=all_x)
    pixel_y_scale = value_scale(resolved_yscale, y_domain, (area.bottom, area.top), column=y, values=all_y)
    render_x_axis(
        document,
        pixel_x_scale,
        area,
        tick_count=ticks_for(area.width, TICK_SPACING_X),
        tick_length=resolved_theme.tick_size,
        font_size=resolved_theme.tick_label_font_size,
    )
    render_y_axis(
        document,
        pixel_y_scale,
        area,
        tick_count=ticks_for(area.height, TICK_SPACING_Y),
        tick_length=resolved_theme.tick_size,
        font_size=resolved_theme.tick_label_font_size,
    )

    radius_of = _radius_mapper([row[2] for row in all_rows], resolved_theme.marker_size) if size is not None else None

    series_classes: list[str] = []
    legend_entries: list[tuple[str, str]] = []
    for label, rows in series_rows:
        series_class = document.semantic_class("series")
        series_classes.append(series_class)
        for row in rows:
            xv, yv, sv = row
            radius = radius_of(sv) if radius_of is not None else resolved_theme.marker_size
            point = document.add_node(
                None,
                "circle",
                attrib={
                    "cx": format_coord(pixel_x_scale(xv)),
                    "cy": format_coord(pixel_y_scale(yv)),
                    "r": format_coord(radius),
                },
                classes=[series_class, "scatter-point"],
            )
            if tooltip:
                add_tooltip(document, point, _point_tooltip(x=x, y=y, size=size, hue=hue, row=row, label=label))
        if label is not None:
            legend_entries.append((str(label), series_class))

    legend_bottom = area.top
    if legend_entries:
        legend_bottom = (
            render_legend(
                document,
                legend_entries,
                x=area.right + LEGEND_X_OFFSET,
                y=area.top,
                mark_style="fill",
                font_size=resolved_theme.legend_font_size,
            )
            + _SIZE_LEGEND_GAP
        )
    if size is not None:
        _render_size_legend(
            document,
            [row[2] for row in all_rows],
            radius_of,
            x=area.right + LEGEND_X_OFFSET,
            y=legend_bottom,
            marker_class=series_classes[0],
        )

    render_theme_style(document, resolved_theme, series_classes, mark_style="fill")

    points = plural(len(all_rows), "point")
    description = describe(
        "Scatter plot",
        over([str(label) for label, _ in series_items] if hue is not None else None, points),
        span("x", *x_domain),
        span("y", *y_domain),
        _size_clause(size),
    )
    return Chart(document, label_data, description=description, domains=Domains(x=x_domain, y=y_domain))
