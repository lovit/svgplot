"""barplot — vertical/horizontal/grouped(dodge)/stacked bar charts (all one function, one mark family)."""

from __future__ import annotations

from collections.abc import Callable

from svgplot.chart._domain import Domains, apply_limit, require_categories
from svgplot.chart.base import Chart
from svgplot.charts._aggregate import Estimator, apply_estimator, resolve_estimator, warn_rows_discarded
from svgplot.charts._axes import fit_left_margin, fit_rotated_labels, render_x_axis, render_y_axis
from svgplot.charts._describe import describe, group, number, span
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
from svgplot.charts._series import series_items as build_series
from svgplot.charts._theme_resolve import resolve_theme
from svgplot.charts._tooltip import add_tooltip, clause, format_label, format_number
from svgplot.data._missing import is_missing
from svgplot.data.ingest import ingest_longform
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


def _category_values(columns: dict[str, list], x: str, y: str) -> dict[str, list[float]]:
    """Map category -> every value under it in one hue group, dropping missing rows.

    Kept as a list rather than folded here so the caller can apply ``estimator=`` — and so
    the default path can still report how many rows it is about to throw away.
    """
    values: dict[str, list[float]] = {}
    for xv, yv in zip(columns[x], columns[y], strict=True):
        if is_missing(xv) or is_missing(yv):
            continue
        values.setdefault(str(xv), []).append(float(yv))
    return values


def _fold(values: dict[str, list[float]], estimate: Callable[[list[float]], float] | None) -> dict[str, float]:
    """One value per category: the estimator's answer, or the last row (the historical
    rule, kept as the default so no existing chart moves — see ``charts/_aggregate.py``).
    """
    if estimate is None:
        return {category: group[-1] for category, group in values.items()}
    return {category: apply_estimator(estimate, group, group=category) for category, group in values.items()}


def _bar_tooltip(*, x: str, y: str, hue: str | None, category: str, value: float, label: object) -> str:
    """What one bar's ``<title>`` says: the category it stands on and the value it reached.

    The value is the bar's own -- for a stacked chart that is the segment, not the running
    total, and where ``estimator=`` folded several rows it is the folded number. Both are what
    the rectangle is: a bar chart's mark is an aggregate, and a tooltip naming the rows behind
    it would be describing something that was never drawn.

    The category goes through :func:`format_label` even though it is already a string, because
    it is the first tooltip *value* in the package that comes straight out of somebody's file
    rather than out of :func:`format_number`. Passed through raw, a three-bar chart with a
    5,000-character category name went from 17,959 bytes to 33,114, and one ``<title>`` held
    5,022 characters; through the cap it is 18,100. A category too long to read is dropped from
    the tooltip rather than truncated, and so is one that draws nothing:
    ``"category:  · value: 1"`` names a bar with a label that is not there.

    The bound is :data:`~svgplot.charts._tooltip.MAX_TOOLTIP_CHARS`, 120 -- not ``_describe``'s
    60, which is a share of one ``<desc>`` sentence and drops two 62-character depot names,
    leaving both bars named ``"value: 10"``. The column names and the ``hue=`` labels are capped
    the same way. **The axis tick is not**: its drawn text is shortened but its own ``<title>``
    still holds the category in full, so the 5,000 characters above are in the file either way
    -- 15,000 of those 17,959 baseline bytes. That sink predates this argument and closing it
    would change the output of charts that never asked for a tooltip.
    """
    parts: list[str] = []
    if (shown := format_label(category)) is not None:
        parts.append(clause(x, shown))
    parts.append(clause(y, format_number(value)))
    if hue is not None and (shown := format_label(label)) is not None:
        parts.append(clause(hue, shown))
    return " · ".join(parts)


