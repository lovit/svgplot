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

from datetime import date, datetime

from svgplot._svg import SvgDocument
from svgplot.chart.base import Chart
from svgplot.charts._axes import render_x_axis, render_y_axis
from svgplot.charts._layout import (
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    LEGEND_X_OFFSET,
    MARGIN_WITH_LEGEND,
    MARGIN_WITHOUT_LEGEND,
    format_coord,
    plot_area,
)
from svgplot.charts._legend import render_legend
from svgplot.charts._theme_resolve import resolve_theme
from svgplot.data._missing import is_missing
from svgplot.data.ingest import ingest_longform
from svgplot.data.semantic import extract_channels
from svgplot.labels._source import collect_label_data
from svgplot.labels.spec import LabelSpec
from svgplot.scales import LinearScale, TimeScale
from svgplot.stats.interpolate import interpolate as interpolate_curve
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style


def _as_datetime(value: object) -> datetime:
    """A ``date`` promoted to midnight, a ``datetime`` unchanged.

    ``datetime`` is a subclass of ``date``, which is why the check reads this way round and
    why ``isinstance(value, datetime)`` alone silently missed every plain ``date`` -- the
    commonest thing a CSV or a pandas column holds. The two mix freely in one column for the
    same reason: promoting is lossless, and a column of dates with one timestamp in it is a
    real shape, not a mistake worth refusing.
    """
    return value if isinstance(value, datetime) else datetime(value.year, value.month, value.day)  # type: ignore[union-attr]


def _is_time_axis(values: list[object], column: str) -> bool:
    """Whether ``column`` holds dates, and therefore wants a time axis.

    Returns ``bool`` rather than the promoted values because nothing needs them: the domain
    is computed by :func:`_numeric_x`, which promotes as it goes. An earlier version built
    and returned a ``list[datetime]`` that every caller threw away.

    Raises:
        ValueError: if the column mixes dates with values that are *numbers*. Anything else
            mixed in -- a ``str``, a ``time`` -- is refused earlier, by :func:`_numeric_x`
            during the sort, and reported by type rather than as a mixture. Both messages
            name the column, which is the part that matters.
    """
    dated = [value for value in values if isinstance(value, date)]
    if not dated:
        return False
    if len(dated) != len(values):
        others = sorted({type(value).__name__ for value in values if not isinstance(value, date)})
        raise ValueError(f"column {column!r} mixes dates with {', '.join(others)}; a time axis needs dates throughout")
    return True


def _numeric_x(value: object, column: str) -> float:
    """``value`` as a number the x axis can position, or a ``ValueError`` naming the column.

    The column name is threaded through rather than added by the caller because the first
    call happens while *sorting*, before the chart has looked at the domain -- so a bad value
    surfaced as ``TypeError: float() argument must be a string or a real number, not
    'datetime.time'``, from inside a ``sorted`` key, naming neither the column nor what to do
    about it.
    """
    if isinstance(value, date):
        try:
            return _as_datetime(value).timestamp()
        except (OverflowError, ValueError, OSError):
            # ``timestamp()`` probes around the value to resolve the local offset, so both
            # ends of the representable range are unreachable whatever this package does --
            # the last hours before ``datetime.max`` and, in a timezone west of UTC, the first
            # after ``datetime.min``. A raw "year 10000 is out of range" names neither the
            # column nor the reason, and saying "too close to datetime.max" points at the
            # wrong end for half of them.
            raise ValueError(
                f"column {column!r} holds {value!r}, which is outside the range timestamp() can place on a time axis"
            ) from None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValueError(f"column {column!r} holds {type(value).__name__}, which has no position on an x axis") from None


