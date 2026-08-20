"""boxplot — box-and-whisker charts (statistics delegated to svgplot.stats.box)."""

from __future__ import annotations

from svgplot._svg import SvgDocument
from svgplot.chart._domain import Domains, apply_limit, require_categories
from svgplot.chart.base import Chart
from svgplot.charts._axes import fit_left_margin, render_x_axis, render_y_axis
from svgplot.charts._describe import describe, group, plural, span
from svgplot.charts._layout import (
    DEFAULT_WIDTH,
    MARGIN_WITHOUT_LEGEND,
    format_coord,
    new_canvas,
)
from svgplot.charts._theme_resolve import resolve_theme
from svgplot.data.ingest import ingest_longform
from svgplot.scales import CategoricalScale, LinearScale
from svgplot.stats.box import BoxStats, box_stats
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style

_BOX_WIDTH_FRACTION = 0.6  # of the category band
_WHISKER_CAP_FRACTION = 0.3  # of the category band, centered


def _group_by_x(columns: dict[str, list], x: str, y: str) -> dict[str, list[float]]:
    """Drop rows with a missing x or y value, then bucket y values by (stringified) x.

    Preserves first-seen category order, so categories render left-to-right in the
    order they first appear in the data rather than an arbitrary sort.
    """
    groups: dict[str, list[float]] = {}
    for xv, yv in zip(columns[x], columns[y], strict=True):
        if xv is None or yv is None or (isinstance(yv, float) and yv != yv):
            continue
        category = str(xv)
        groups.setdefault(category, []).append(float(yv))
    return groups


def boxplot(
    data: object,
    x: str,
    y: str,
    *,
    mode: str = "1.5IQR",
    theme: Theme | str | None = None,
    categories: tuple[str, ...] | None = None,
    ylim: tuple[float, float] | None = None,
) -> Chart:
    """Draw a box plot from long-form data: one box per distinct ``x`` value,
    computed from that group's ``y`` values via ``stats.box.box_stats``.

    Each box's median/whisker lines are stroked and its body/outlier markers are
    filled, both colored by cycling through the theme's palette (one color per
    category) — there's no ``hue=`` here since the categories themselves are
    already the grouping axis, so no legend is drawn (the x-axis tick labels
    already name each category).

    ``categories=`` replaces the category list this chart would take from its own data, and
    ``ylim=`` its value domain. They exist so several charts can be made to agree -- see
    :func:`~svgplot.layout.facet.facet`. A category with no rows still gets its band **and
    its place in the palette**, so the same category is the same colour in every chart
    sharing the list; it simply has no mark drawn in it. Minting the class for an undrawn
    category is the point: skipping it would shift every later category's colour, and two
    panels would disagree about what blue means.

    Raises:
        KeyError: if ``x``/``y`` isn't a column in ``data``, or if ``theme`` is a
            string that isn't a registered preset name.
        TypeError: if ``theme`` is neither a ``Theme``, a preset name, nor ``None``.
        ValueError: if ``data`` has no rows, no rows survive dropping missing x/y
            values, or (via ``stats.box.box_stats``) if ``mode`` isn't a recognized
            box mode or a group's values overflow that mode's arithmetic.
    """
    resolved_theme = resolve_theme(theme)
    longform = ingest_longform(data, x, y)
    if len(longform) == 0:
        raise ValueError("data must contain at least one row")

    groups = _group_by_x(longform.columns, x, y)
    if not groups:
        raise ValueError("no rows with both x and y present after dropping missing values")

    drawn_categories = list(require_categories(categories)) if categories is not None else list(groups.keys())
    stats_by_category: dict[str, BoxStats] = {category: box_stats(values, mode=mode) for category, values in groups.items()}

    all_low = [s.whisker_low for s in stats_by_category.values()] + [o for s in stats_by_category.values() for o in s.outliers]
    all_high = [s.whisker_high for s in stats_by_category.values()] + [
        o for s in stats_by_category.values() for o in s.outliers
    ]
    y_domain = apply_limit((min(all_low), max(all_high)), ylim)

    document, area = new_canvas(
        fit_left_margin(MARGIN_WITHOUT_LEGEND, y_domain, width=DEFAULT_WIDTH, font_size=resolved_theme.tick_label_font_size)
    )

    x_scale = CategoricalScale(drawn_categories, (area.left, area.right))
    y_scale = LinearScale(y_domain, (area.bottom, area.top))
    render_x_axis(document, x_scale, area, tick_length=resolved_theme.tick_size, font_size=resolved_theme.tick_label_font_size)
    render_y_axis(document, y_scale, area, tick_length=resolved_theme.tick_size, font_size=resolved_theme.tick_label_font_size)

    series_classes: list[str] = []
    box_half_width = x_scale.bandwidth * _BOX_WIDTH_FRACTION / 2
    cap_half_width = x_scale.bandwidth * _WHISKER_CAP_FRACTION / 2
    for category in drawn_categories:
        # Minted even when this panel has no rows for the category, so a shared list keeps
        # one colour per category across every chart using it.
        series_class = document.semantic_class("series")
        series_classes.append(series_class)
        stats = stats_by_category.get(category)
        if stats is None:
            continue
        marker_class = f"{series_class}-marker"
        _render_box(
            document,
            x_scale,
            y_scale,
            category,
            stats,
            series_class,
            marker_class,
            box_half_width,
            cap_half_width,
            resolved_theme.corner_radius,
        )
        for outlier in stats.outliers:
            document.add_node(
                None,
                "circle",
                attrib={
                    "cx": format_coord(x_scale.center(category)),
                    "cy": format_coord(y_scale(outlier)),
                    "r": format_coord(resolved_theme.marker_size),
                },
                classes=[marker_class],
            )

    render_theme_style(document, resolved_theme, series_classes, mark_style="stroke")

    observations = plural(sum(len(values) for values in groups.values()), "observation")
    description = describe(
        "Box plot",
        f'{group(drawn_categories, "category")} over {observations}',
        span("y", *y_domain),
        f"{mode} whiskers",
    )
    return Chart(document, description=description, domains=Domains(y=y_domain, categories=tuple(drawn_categories)))


