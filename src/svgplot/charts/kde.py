"""kdeplot — kernel density curves (delegates to svgplot.stats.kde).

Structurally ``histplot`` with the binning swapped for a density estimate, including the
part that matters most for comparison: ``histplot`` computes one set of bin edges across
every group so their bars land on the same boundaries, and this computes one evaluation
grid across every group for the same reason.
"""

from __future__ import annotations

from svgplot.chart._domain import Domains, apply_limit, narrows
from svgplot.chart.base import Chart
from svgplot.charts._axes import fit_left_margin, render_x_axis, render_y_axis
from svgplot.charts._density_grid import union_grid_range
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
from svgplot.stats.kde import KdeCurve, kde
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style

_PROBE_GRID = 2
"""Grid size for the pass that only needs a group's bandwidth.

The shared grid's span depends on every group's bandwidth, which is chosen from that
group's own values -- so the bandwidths have to be known before the grid exists. Two is
the smallest grid ``kde`` accepts, making this probe cost ~1% of the real evaluation
instead of running the estimator twice at full width.
"""


def _clean_values(columns: dict[str, list], x: str) -> list[float]:
    """Drop missing (``None``/NaN) values from column ``x``."""
    return [require_number(value, x) for value in columns[x] if not is_missing(value)]


def _shared_grid_range(
    series_values: list[tuple[object, list[float]]], bandwidth: float | str, cut: float
) -> tuple[float, float]:
    """The union of the spans each hue group would have chosen for itself.

    The rule, and the cost of sharing a grid at all, live in
    :mod:`~svgplot.charts._density_grid`; this passes ``_bandwidth_of`` so a failure names the
    hue group rather than the category ``violinplot`` would name.
    """
    return union_grid_range(series_values, lambda values, label: _bandwidth_of(values, label, bandwidth), cut)


def _bandwidth_of(values: list[float], label: object, bandwidth: float | str) -> float:
    """One group's bandwidth, with the group named in any failure.

    Otherwise a single bad group reports only "every value is 3.0" and the caller is left
    to work out which of their hue values that was.
    """
    try:
        return kde(values, bandwidth=bandwidth, grid=_PROBE_GRID).bandwidth
    except ValueError as error:
        raise ValueError(f"hue group {label!r}: {error}" if label is not None else str(error)) from error


def _curve_of(values: list[float], label: object, bandwidth: float | str, grid_range: tuple[float, float]) -> KdeCurve:
    """One group's density on the shared grid, with the group named in any failure."""
    try:
        return kde(values, bandwidth=bandwidth, grid_range=grid_range)
    except ValueError as error:
        raise ValueError(f"hue group {label!r}: {error}" if label is not None else str(error)) from error


def _curve_path(curve: KdeCurve, x_scale: LinearScale, y_scale: LinearScale, *, baseline: float, fill: bool) -> str:
    """The polyline through the density, closed down to the baseline when filling."""
    points = [f"{format_coord(x_scale(x))},{format_coord(y_scale(y))}" for x, y in zip(curve.x, curve.y, strict=True)]
    commands = [f"M {points[0]}", *(f"L {point}" for point in points[1:])]
    if fill:
        # Down to the axis at the right end, back along it, then Z -- so the closed region
        # is the area under the curve rather than the chord between its two ends.
        commands.append(f"L {format_coord(x_scale(curve.x[-1]))},{format_coord(baseline)}")
        commands.append(f"L {format_coord(x_scale(curve.x[0]))},{format_coord(baseline)}")
        commands.append("Z")
    return " ".join(commands)


