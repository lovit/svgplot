"""histplot — histograms with automatic binning (delegates to svgplot.stats.binning)."""

from __future__ import annotations

import bisect

from svgplot.chart._domain import Domains, apply_limit, narrows
from svgplot.chart.base import Chart
from svgplot.charts._axes import fit_left_margin, render_x_axis, render_y_axis
from svgplot.charts._describe import describe, over, plural, span
from svgplot.charts._layout import (
    LEGEND_X_OFFSET,
    MARGIN_WITH_LEGEND,
    MARGIN_WITHOUT_LEGEND,
    TICK_SPACING_X,
    TICK_SPACING_Y,
    corner_radius_attr,
    fit_margin,
    format_coord,
    marks_viewport,
    new_canvas,
    resolve_size,
    ticks_for,
)
from svgplot.charts._legend import render_legend
from svgplot.charts._series import series_items as build_series
from svgplot.charts._theme_resolve import resolve_theme
from svgplot.charts._tooltip import add_tooltip, clause, format_label, format_number
from svgplot.data._missing import is_missing, require_number
from svgplot.data.ingest import ingest_longform
from svgplot.scales import LinearScale
from svgplot.stats.binning import histogram_bins
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style


def _clean_values(columns: dict[str, list], x: str) -> list[float]:
    """Drop missing (``None``/NaN) values from column ``x``."""
    return [require_number(v, x) for v in columns[x] if not is_missing(v)]


def _count_in_bins(values: list[float], edges: list[float]) -> list[int]:
    """Bin each value via ``edges`` (``edges[i] <= value < edges[i+1]``), except the
    final bin, which is inclusive on both ends — otherwise the maximum value in the
    dataset is silently dropped (the standard numpy/histogram convention).

    **A value outside ``[edges[0], edges[-1]]`` is dropped, not folded into the nearest bin.**
    That case is reachable and always was: ``xlim=`` narrower than the data is the documented
    use of that argument (``chart/_domain.py``: "a caller who asks for ``(0, 100)`` on data
    spanning 0..300 means to clip the view"), and ``xlim`` decides the bin range. An earlier
    version of this function clamped instead, with a comment calling the case unreachable, and
    the outermost bars absorbed everything past the window: measured on 200 samples of
    ``Random(3).gauss(10, 3)`` with ``xlim=(8, 12)`` and ``bins=4``, the first bar counted **80**
    where 24 values are in ``[8, 9)`` and the last **63** where 21 are in ``[11, 12]`` -- 98 of
    the 200 values are outside the window.

    Clipping is what a caller narrowing the view asks for, and a clamped edge bar is not a
    smaller chart of the same data: it is a bar that means something else. It also makes the
    interval a bar names untrue, which is visible now that ``tooltip=`` says it -- the real
    membership rule of a clamped last bin is ``value >= edges[-2]``, unbounded above.
    """
    n_bins = len(edges) - 1
    counts = [0] * n_bins
    for value in values:
        if value < edges[0] or value > edges[-1]:
            continue
        # bisect_right(edges, value) - 1 gives the bin index i such that
        # edges[i] <= value < edges[i+1]; the min() handles value == edges[-1]
        # (bisect_right returns len(edges) there) by folding it into the last bin, which is
        # the inclusive-both-ends convention above rather than a clamp.
        index = min(bisect.bisect_right(edges, value) - 1, n_bins - 1)
        counts[index] += 1
    return counts


def _bin_tooltip(*, x: str, hue: str | None, low: float, high: float, closed: bool, count: int, label: object) -> str:
    """What one bar's ``<title>`` says: the bin it covers, and how many values landed in it.

    **It cannot say which rows those were, and this is the first chart where that is visible.**
    A scatter point is a row, so its tooltip reads the row back. A bar here is a *count*, and
    the values that produced it were dropped at :func:`_count_in_bins` -- nothing downstream
    holds them. Naming a row would mean naming one of many, which is a different claim from the
    one the bar makes.

    The interval is written with a bracket rather than a dash because the bins are half-open and
    the last one is not: ``12`` belongs to ``[12, 18)`` and not to ``[6, 12)``, and whatever sits
    on the window's upper bound belongs to the final bin, which is why that one closes. (Without
    ``xlim`` that bound is the data's maximum; with a narrowing one it is the window's, and
    anything past it was dropped -- see :func:`_count_in_bins`.) A bar reading ``12 - 18`` beside
    one reading ``18 - 24`` leaves the reader to guess where ``18`` went, and the two bars answer
    differently.

    Bounded like every other tooltip: the column names go through :func:`clause`, which drops
    one too long to read, and the numbers through :func:`format_number`. A clause is written
    once per bar per series.
    """
    interval = f"[{format_number(low)}, {format_number(high)}{']' if closed else ')'}"
    parts = [clause(x, interval), plural(count, "observation")]
    if hue is not None and (shown := format_label(label)) is not None:
        parts.append(clause(hue, shown))
    return " · ".join(parts)


