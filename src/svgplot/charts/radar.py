"""radarplot — a line chart on a polar view (pygal's model).

Needs no new scale type: ``CategoricalScale(categories, (-pi/2, -pi/2 + 2*pi))`` maps a
category to a spoke angle, and ``LinearScale((0, max), (0, radius))`` maps a value to a
distance from the centre. Both are pixel-agnostic, so "polar" is a use of the existing
scales rather than a third kind.

There are no cartesian axes here, so this owns its own margin the way ``pie.py`` does and
never calls ``charts/_axes``.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from svgplot.chart.base import Chart
from svgplot.charts._aggregate import Estimator, apply_estimator, resolve_estimator, warn_rows_discarded
from svgplot.charts._describe import describe, group, span
from svgplot.charts._layout import (
    LEGEND_X_OFFSET,
    fit_margin,
    format_coord,
    new_canvas,
    resolve_size,
)
from svgplot.charts._legend import render_legend
from svgplot.charts._polar import label_anchor, polar_point
from svgplot.charts._series import series_items as build_series
from svgplot.charts._theme_resolve import resolve_theme
from svgplot.data._missing import is_missing
from svgplot.data.ingest import ingest_longform
from svgplot.scales import CategoricalScale, LinearScale, make_ticks
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style

_MIN_CATEGORIES = 3
"""Two spokes make a line, not a radar -- the shape has no interior to read."""

_MARGIN_WITH_LEGEND = (40.0, 180.0, 40.0, 40.0)  # top, right, bottom, left -- right reserves legend space
_MARGIN_WITHOUT_LEGEND = (40.0, 40.0, 40.0, 40.0)
"""Picked on ``hue``, the way every axed chart picks between ``MARGIN_WITH_LEGEND`` and
``MARGIN_WITHOUT_LEGEND``. ``pie.py``'s single fixed margin is not the precedent here: a
pie always draws a legend, a radar only does with ``hue=``, and reserving the space anyway
pushes the dial 70px off the canvas centre with nothing filling the gap."""

_START_ANGLE = -math.pi / 2
"""Twelve o'clock. Radars are read clockwise from the top, like a clock face."""

_LABEL_GAP = 18.0
"""Distance from the outer ring to a category label, in pixels. Fixed rather than derived
from the text, because this package measures no glyphs."""


def _category_values(columns: dict[str, list], x: str, y: str) -> dict[str, list[float]]:
    """Map category -> every value under it in one series, dropping missing rows.

    Kept as a list rather than folded here for the two reasons ``barplot``'s twin gives: the
    caller applies ``estimator=`` to it, and the default path counts what it is about to throw
    away so it can say so.

    Deliberately still a copy of ``bar.py``'s ``_category_values`` rather than a shared helper.
    The two differ in one line that matters -- this one names the category and the chart when
    ``float()`` fails, ``barplot``'s lets the bare ``ValueError`` out -- so merging them today
    would either lose this message or change ``barplot``'s. That is #256's question, and the
    merge belongs to whichever change answers it.
    """
    values: dict[str, list[float]] = {}
    for xv, yv in zip(columns[x], columns[y], strict=True):
        if is_missing(xv) or is_missing(yv):
            continue
        try:
            value = float(yv)
        except (TypeError, ValueError) as error:
            # Same reason _validate_radius_values checks here rather than leaving it to
            # LinearScale: the bare message names neither the category nor the column.
            raise ValueError(f"radar values must be numbers, got {yv!r} for {str(xv)!r}") from error
        values.setdefault(str(xv), []).append(value)
    return values


def _fold(values: dict[str, list[float]], estimate: Callable[[list[float]], float] | None) -> dict[str, float]:
    """One value per spoke: the estimator's answer, or the last row.

    The default is the rule this chart has always used, kept so that no existing call moves a
    byte. It is also the rule that discards data, which is why the caller warns about it.
    """
    if estimate is None:
        return {category: group[-1] for category, group in values.items()}
    return {category: apply_estimator(estimate, group, group=category) for category, group in values.items()}


def _validate_radius_values(label: object, values: dict[str, float]) -> None:
    """Reject values a radial axis cannot draw, naming the offending category.

    A radar encodes a value as a **distance from the centre**, so the sign matters in a way
    it does not on a cartesian axis: a negative radius reflects the vertex through the
    centre and lands it on the *opposite* spoke, where a reader decodes it as a value for a
    different category. Measured on ``[-5, 2, 3]``, the -5 vertex came out at radius 403 on
    a 242px dial, 103px outside the canvas. ``pieplot``/``treemap``/``barplot`` reject
    negatives for the same reason, and this chart is the one that reflects rather than
    merely inverting.

    Checked here rather than left to ``LinearScale``: an inf raises there too, but with a
    message about a domain value that names neither the category nor the series.

    Raises:
        ValueError: if a value is not finite or is negative.
    """
    named = f"series {label!r}" if label is not None else "the series"
    for category, value in values.items():
        if not math.isfinite(value):
            raise ValueError(f"radar values must be finite, got {value!r} for {category!r} in {named}")
        if value < 0:
            raise ValueError(f"radar values must be non-negative, got {value!r} for {category!r} in {named}")