def kdeplot(
    data: object,
    x: str,
    hue: str | None = None,
    *,
    bandwidth: float | str = "scott",
    fill: bool = False,
    width: float | None = None,
    height: float | None = None,
    theme: Theme | str | None = None,
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
) -> Chart:
    """Draw a kernel density estimate from long-form data.

    With ``hue=``, one curve per distinct hue value is drawn with an auto-generated
    legend. Every group is evaluated on **one shared x grid**, so the curves are directly
    comparable and a reader can trace a single vertical line across all of them.

    ``fill=True`` closes each curve down to the axis and draws it outlined -- a filled
    density with no outline loses its own edge where two groups overlap.

    ``bandwidth`` is passed to :func:`svgplot.stats.kde.kde` untouched, so its rules and
    its validation (including the refusal to pick a bandwidth for a zero-variance sample)
    apply here unchanged.

    ``xlim=``/``ylim=`` replace the domain this chart would compute from its own data. They
    exist so several charts can be made to agree -- see :func:`~svgplot.layout.facet.facet`,
    which uses them to give faceted panels one axis -- and replace rather than widen, so a
    caller asking for a narrower view gets one. Note that this chart's y domain is a
    **derived** quantity, not a column: nothing outside the chart could have computed it,
    which is why the domain is recorded on the returned chart rather than predicted.

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

    **There is no ``tooltip=``.** Ten charts have one; these six do not, and the reason is the
    same for all six: a series is drawn as **one** mark, so the only thing a ``<title>`` on it
    could say is the series name. With ``hue=`` the legend already says that, in the same
    colour, without the reader having to find and hold the pointer; without ``hue=`` there is
    no legend and no name to say. A tooltip earns its element when a mark is one row or one
    bin -- here it would repeat the legend, or repeat nothing.

    ``fill=True`` gives the curve an interior and so a real hit area, but not a second thing to
    say: the mark is still the whole series.

    Raises:
        KeyError: if ``x``/``hue`` isn't a column in ``data``, or if ``theme`` is a string
            that isn't a registered preset name.
        TypeError: if ``theme`` is neither a ``Theme``, a preset name, nor ``None``.
        ValueError: if ``data`` has no rows, if no rows have a non-missing ``x`` value, or
            (via ``stats.kde``) for anything that module rejects — an unusable bandwidth,
            a group with fewer than two values, or a group with no spread.
    """
    resolved_theme = resolve_theme(theme)
    longform = ingest_longform(data, x)
    if len(longform) == 0:
        raise ValueError("data must contain at least one row")

    series_items = build_series(data, longform.columns, hue)

    series_values = [(label, _clean_values(columns, x)) for label, columns in series_items]
    if not any(values for _, values in series_values):
        raise ValueError("no rows with a non-missing x value after dropping missing values")

    cut = 3.0
    grid_range = _shared_grid_range(series_values, bandwidth, cut)
    series_curves = [(label, _curve_of(values, label, bandwidth, grid_range)) for label, values in series_values]
    peak = max(value for _, curve in series_curves for value in curve.y)

    clipped = narrows(grid_range, xlim) or narrows((0.0, peak), ylim)
    x_domain = apply_limit(grid_range, xlim)
    y_domain = apply_limit((0.0, peak), ylim)
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
    mark_style = "outlined" if fill else "stroke"
    series_classes: list[str] = []
    legend_entries: list[tuple[str, str]] = []
    for label, curve in series_curves:
        series_class = document.semantic_class("series")
        series_classes.append(series_class)
        path = _curve_path(curve, pixel_x_scale, pixel_y_scale, baseline=area.bottom, fill=fill)
        document.add_node(viewport, "path", attrib={"d": path}, classes=[series_class, "kde-series"])
        if label is not None:
            legend_entries.append((str(label), series_class))

    if legend_entries:
        # The legend takes the swatch *shape*, not the series' mark style: it only knows
        # "stroke" (a line) and "fill" (a rect). An outlined curve reads as a filled swatch
        # -- the outlined CSS rule sets stroke, fill and fill-opacity, so the rect shows all
        # three. Passing "outlined" straight through is a ValueError from render_legend.
        render_legend(
            document,
            legend_entries,
            x=area.right + LEGEND_X_OFFSET,
            y=area.top,
            mark_style="fill" if fill else "stroke",
            font_size=resolved_theme.legend_font_size,
        )

    render_theme_style(document, resolved_theme, series_classes, mark_style=mark_style)

    observations = plural(sum(len(values) for _, values in series_values), "observation")
    description = describe(
        "Density plot",
        over([str(label) for label, _ in series_items] if hue is not None else None, observations),
        span("x", *grid_range),
        span("density", 0.0, peak),
    )
    return Chart(document, description=description, domains=Domains(x=x_domain, y=y_domain))