def histplot(
    data: object,
    x: str,
    hue: str | None = None,
    *,
    bins: str | int = "auto",
    tooltip: bool = False,
    width: float | None = None,
    height: float | None = None,
    theme: Theme | str | None = None,
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
) -> Chart:
    """Draw a histogram from long-form data with automatic binning.

    With ``hue=``, one histogram per distinct hue value is drawn as overlapping
    bars (colors cycling through the theme's palette, ``theme.fill_opacity``
    making the overlap visible) sharing one set of bin edges computed across all groups'
    combined values — so every group's bars land on directly comparable
    boundaries — with an auto-generated legend.

    ``tooltip=True`` gives every bar a ``<title>`` naming the interval it covers and how many
    values landed in it, plus the ``hue=`` group where one was given. A browser shows that as
    the ordinary hover tooltip, and it is also the bar's accessible name. It works only where
    the SVG is *inlined* into the page: inside an ``<img>`` the file is a separate document and
    the browser draws it without interaction.

    **The tooltip cannot name a row, because a bar here is not one.** It is a count, and the
    values behind it are not carried past binning. That is the difference from
    :func:`~svgplot.scatterplot`, where a mark *is* a row and the tooltip reads that row back.

    ``tooltip=False`` is the default, and not as a matter of taste. A ``<title>`` per bar is an
    element per bar, and every existing caller's output would change bytes for a feature they
    did not ask for. Off, the file is what it was.

    A narrowing ``xlim=`` **clips**: values outside the window are dropped rather than folded
    into the edge bars, and the ``<desc>``'s observation count is the number that survived. The
    ``hue=`` group list in that sentence is not filtered the same way -- a group whose every
    value is outside the window still appears there, still takes a palette entry and still gets
    a legend swatch, with no bar. That is deliberate: the caller's data does have that group,
    and dropping it from the legend would shift every later group's colour, which is the thing
    ``categories=`` exists to prevent elsewhere.

    ``xlim=``/``ylim=`` replace the domain this chart would compute from its own data. They
    exist so several charts can be made to agree -- see :func:`~svgplot.layout.facet.facet`,
    which uses them to give faceted panels one axis -- and replace rather than widen, so a
    caller asking for a narrower view gets one. Note that this chart's y domain is a
    **derived** quantity, not a column: nothing outside the chart could have computed it,
    which is why the domain is recorded on the returned chart rather than predicted.

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

    ``x`` names the numeric column being binned -- the only data column this chart needs,
    since the y axis is a count it computes. ``bins=`` is either an integer count or the name
    of a strategy that picks one from the data: ``"auto"`` (the default), ``"fd"``,
    ``"doane"``, ``"scott"``, ``"rice"``, ``"sturges"``, ``"sqrt"``.

    Raises:
        KeyError: if ``x``/``hue`` isn't a column in ``data``, or if ``theme`` is a
            string that isn't a registered preset name.
        TypeError: if ``theme`` is neither a ``Theme``, a preset name, nor ``None``.
        ValueError: if ``data`` has no rows, if no rows have a non-missing ``x``
            value, or (via ``stats.binning.histogram_bins``) if ``bins`` isn't a
            recognized spec.
    """
    resolved_theme = resolve_theme(theme)
    longform = ingest_longform(data, x)
    if len(longform) == 0:
        raise ValueError("data must contain at least one row")

    series_items = build_series(data, longform.columns, hue)

    series_values = [(label, _clean_values(columns, x)) for label, columns in series_items]
    all_values = [value for _, values in series_values for value in values]
    if not all_values:
        raise ValueError("no rows with a non-missing x value after dropping missing values")

    # Binned over xlim when one is given, not over this chart's own values: two charts
    # sharing an axis but not their bin boundaries draw bars of different widths, and a
    # count of 3 covers a different amount of data in each. Same rule this chart already
    # applies across hue= groups. The range alone does not settle it -- a strategy like
    # "auto" still picks its width from the values -- so the division is shared too.
    # ``xlim`` is validated here rather than left to ``bin_range``, so a bad value reports
    # the argument the caller wrote and gets the same message every other chart gives.
    # ``bin_range=None`` when there is no xlim: a constant column has a zero-width range,
    # which numpy handles by widening and ``apply_limit`` rightly refuses from a caller.
    bin_range = apply_limit((min(all_values), max(all_values)), xlim) if xlim is not None else None
    edges = histogram_bins(all_values, bins=bins, bin_range=bin_range)
    series_counts = [(label, _count_in_bins(values, edges)) for label, values in series_values]
    max_count = max((count for _, counts in series_counts for count in counts), default=0)
    if max_count == 0:
        # Reachable only since out-of-window values started being dropped rather than clamped
        # (see ``_count_in_bins``): before that the edge bins always caught something. There is
        # nothing to draw, and the two things a chart would carry away are both broken -- the
        # value domain would be ``(0, 0)``, which ``apply_limit`` refuses from a caller and so
        # cannot be replayed onto another chart, and the y axis would render its single ``0``
        # tick halfway up an otherwise empty plot area.
        #
        # Refused rather than widened to ``(0, 1)``, because ``xlim`` is the caller's argument
        # and this is the one value of it that can produce no chart at all. Naming it is what
        # separates "your window is empty" from a picture that looks like a rendering bug.
        raise ValueError(f"xlim={xlim!r} leaves no values in range, so there is nothing to bin")

    clipped = narrows((edges[0], edges[-1]), xlim) or narrows((0.0, float(max_count)), ylim)
    x_domain = apply_limit((edges[0], edges[-1]), xlim)
    y_domain = apply_limit((0.0, float(max_count)), ylim)
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

    pixel_x_scale = LinearScale(x_domain, (area.left, area.right))
    pixel_y_scale = LinearScale(y_domain, (area.bottom, area.top))
    render_x_axis(
        document,
        pixel_x_scale,
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

    viewport = marks_viewport(document, area, clipped=clipped)
    corner_radius = corner_radius_attr(resolved_theme.corner_radius)
    series_classes: list[str] = []
    legend_entries: list[tuple[str, str]] = []
    for label, counts in series_counts:
        series_class = document.semantic_class("series")
        series_classes.append(series_class)
        for bin_index, count in enumerate(counts):
            if count == 0:
                continue
            bar_left = pixel_x_scale(edges[bin_index])
            bar_right = pixel_x_scale(edges[bin_index + 1])
            bar_top = pixel_y_scale(count)
            attrib = {
                "x": format_coord(bar_left),
                "y": format_coord(bar_top),
                "width": format_coord(bar_right - bar_left),
                "height": format_coord(area.bottom - bar_top),
            }
            if corner_radius is not None:
                attrib["rx"] = corner_radius
            bar = document.add_node(viewport, "rect", attrib=attrib, classes=[series_class])
            if tooltip:
                add_tooltip(
                    document,
                    bar,
                    _bin_tooltip(
                        x=x,
                        hue=hue,
                        low=edges[bin_index],
                        high=edges[bin_index + 1],
                        # Only the final bin includes its right edge -- see ``_count_in_bins``.
                        closed=bin_index == len(counts) - 1,
                        count=count,
                        label=label,
                    ),
                )
        if label is not None:
            legend_entries.append((str(label), series_class))

    if legend_entries:
        render_legend(
            document,
            legend_entries,
            x=area.right + LEGEND_X_OFFSET,
            y=area.top,
            mark_style="fill",
            font_size=resolved_theme.legend_font_size,
        )

    render_theme_style(document, resolved_theme, series_classes, mark_style="fill")

    # The values *in the window*, not every value read. With a narrowing ``xlim`` those differ,
    # and the sentence already names the window on its next clause -- "200 observations, x 8 to
    # 12" describes a chart that was not drawn.
    drawn_count = sum(count for _, counts in series_counts for count in counts)
    observations = f'{plural(drawn_count, "observation")} in {plural(len(edges) - 1, "bin")}'
    description = describe(
        "Histogram",
        over([str(label) for label, _ in series_items] if hue is not None else None, observations),
        span("x", edges[0], edges[-1]),
        span("counts", 0, max_count),
    )
    return Chart(
        document,
        description=description,
        domains=Domains(x=x_domain, y=y_domain, x_step=(edges[-1] - edges[0]) / (len(edges) - 1)),
    )
