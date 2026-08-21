"""violinplot — a mirrored kernel density per category, optionally with a box inside.

The signature deliberately matches ``boxplot(data, x, y, ...)``: the two answer the same
question about the same shape of data, and swapping one for the other should not mean
rewriting the call.

``split=`` (seaborn's half-and-half comparison) is out of scope -- it doubles the geometry
cases and is a refinement on top of this, not part of it.
"""

from __future__ import annotations

from collections.abc import Mapping

from svgplot.chart._domain import Domains, apply_limit, require_categories
from svgplot.chart.base import Chart
from svgplot.charts._axes import fit_left_margin, fit_rotated_labels, render_x_axis, render_y_axis
from svgplot.charts._describe import describe, group, plural, span
from svgplot.charts._layout import (
    LEGEND_X_OFFSET,
    MARGIN_WITH_LEGEND,
    MARGIN_WITHOUT_LEGEND,
    TICK_SPACING_X,
    TICK_SPACING_Y,
    fit_margin,
    format_coord,
    new_canvas,
    resolve_size,
    ticks_for,
)
from svgplot.charts._legend import render_legend
from svgplot.charts._theme_resolve import resolve_theme
from svgplot.charts.box import NO_HUE, group_by_category
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


def _group_by_x(columns: dict[str, list], x: str, y: str, hue: str | None = None) -> dict[tuple[str, str], list[float]]:
    """``charts/box.py``'s grouping, reused so the two charts cannot disagree about what a
    category or a hue group *is* -- the README tells readers they take the same positional
    arguments, and that promise is worth more than a saved import."""
    return group_by_category(columns, x, y, hue)


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


