"""boxplot — box-and-whisker charts (statistics delegated to svgplot.stats.box)."""

from __future__ import annotations

from svgplot._svg import SvgDocument
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
from svgplot.data._missing import is_missing
from svgplot.data.ingest import ingest_longform
from svgplot.scales import CategoricalScale, LinearScale
from svgplot.stats.box import BoxStats, box_stats
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style

_BOX_WIDTH_FRACTION = 0.6  # of the category band
_WHISKER_CAP_FRACTION = 0.3  # of the category band, centered


NO_HUE = ""
"""The single hue slot a chart drawn without ``hue=`` has.

A sentinel rather than a branch: one code path that draws N boxes per band, where N is 1
unless a hue says otherwise, is what keeps the no-hue geometry exactly what it was.
"""


def group_by_category(columns: dict[str, list], x: str, y: str, hue: str | None = None) -> dict[tuple[str, str], list[float]]:
    """Drop rows with a missing x or y value, then bucket y values by (category, hue).

    Preserves first-seen order on both axes, so categories render left-to-right and hue
    groups slot within a band in the order they first appear in the data rather than an
    arbitrary sort -- the rule every other chart here already follows.
    """
    groups: dict[tuple[str, str], list[float]] = {}
    # ``columns[hue]`` rather than a guarded lookup: a hue naming no column is a ``KeyError``,
    # which is what this function's callers document and what every other chart raises.
    hues = columns[hue] if hue is not None else None
    for index, (xv, yv) in enumerate(zip(columns[x], columns[y], strict=True)):
        # ``is_missing`` rather than ``is None``: a NaN category label is not a category, and
        # letting it through buckets those rows under the string "nan". ``violinplot`` already
        # filtered this way and ``boxplot`` did not, which is exactly the kind of disagreement
        # sharing this function is meant to end.
        if is_missing(xv) or is_missing(yv):
            continue
        hue_value = NO_HUE if hues is None else hues[index]
        if is_missing(hue_value):
            continue
        groups.setdefault((str(xv), str(hue_value)), []).append(float(yv))
    return groups


