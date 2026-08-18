"""violinplot — a mirrored kernel density per category, optionally with a box inside.

The signature deliberately matches ``boxplot(data, x, y, ...)``: the two answer the same
question about the same shape of data, and swapping one for the other should not mean
rewriting the call.

``split=`` (seaborn's half-and-half comparison) is out of scope -- it doubles the geometry
cases and is a refinement on top of this, not part of it.
"""

from __future__ import annotations

from svgplot._svg import SvgDocument
from svgplot.chart.base import Chart
from svgplot.charts._axes import render_x_axis, render_y_axis
from svgplot.charts._layout import DEFAULT_HEIGHT, DEFAULT_WIDTH, MARGIN_WITHOUT_LEGEND, format_coord, plot_area
from svgplot.charts._theme_resolve import resolve_theme
from svgplot.data._missing import is_missing
from svgplot.data.ingest import ingest_longform
from svgplot.scales import CategoricalScale, LinearScale
from svgplot.stats.kde import KdeCurve, kde
from svgplot.stats.quantile import quantiles
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style

INNER_STYLES = ("box", None)
"""What may be drawn inside a violin. ``None`` leaves the density alone."""

_VIOLIN_PADDING = 0.2
"""Gutter between neighbouring violins, as a fraction of the category band -- the same
share ``bar`` leaves between bars, so a violin chart and a bar chart of the same
categories line up."""

_INNER_BOX_FRACTION = 0.12
"""Width of the inner quartile box, as a fraction of the category *step* (band + gutter).
Deliberately thin: it is an annotation on the density, not a second chart competing with
it. Measured against the step rather than the band so the two inner marks keep their
proportions when ``_VIOLIN_PADDING`` changes."""

_MEDIAN_TICK_FRACTION = 0.2
"""Width of the median tick, also a fraction of the step. Wider than the box so it reads
as a mark rather than as the box's own edge, and below ``1 - _VIOLIN_PADDING`` so it stays
inside its own band."""

_CUT = 3.0
"""Bandwidths of room past each category's extremes, matching ``stats.kde``'s default."""

_PROBE_GRID = 2
"""Grid size for the pass that only needs a category's bandwidth -- see ``charts/kde.py``,
which shares a grid across hue groups for the same reason and by the same means."""

_EVALUATION_GRID = 200
"""Points per violin outline. Named rather than left to ``stats.kde``'s default, because it
also fixes how many vertices each emitted path carries."""


def _group_by_x(columns: dict[str, list], x: str, y: str) -> dict[str, list[float]]:
    """Bucket ``y`` values by stringified ``x``, dropping rows missing either.

    First-seen category order, so violins render left-to-right in input order -- the same
    rule ``boxplot`` uses, which is what keeps the two interchangeable.
    """
    groups: dict[str, list[float]] = {}
    for xv, yv in zip(columns[x], columns[y], strict=True):
        if is_missing(xv) or is_missing(yv):
            continue
        groups.setdefault(str(xv), []).append(float(yv))
    return groups


def _density(values: list[float], category: str, bandwidth: float | str, grid_range: tuple[float, float] | None) -> KdeCurve:
    """``kde`` over one category's values, with the category named in any failure.

    Without this the most common mistake -- a category holding a single observation, or
    the same value repeated -- reports only "every value is 3.0", leaving the caller to
    work out which of their categories that was.
    """
    try:
        if grid_range is None:
            return kde(values, bandwidth=bandwidth, grid=_PROBE_GRID)
        return kde(values, bandwidth=bandwidth, grid=_EVALUATION_GRID, grid_range=grid_range)
    except ValueError as error:
        raise ValueError(f"category {category!r}: {error}") from error


def shared_grid_range(groups: dict[str, list[float]], bandwidth: float | str) -> tuple[float, float]:
    """The y span every category is evaluated over: the union of what each would have
    chosen alone.

    Bandwidth is chosen per category, so pooling the values first would settle on one width
    and clip a narrow category's tail. Public (unlike this module's other helpers) because
    it is the only way to reconstruct the chart's y mapping from outside.

    A shared grid has one inherent cost: if two categories differ in scale by orders of
    magnitude, the grid step can exceed the narrow one's bandwidth entirely and it
    evaluates to zero everywhere -- drawn as a vertical line with its inner box still
    beside it. seaborn shares the limitation; ``charts/kde.py`` records the same note.
    """
    lows: list[float] = []
    highs: list[float] = []
    for category, values in groups.items():
        width = _density(values, category, bandwidth, None).bandwidth
        lows.append(min(values) - _CUT * width)
        highs.append(max(values) + _CUT * width)
    return min(lows), max(highs)


