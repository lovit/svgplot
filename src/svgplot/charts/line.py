"""lineplot — line charts, including time-axis (a scales.TimeScale option, not a separate chart type).

The reference chart-type implementation (issue #12): the first code in this
package that renders actual visual output (axes/marks/legend) via
``svgplot._svg.SvgDocument``, and the first consumer of ``svgplot.theme.Theme``
in a real render. ``charts/_layout.py``/``charts/_axes.py``/``charts/_legend.py``
and ``theme/css.py`` (all introduced alongside this file) are the shared
rendering infrastructure every later chart-type issue (#13-18) is expected to
reuse rather than duplicate.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from svgplot.chart._domain import Domains, apply_limit
from svgplot.chart.base import Chart
from svgplot.charts._aggregate import Estimator, apply_estimator, resolve_estimator
from svgplot.charts._axes import fit_left_margin, render_x_axis, render_y_axis
from svgplot.charts._layout import (
    DEFAULT_WIDTH,
    LEGEND_X_OFFSET,
    MARGIN_WITH_LEGEND,
    MARGIN_WITHOUT_LEGEND,
    format_coord,
    new_canvas,
)
from svgplot.charts._legend import render_legend
from svgplot.charts._series import series_items as build_series
from svgplot.charts._theme_resolve import resolve_theme
from svgplot.data._missing import is_missing
from svgplot.data.ingest import ingest_longform
from svgplot.labels._source import collect_label_data
from svgplot.labels.spec import LabelSpec
from svgplot.scales import LinearScale, TimeScale
from svgplot.stats.interpolate import interpolate as interpolate_curve
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style


def _numeric_x(value: object) -> float:
    return value.timestamp() if isinstance(value, datetime) else float(value)


def _series_points(
    columns: dict[str, list], x: str, y: str, estimate: Callable[[list[float]], float] | None
) -> list[tuple[object, float]]:
    """Drop rows with a missing x or y value, then sort by x — a line connects
    points in x order regardless of the input rows' original order.

    ``estimate=None`` keeps every row as its own vertex, which is this chart's historical
    rule: two rows sharing an x draw a vertical segment between them. Nothing is lost that
    way, which is why ``lineplot`` never warns about repeated x values — unlike
    ``barplot``, whose rule discards them.

    With an estimator, rows sharing an x fold into one vertex. "Sharing an x" means the
    values are **equal**, not that they happen to land on the same pixel — grouping is by
    the raw x value rather than by ``_numeric_x``. Two reasons, and the first is the one
    that decides it: the default path already treats ``"1"`` and ``1.0`` as two x values
    (they are two dict keys, two vertices), so folding them here would make ``estimator=``
    quietly change *which rows are the same row*, not just how they combine. The second is
    that ``_numeric_x`` sends a naive ``datetime`` through ``timestamp()``, which reads the
    machine's local timezone — so a naive and an aware datetime would fold together on a
    UTC machine and stay apart everywhere else.
    """
    points = [
        (xv, float(yv)) for xv, yv in zip(columns[x], columns[y], strict=True) if not is_missing(xv) and not is_missing(yv)
    ]
    if estimate is not None:
        groups: dict[object, list[float]] = {}
        for xv, yv in points:
            groups.setdefault(xv, []).append(yv)
        points = [(xv, apply_estimator(estimate, values, group=str(xv))) for xv, values in groups.items()]
    return sorted(points, key=lambda point: _numeric_x(point[0]))


def _path_data(xs: list[float], ys: list[float]) -> str:
    if not xs:
        return ""
    commands = [f"M {format_coord(xs[0])},{format_coord(ys[0])}"]
    commands.extend(f"L {format_coord(px)},{format_coord(py)}" for px, py in zip(xs[1:], ys[1:], strict=True))
    return " ".join(commands)


def lineplot(
    data: object,
    x: str,
    y: str,
    hue: str | None = None,
    *,
    interpolate: str = "linear",
    estimator: Estimator | None = None,
    info: LabelSpec | list[tuple[str, str]] | None = None,
    theme: Theme | str | None = None,
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
) -> Chart:
    """Draw a line chart from long-form data.

    With ``hue=``, one line per distinct hue value is drawn (colors cycling
    through the theme's palette) with an auto-generated legend. Datetime ``x``
    values automatically use a time axis (``scales.TimeScale``) instead of a
    linear one. ``interpolate="linear"`` (the default) connects the raw points
    with straight segments; any other value is passed to
    ``stats.interpolate.interpolate`` as its ``method=`` (e.g. ``"cubic"``) to
    smooth the line — see that function for the full set of supported methods
    and its own validation of ``method``/point-count/finiteness.

    ``xlim=``/``ylim=`` replace the domain this chart would compute from its own data. They
    exist so several charts can be made to agree -- see :func:`~svgplot.layout.facet.facet`,
    which uses them to give faceted panels one axis -- and replace rather than widen, so a
    caller asking for a narrower view gets one.

    ``estimator=`` folds rows that share an x into one vertex: ``"mean"``/``"median"``/
    ``"sum"``, or any callable taking the group's values in row order and returning a
    number. The default, ``None``, keeps this chart's historical rule — every row is its
    own vertex, so two rows at the same x draw a vertical segment. Nothing is discarded
    either way, so this chart never warns; see ``charts/_aggregate.py``.

    ``estimator=`` and ``info=`` cannot be combined. The footnote table exists on exactly
    the charts where one input row is one mark, and an estimator is the thing that breaks
    that: the table would list rows the chart no longer drew, which is the same
    contradiction that keeps ``info=`` off ``barplot``/``areaplot``/``boxplot``/``histplot``
    in the first place.

    Raises:
        KeyError: if ``x``/``y``/``hue`` isn't a column in ``data``, or if ``theme``
            is a string that isn't a registered preset name.
        TypeError: if ``theme`` is neither a ``Theme``, a preset name, nor ``None``.
        ValueError: if ``data`` has no rows, or (via ``stats.interpolate``) if
            ``interpolate`` isn't a recognized method name, if a series has too few
            points to interpolate, if ``estimator`` is an unknown name or returns a value
            that can't be plotted, or if ``estimator`` and ``info`` are both given.
        TypeError: if ``estimator`` is neither a name, a callable, nor ``None``.
    """
    if estimator is not None and info is not None:
        raise ValueError(
            "estimator= and info= cannot be combined: the footnote table lists one row per mark, "
            "and an estimator folds several rows into one"
        )
    estimate = resolve_estimator(estimator)
    resolved_theme = resolve_theme(theme)
    longform = ingest_longform(data, x, y)
    if len(longform) == 0:
        raise ValueError("data must contain at least one row")

    series_items = build_series(data, longform.columns, hue)

    series_points = [(label, _series_points(columns, x, y, estimate)) for label, columns in series_items]

    all_x = [point[0] for _, points in series_points for point in points]
    all_y = [point[1] for _, points in series_points for point in points]
    if not all_x:
        raise ValueError("no rows with both x and y present after dropping missing values")
    is_time = isinstance(all_x[0], datetime)
    numeric_x_domain = (min(_numeric_x(v) for v in all_x), max(_numeric_x(v) for v in all_x))
    y_domain = (min(all_y), max(all_y))
    numeric_x_domain = apply_limit(numeric_x_domain, xlim)
    y_domain = apply_limit(y_domain, ylim)

    # After the checks above, so a bad column still reports the chart's own error first.
    label_data = collect_label_data(data, info, required=(x, y, hue))

    document, area = new_canvas(
        fit_left_margin(
            MARGIN_WITH_LEGEND if hue is not None else MARGIN_WITHOUT_LEGEND,
            y_domain,
            width=DEFAULT_WIDTH,
            font_size=resolved_theme.tick_label_font_size,
        )
    )

    pixel_x_scale = LinearScale(numeric_x_domain, (area.left, area.right))
    pixel_y_scale = LinearScale(y_domain, (area.bottom, area.top))
    tick_x_scale = (
        TimeScale(
            (datetime.fromtimestamp(numeric_x_domain[0]), datetime.fromtimestamp(numeric_x_domain[1])), (area.left, area.right)
        )
        if is_time
        else pixel_x_scale
    )
    render_x_axis(
        document, tick_x_scale, area, tick_length=resolved_theme.tick_size, font_size=resolved_theme.tick_label_font_size
    )
    render_y_axis(
        document, pixel_y_scale, area, tick_length=resolved_theme.tick_size, font_size=resolved_theme.tick_label_font_size
    )

    series_classes: list[str] = []
    legend_entries: list[tuple[str, str]] = []
    for label, points in series_points:
        series_class = document.semantic_class("series")
        series_classes.append(series_class)
        if points:
            raw_x = [_numeric_x(px) for px, _ in points]
            raw_y = [py for _, py in points]
            if interpolate == "linear":
                curve_x, curve_y = raw_x, raw_y
            else:
                curve = interpolate_curve(raw_x, raw_y, method=interpolate)
                curve_x, curve_y = curve.x, curve.y
            pixel_xs = [pixel_x_scale(value) for value in curve_x]
            pixel_ys = [pixel_y_scale(value) for value in curve_y]
            document.add_node(
                None, "path", attrib={"d": _path_data(pixel_xs, pixel_ys)}, classes=[series_class, "line-series"]
            )
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

    return Chart(document, label_data, domains=Domains(x=numeric_x_domain, y=y_domain))
