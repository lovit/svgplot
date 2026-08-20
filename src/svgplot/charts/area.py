"""areaplot — filled area charts (fill_between-style), with an optional stacked mode.

Reuses charts/line.py's overall shape (SvgDocument -> plot area -> scales ->
axes -> per-series marks -> legend -> theme.css style block -> Chart) — see
that module for the fuller rationale of the shared pieces this also uses
(charts/_axes.py, _legend.py, _layout.py, _theme_resolve.py, theme/css.py).
Marks are filled (``mark_style="fill"``), unlike lineplot's stroked paths.
"""

from __future__ import annotations

from collections.abc import Callable

from svgplot.chart._domain import Domains, apply_limit
from svgplot.chart.base import Chart
from svgplot.charts._aggregate import Estimator, apply_estimator, resolve_estimator
from svgplot.charts._axes import fit_left_margin, render_x_axis, render_y_axis
from svgplot.charts._describe import describe, over, plural, span
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
from svgplot.charts._legend import render_legend
from svgplot.charts._series import series_items as build_series
from svgplot.charts._theme_resolve import resolve_theme
from svgplot.data.ingest import ingest_longform
from svgplot.scales import LinearScale
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style


def _series_points(
    columns: dict[str, list], x: str, y: str, estimate: Callable[[list[float]], float] | None
) -> list[tuple[float, float]]:
    """Drop rows with a missing x or y value, fold any rows sharing an x, then sort
    by x (mirrors ``charts/line.py``'s ``_series_points`` — no datetime x support
    here, this issue's AC doesn't call for it).

    An area is a function of x: exactly one filled height per x. Rows sharing an x
    are therefore folded into one point rather than kept as separate vertices, and
    the aggregation happens here so the stacked and unstacked paths — which both
    build on this — can never disagree about what a repeated x means.

    ``estimate=None`` sums, which is the rule this chart has always used and the reason
    it never warns: nothing is discarded, so there is nothing to advise about. An explicit
    ``estimator="sum"`` folds with ``math.fsum`` instead, and a test pins that the two
    produce byte-identical SVG -- CPython 3.12+ already compensates ``sum()`` over floats,
    so writing the historical rule out by name is documentation, not a behaviour change.
    """
    groups: dict[float, list[float]] = {}
    for xv, yv in zip(columns[x], columns[y], strict=True):
        if xv is None or yv is None or (isinstance(yv, float) and yv != yv):
            continue
        groups.setdefault(float(xv), []).append(float(yv))
    if estimate is None:
        return sorted((key, sum(values)) for key, values in groups.items())
    return sorted((key, apply_estimator(estimate, values, group=str(key))) for key, values in groups.items())


def _closed_path_data(xs: list[float], ys: list[float], baseline_y: float) -> str:
    """A single unstacked series' filled area: the point path, then closed down
    to the baseline and back to the start — the baseline is data-space y=0,
    mapped through the y scale (so it sits at the plot area's bottom only when
    0 is also the y domain's minimum, which ``areaplot`` always ensures by
    including 0 in the domain).
    """
    if not xs:
        return ""
    commands = [f"M {format_coord(xs[0])},{format_coord(ys[0])}"]
    commands.extend(f"L {format_coord(px)},{format_coord(py)}" for px, py in zip(xs[1:], ys[1:], strict=True))
    commands.append(f"L {format_coord(xs[-1])},{format_coord(baseline_y)}")
    commands.append(f"L {format_coord(xs[0])},{format_coord(baseline_y)}")
    commands.append("Z")
    return " ".join(commands)


def _stacked_band_path_data(xs: list[float], tops: list[float], bottoms: list[float]) -> str:
    """A stacked series' filled band: along its own cumulative top edge left-to-right,
    then back along the previous series' cumulative top (this series' bottom edge)
    right-to-left, closing the shape.
    """
    if not xs:
        return ""
    commands = [f"M {format_coord(xs[0])},{format_coord(tops[0])}"]
    commands.extend(f"L {format_coord(px)},{format_coord(py)}" for px, py in zip(xs[1:], tops[1:], strict=True))
    for px, py in zip(reversed(xs), reversed(bottoms), strict=True):
        commands.append(f"L {format_coord(px)},{format_coord(py)}")
    commands.append("Z")
    return " ".join(commands)