def barplot(
    data: object,
    x: str,
    y: str,
    hue: str | None = None,
    *,
    orient: str = "v",
    stacked: bool = False,
    estimator: Estimator | None = None,
    tooltip: bool = False,
    width: float | None = None,
    height: float | None = None,
    theme: Theme | str | None = None,
    categories: tuple[str, ...] | None = None,
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
) -> Chart:
    """Draw a bar chart from long-form data.

    ``orient="v"`` (default) draws vertical bars with categories along the bottom
    axis; ``orient="h"`` draws horizontal bars with categories along the left axis.

    Colour follows ``hue=`` and nothing else. Without it every bar is one series and one
    colour, however many categories there are -- the categories are already told apart by
    their position and their axis label, and a palette rotating under them would say that the
    colour means something. With ``hue=``, each hue value takes a palette entry, so a group is
    the same colour in every category.
    With ``hue=`` given and ``stacked=False`` (the default), one bar per hue value
    is drawn side by side (dodge) within each category's band, with an
    auto-generated legend. With ``stacked=True``, one full-width bar per category
    is drawn, segmented by hue value stacked cumulatively from a zero baseline.
    ``stacked=True`` with no ``hue=`` has nothing to stack and renders a plain
    single-series bar per category.

    ``categories=`` replaces the category list this chart would take from its own data, and
    ``xlim=``/``ylim=`` its value domain -- whichever names the axis the values run along,
    which ``orient=`` decides. They exist so several charts can be made to agree -- see
    :func:`~svgplot.layout.facet.facet`. A category with no rows still gets its band, in the
    position the list gives it, so the same category is at the same place on the axis in every
    chart sharing the list; it simply has no mark drawn in it.

    It does **not** get a place in the palette, because in this chart the palette does not
    follow the categories at all -- see the note on colour under ``hue=`` above. That is a
    difference from :func:`~svgplot.charts.box.boxplot` and
    :func:`~svgplot.charts.violin.violinplot`, whose identically-worded paragraphs are about
    charts that really do rotate the palette per category.

    ``tooltip=True`` gives every bar a ``<title>`` naming its category and its value, plus its
    ``hue=`` group where there is one. The value is the bar's own: a segment in a stacked
    chart, and the folded number where ``estimator=`` folded several rows -- what the rectangle
    actually is. A browser shows it on hover, and it is also the bar's accessible name.

    A clause naming something the caller supplied -- the column names, the category, the
    ``hue=`` label -- is left out when it is over 120 characters or would draw nothing, because
    it is written once per bar. The bar still says its value.

    ``tooltip=False`` is the default. A ``<title>`` per bar is an element per bar, so turning
    it on changes the bytes of every existing caller's output for a feature they did not ask
    for. It also only works where the SVG is *inlined* into the page: inside an ``<img>`` the
    file is a separate document and the browser draws it without interaction.

    ``estimator=`` decides what happens when several rows share a category within one
    series. The default, ``None``, keeps the historical rule — **the last row wins**, and
    the others are discarded with an :class:`~svgplot.warnings.AggregationWarning` naming
    how many. ``"mean"``/``"median"``/``"sum"``, or any callable taking the group's values
    in row order and returning a number, fold them instead. ``None`` stays the default so
    that no chart anyone has already built changes its output; see
    ``charts/_aggregate.py`` for the fuller reasoning and for which charts take this
    argument at all.

    Warns:
        AggregationWarning: when ``estimator=None`` and rows were actually discarded.
            Once per call, not once per category.

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

    ``data`` is long-form, with ``x`` naming the category column and ``y`` the numeric column
    a bar's length comes from; both are read by name, so the other columns come along
    untouched and can be used for ``hue=``. One row per bar is the simple case, not a
    requirement, but the two ways of exceeding it differ: with ``estimator=`` the rows sharing
    a category within one series are combined, silently, because combining them is what was
    asked for; without it the last such row wins and the others are dropped, which is reported
    as an ``AggregationWarning`` because nobody asked for that.

    Raises:
        KeyError: if ``x``/``y``/``hue`` isn't a column in ``data``, or if ``theme``
            is a string that isn't a registered preset name.
        TypeError: if ``theme`` is neither a ``Theme``, a preset name, nor ``None``.
        ValueError: if ``data`` has no rows, if ``orient`` isn't ``"v"``/``"h"``, if
            no category survives after dropping missing values, if any value is
            negative (bars below a zero baseline aren't supported yet), or if
            ``estimator`` is an unknown name or returns a value that can't be plotted.
        TypeError: if ``estimator`` is neither a name, a callable, nor ``None``.
    """
    if orient not in ("v", "h"):
        raise ValueError(f"orient must be 'v' or 'h', got {orient!r}")
    resolved_theme = resolve_theme(theme)
    longform = ingest_longform(data, x, y)
    if len(longform) == 0:
        raise ValueError("data must contain at least one row")

    group_items = build_series(data, longform.columns, hue)

    own_categories = _unique_categories(longform.columns[x])
    if not own_categories:
        raise ValueError("no rows with a non-missing category value")
    drawn_categories = list(require_categories(categories)) if categories is not None else own_categories

    estimate = resolve_estimator(estimator)
    group_values = [(label, _category_values(columns, x, y)) for label, columns in group_items]
    group_lookups = [(label, _fold(values, estimate)) for label, values in group_values]
    if estimate is None:
        warn_rows_discarded(
            "barplot",
            rows=sum(len(group) for _, values in group_values for group in values.values()),
            marks=sum(len(values) for _, values in group_values),
        )
    all_values = [value for _, lookup in group_lookups for value in lookup.values()]
    if any(value < 0 for value in all_values):
        raise ValueError("barplot doesn't support negative values yet")

    is_stacked = stacked
    if is_stacked:
        totals = [sum(lookup.get(category, 0.0) for _, lookup in group_lookups) for category in drawn_categories]
        value_max = max(totals) if totals else 0.0
    else:
        value_max = max(all_values) if all_values else 0.0
    value_max = value_max or 1.0  # an all-zero chart still needs a non-degenerate axis
    # xlim/ylim name the axis on screen, not the data role: a horizontal bar's values run
    # along x. Taking ylim there would mean "share the y axis" moved the bars sideways.
    value_domain = apply_limit((0.0, value_max), xlim if orient == "h" else ylim)

    canvas_width, canvas_height = resolve_size(width, height)
    fitted = fit_left_margin(
        MARGIN_WITH_LEGEND if hue is not None else MARGIN_WITHOUT_LEGEND,
        drawn_categories if orient == "h" else value_domain,
        width=canvas_width,
        font_size=resolved_theme.tick_label_font_size,
    )
    # Only a vertical bar puts its categories on the bottom axis; a horizontal one puts values
    # there, and a value label is never turned. The plot width is estimated from the margin
    # settled so far, the same provisional move ``fit_left_margin`` makes for the same reason:
    # the band a label must fit in is a share of a plot area that does not exist yet.
    fitted, turn_labels = (
        fit_rotated_labels(
            fitted,
            drawn_categories,
            height=canvas_height,
            plot_width=canvas_width - fitted[3] - fitted[1],
            font_size=resolved_theme.tick_label_font_size,
            tick_length=resolved_theme.tick_size,
        )
        if orient == "v"
        else (fitted, False)
    )
    document, area = new_canvas(
        fit_margin(fitted, canvas_width, canvas_height),
        width=canvas_width,
        height=canvas_height,
    )

    category_range = (area.left, area.right) if orient == "v" else (area.top, area.bottom)
    value_range = (area.bottom, area.top) if orient == "v" else (area.left, area.right)
    category_scale = CategoricalScale(drawn_categories, category_range)
    value_scale = LinearScale(value_domain, value_range)

    if orient == "v":
        render_x_axis(
            document,
            category_scale,
            area,
            tick_count=ticks_for(area.width, TICK_SPACING_X),
            tick_length=resolved_theme.tick_size,
            font_size=resolved_theme.tick_label_font_size,
            rotate=turn_labels,
        )
        render_y_axis(
            document,
            value_scale,
            area,
            tick_count=ticks_for(area.height, TICK_SPACING_Y),
            tick_length=resolved_theme.tick_size,
            font_size=resolved_theme.tick_label_font_size,
        )
    else:
        render_y_axis(
            document,
            category_scale,
            area,
            tick_count=ticks_for(area.height, TICK_SPACING_Y),
            tick_length=resolved_theme.tick_size,
            font_size=resolved_theme.tick_label_font_size,
        )
        render_x_axis(
            document,
            value_scale,
            area,
            tick_count=ticks_for(area.width, TICK_SPACING_X),
            tick_length=resolved_theme.tick_size,
            font_size=resolved_theme.tick_label_font_size,
        )

    series_classes = [document.semantic_class("series") for _ in group_items]
    corner_radius = format_coord(resolved_theme.corner_radius) if resolved_theme.corner_radius > 0 else None

    band_width = category_scale.bandwidth
    band_inset = band_width * _BAND_PADDING_FRACTION / 2
    usable_width = band_width * (1 - _BAND_PADDING_FRACTION)
    group_count = len(group_items) if not is_stacked else 1
    slot_width = usable_width / group_count
    bar_width = slot_width * (1 - _GROUP_GAP_FRACTION) if group_count > 1 else slot_width
    slot_gap = (slot_width - bar_width) / 2

    stack_cumulative = dict.fromkeys(drawn_categories, 0.0)
    for group_index, (label, lookup) in enumerate(group_lookups):
        series_class = series_classes[group_index]
        slot_index = 0 if is_stacked else group_index
        for category in drawn_categories:
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
            bar = document.add_node(None, "rect", attrib=attrib, classes=[series_class])
            if tooltip:
                add_tooltip(document, bar, _bar_tooltip(x=x, y=y, hue=hue, category=category, value=value, label=label))

    if hue is not None:
        legend_entries = [(str(label), series_classes[index]) for index, (label, _) in enumerate(group_items)]
        render_legend(
            document,
            legend_entries,
            x=area.right + LEGEND_X_OFFSET,
            y=area.top,
            mark_style="fill",
            font_size=resolved_theme.legend_font_size,
        )

    render_theme_style(document, resolved_theme, series_classes, mark_style="fill")

    shape = "horizontal bar chart" if orient == "h" else "bar chart"
    description = describe(
        f"Stacked {shape}" if is_stacked else shape.capitalize(),
        group(drawn_categories, "category"),
        group([str(label) for label, _ in group_items], "series") if hue is not None else None,
        span("values", min(all_values), max(all_values)) if all_values else None,
        f"stacked totals up to {number(max(totals))}" if is_stacked and totals else None,
    )
    value_axis = "x" if orient == "h" else "y"
    return Chart(
        document,
        description=description,
        domains=Domains(
            **{value_axis: value_domain},
            categories=tuple(drawn_categories),
            categories_axis="y" if orient == "h" else "x",
        ),
    )