def shared_grid_range(groups: Mapping[str | tuple[str, str], list[float]], bandwidth: float | str) -> tuple[float, float]:
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
    for key, values in groups.items():
        # The key is ``(category, hue)`` from the chart and a bare category from a caller
        # reconstructing the mapping; only the category is ever reported, and naming the hue
        # group in a bandwidth error would point at the wrong half of the problem.
        category = key[0] if isinstance(key, tuple) else key
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
    hue: str | None = None,
    *,
    bandwidth: float | str = "scott",
    inner: str | None = "box",
    width: float | None = None,
    height: float | None = None,
    theme: Theme | str | None = None,
    categories: tuple[str, ...] | None = None,
    ylim: tuple[float, float] | None = None,
) -> Chart:
    """Draw one mirrored density per distinct ``x`` value, from that group's ``y`` values.

    Every category is evaluated on **one shared y grid** and scaled against **one shared
    peak density**, so the violins' widths mean the same thing across the chart -- the
    widest one fills its band and the rest are drawn in proportion. Scaling each violin to
    its own peak would make every category look equally dense.

    ``inner="box"`` overlays the quartile range and the median, matching what ``boxplot``
    would draw for the same data.

    ``categories=`` replaces the category list this chart would take from its own data, and
    ``ylim=`` its value domain. They exist so several charts can be made to agree -- see
    :func:`~svgplot.layout.facet.facet`. A category with no rows still gets its band **and
    its place in the palette**, so the same category is the same colour in every chart
    sharing the list; it simply has no mark drawn in it. Minting the class for an undrawn
    category is the point: skipping it would shift every later category's colour, and two
    panels would disagree about what blue means.

    ``width``/``height`` set the canvas in pixels; ``None`` (the default) means 800x600, so a
    call that does not mention them is byte-identical to one written before they existed. The
    margin presets shrink to keep the plot area the majority of a small canvas and the tick
    count follows the plot extent — see ``charts/_layout.py``. Canvases below 240x180 are
    refused rather than clamped, and a chart may refuse a larger one if its own legend does
    not fit.

    ``hue=`` splits each category once more, drawing one violin per group side by side inside
    the category's band -- the same dodge :func:`~svgplot.charts.box.boxplot` does, and the two
    take the same positional arguments so a reader can swap one for the other.

    ``bandwidth`` is passed to :func:`svgplot.stats.kde.kde` untouched, so its rules and its
    validation are that function's: ``"scott"``/``"silverman"`` or a positive number, and a
    zero-variance sample is refused rather than given an arbitrary width. Every violin in a
    chart shares one y domain and one peak width, which is what makes their widths comparable,
    so a bandwidth chosen here applies to all of them.

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

    groups = _group_by_x(longform.columns, x, y, hue)
    if not groups:
        raise ValueError("no rows with both x and y present after dropping missing values")

    grid_range = shared_grid_range(groups, bandwidth)
    y_domain = apply_limit(grid_range, ylim)
    curves = {key: _density(values, key[0], bandwidth, grid_range) for key, values in groups.items()}
    peak = max(value for curve in curves.values() for value in curve.y)

    own_categories = list(dict.fromkeys(category for category, _ in groups))
    drawn_categories = list(require_categories(categories)) if categories is not None else own_categories
    # Sorted by ``str``, the order ``charts/_series.py`` gives every other chart's hue.
    hue_values = sorted({value for _, value in groups}, key=str) if hue is not None else [NO_HUE]
    canvas_width, canvas_height = resolve_size(width, height)
    fitted = fit_left_margin(
        MARGIN_WITH_LEGEND if hue is not None else MARGIN_WITHOUT_LEGEND,
        y_domain,
        width=canvas_width,
        font_size=resolved_theme.tick_label_font_size,
    )
    fitted, turn_labels = fit_rotated_labels(
        fitted,
        drawn_categories,
        height=canvas_height,
        plot_width=canvas_width - fitted[3] - fitted[1],
        font_size=resolved_theme.tick_label_font_size,
        tick_length=resolved_theme.tick_size,
        padding=_VIOLIN_PADDING,
    )
    document, area = new_canvas(
        fit_margin(fitted, canvas_width, canvas_height),
        width=canvas_width,
        height=canvas_height,
    )

    x_scale = CategoricalScale(drawn_categories, (area.left, area.right), padding=_VIOLIN_PADDING)
    y_scale = LinearScale(y_domain, (area.bottom, area.top))
    render_x_axis(
        document,
        x_scale,
        area,
        tick_count=ticks_for(area.width, TICK_SPACING_X),
        tick_length=resolved_theme.tick_size,
        font_size=resolved_theme.tick_label_font_size,
        rotate=turn_labels,
    )
    render_y_axis(
        document,
        y_scale,
        area,
        tick_count=ticks_for(area.height, TICK_SPACING_Y),
        tick_length=resolved_theme.tick_size,
        font_size=resolved_theme.tick_label_font_size,
    )

    # Without ``hue`` a slot *is* a band, so every width here reduces to what it was before
    # this argument existed -- which is what keeps the no-hue output byte-identical.
    slot_width = x_scale.bandwidth / len(hue_values)
    band = x_scale.step / len(hue_values)
    half_width = slot_width / 2 / peak
    series_classes: list[str] = []
    for _name in hue_values if hue is not None else drawn_categories:
        # Minted even when this panel has no rows for it, so a shared list keeps one colour
        # per name across every chart using it.
        series_classes.append(document.semantic_class("series"))
    for slot, hue_value in enumerate(hue_values):
        for index, category in enumerate(drawn_categories):
            curve = curves.get((category, hue_value))
            if curve is None:
                continue
            series_class = series_classes[slot if hue is not None else index]
            centre = x_scale(category) + (slot + 0.5) * slot_width
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
                q1, median, q3 = quantiles(groups[(category, hue_value)], (0.25, 0.5, 0.75))
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
    if hue is not None:
        render_legend(
            document,
            [(str(value), series_classes[index]) for index, value in enumerate(hue_values)],
            x=area.right + LEGEND_X_OFFSET,
            y=area.top,
            mark_style="fill",
            font_size=resolved_theme.legend_font_size,
        )

    observations = plural(sum(len(values) for values in groups.values()), "observation")
    description = describe(
        "Violin plot",
        f'{group(drawn_categories, "category")} over {observations}',
        group([str(value) for value in hue_values], "series") if hue is not None else None,
        span("y", *grid_range),
        "with an inner box" if inner == "box" else None,
    )
    return Chart(document, description=description, domains=Domains(y=y_domain, categories=tuple(drawn_categories)))