def _series_points(columns: dict[str, list], x: str, y: str) -> list[tuple[object, float]]:
    """Drop rows with a missing x or y value, then sort by x — a line connects
    points in x order regardless of the input rows' original order.
    """
    points = [
        (xv, float(yv)) for xv, yv in zip(columns[x], columns[y], strict=True) if not is_missing(xv) and not is_missing(yv)
    ]
    return sorted(points, key=lambda point: _numeric_x(point[0], x))


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
    info: LabelSpec | list[tuple[str, str]] | None = None,
    theme: Theme | str | None = None,
) -> Chart:
    """Draw a line chart from long-form data.

    With ``hue=``, one line per distinct hue value is drawn (colors cycling
    through the theme's palette) with an auto-generated legend.

    An ``x`` column of ``datetime.date`` or ``datetime.datetime`` values automatically uses a
    time axis (``scales.TimeScale``) instead of a linear one, and its tick labels take their
    resolution from the domain -- clock time inside a day, dates across days, year-month
    across months, years beyond that. A ``date`` is read as midnight, and a column holding
    both kinds is promoted the same way rather than refused: promoting is lossless, and a
    column of dates with one timestamp in it is an ordinary shape.

    ``interpolate="linear"`` (the default) connects the raw points
    with straight segments; any other value is passed to
    ``stats.interpolate.interpolate`` as its ``method=`` (e.g. ``"cubic"``) to
    smooth the line — see that function for the full set of supported methods
    and its own validation of ``method``/point-count/finiteness.

    Raises:
        ValueError: if ``x`` holds a type with no position on an axis (``datetime.time`` is
            a time of day with no day, so two values a week apart are the same point), if it
            mixes dates with numbers, or if a value sits too close to ``datetime.max`` for
            ``timestamp()`` to place. Every one of these names the column.
        KeyError: if ``x``/``y``/``hue`` isn't a column in ``data``, or if ``theme``
            is a string that isn't a registered preset name.
        TypeError: if ``theme`` is neither a ``Theme``, a preset name, nor ``None``.
        ValueError: if ``data`` has no rows, or (via ``stats.interpolate``) if
            ``interpolate`` isn't a recognized method name or a series has too few
            points to interpolate.
    """
    resolved_theme = resolve_theme(theme)
    longform = ingest_longform(data, x, y)
    if len(longform) == 0:
        raise ValueError("data must contain at least one row")

    if hue is not None:
        groups = extract_channels(data, hue=hue)
        if not groups:
            raise ValueError(f"no rows with a non-missing {hue!r} value")
        series_items = sorted(groups.items(), key=lambda item: str(item[0]))
    else:
        series_items = [(None, longform.columns)]

    series_points = [(label, _series_points(columns, x, y)) for label, columns in series_items]

    all_x = [point[0] for _, points in series_points for point in points]
    all_y = [point[1] for _, points in series_points for point in points]
    if not all_x:
        raise ValueError("no rows with both x and y present after dropping missing values")
    is_time = _is_time_axis(all_x, x)
    numeric_x_domain = (min(_numeric_x(v, x) for v in all_x), max(_numeric_x(v, x) for v in all_x))
    y_domain = (min(all_y), max(all_y))

    # After the checks above, so a bad column still reports the chart's own error first.
    label_data = collect_label_data(data, info, required=(x, y, hue))

    document = SvgDocument(width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT)
    area = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=MARGIN_WITH_LEGEND if hue is not None else MARGIN_WITHOUT_LEGEND)
    document.add_node(
        None,
        "rect",
        attrib={"x": 0, "y": 0, "width": format_coord(DEFAULT_WIDTH), "height": format_coord(DEFAULT_HEIGHT)},
        classes=["plot-background"],
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
    render_x_axis(document, tick_x_scale, area, tick_length=resolved_theme.tick_size)
    render_y_axis(document, pixel_y_scale, area, tick_length=resolved_theme.tick_size)

    series_classes: list[str] = []
    legend_entries: list[tuple[str, str]] = []
    for label, points in series_points:
        series_class = document.semantic_class("series")
        series_classes.append(series_class)
        if points:
            raw_x = [_numeric_x(px, x) for px, _ in points]
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
        render_legend(document, legend_entries, x=area.right + LEGEND_X_OFFSET, y=area.top)

    render_theme_style(document, resolved_theme, series_classes)

    return Chart(document, label_data)