def _violin_path(ys: list[float], densities: list[float], centre: float, half_width: float, y_scale: LinearScale) -> str:
    """One closed outline: up the left flank, back down the right.

    Both flanks are ``centre -+ offset`` from the same offset, so the shape is symmetric by
    construction rather than by two separate calculations that could drift.
    """
    left = [(centre - half_width * density, y_scale(y)) for y, density in zip(ys, densities, strict=True)]
    right = [(centre + half_width * density, y_scale(y)) for y, density in zip(ys, densities, strict=True)]
    commands = [f"M {format_coord(left[0][0])},{format_coord(left[0][1])}"]
    commands.extend(f"L {format_coord(px)},{format_coord(py)}" for px, py in left[1:])
    commands.extend(f"L {format_coord(px)},{format_coord(py)}" for px, py in reversed(right))
    commands.append("Z")
    return " ".join(commands)


def violinplot(
    data: object,
    x: str,
    y: str,
    *,
    bandwidth: float | str = "scott",
    inner: str | None = "box",
    theme: Theme | str | None = None,
) -> Chart:
    """Draw one mirrored density per distinct ``x`` value, from that group's ``y`` values.

    Every category is evaluated on **one shared y grid** and scaled against **one shared
    peak density**, so the violins' widths mean the same thing across the chart -- the
    widest one fills its band and the rest are drawn in proportion. Scaling each violin to
    its own peak would make every category look equally dense.

    ``inner="box"`` overlays the quartile range and the median, matching what ``boxplot``
    would draw for the same data.

    Raises:
        KeyError: if ``x``/``y`` isn't a column in ``data``, or if ``theme`` is a string
            that isn't a registered preset name.
        TypeError: if ``theme`` is neither a ``Theme``, a preset name, nor ``None``.
        ValueError: if ``inner`` isn't one of :data:`INNER_STYLES`, if ``data`` has no
            rows, if no rows have both channels, or (via ``stats.kde``) if a category has
            too few values or no spread -- reported with the category's name.
    """
    if inner not in INNER_STYLES:
        raise ValueError(f"inner must be one of {INNER_STYLES}, got {inner!r}")

    resolved_theme = resolve_theme(theme)
    longform = ingest_longform(data, x, y)
    if len(longform) == 0:
        raise ValueError("data must contain at least one row")

    groups = _group_by_x(longform.columns, x, y)
    if not groups:
        raise ValueError("no rows with both x and y present after dropping missing values")

    grid_range = shared_grid_range(groups, bandwidth)
    curves = {category: _density(values, category, bandwidth, grid_range) for category, values in groups.items()}
    peak = max(value for curve in curves.values() for value in curve.y)

    categories = list(groups)
    document = SvgDocument(width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT)
    area = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=MARGIN_WITHOUT_LEGEND)
    document.add_node(
        None,
        "rect",
        attrib={"x": 0, "y": 0, "width": format_coord(DEFAULT_WIDTH), "height": format_coord(DEFAULT_HEIGHT)},
        classes=["plot-background"],
    )

    x_scale = CategoricalScale(categories, (area.left, area.right), padding=_VIOLIN_PADDING)
    y_scale = LinearScale(grid_range, (area.bottom, area.top))
    render_x_axis(document, x_scale, area, tick_length=resolved_theme.tick_size)
    render_y_axis(document, y_scale, area, tick_length=resolved_theme.tick_size)

    band = x_scale.step
    half_width = x_scale.bandwidth / 2 / peak
    series_classes: list[str] = []
    for category in categories:
        series_class = document.semantic_class("series")
        series_classes.append(series_class)
        centre = x_scale.center(category)
        curve = curves[category]
        document.add_node(
            None,
            "path",
            attrib={"d": _violin_path(curve.x, curve.y, centre, half_width, y_scale)},
            classes=[series_class, "violin-body"],
        )

        if inner == "box":
            # Quartiles from stats.quantile, which is what stats.box's hinges resolve to in
            # its default "1.5IQR" mode -- so this annotation lands exactly where a default
            # boxplot would put the same box. (boxplot's mode="tukey" uses different
            # hinges; violinplot has no mode= of its own.)
            # quantiles(), not three quantile() calls: it sorts once, which is exactly what
            # its docstring asks callers with several probabilities to do (stats.box too).
            q1, median, q3 = quantiles(groups[category], (0.25, 0.5, 0.75))
            box_half = abs(band) * _INNER_BOX_FRACTION / 2
            top, bottom = y_scale(q3), y_scale(q1)
            document.add_node(
                None,
                "rect",
                attrib={
                    "x": format_coord(centre - box_half),
                    "y": format_coord(min(top, bottom)),
                    "width": format_coord(box_half * 2),
                    "height": format_coord(abs(bottom - top)),
                },
                classes=[series_class, "violin-box"],
            )
            tick_half = abs(band) * _MEDIAN_TICK_FRACTION / 2
            document.add_node(
                None,
                "line",
                attrib={
                    "x1": format_coord(centre - tick_half),
                    "y1": format_coord(y_scale(median)),
                    "x2": format_coord(centre + tick_half),
                    "y2": format_coord(y_scale(median)),
                },
                classes=[series_class, "violin-median"],
            )

    # "outlined" so the body reads as a translucent fill that still has its own edge, and
    # the inner box and median inherit the same colour at full strength.
    render_theme_style(document, resolved_theme, series_classes, mark_style="outlined")

    return Chart(document)
