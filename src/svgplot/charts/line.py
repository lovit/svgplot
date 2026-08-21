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
from datetime import date, datetime

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
from svgplot.data._missing import is_missing
from svgplot.data.ingest import ingest_longform
from svgplot.labels._source import collect_label_data
from svgplot.labels.spec import LabelSpec
from svgplot.scales import TimeScale
from svgplot.stats.interpolate import interpolate as interpolate_curve
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style


def _as_datetime(value: date) -> datetime:
    """A ``date`` promoted to midnight, a ``datetime`` unchanged.

    ``datetime`` is a subclass of ``date``, which is why the check reads this way round and
    why ``isinstance(value, datetime)`` alone silently missed every plain ``date`` -- the
    commonest thing a CSV or a pandas column holds. The two mix freely in one column for the
    same reason: promoting is lossless, and a column of dates with one timestamp in it is a
    real shape, not a mistake worth refusing.
    """
    return value if isinstance(value, datetime) else datetime(value.year, value.month, value.day)


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

            Also if the column mixes timezone-aware and naive datetimes. That is a different
            mixture from ``date`` with ``datetime``, which stays welcome because promoting a
            date to midnight is lossless -- here there is nothing to promote to. Python
            refuses to compare the two, and an axis has to: it needs a smallest and a largest.
            The previous code did not refuse, it *rounded them all off* -- the domain went
            through ``fromtimestamp``, which reads every aware value in the drawing machine's
            local time and silently answers a different question.
    """
    dated = [value for value in values if isinstance(value, date)]
    if not dated:
        return False
    if len(dated) != len(values):
        others = sorted({type(value).__name__ for value in values if not isinstance(value, date)})
        raise ValueError(f"column {column!r} mixes dates with {', '.join(others)}; a time axis needs dates throughout")
    aware = {isinstance(value, datetime) and value.tzinfo is not None for value in dated}
    if len(aware) > 1:
        raise ValueError(
            f"column {column!r} mixes timezone-aware and naive datetimes; "
            "a time axis has to compare them and Python does not define that comparison"
        )
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
            # ``timestamp()`` probes around the value to resolve the local offset, so the ends
            # of the representable range are unreachable whatever this package does. Which end
            # depends on the running zone -- the first minutes after ``datetime.min`` fail
            # everywhere, the last before ``datetime.max`` only east of UTC. A raw "year 10000
            # is out of range" names neither the column nor the reason, and naming one end
            # points at the wrong one for half the failures.
            raise ValueError(
                f"column {column!r} holds {value!r}, which is outside the range timestamp() can place on a time axis"
            ) from None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValueError(f"column {column!r} holds {type(value).__name__}, which has no position on an x axis") from None


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
    estimator: Estimator | None = None,
    info: LabelSpec | list[tuple[str, str]] | None = None,
    width: float | None = None,
    height: float | None = None,
    theme: Theme | str | None = None,
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
    xscale: str = "linear",
    yscale: str = "linear",
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

    A tick label is always an exact truncation of the instant its tick stands at, with one
    documented exception: inside a single day the clock formats (``%H:%M`` and finer) hide
    the year, month and day the tick also carries, so **a chart whose domain falls inside a
    single calendar day carries no date anywhere in its output**. That is a real limit for a figure meant to be
    pasted into a document and read away from its caption; naming the date once on the axis
    is left to a later change rather than guessed at here.

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

    ``x`` and ``y`` name the two columns the line is drawn through: ``x`` its position along
    the horizontal axis (numeric, date or datetime), ``y`` the numeric column it plots.

    Raises:
        ValueError: if ``x`` holds a type with no position on an axis (``datetime.time`` is
            a time of day with no day, so two values a week apart are the same point), if it
            mixes dates with numbers, or if a value sits too close to ``datetime.max`` for
            ``timestamp()`` to place. Every one of these names the column.
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
    is_time = _is_time_axis(all_x, x)
    # Once, and reused: a log x axis has to be told the values as well as the domain (a narrow
    # ``xlim`` can exclude a zero the chart still draws), and on a time axis these are the
    # timestamps rather than the datetimes.
    resolved_xscale = resolve_axis_scale(xscale, parameter="xscale")
    resolved_yscale = resolve_axis_scale(yscale, parameter="yscale")
    numeric_all_x = [_numeric_x(value, x) for value in all_x]
    numeric_x_domain = (min(numeric_all_x), max(numeric_all_x))
    if is_time and resolved_xscale == "log":
        # A logarithm of a Unix timestamp is not a quantity anyone means. It says the *ratio*
        # between two instants is what the axis should show, and that ratio is an artefact of
        # where the epoch happens to sit -- 2000 to 2020 reads as a factor of 1.6 only because
        # 1970 was chosen as zero. Every date before the epoch is negative besides, so the
        # alternative to refusing here is telling a caller who wrote 1950 about -631184400.
        raise ValueError(
            f"column {x!r} holds dates, which a log axis cannot show: the logarithm of a "
            "timestamp measures a ratio to the 1970 epoch rather than anything in the data. "
            "Use the default linear time axis."
        )
    # The tick axis is built from the *original* datetimes, not from these numbers rebuilt
    # by ``fromtimestamp``. That round trip returns a naive local value, so an aware column
    # lost its offset and every label became a reading of whichever machine drew the chart:
    # the same UTC data labelled 00:00-12:00 under TZ=UTC, 10:00-20:00 under Asia/Seoul, and
    # switched format entirely under America/Santiago. ``TimeScale``'s own docstring tells a
    # caller to pass aware values for exactly that reason, which this path had made untrue.
    time_domain = (min(all_x, key=lambda value: _numeric_x(value, x)), max(all_x, key=lambda value: _numeric_x(value, x)))
    y_domain = (min(all_y), max(all_y))
    numeric_x_domain = apply_limit(numeric_x_domain, xlim)
    y_domain = apply_limit(y_domain, ylim)

    # After the checks above, so a bad column still reports the chart's own error first.
    label_data = collect_label_data(data, info, required=(x, y, hue))

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

    pixel_x_scale = value_scale(resolved_xscale, numeric_x_domain, (area.left, area.right), column=x, values=numeric_all_x)
    pixel_y_scale = value_scale(resolved_yscale, y_domain, (area.bottom, area.top), column=y, values=all_y)
    tick_x_scale = (
        TimeScale((_as_datetime(time_domain[0]), _as_datetime(time_domain[1])), (area.left, area.right))
        if is_time
        else pixel_x_scale
    )
    render_x_axis(
        document,
        tick_x_scale,
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
        render_legend(
            document,
            legend_entries,
            x=area.right + LEGEND_X_OFFSET,
            y=area.top,
            font_size=resolved_theme.legend_font_size,
        )

    render_theme_style(document, resolved_theme, series_classes)

    points = plural(len(all_x), "point")
    description = describe(
        "Line chart",
        over([str(label) for label, _ in series_items] if hue is not None else None, points),
        # ``time_domain``, not ``min(all_x)``: a column may hold both ``date`` and
        # ``datetime`` values, which do not compare to each other, and that mixture is
        # explicitly welcome. ``time_domain`` is already ordered by the numeric position
        # each value maps to, which is the order the axis draws them in anyway.
        span("x", _as_datetime(time_domain[0]), _as_datetime(time_domain[1])) if is_time else span("x", *numeric_x_domain),
        span("y", *y_domain),
        f"{interpolate} interpolation" if interpolate != "linear" else None,
    )
    return Chart(document, label_data, description=description, domains=Domains(x=numeric_x_domain, y=y_domain))
