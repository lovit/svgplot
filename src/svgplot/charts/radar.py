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

from svgplot._svg import SvgDocument
from svgplot.chart.base import Chart
from svgplot.charts._layout import (
    LEGEND_X_OFFSET,
    fit_margin,
    format_coord,
    plot_area,
    resolve_size,
)
from svgplot.charts._legend import render_legend
from svgplot.charts._polar import polar_point
from svgplot.charts._theme_resolve import resolve_theme
from svgplot.data._missing import is_missing
from svgplot.data.ingest import ingest_longform
from svgplot.data.semantic import extract_channels
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

_ANCHOR_EPSILON = 1e-9
"""How close to straight up/down counts as vertical when choosing a label's anchor. Guards
against a float that is 1e-17 off the axis flipping the anchor to a side."""


def _values_by_category(columns: dict[str, list], x: str, y: str) -> dict[str, float]:
    """One value per category, later rows winning -- radar has a single spoke per label.

    Same rule as ``barplot``'s category lookup, for the same reason: one category owns one
    mark, so a repeated row can only replace the previous one.
    """
    values: dict[str, float] = {}
    for xv, yv in zip(columns[x], columns[y], strict=True):
        if is_missing(xv) or is_missing(yv):
            continue
        try:
            values[str(xv)] = float(yv)
        except (TypeError, ValueError) as error:
            # Same reason _validate_radius_values checks here rather than leaving it to
            # LinearScale: the bare message names neither the category nor the column.
            raise ValueError(f"radar values must be numbers, got {yv!r} for {str(xv)!r}") from error
    return values


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


def _label_anchor(angle: float) -> str:
    """The ``text-anchor`` for a label sitting at ``angle``, from the quadrant alone.

    An angle, not a measured width: this package has no font metrics, and a label's side
    is fully determined by which half of the circle it is on. Straight up and straight
    down get ``middle`` because neither side is nearer.
    """
    cosine = math.cos(angle)
    if abs(cosine) < _ANCHOR_EPSILON:
        return "middle"
    return "start" if cosine > 0 else "end"


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
    one series replaces the earlier row, as ``barplot`` does.

    Values are distances from the centre, so they must be finite and non-negative: a
    negative radius reflects its vertex onto the opposite spoke, where it reads as another
    category's value.

    ``width``/``height`` set the canvas in pixels; ``None`` (the default) means 800x600, so a
    call that does not mention them is byte-identical to one written before they existed. The
    margin presets shrink to keep the plot area the majority of a small canvas — see
    ``charts/_layout.py``. (This chart draws no cartesian axis, so the tick-density rule
    described there does not reach it.) Canvases below 240x180 are
    refused rather than clamped, and a chart may refuse a larger one if its own legend does
    not fit.

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

    if hue is not None:
        groups = extract_channels(data, hue=hue)
        if not groups:
            raise ValueError(f"no rows with a non-missing {hue!r} value")
        series_items = sorted(groups.items(), key=lambda item: str(item[0]))
    else:
        series_items = [(None, longform.columns)]

    series_values = [(label, _values_by_category(columns, x, y)) for label, columns in series_items]
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
    document = SvgDocument(width=canvas_width, height=canvas_height)
    area = plot_area(
        canvas_width,
        canvas_height,
        margin=fit_margin(_MARGIN_WITH_LEGEND if hue is not None else _MARGIN_WITHOUT_LEGEND, canvas_width, canvas_height),
    )
    document.add_node(
        None,
        "rect",
        attrib={"x": 0, "y": 0, "width": format_coord(canvas_width), "height": format_coord(canvas_height)},
        classes=["plot-background"],
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
                "text-anchor": _label_anchor(angle),
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
        )

    render_theme_style(document, resolved_theme, series_classes, mark_style=mark_style)

    return Chart(document)