def areaplot(
    data: object,
    x: str,
    y: str,
    hue: str | None = None,
    *,
    stacked: bool = False,
    estimator: Estimator | None = None,
    width: float | None = None,
    height: float | None = None,
    theme: Theme | str | None = None,
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
    xscale: str = "linear",
) -> Chart:
    """Draw a filled area chart from long-form data.

    With ``hue=``, one area per distinct hue value is drawn (colors cycling
    through the theme's palette) with an auto-generated legend. With
    ``stacked=True`` and ``hue=``, areas stack cumulatively instead of each
    starting at the baseline — the shared x axis is the union of every hue
    group's x values, and a (hue, x) pair absent from a group counts as 0 for
    that group's contribution to the stack. ``stacked=True`` without ``hue=``
    has nothing to stack and renders as a single plain area.

    Rows sharing an x within one series are **summed** into a single point — an
    area has one filled height per x, so two records at the same x contribute
    their combined value there. This holds identically in stacked and unstacked
    mode.

    ``xlim=``/``ylim=`` replace the domain this chart would compute from its own data. They
    exist so several charts can be made to agree -- see :func:`~svgplot.layout.facet.facet`,
    which uses them to give faceted panels one axis -- and replace rather than widen, so a
    caller asking for a narrower view gets one.

    ``estimator=`` replaces that sum: ``"mean"``/``"median"``/``"sum"``, or any callable
    taking the group's values in row order and returning a number. The default stays
    ``None`` (the historical sum) so no existing chart changes — see
    ``charts/_aggregate.py``. Nothing is discarded on either path, so unlike ``barplot``
    this chart never warns about repeated x values.

    ``width``/``height`` set the canvas in pixels; ``None`` (the default) means 800x600, so a
    call that does not mention them is byte-identical to one written before they existed. The
    margin presets shrink to keep the plot area the majority of a small canvas and the tick
    count follows the plot extent — see ``charts/_layout.py``. Canvases below 240x180 are
    refused rather than clamped, and a chart may refuse a larger one if its own legend does
    not fit.

    ``xscale=`` chooses the x axis' scale: ``"linear"`` (the default) or ``"log"``. Values at
    or below zero are **refused by column name** rather than masked or clipped: a logarithm is
    undefined there, and both alternatives silently draw a different chart than the data.

    There is no ``yscale=``. An area chart's filled region *is* the quantity, measured from
    zero -- which is why ``0.0`` is forced into the y domain a few lines below. A log axis has
    no zero to measure from, so the fill would have to start somewhere arbitrary and its area
    would stop being proportional to anything. That is not an area chart with a log axis; it
    is a different chart, and offering the argument would only let a caller ask for it and get
    a refusal about their data instead of an answer about the shape.

    Raises:
        KeyError: if ``x``/``y``/``hue`` isn't a column in ``data``, or if ``theme``
            is a string that isn't a registered preset name.
        TypeError: if ``theme`` is neither a ``Theme``, a preset name, nor ``None``.
        ValueError: if ``data`` has no rows, if no rows survive after dropping
            rows with a missing x or y value, or if ``estimator`` is an unknown name or
            returns a value that can't be plotted.
        TypeError: if ``estimator`` is neither a name, a callable, nor ``None``.
    """
    resolved_theme = resolve_theme(theme)
    longform = ingest_longform(data, x, y)
    if len(longform) == 0:
        raise ValueError("data must contain at least one row")

    series_items = build_series(data, longform.columns, hue)

    estimate = resolve_estimator(estimator)
    series_points = [(label, _series_points(columns, x, y, estimate)) for label, columns in series_items]

    all_x = [point[0] for _, points in series_points for point in points]
    all_y = [point[1] for _, points in series_points for point in points]
    if not all_x:
        raise ValueError("no rows with both x and y present after dropping missing values")

    do_stack = stacked and hue is not None

    stacked_bands: list[tuple[object, list[float], list[float], list[float]]] = []
    if do_stack:
        x_union = sorted(set(all_x))
        cumulative = [0.0] * len(x_union)
        for label, points in series_points:
            # Safe as a dict: _series_points already collapsed repeated x values,
            # so nothing here can be silently overwritten.
            lookup = dict(points)
            values = [lookup.get(xv, 0.0) for xv in x_union]
            bottoms = list(cumulative)
            cumulative = [c + v for c, v in zip(cumulative, values, strict=True)]
            stacked_bands.append((label, x_union, bottoms, list(cumulative)))
        x_domain = (x_union[0], x_union[-1])
        y_domain_values = [0.0, *cumulative]
    else:
        x_domain = (min(all_x), max(all_x))
        y_domain_values = [0.0, *all_y]

    y_domain = (min(y_domain_values), max(y_domain_values))
    x_domain = apply_limit(x_domain, xlim)
    y_domain = apply_limit(y_domain, ylim)

    resolved_xscale = resolve_axis_scale(xscale, parameter="xscale")
    canvas_width, canvas_height = resolve_size(width, height)
    document, area = new_canvas(
        fit_margin(
            fit_left_margin(
                MARGIN_WITH_LEGEND if hue is not None else MARGIN_WITHOUT_LEGEND,
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
    pixel_y_scale = LinearScale(y_domain, (area.bottom, area.top))
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

    baseline_y = pixel_y_scale(0.0)
    series_classes: list[str] = []
    legend_entries: list[tuple[str, str]] = []

    if do_stack:
        for label, xs, bottoms, tops in stacked_bands:
            series_class = document.semantic_class("series")
            series_classes.append(series_class)
            pixel_xs = [pixel_x_scale(value) for value in xs]
            pixel_tops = [pixel_y_scale(value) for value in tops]
            pixel_bottoms = [pixel_y_scale(value) for value in bottoms]
            document.add_node(
                None,
                "path",
                attrib={"d": _stacked_band_path_data(pixel_xs, pixel_tops, pixel_bottoms)},
                classes=[series_class, "area-series"],
            )
            if label is not None:
                legend_entries.append((str(label), series_class))
    else:
        for label, points in series_points:
            series_class = document.semantic_class("series")
            series_classes.append(series_class)
            if points:
                pixel_xs = [pixel_x_scale(px) for px, _ in points]
                pixel_ys = [pixel_y_scale(py) for _, py in points]
                document.add_node(
                    None,
                    "path",
                    attrib={"d": _closed_path_data(pixel_xs, pixel_ys, baseline_y)},
                    classes=[series_class, "area-series"],
                )
            if label is not None:
                legend_entries.append((str(label), series_class))

    if legend_entries:
        render_legend(
            document,
            legend_entries,
            x=area.right + LEGEND_X_OFFSET,
            y=area.top,
            mark_style="fill",
            font_size=resolved_theme.legend_font_size,
        )

    render_theme_style(document, resolved_theme, series_classes, mark_style="fill")

    points = plural(len(all_x), "point")
    description = describe(
        "Stacked area chart" if do_stack else "Area chart",
        over([str(label) for label, _ in series_items] if hue is not None else None, points),
        span("x", *x_domain),
        span("y", *y_domain),
    )
    return Chart(document, description=description, domains=Domains(x=x_domain, y=y_domain))
