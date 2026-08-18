"""barplot — vertical/horizontal/grouped(dodge)/stacked bar charts (all one function, one mark family)."""

from __future__ import annotations

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
from svgplot.scales import CategoricalScale, LinearScale
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style

# A category's full band is never filled edge-to-edge — some of it is inset as
# whitespace so adjacent bands read as visually distinct, and (in grouped mode)
# a further small gap separates each hue's bar within the band.
_BAND_PADDING_FRACTION = 0.2
_GROUP_GAP_FRACTION = 0.1


def _unique_categories(values: list) -> list[str]:
    """Distinct category labels, in first-appearance order (not sorted) — matches
    how a caller's data is usually already meaningfully ordered.
    """
    seen: dict[str, None] = {}
    for value in values:
        if not is_missing(value):
            seen.setdefault(str(value), None)
    return list(seen)


def _category_value_lookup(columns: dict[str, list], x: str, y: str) -> dict[str, float]:
    """Map category -> value for one hue group, dropping missing rows. If a category
    appears more than once within a group, the last row wins (no implicit aggregation
    — this issue doesn't ask for one, and silently summing would be a surprising
    default for a caller who didn't opt into stacking across duplicate rows).
    """
    lookup: dict[str, float] = {}
    for xv, yv in zip(columns[x], columns[y], strict=True):
        if is_missing(xv) or is_missing(yv):
            continue
        lookup[str(xv)] = float(yv)
    return lookup


def barplot(
    data: object,
    x: str,
    y: str,
    hue: str | None = None,
    *,
    orient: str = "v",
    stacked: bool = False,
    theme: Theme | str | None = None,
) -> Chart:
    """Draw a bar chart from long-form data.

    ``orient="v"`` (default) draws vertical bars with categories along the bottom
    axis; ``orient="h"`` draws horizontal bars with categories along the left axis.
    With ``hue=`` given and ``stacked=False`` (the default), one bar per hue value
    is drawn side by side (dodge) within each category's band, with an
    auto-generated legend. With ``stacked=True``, one full-width bar per category
    is drawn, segmented by hue value stacked cumulatively from a zero baseline.
    ``stacked=True`` with no ``hue=`` has nothing to stack and renders a plain
    single-series bar per category.

    Raises:
        KeyError: if ``x``/``y``/``hue`` isn't a column in ``data``, or if ``theme``
            is a string that isn't a registered preset name.
        TypeError: if ``theme`` is neither a ``Theme``, a preset name, nor ``None``.
        ValueError: if ``data`` has no rows, if ``orient`` isn't ``"v"``/``"h"``, if
            no category survives after dropping missing values, or if any value is
            negative (bars below a zero baseline aren't supported yet).
    """
    if orient not in ("v", "h"):
        raise ValueError(f"orient must be 'v' or 'h', got {orient!r}")
    resolved_theme = resolve_theme(theme)
    longform = ingest_longform(data, x, y)
    if len(longform) == 0:
        raise ValueError("data must contain at least one row")

    if hue is not None:
        groups = extract_channels(data, hue=hue)
        if not groups:
            raise ValueError(f"no rows with a non-missing {hue!r} value")
        group_items = sorted(groups.items(), key=lambda item: str(item[0]))
    else:
        group_items = [(None, longform.columns)]

    categories = _unique_categories(longform.columns[x])
    if not categories:
        raise ValueError("no rows with a non-missing category value")

    group_lookups = [(label, _category_value_lookup(columns, x, y)) for label, columns in group_items]
    all_values = [value for _, lookup in group_lookups for value in lookup.values()]
    if any(value < 0 for value in all_values):
        raise ValueError("barplot doesn't support negative values yet")

    is_stacked = stacked
    if is_stacked:
        totals = [sum(lookup.get(category, 0.0) for _, lookup in group_lookups) for category in categories]
        value_max = max(totals) if totals else 0.0
    else:
        value_max = max(all_values) if all_values else 0.0
    value_max = value_max or 1.0  # an all-zero chart still needs a non-degenerate axis

    document = SvgDocument(width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT)
    area = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=MARGIN_WITH_LEGEND if hue is not None else MARGIN_WITHOUT_LEGEND)
    document.add_node(
        None,
        "rect",
        attrib={"x": 0, "y": 0, "width": format_coord(DEFAULT_WIDTH), "height": format_coord(DEFAULT_HEIGHT)},
        classes=["plot-background"],
    )

    category_range = (area.left, area.right) if orient == "v" else (area.top, area.bottom)
    value_range = (area.bottom, area.top) if orient == "v" else (area.left, area.right)
    category_scale = CategoricalScale(categories, category_range)
    value_scale = LinearScale((0.0, value_max), value_range)

    if orient == "v":
        render_x_axis(document, category_scale, area, tick_length=resolved_theme.tick_size)
        render_y_axis(document, value_scale, area, tick_length=resolved_theme.tick_size)
    else:
        render_y_axis(document, category_scale, area, tick_length=resolved_theme.tick_size)
        render_x_axis(document, value_scale, area, tick_length=resolved_theme.tick_size)

    series_classes = [document.semantic_class("series") for _ in group_items]
    corner_radius = format_coord(resolved_theme.corner_radius) if resolved_theme.corner_radius > 0 else None

    band_width = category_scale.bandwidth
    band_inset = band_width * _BAND_PADDING_FRACTION / 2
    usable_width = band_width * (1 - _BAND_PADDING_FRACTION)
    group_count = len(group_items) if not is_stacked else 1
    slot_width = usable_width / group_count
    bar_width = slot_width * (1 - _GROUP_GAP_FRACTION) if group_count > 1 else slot_width
    slot_gap = (slot_width - bar_width) / 2

    stack_cumulative = dict.fromkeys(categories, 0.0)
    for group_index, (_, lookup) in enumerate(group_lookups):
        series_class = series_classes[group_index]
        slot_index = 0 if is_stacked else group_index
        for category in categories:
            value = lookup.get(category)
            if value is None:
                continue
            position = category_scale(category) + band_inset + slot_index * slot_width + slot_gap

            if is_stacked:
                v0, v1 = stack_cumulative[category], stack_cumulative[category] + value
                stack_cumulative[category] = v1
            else:
                v0, v1 = 0.0, value
            v0_px, v1_px = value_scale(v0), value_scale(v1)
            value_start, value_length = min(v0_px, v1_px), abs(v1_px - v0_px)

            attrib = (
                {
                    "x": format_coord(position),
                    "y": format_coord(value_start),
                    "width": format_coord(bar_width),
                    "height": format_coord(value_length),
                }
                if orient == "v"
                else {
                    "x": format_coord(value_start),
                    "y": format_coord(position),
                    "width": format_coord(value_length),
                    "height": format_coord(bar_width),
                }
            )
            if corner_radius is not None:
                attrib["rx"] = corner_radius
            document.add_node(None, "rect", attrib=attrib, classes=[series_class])

    if hue is not None:
        legend_entries = [(str(label), series_classes[index]) for index, (label, _) in enumerate(group_items)]
        render_legend(document, legend_entries, x=area.right + LEGEND_X_OFFSET, y=area.top, mark_style="fill")

    render_theme_style(document, resolved_theme, series_classes, mark_style="fill")

    return Chart(document)
