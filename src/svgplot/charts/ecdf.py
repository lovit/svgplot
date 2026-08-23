"""ecdfplot — empirical cumulative distribution, drawn as a step line.

No statistical machinery is needed here: the ECDF is a sort plus a running
count, so unlike ``histplot``/``boxplot`` this module consumes nothing from
``svgplot.stats``.
"""

from __future__ import annotations

from svgplot.chart._domain import Domains, apply_limit, narrows
from svgplot.chart.base import Chart
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
    marks_viewport,
    new_canvas,
    resolve_size,
    ticks_for,
)
from svgplot.charts._legend import render_legend
from svgplot.charts._series import series_items as build_series
from svgplot.charts._theme_resolve import resolve_theme
from svgplot.data._missing import is_missing, require_number
from svgplot.data.ingest import ingest_longform
from svgplot.scales import LinearScale
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style

STATS = ("proportion", "count")
"""What the y axis measures: a 0-1 proportion of the sample, or a raw running count."""


def _clean_values(columns: dict[str, list], x: str) -> list[float]:
    """Drop missing (``None``/NaN) values from column ``x``."""
    return [require_number(v, x) for v in columns[x] if not is_missing(v)]


def _cumulative_steps(values: list[float]) -> list[tuple[float, int]]:
    """Distinct values ascending, each paired with how many values are <= it.

    Ties collapse into one entry: ``[1, 1, 2]`` gives ``[(1, 2), (2, 3)]``. Emitting a
    step per *value* instead would put two risers of 1/n at the same x, which renders
    as a doubled vertical segment (two overlapping line commands) rather than the
    single riser of 2/n the distribution actually has.
    """
    steps: list[tuple[float, int]] = []
    # Sorted, so a value's 1-based position *is* the number of values <= it.
    for cumulative, value in enumerate(sorted(values), start=1):
        if steps and steps[-1][0] == value:
            steps[-1] = (value, cumulative)
        else:
            steps.append((value, cumulative))
    return steps


def _step_vertices(steps: list[tuple[float, int]], *, count: int, stat: str, complementary: bool) -> list[tuple[float, float]]:
    """Turn cumulative steps into the polyline vertices of the staircase.

    The curve starts at the leftmost observation rather than at the axis edge, so the
    line spans exactly the observed range and no x value is implied that isn't in the
    data. Each distinct value then contributes a horizontal tread to its x followed by
    a vertical riser to its new height.
    """
    top = float(count) if stat == "count" else 1.0

    def height(cumulative: int) -> float:
        reached = float(cumulative) if stat == "count" else cumulative / count
        return top - reached if complementary else reached

    vertices: list[tuple[float, float]] = [(steps[0][0], top if complementary else 0.0)]
    for value, cumulative in steps:
        if value != vertices[-1][0]:
            vertices.append((value, vertices[-1][1]))  # tread across to this x
        vertices.append((value, height(cumulative)))  # riser to the new height
    return vertices


def _path_data(points: list[tuple[float, float]]) -> str:
    commands = [f"M {format_coord(points[0][0])},{format_coord(points[0][1])}"]
    commands.extend(f"L {format_coord(px)},{format_coord(py)}" for px, py in points[1:])
    return " ".join(commands)


def ecdfplot(
    data: object,
    x: str,
    hue: str | None = None,
    *,
    stat: str = "proportion",
    complementary: bool = False,
    width: float | None = None,
    height: float | None = None,
    theme: Theme | str | None = None,
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
) -> Chart:
    """Draw an empirical cumulative distribution from long-form data.

    Every observation contributes one riser, so the staircase reaches 1.0 (or ``n``
    under ``stat="count"``) at the largest value. With ``hue=``, one staircase per
    distinct hue value is drawn with an auto-generated legend; under
    ``stat="count"`` the groups share one y axis scaled to the largest group, so
    their heights stay directly comparable.

    ``complementary=True`` plots the survival function ``1 - F`` instead, descending
    from the top to zero.

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

    ``theme=`` takes a :class:`~svgplot.theme.base.Theme`, the name of a preset
    (``"light"``, ``"dark"``, ``"minimal"``, ``"high_contrast"``, ``"print"``), or ``None``
    for the default theme. Fonts, line widths, opacities, the grid/spine/tick colours and --
    where a chart has series -- the palette all come from it. No render reads or writes global
    style state, so two charts given the same ``Theme`` are styled alike no matter what was
    drawn in between.

    ``x`` names the numeric column the distribution is taken over -- the only data column
    this chart needs, since the y axis is computed from the values rather than read.

    **There is no ``tooltip=``.** Ten charts have one; these six do not, and the reason is the
    same for all six: a series is drawn as **one** mark, so the only thing a ``<title>`` on it
    could say is the series name. With ``hue=`` the legend already says that, in the same
    colour, without the reader having to find and hold the pointer; without ``hue=`` there is
    no legend and no name to say. A tooltip earns its element when a mark is one row or one
    bin -- here it would repeat the legend, or repeat nothing.

    Raises:
        KeyError: if ``x``/``hue`` isn't a column in ``data``, or if ``theme`` is a
            string that isn't a registered preset name.
        TypeError: if ``theme`` is neither a ``Theme``, a preset name, nor ``None``.
        ValueError: if ``stat`` isn't one of :data:`STATS`, if ``data`` has no rows,
            or if no rows have a non-missing ``x`` value.
    """
    if stat not in STATS:
        raise ValueError(f"stat must be one of {STATS}, got {stat!r}")

    resolved_theme = resolve_theme(theme)
    longform = ingest_longform(data, x)
    if len(longform) == 0:
        raise ValueError("data must contain at least one row")

    series_items = build_series(data, longform.columns, hue)

    series_values = [(label, _clean_values(columns, x)) for label, columns in series_items]
    all_values = [value for _, values in series_values for value in values]
    if not all_values:
        raise ValueError("no rows with a non-missing x value after dropping missing values")

    x_domain = (min(all_values), max(all_values))
    y_top = max(len(values) for _, values in series_values) if stat == "count" else 1.0
    y_domain = (0.0, float(y_top))
    clipped = narrows(x_domain, xlim) or narrows(y_domain, ylim)
    x_domain = apply_limit(x_domain, xlim)
    y_domain = apply_limit(y_domain, ylim)

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

    pixel_x_scale = LinearScale(x_domain, (area.left, area.right))
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

    viewport = marks_viewport(document, area, clipped=clipped)
    series_classes: list[str] = []
    legend_entries: list[tuple[str, str]] = []
    for label, values in series_values:
        series_class = document.semantic_class("series")
        series_classes.append(series_class)
        if values:
            vertices = _step_vertices(_cumulative_steps(values), count=len(values), stat=stat, complementary=complementary)
            pixels = [(pixel_x_scale(vx), pixel_y_scale(vy)) for vx, vy in vertices]
            document.add_node(viewport, "path", attrib={"d": _path_data(pixels)}, classes=[series_class, "ecdf-series"])
        if label is not None:
            legend_entries.append((str(label), series_class))

    if legend_entries:
        render_legend(
            document,
            legend_entries,
            x=area.right + LEGEND_X_OFFSET,
            y=area.top,
            font_size=resolved_theme.legend_font_size,
        )

    render_theme_style(document, resolved_theme, series_classes)

    observations = plural(len(all_values), "observation")
    description = describe(
        "Complementary cumulative distribution plot" if complementary else "Cumulative distribution plot",
        over([str(label) for label, _ in series_items] if hue is not None else None, observations),
        span("x", *x_domain),
        span(stat, *y_domain),
    )
    return Chart(document, description=description, domains=Domains(x=x_domain, y=y_domain))