def _render_box(
    document: SvgDocument,
    x_scale: CategoricalScale,
    y_scale: LinearScale,
    category: str,
    stats: BoxStats,
    series_class: str,
    marker_class: str,
    box_half_width: float,
    cap_half_width: float,
    corner_radius: float,
) -> None:
    """Draw one category's box, median line, whisker stems and caps.

    Known quirk (not a defect here): in the ``stdev``/``pstdev`` modes a whisker is
    ``mean ± 1 SD``, which is unrelated to the quartiles, so ``whisker_high`` can land
    *below* ``q3`` (e.g. ``pstdev([9.62, 63.39, 9.45, 55.94, 0.51])`` gives ``q3=55.94``
    but ``whisker_high=54.13``). The stem is then drawn backwards, into the box, with its
    cap inside the box body. That follows directly from ``box_stats``' ±1 SD semantics
    rather than from anything this renderer does, so it is left as-is; clamping the stems
    to the box would misrepresent the statistic.
    """
    center = x_scale.center(category)
    left, right = center - box_half_width, center + box_half_width
    cap_left, cap_right = center - cap_half_width, center + cap_half_width
    y_q1, y_q3 = y_scale(stats.q1), y_scale(stats.q3)
    y_median = y_scale(stats.median)
    y_low, y_high = y_scale(stats.whisker_low), y_scale(stats.whisker_high)

    box_attrib = {
        "x": format_coord(left),
        "y": format_coord(min(y_q1, y_q3)),
        "width": format_coord(right - left),
        "height": format_coord(abs(y_q1 - y_q3)),
    }
    if corner_radius:
        box_attrib["rx"] = format_coord(corner_radius)
    document.add_node(None, "rect", attrib=box_attrib, classes=[marker_class])
    document.add_node(
        None,
        "line",
        attrib={
            "x1": format_coord(left),
            "y1": format_coord(y_median),
            "x2": format_coord(right),
            "y2": format_coord(y_median),
        },
        classes=[series_class],
    )
    # whiskers: box edge (q1/q3) out to the whisker end, plus a short cap at each end
    document.add_node(
        None,
        "line",
        attrib={"x1": format_coord(center), "y1": format_coord(y_q3), "x2": format_coord(center), "y2": format_coord(y_high)},
        classes=[series_class],
    )
    document.add_node(
        None,
        "line",
        attrib={
            "x1": format_coord(cap_left),
            "y1": format_coord(y_high),
            "x2": format_coord(cap_right),
            "y2": format_coord(y_high),
        },
        classes=[series_class],
    )
    document.add_node(
        None,
        "line",
        attrib={"x1": format_coord(center), "y1": format_coord(y_q1), "x2": format_coord(center), "y2": format_coord(y_low)},
        classes=[series_class],
    )
    document.add_node(
        None,
        "line",
        attrib={
            "x1": format_coord(cap_left),
            "y1": format_coord(y_low),
            "x2": format_coord(cap_right),
            "y2": format_coord(y_low),
        },
        classes=[series_class],
    )