def boxplot(
    data: object,
    x: str,
    y: str,
    hue: str | None = None,
    *,
    mode: str = "1.5IQR",
    width: float | None = None,
    height: float | None = None,
    theme: Theme | str | None = None,
    categories: tuple[str, ...] | None = None,
    ylim: tuple[float, float] | None = None,
) -> Chart:
    """Draw a box plot from long-form data: one box per distinct ``x`` value,
    computed from that group's ``y`` values via ``stats.box.box_stats``.

    Each box's median/whisker lines are stroked and its body/outlier markers are filled.

    ``hue=`` groups *within* each category: every category's band is split into one slot per
    hue value and the boxes are drawn side by side, the same dodge ``barplot`` does. The two
    arguments answer different questions -- ``x=`` decides what is placed next to what, and
    ``hue=`` decides what is compared inside each of those. seaborn's
    ``boxplot(x="day", y="total_bill", hue="smoker")`` is the shape this exists for.

    Colour follows whichever is doing the grouping. Without ``hue=`` the palette cycles per
    **category**, because colour is then the only thing telling two boxes apart. With it the
    palette cycles per **hue value**, so the same group is the same colour in every category
    -- which is the comparison the argument is for -- and a legend names them.

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

    groups = group_by_category(longform.columns, x, y, hue)
    if not groups:
        raise ValueError("no rows with both x and y present after dropping missing values")

    own_categories = list(dict.fromkeys(category for category, _ in groups))
    drawn_categories = list(require_categories(categories)) if categories is not None else own_categories
    # Sorted by ``str`` rather than first-seen, which is what ``charts/_series.py`` does for
    # every other chart's hue: the order decides both the palette slot and the legend row, so
    # two charts of the same groups have to agree on it whatever order the rows arrived in.
    hue_values = sorted({value for _, value in groups}, key=str) if hue is not None else [NO_HUE]
    stats_by_category: dict[tuple[str, str], BoxStats] = {key: box_stats(values, mode=mode) for key, values in groups.items()}

    all_low = [s.whisker_low for s in stats_by_category.values()] + [o for s in stats_by_category.values() for o in s.outliers]
    all_high = [s.whisker_high for s in stats_by_category.values()] + [
        o for s in stats_by_category.values() for o in s.outliers
    ]
    y_domain = apply_limit((min(all_low), max(all_high)), ylim)

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
    )
    document, area = new_canvas(
        fit_margin(fitted, canvas_width, canvas_height),
        width=canvas_width,
        height=canvas_height,
    )

    x_scale = CategoricalScale(drawn_categories, (area.left, area.right))
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

    # Without ``hue`` a slot *is* a band, so every width below reduces to what it was before
    # this argument existed -- which is what keeps the no-hue output byte-identical.
    slot_width = x_scale.bandwidth / len(hue_values)
    box_half_width = slot_width * _BOX_WIDTH_FRACTION / 2
    cap_half_width = slot_width * _WHISKER_CAP_FRACTION / 2

    series_classes: list[str] = []
    # One class per *hue* when there is a hue, one per category when there is not. The two
    # cannot be merged: with ``hue=`` the same group has to be the same colour in every
    # category, which is the comparison the argument exists to make; without it, colour is the
    # only thing telling two categories apart.
    for _name in hue_values if hue is not None else drawn_categories:
        # Minted even when this panel has no rows for it, so a shared list keeps one colour
        # per name across every chart using it.
        series_classes.append(document.semantic_class("series"))

    for slot, hue_value in enumerate(hue_values):
        for index, category in enumerate(drawn_categories):
            stats = stats_by_category.get((category, hue_value))
            if stats is None:
                continue
            series_class = series_classes[slot if hue is not None else index]
            marker_class = f"{series_class}-marker"
            center = x_scale(category) + (slot + 0.5) * slot_width
            _render_box(
                document,
                center,
                y_scale,
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
                        "cx": format_coord(center),
                        "cy": format_coord(y_scale(outlier)),
                        "r": format_coord(resolved_theme.marker_size),
                    },
                    classes=[marker_class],
                )

    render_theme_style(document, resolved_theme, series_classes, mark_style="stroke")
    if hue is not None:
        render_legend(
            document,
            [(str(value), series_classes[index]) for index, value in enumerate(hue_values)],
            x=area.right + LEGEND_X_OFFSET,
            y=area.top,
            mark_style="stroke",
            font_size=resolved_theme.legend_font_size,
        )

    observations = plural(sum(len(values) for values in groups.values()), "observation")
    description = describe(
        "Box plot",
        f'{group(drawn_categories, "category")} over {observations}',
        group([str(value) for value in hue_values], "series") if hue is not None else None,
        span("y", *y_domain),
        f"{mode} whiskers",
    )
    return Chart(document, description=description, domains=Domains(y=y_domain, categories=tuple(drawn_categories)))


def _render_box(
    document: SvgDocument,
    center: float,
    y_scale: LinearScale,
    stats: BoxStats,
    series_class: str,
    marker_class: str,
    box_half_width: float,
    cap_half_width: float,
    corner_radius: float,
) -> None:
    """Draw one box at ``center``, with its median line, whisker stems and caps.

    The centre is passed rather than taken from the scale because with ``hue=`` a category's
    band holds one box per hue group, each in its own slot -- the scale knows where the band
    is, and only the caller knows which slot inside it this box belongs to.

    Known quirk (not a defect here): in the ``stdev``/``pstdev`` modes a whisker is
    ``mean ± 1 SD``, which is unrelated to the quartiles, so ``whisker_high`` can land
    *below* ``q3`` (e.g. ``pstdev([9.62, 63.39, 9.45, 55.94, 0.51])`` gives ``q3=55.94``
    but ``whisker_high=54.13``). The stem is then drawn backwards, into the box, with its
    cap inside the box body. That follows directly from ``box_stats``' ±1 SD semantics
    rather than from anything this renderer does, so it is left as-is; clamping the stems
    to the box would misrepresent the statistic.
    """
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
