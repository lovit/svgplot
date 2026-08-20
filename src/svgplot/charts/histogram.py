"""histplot — histograms with automatic binning (delegates to svgplot.stats.binning)."""

from __future__ import annotations

import bisect

from svgplot.chart._domain import Domains, apply_limit
from svgplot.chart.base import Chart
from svgplot.charts._axes import fit_left_margin, render_x_axis, render_y_axis
from svgplot.charts._describe import describe, over, plural, span
from svgplot.charts._layout import (
    DEFAULT_WIDTH,
    LEGEND_X_OFFSET,
    MARGIN_WITH_LEGEND,
    MARGIN_WITHOUT_LEGEND,
    format_coord,
    new_canvas,
)
from svgplot.charts._legend import render_legend
from svgplot.charts._theme_resolve import resolve_theme
from svgplot.data.ingest import ingest_longform
from svgplot.data.semantic import extract_channels
from svgplot.scales import LinearScale
from svgplot.stats.binning import histogram_bins
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style


def _clean_values(columns: dict[str, list], x: str) -> list[float]:
    """Drop missing (``None``/NaN) values from column ``x``."""
    return [float(v) for v in columns[x] if v is not None and not (isinstance(v, float) and v != v)]


def _count_in_bins(values: list[float], edges: list[float]) -> list[int]:
    """Bin each value via ``edges`` (``edges[i] <= value < edges[i+1]``), except the
    final bin, which is inclusive on both ends — otherwise the maximum value in the
    dataset is silently dropped (the standard numpy/histogram convention).
    """
    n_bins = len(edges) - 1
    counts = [0] * n_bins
    for value in values:
        # bisect_right(edges, value) - 1 gives the bin index i such that
        # edges[i] <= value < edges[i+1]; the upper clamp handles value == edges[-1]
        # (bisect_right returns len(edges) there) by folding it into the last bin.
        # The lower clamp is defensive: a value below edges[0] would give -1, which
        # indexes the *last* bin instead of the first. Unreachable today (edges always
        # come from histogram_bins(all_values), so edges[0] == min(values)), but it
        # would silently miscount for any future caller passing custom edges.
        index = max(0, min(bisect.bisect_right(edges, value) - 1, n_bins - 1))
        counts[index] += 1
    return counts


def histplot(
    data: object,
    x: str,
    hue: str | None = None,
    *,
    bins: str | int = "auto",
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

    ``xlim=``/``ylim=`` replace the domain this chart would compute from its own data. They
    exist so several charts can be made to agree -- see :func:`~svgplot.layout.facet.facet`,
    which uses them to give faceted panels one axis -- and replace rather than widen, so a
    caller asking for a narrower view gets one. Note that this chart's y domain is a
    **derived** quantity, not a column: nothing outside the chart could have computed it,
    which is why the domain is recorded on the returned chart rather than predicted.

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

    if hue is not None:
        groups = extract_channels(data, hue=hue)
        if not groups:
            raise ValueError(f"no rows with a non-missing {hue!r} value")
        series_items = sorted(groups.items(), key=lambda item: str(item[0]))
    else:
        series_items = [(None, longform.columns)]

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

    x_domain = apply_limit((edges[0], edges[-1]), xlim)
    y_domain = apply_limit((0.0, float(max_count)), ylim)
    document, area = new_canvas(
        fit_left_margin(
            MARGIN_WITH_LEGEND if hue is not None else MARGIN_WITHOUT_LEGEND,
            y_domain,
            width=DEFAULT_WIDTH,
            font_size=resolved_theme.tick_label_font_size,
        )
    )

    pixel_x_scale = LinearScale(x_domain, (area.left, area.right))
    pixel_y_scale = LinearScale(y_domain, (area.bottom, area.top))
    render_x_axis(
        document, pixel_x_scale, area, tick_length=resolved_theme.tick_size, font_size=resolved_theme.tick_label_font_size
    )
    render_y_axis(
        document, pixel_y_scale, area, tick_length=resolved_theme.tick_size, font_size=resolved_theme.tick_label_font_size
    )

    corner_radius = format_coord(resolved_theme.corner_radius) if resolved_theme.corner_radius else None
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
            document.add_node(None, "rect", attrib=attrib, classes=[series_class])
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

    observations = f'{plural(len(all_values), "observation")} in {plural(len(edges) - 1, "bin")}'
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
