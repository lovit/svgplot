"""scatterplot — point charts with hue/size semantic channel mapping.

Follows ``charts/line.py``'s reference structure (issue #12): same shared
rendering infrastructure (``_layout``/``_axes``/``_legend``/``theme.css``),
adapted for unconnected point marks instead of a connected path.
"""

from __future__ import annotations

from collections.abc import Callable

from svgplot._svg import SvgDocument
from svgplot.chart.base import Chart
from svgplot.charts._axes import render_x_axis, render_y_axis
from svgplot.charts._layout import format_coord, plot_area
from svgplot.charts._legend import render_legend
from svgplot.charts._theme_resolve import resolve_theme
from svgplot.data.ingest import ingest_longform
from svgplot.data.semantic import extract_channels
from svgplot.scales import LinearScale
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style

_WIDTH = 800.0
_HEIGHT = 600.0
_MARGIN_WITH_LEGEND = (30.0, 160.0, 50.0, 60.0)  # top, right, bottom, left
_MARGIN_WITHOUT_LEGEND = (30.0, 40.0, 50.0, 60.0)
_LEGEND_X_OFFSET = 20.0  # past the plot area's right edge
_SIZE_LEGEND_GAP = 24.0  # vertical gap between the hue legend and the size legend
_SIZE_LEGEND_ROW_HEIGHT = 22.0
_SIZE_LEGEND_LABEL_GAP = 6.0

# A point's radius ranges from 0.5x to 2.5x the theme's base marker size when size=
# is mapped from data — wide enough to read as "varying," not so wide that the
# smallest points vanish or the largest overwhelm the plot area. Chosen empirically,
# not from a formula; documented here so a future reviewer knows it's a deliberate
# (if arbitrary) choice, not an accident.
_SIZE_RADIUS_MIN_FACTOR = 0.5
_SIZE_RADIUS_MAX_FACTOR = 2.5


def _is_missing(value: object) -> bool:
    return value is None or (isinstance(value, float) and value != value)


def _numeric_or_none(value: object) -> float | None:
    return None if _is_missing(value) else float(value)


def _radius_mapper(size_values: list[float], base_radius: float) -> Callable[[float], float]:
    """Return a function mapping a raw size value to a pixel radius, linearly
    scaled across ``size_values``'s ``[min, max]`` into
    ``[base_radius * _SIZE_RADIUS_MIN_FACTOR, base_radius * _SIZE_RADIUS_MAX_FACTOR]``.
    A constant size column (min == max) maps every value to ``base_radius``,
    since a 0-width domain has no meaningful ratio to scale by.
    """
    low, high = min(size_values), max(size_values)
    min_radius = base_radius * _SIZE_RADIUS_MIN_FACTOR
    max_radius = base_radius * _SIZE_RADIUS_MAX_FACTOR
    if high == low:
        return lambda _value: base_radius
    return lambda value: min_radius + (value - low) / (high - low) * (max_radius - min_radius)


def _render_size_legend(
    document: SvgDocument,
    size_values: list[float],
    radius_of: Callable[[float], float],
    *,
    x: float,
    y: float,
    marker_class: str,
) -> None:
    """Draw 3 representative samples (min/mid/max of ``size_values``) as circles
    of their mapped radius plus a value label each — a size legend can't reuse
    ``charts._legend.render_legend`` (uniform swatch shape), so this stays local
    to ``scatter.py`` rather than becoming a shared module for a single caller.

    ``marker_class`` reuses an already-``theme.css``-styled series class (rather
    than introducing an unstyled class this module has no way to color, since
    that would require a change to the shared ``theme/css.py`` this issue
    intentionally avoids touching) — every size sample renders in that one
    series' color, which stays theme-aware even when it isn't a perfect visual
    match for every hue group.
    """
    low, high = min(size_values), max(size_values)
    samples = sorted({low, (low + high) / 2, high})
    for index, sample in enumerate(samples):
        row_y = y + index * _SIZE_LEGEND_ROW_HEIGHT
        radius = radius_of(sample)
        document.add_node(
            None,
            "circle",
            attrib={"cx": format_coord(x + radius), "cy": format_coord(row_y), "r": format_coord(radius)},
            classes=[marker_class],
        )
        document.add_text(
            None,
            format_coord(sample),
            tag="text",
            attrib={
                "x": format_coord(x + 2 * (max(radius_of(high), radius_of(low))) + _SIZE_LEGEND_LABEL_GAP),
                "y": format_coord(row_y + 4),
            },
            classes=["legend-text"],
        )