def _polygon_points(
    categories: list[str],
    values: dict[str, float],
    centre: tuple[float, float],
    angle_of: CategoricalScale,
    radius_of: LinearScale,
) -> list[tuple[float, float]]:
    return [polar_point(centre[0], centre[1], radius_of(values[category]), angle_of(category)) for category in categories]


def _closed_path(points: list[tuple[float, float]]) -> str:
    commands = [f"M {format_coord(points[0][0])},{format_coord(points[0][1])}"]
    commands.extend(f"L {format_coord(px)},{format_coord(py)}" for px, py in points[1:])
    commands.append("Z")
    return " ".join(commands)


def radarplot(
    data: object,
    x: str,
    y: str,
    hue: str | None = None,
    *,
    fill: bool = True,
    estimator: Estimator | None = None,
    width: float | None = None,
    height: float | None = None,
    theme: Theme | str | None = None,
) -> Chart:
    """Draw a radar chart: one spoke per ``x`` category, one closed polygon per series.

    The grid is drawn as concentric **polygons** rather than circles, so a ring crosses
    every spoke at the value its tick names -- on a circular ring the reader would have to
    interpolate between spokes to place a value.

    ``fill=True`` draws each series outlined over a translucent fill; ``fill=False`` leaves
    the outline alone, which is what several overlapping series usually want.

    Every category named by a usable row becomes a spoke, and **every series must have a
    value for every spoke** -- a radar polygon with a gap in it is a different shape, not a
    smaller one, so a missing value is refused rather than silently dropping the axis. A row
    whose ``x`` or ``hue`` is missing is not usable and names no spoke; a row whose ``y`` is
    missing still names one, and is what that refusal is about. Repeating a category within
    one series folds those rows into one value: ``estimator=None`` (the default) keeps the last
    of them, as ``barplot`` does, and says so with an
    :class:`~svgplot.warnings.AggregationWarning` because that rule discards data.

    Values are distances from the centre, so they must be finite and non-negative: a
    negative radius reflects its vertex onto the opposite spoke, where it reads as another
    category's value.

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

    ``data`` is long-form, with ``x`` naming the category column that becomes the spokes and
    ``y`` the numeric column plotted along them. One row per spoke, or per spoke and series, is
    the shape this expects.

    ``estimator=`` folds rows that share a spoke within one series: ``"mean"``, ``"median"``,
    ``"sum"``, or any callable taking a list of floats and returning one. It works per (series,
    spoke) pair rather than per spoke, so two series with different numbers of observations each
    fold their own. It cannot create or remove a spoke, so the no-gaps rule above is unaffected
    by it -- the gap check runs on the folded values either way. ``None`` (the default) keeps the
    last row, which is what this chart has always done, so no existing call moves a byte.

    **There is no ``tooltip=``.** Ten charts have one; these six do not, and the reason is the
    same for all six: a series is drawn as **one** mark, so the only thing a ``<title>`` on it
    could say is the series name. With ``hue=`` the legend already says that, in the same
    colour, without the reader having to find and hold the pointer; without ``hue=`` there is
    no legend and no name to say. A tooltip earns its element when a mark is one row or one
    bin -- here it would repeat the legend, or repeat nothing.

    ``fill=True`` gives the polygon an interior and so a real hit area, but not a second thing
    to say: the mark is still the whole series.

    Raises:
        KeyError: if ``x``/``y``/``hue`` isn't a column in ``data``, or if ``theme`` is a
            string that isn't a registered preset name.
        TypeError: if ``data`` isn't a supported table type, or if ``theme`` is neither a
            ``Theme``, a preset name, nor ``None``.
        ValueError: if ``data`` has no rows, if its columns have different lengths, if no
            row has a non-missing ``hue``, if fewer than three categories remain, if a
            series is missing a value for some category (a radar polygon has no meaning
            with a gap in it), if a value isn't a number, isn't finite, or is negative, or
            if every value is zero.
    """
    resolved_theme = resolve_theme(theme)
    longform = ingest_longform(data, x, y)
    if len(longform) == 0:
        raise ValueError("data must contain at least one row")

    series_items = build_series(data, longform.columns, hue)

    estimate = resolve_estimator(estimator)
    series_groups = [(label, _category_values(columns, x, y)) for label, columns in series_items]
    series_values = [(label, _fold(groups, estimate)) for label, groups in series_groups]
    if estimate is None:
        warn_rows_discarded(
            "radarplot",
            rows=sum(len(group) for _, groups in series_groups for group in groups.values()),
            marks=sum(len(groups) for _, groups in series_groups),
        )
    # Every category named by a row that belongs to some series is a spoke, whether or not
    # a *value* reached it. Two rules meet here and they are not the same rule:
    #
    # - A missing y leaves the category standing, so the series is caught below with a gap.
    #   Filtering those out instead made the rule depend on how many series there were:
    #   with hue= a gap raised, while a single series quietly lost the whole spoke.
    # - A row with a missing hue belongs to no series at all -- extract_channels drops it
    #   from every group -- so it can no more name a spoke than a row with a missing x can.
    #   Counting it would leave a category no series could ever fill, and blame the gap on
    #   an arbitrary series that never had that row.
    in_a_series = {str(value) for _, columns in series_items for value in columns[x] if not is_missing(value)}
    categories = [
        category
        for category in dict.fromkeys(str(value) for value in longform.columns[x] if not is_missing(value))
        if category in in_a_series
    ]
    if len(categories) < _MIN_CATEGORIES:
        raise ValueError(f"a radar needs at least {_MIN_CATEGORIES} categories, got {len(categories)}")

    for label, values in series_values:
        missing = [category for category in categories if category not in values]
        if missing:
            named = f"series {label!r}" if label is not None else "the series"
            raise ValueError(f"{named} has no value for {missing[0]!r}; a radar polygon cannot have a gap")
        _validate_radius_values(label, values)

    peak = max(value for _, values in series_values for value in values.values())
    if peak == 0:
        # LinearScale((0, 0), ...) answers the midpoint of its range for every input, so an
        # all-zero series would draw at exactly half the outer radius -- indistinguishable
        # from real mid-scale data. pieplot refuses an all-zero column for the same reason.
        raise ValueError("radar values must not all be zero; there is no scale to draw them against")

    canvas_width, canvas_height = resolve_size(width, height)
    document, area = new_canvas(
        fit_margin(_MARGIN_WITH_LEGEND if hue is not None else _MARGIN_WITHOUT_LEGEND, canvas_width, canvas_height),
        width=canvas_width,
        height=canvas_height,
    )

    centre = ((area.left + area.right) / 2, (area.top + area.bottom) / 2)
    outer_radius = min(area.right - area.left, area.bottom - area.top) / 2 - _LABEL_GAP
    angle_of = CategoricalScale(categories, (_START_ANGLE, _START_ANGLE + 2 * math.pi))
    radius_of = LinearScale((0.0, peak), (0.0, outer_radius))

    # Concentric rings, one per radial tick, each an n-gon through the spokes.
    for tick in make_ticks(radius_of):
        ring_radius = radius_of(float(tick))
        if ring_radius <= 0:
            continue
        ring = [polar_point(centre[0], centre[1], ring_radius, angle_of(category)) for category in categories]
        document.add_node(None, "path", attrib={"d": _closed_path(ring)}, classes=["grid-line"])

    for category in categories:
        angle = angle_of(category)
        spoke_end = polar_point(centre[0], centre[1], outer_radius, angle)
        document.add_node(
            None,
            "line",
            attrib={
                "x1": format_coord(centre[0]),
                "y1": format_coord(centre[1]),
                "x2": format_coord(spoke_end[0]),
                "y2": format_coord(spoke_end[1]),
            },
            classes=["grid-line"],
        )
        label_point = polar_point(centre[0], centre[1], outer_radius + _LABEL_GAP, angle)
        document.add_text(
            None,
            category,
            attrib={
                "x": format_coord(label_point[0]),
                "y": format_coord(label_point[1]),
                "text-anchor": label_anchor(angle),
                "dominant-baseline": "middle",
            },
            classes=["tick-label"],
        )

    mark_style = "outlined" if fill else "stroke"
    series_classes: list[str] = []
    legend_entries: list[tuple[str, str]] = []
    for label, values in series_values:
        series_class = document.semantic_class("series")
        series_classes.append(series_class)
        points = _polygon_points(categories, values, centre, angle_of, radius_of)
        document.add_node(None, "path", attrib={"d": _closed_path(points)}, classes=[series_class, "radar-series"])
        if label is not None:
            legend_entries.append((str(label), series_class))

    if legend_entries:
        # The legend swatch knows "stroke" (a line) and "fill" (a rect) only; an outlined
        # polygon reads as a filled swatch, and passing "outlined" through raises.
        render_legend(
            document,
            legend_entries,
            x=area.right + LEGEND_X_OFFSET,
            y=area.top,
            mark_style="fill" if fill else "stroke",
            font_size=resolved_theme.legend_font_size,
        )

    render_theme_style(document, resolved_theme, series_classes, mark_style=mark_style)

    description = describe(
        "Radar chart",
        group(categories, "spoke"),
        group([str(label) for label, _ in series_items], "series") if hue is not None else None,
        span("values", 0.0, peak),
    )
    return Chart(document, description=description)
