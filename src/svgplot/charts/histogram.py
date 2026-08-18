"""histplot — histograms with automatic binning (delegates to svgplot.stats.binning)."""

from __future__ import annotations

import bisect

from svgplot._svg import SvgDocument
from svgplot.chart.base import Chart
from svgplot.charts._axes import render_x_axis, render_y_axis
from svgplot.charts._layout import format_coord, plot_area
from svgplot.charts._legend import render_legend
from svgplot.charts._theme_resolve import resolve_theme
from svgplot.data.ingest import ingest_longform
from svgplot.data.semantic import extract_channels
from svgplot.scales import LinearScale
from svgplot.stats.binning import histogram_bins
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style

_WIDTH = 800.0
_HEIGHT = 600.0
_MARGIN_WITH_LEGEND = (30.0, 160.0, 50.0, 60.0)  # top, right, bottom, left
_MARGIN_WITHOUT_LEGEND = (30.0, 40.0, 50.0, 60.0)
_LEGEND_X_OFFSET = 20.0


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
) -> Chart:
    """Draw a histogram from long-form data with automatic binning.

    With ``hue=``, one histogram per distinct hue value is drawn as overlapping
    bars (colors cycling through the theme's palette, ``theme.fill_opacity``
    making the overlap visible) sharing one set of bin edges computed across all groups'
    combined values — so every group's bars land on directly comparable
    boundaries — with an auto-generated legend.

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

    edges = histogram_bins(all_values, bins=bins)
    series_counts = [(label, _count_in_bins(values, edges)) for label, values in series_values]
    max_count = max((count for _, counts in series_counts for count in counts), default=0)

    document = SvgDocument(width=_WIDTH, height=_HEIGHT)
    area = plot_area(_WIDTH, _HEIGHT, margin=_MARGIN_WITH_LEGEND if hue is not None else _MARGIN_WITHOUT_LEGEND)
    document.add_node(
        None,
        "rect",
        attrib={"x": 0, "y": 0, "width": format_coord(_WIDTH), "height": format_coord(_HEIGHT)},
        classes=["plot-background"],
    )

    pixel_x_scale = LinearScale((edges[0], edges[-1]), (area.left, area.right))
    pixel_y_scale = LinearScale((0, max_count), (area.bottom, area.top))
    render_x_axis(document, pixel_x_scale, area, tick_length=resolved_theme.tick_size)
    render_y_axis(document, pixel_y_scale, area, tick_length=resolved_theme.tick_size)

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
        render_legend(document, legend_entries, x=area.right + _LEGEND_X_OFFSET, y=area.top, mark_style="fill")

    render_theme_style(document, resolved_theme, series_classes, mark_style="fill")

    return Chart(document)
