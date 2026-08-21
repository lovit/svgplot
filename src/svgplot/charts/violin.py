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
from svgplot.charts._tooltip import add_tooltip, clause, format_label, format_number
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


def _violin_tooltip(
    *, x: str, y: str, hue: str | None, category: str, hue_value: str, values: list[float], quartiles: tuple[float, ...]
) -> str:
    """What one violin's ``<title>`` says: which group it is, and what the outline is made of.

    **What it adds depends on ``inner=``, and only one of the two is "the numbers do not
    exist".** Under the default ``inner="box"`` the quartiles *are* on screen -- the inner box
    is drawn against the same labelled y axis the reader can measure against, which is why this
    branch's own test decodes ``box["y"]`` back into Q3 -- so the tooltip adds precision, not
    existence. Under ``inner=None`` there is nothing: the width is a density scaled against the
    chart's shared peak, so it says how the values pile up and not where they sit. The numbers
    are said in both cases because they describe the values the outline was computed from,
    which are there whether or not the annotation is.

    The same sentence goes on all three marks of a violin -- body, inner box, median tick.
    ``boxplot`` repeats its own across six for the same reason: the pointer stops at the
    topmost element under it, and here the box and the tick are added after the body, so leaving
    either untitled puts a hole in the middle of a violin that otherwise responds. Giving them *different* sentences would be worse, since which one the
    reader gets would depend on the pixel.

    ``quartiles`` is computed by the caller and shared with the inner box, so the two cannot
    describe the same shape differently -- and the values are sorted once rather than twice.

    A quartile is *interpolated*, so it can carry representation noise no input value had: the
    gallery's own data is ``round(gauss(...), 2)`` and one violin reads ``Q1
    3.1224999999999996``. It is spelled exactly anyway, under the rule
    :func:`~svgplot.charts._tooltip.format_number` states -- a tooltip that rewrites the number
    it names is worse than a long one -- and because rounding it would move it off the box the
    reader can measure. Every fixture in the test file uses integral floats where interpolation
    lands clean (2.25 / 3.5 / 4.75), which is why nothing there sees this.
    """
    parts = []
    if (shown := format_label(category)) is not None:
        parts.append(clause(x, shown))
    # ``hue is not None`` is redundant with ``NO_HUE`` being the empty string, which
    # ``format_label`` already returns ``None`` for. Kept because it says which case this is;
    # no mutation can make it fail, and that is worth knowing rather than hiding.
    if hue is not None and (group_name := format_label(hue_value)) is not None:
        parts.append(clause(hue, group_name))
    q1, median, q3 = quartiles
    parts.append(clause(y, f"Q1 {format_number(q1)} · median {format_number(median)} · Q3 {format_number(q3)}"))
    parts.append(plural(len(values), "observation"))
    return " · ".join(parts)


def violinplot(
    data: object,
    x: str,
    y: str,
    hue: str | None = None,
    *,
    bandwidth: float | str = "scott",
    inner: str | None = "box",
    tooltip: bool = False,
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

    ``tooltip=True`` gives every mark a ``<title>`` naming the category, the ``hue=`` group
    where there is one, Q1/median/Q3, and how many values the outline was computed from. Under
    the default ``inner="box"`` that is added *precision* -- the box is already drawn against a
    labelled axis. Under ``inner=None`` it is the only reading available: the width is a density
    scaled against the chart's shared peak, so the outline says how the values pile up and not
    where they sit. A browser shows them as ordinary hover tooltips, and they are also the
    marks' accessible names; it works only where the SVG is *inlined* into the page.

    All three marks of a violin carry the same sentence. The pointer stops at the topmost
    element under it and the inner box and median tick are drawn over the body, so leaving
    either untitled puts a hole in the middle of a violin that otherwise responds.

    ``tooltip=False`` is the default, and not as a matter of taste: every existing caller's
    output would otherwise change bytes for a feature they did not ask for.

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
    validation are that function's: ``"scott"``/``"silverman"`` or a positive number. A
    category whose values are all equal is refused *while a named rule is in use* -- there is
    no spread for the rule to scale -- but a number is accepted for it, which is the escape
    hatch the error message points at. A bandwidth chosen here applies to every violin, since
    they share one grid.

    ``theme=`` takes a :class:`~svgplot.theme.base.Theme`, the name of a preset
    (``"light"``, ``"dark"``, ``"minimal"``, ``"high_contrast"``, ``"print"``), or ``None``
    for the default theme. It is the only styling input -- colours, fonts, widths and
    opacities all come from it, and no render reads or writes global style state, so two
    charts given the same ``Theme`` are styled alike no matter what was drawn in between.

    Raises:
        KeyError: if ``x``/``y`` isn't a column in ``data``, or if ``theme`` is a string
            that isn't a registered preset name.
        TypeError: if ``theme`` is neither a ``Theme``, a preset name, nor ``None``.
        ValueError: if ``inner`` isn't one of :data:`INNER_STYLES`, if ``data`` has no
            rows, if no rows have both channels, or (via ``stats.kde``) if a category has
            too few values, or no spread while a named ``bandwidth`` rule is in use --
            reported with the category's name. No spread with an explicit numeric
            ``bandwidth`` is drawn rather than refused.
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
            values = groups[(category, hue_value)]
            # One call, shared by the tooltip and the inner box below. Two calls agree today and
            # the docstring said they could not disagree, which was a claim about a structure
            # that was not there -- and it doubled the sort the comment at that call site exists
            # to avoid. ``quantiles`` is asked for the three probabilities together for the same
            # reason: it sorts once.
            quartiles = quantiles(values, (0.25, 0.5, 0.75)) if tooltip or inner == "box" else None
            said = (
                _violin_tooltip(x=x, y=y, hue=hue, category=category, hue_value=hue_value, values=values, quartiles=quartiles)
                if tooltip
                else None
            )
            # Collected rather than titled at each call site, so a mark added later cannot
            # quietly become a hole in the glyph -- see ``_violin_tooltip``.
            marks = [
                document.add_node(
                    None,
                    "path",
                    attrib={"d": _violin_path(curve.x, curve.y, centre, half_width, y_scale)},
                    classes=[series_class, "violin-body"],
                )
            ]

            if inner == "box":
                # Quartiles from stats.quantile, which is what stats.box's hinges resolve to in
                # its default "1.5IQR" mode -- so this annotation lands exactly where a default
                # boxplot would put the same box. (boxplot's mode="tukey" uses different
                # hinges; violinplot has no mode= of its own.)
                # Computed once above and shared with the tooltip, so the two cannot describe
                # the same box differently. ``quantiles()`` rather than three ``quantile()``
                # calls: it sorts once, which is what its docstring asks of a caller with
                # several probabilities (stats.box too).
                assert quartiles is not None
                q1, median, q3 = quartiles
                box_half = abs(band) * _INNER_BOX_FRACTION / 2
                top, bottom = y_scale(q3), y_scale(q1)
                marks.append(
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
                )
                tick_half = abs(band) * _MEDIAN_TICK_FRACTION / 2
                marks.append(
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
                )
            if said is not None:
                for mark in marks:
                    add_tooltip(document, mark, said)

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