def scatterplot(
    data: object,
    x: str,
    y: str,
    hue: str | None = None,
    size: str | None = None,
    *,
    theme: Theme | str | None = None,
) -> Chart:
    """Draw a scatter plot from long-form data.

    With ``hue=``, points are colored by distinct hue value (colors cycling
    through the theme's palette) with an auto-generated legend. With ``size=``,
    marker radius is linearly mapped from that numeric column's range (theme's
    ``marker_size`` as the anchor), with its own auto-generated legend showing
    representative min/mid/max samples. ``hue=`` and ``size=`` can be combined.

    Raises:
        KeyError: if ``x``/``y``/``hue``/``size`` isn't a column in ``data``, or if
            ``theme`` is a string that isn't a registered preset name.
        TypeError: if ``theme`` is neither a ``Theme``, a preset name, nor ``None``.
        ValueError: if ``data`` has no rows, or no rows remain after dropping rows
            with a missing x/y/size value.
    """
    resolved_theme = resolve_theme(theme)
    longform = ingest_longform(data, x, y)
    if len(longform) == 0:
        raise ValueError("data must contain at least one row")
    if size is not None and size not in longform.columns:
        raise KeyError(f"size column not found in data: {size!r}")

    if hue is not None:
        groups = extract_channels(data, hue=hue)
        if not groups:
            raise ValueError(f"no rows with a non-missing {hue!r} value")
        series_items = sorted(groups.items(), key=lambda item: str(item[0]))
    else:
        series_items = [(None, longform.columns)]

    # (label, x, y, size_or_None) per surviving row, grouped by hue label.
    series_rows: list[tuple[object, list[tuple[float, float, float | None]]]] = []
    for label, columns in series_items:
        rows = []
        for xv, yv, sv in zip(
            columns[x], columns[y], columns[size] if size is not None else [None] * len(columns[x]), strict=True
        ):
            xn, yn = _numeric_or_none(xv), _numeric_or_none(yv)
            sn = _numeric_or_none(sv) if size is not None else None
            if xn is None or yn is None or (size is not None and sn is None):
                continue
            rows.append((xn, yn, sn))
        series_rows.append((label, rows))

    all_rows = [row for _, rows in series_rows for row in rows]
    if not all_rows:
        raise ValueError("no rows with usable x/y (and size=, if given) values after dropping missing values")
    all_x = [row[0] for row in all_rows]
    all_y = [row[1] for row in all_rows]
    x_domain = (min(all_x), max(all_x))
    y_domain = (min(all_y), max(all_y))

    has_legend = hue is not None or size is not None
    document = SvgDocument(width=_WIDTH, height=_HEIGHT)
    area = plot_area(_WIDTH, _HEIGHT, margin=_MARGIN_WITH_LEGEND if has_legend else _MARGIN_WITHOUT_LEGEND)
    document.add_node(
        None,
        "rect",
        attrib={"x": 0, "y": 0, "width": format_coord(_WIDTH), "height": format_coord(_HEIGHT)},
        classes=["plot-background"],
    )

    pixel_x_scale = LinearScale(x_domain, (area.left, area.right))
    pixel_y_scale = LinearScale(y_domain, (area.bottom, area.top))
    render_x_axis(document, pixel_x_scale, area, tick_length=resolved_theme.tick_size)
    render_y_axis(document, pixel_y_scale, area, tick_length=resolved_theme.tick_size)

    radius_of = _radius_mapper([row[2] for row in all_rows], resolved_theme.marker_size) if size is not None else None

    series_classes: list[str] = []
    legend_entries: list[tuple[str, str]] = []
    for label, rows in series_rows:
        series_class = document.semantic_class("series")
        series_classes.append(series_class)
        for xv, yv, sv in rows:
            radius = radius_of(sv) if radius_of is not None else resolved_theme.marker_size
            document.add_node(
                None,
                "circle",
                attrib={
                    "cx": format_coord(pixel_x_scale(xv)),
                    "cy": format_coord(pixel_y_scale(yv)),
                    "r": format_coord(radius),
                },
                classes=[series_class, "scatter-point"],
            )
        if label is not None:
            legend_entries.append((str(label), series_class))

    legend_bottom = area.top
    if legend_entries:
        render_legend(document, legend_entries, x=area.right + _LEGEND_X_OFFSET, y=area.top, mark_style="fill")
        legend_bottom = area.top + len(legend_entries) * 20.0 + _SIZE_LEGEND_GAP
    if size is not None:
        _render_size_legend(
            document,
            [row[2] for row in all_rows],
            radius_of,
            x=area.right + _LEGEND_X_OFFSET,
            y=legend_bottom,
            marker_class=series_classes[0],
        )

    render_theme_style(document, resolved_theme, series_classes, mark_style="fill")

    return Chart(document)
