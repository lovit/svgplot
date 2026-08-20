"""areaplot — filled area charts (fill_between-style), with an optional stacked mode.

Reuses charts/line.py's overall shape (SvgDocument -> plot area -> scales ->
axes -> per-series marks -> legend -> theme.css style block -> Chart) — see
that module for the fuller rationale of the shared pieces this also uses
(charts/_axes.py, _legend.py, _layout.py, _theme_resolve.py, theme/css.py).
Marks are filled (``mark_style="fill"``), unlike lineplot's stroked paths.
"""

from __future__ import annotations

from svgplot.chart._domain import Domains, apply_limit
from svgplot.chart.base import Chart
from svgplot.charts._axes import fit_left_margin, render_x_axis, render_y_axis
from svgplot.charts._layout import (
    DEFAULT_WIDTH,
    LEGEND_X_OFFSET,
    MARGIN_WITH_LEGEND,
    MARGIN_WITHOUT_LEGEND,
    format_coord,
    new_canvas,
)
from svgplot.charts._legend import render_legend
from svgplot.charts._series import series_items as build_series
from svgplot.charts._theme_resolve import resolve_theme
from svgplot.data.ingest import ingest_longform
from svgplot.scales import LinearScale
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style


def _series_points(columns: dict[str, list], x: str, y: str) -> list[tuple[float, float]]:
    """Drop rows with a missing x or y value, sum any rows sharing an x, then sort
    by x (mirrors ``charts/line.py``'s ``_series_points`` — no datetime x support
    here, this issue's AC doesn't call for it).

    An area is a function of x: exactly one filled height per x. Rows sharing an x
    are therefore summed into one point rather than kept as separate vertices, and
    the aggregation happens here so the stacked and unstacked paths — which both
    build on this — can never disagree about what a repeated x means.
    """
    totals: dict[float, float] = {}
    for xv, yv in zip(columns[x], columns[y], strict=True):
        if xv is None or yv is None or (isinstance(yv, float) and yv != yv):
            continue
        key = float(xv)
        totals[key] = totals.get(key, 0.0) + float(yv)
    return sorted(totals.items())


def _closed_path_data(xs: list[float], ys: list[float], baseline_y: float) -> str:
    """A single unstacked series' filled area: the point path, then closed down
    to the baseline and back to the start — the baseline is data-space y=0,
    mapped through the y scale (so it sits at the plot area's bottom only when
    0 is also the y domain's minimum, which ``areaplot`` always ensures by
    including 0 in the domain).
    """
    if not xs:
        return ""
    commands = [f"M {format_coord(xs[0])},{format_coord(ys[0])}"]
    commands.extend(f"L {format_coord(px)},{format_coord(py)}" for px, py in zip(xs[1:], ys[1:], strict=True))
    commands.append(f"L {format_coord(xs[-1])},{format_coord(baseline_y)}")
    commands.append(f"L {format_coord(xs[0])},{format_coord(baseline_y)}")
    commands.append("Z")
    return " ".join(commands)


def _stacked_band_path_data(xs: list[float], tops: list[float], bottoms: list[float]) -> str:
    """A stacked series' filled band: along its own cumulative top edge left-to-right,
    then back along the previous series' cumulative top (this series' bottom edge)
    right-to-left, closing the shape.
    """
    if not xs:
        return ""
    commands = [f"M {format_coord(xs[0])},{format_coord(tops[0])}"]
    commands.extend(f"L {format_coord(px)},{format_coord(py)}" for px, py in zip(xs[1:], tops[1:], strict=True))
    for px, py in zip(reversed(xs), reversed(bottoms), strict=True):
        commands.append(f"L {format_coord(px)},{format_coord(py)}")
    commands.append("Z")
    return " ".join(commands)


def areaplot(
    data: object,
    x: str,
    y: str,
    hue: str | None = None,
    *,
    stacked: bool = False,
    theme: Theme | str | None = None,
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
) -> Chart:
    """Draw a filled area chart from long-form data.

    With ``hue=``, one area per distinct hue value is drawn (colors cycling
    through the theme's palette) with an auto-generated legend. With
    ``stacked=True`` and ``hue=``, areas stack cumulatively instead of each
    starting at the baseline — the shared x axis is the union of every hue
    group's x values, and a (hue, x) pair absent from a group counts as 0 for
    that group's contribution to the stack. ``stacked=True`` without ``hue=``
    has nothing to stack and renders as a single plain area.

    Rows sharing an x within one series are **summed** into a single point — an
    area has one filled height per x, so two records at the same x contribute
    their combined value there. This holds identically in stacked and unstacked
    mode.

    ``xlim=``/``ylim=`` replace the domain this chart would compute from its own data. They
    exist so several charts can be made to agree -- see :func:`~svgplot.layout.facet.facet`,
    which uses them to give faceted panels one axis -- and replace rather than widen, so a
    caller asking for a narrower view gets one.

    Raises:
        KeyError: if ``x``/``y``/``hue`` isn't a column in ``data``, or if ``theme``
            is a string that isn't a registered preset name.
        TypeError: if ``theme`` is neither a ``Theme``, a preset name, nor ``None``.
        ValueError: if ``data`` has no rows, or no rows survive after dropping
            rows with a missing x or y value.
    """
    resolved_theme = resolve_theme(theme)
    longform = ingest_longform(data, x, y)
    if len(longform) == 0:
        raise ValueError("data must contain at least one row")

    series_items = build_series(data, longform.columns, hue)

    series_points = [(label, _series_points(columns, x, y)) for label, columns in series_items]

    all_x = [point[0] for _, points in series_points for point in points]
    all_y = [point[1] for _, points in series_points for point in points]
    if not all_x:
        raise ValueError("no rows with both x and y present after dropping missing values")

    do_stack = stacked and hue is not None

    stacked_bands: list[tuple[object, list[float], list[float], list[float]]] = []
    if do_stack:
        x_union = sorted(set(all_x))
        cumulative = [0.0] * len(x_union)
        for label, points in series_points:
            # Safe as a dict: _series_points already collapsed repeated x values,
            # so nothing here can be silently overwritten.
            lookup = dict(points)
            values = [lookup.get(xv, 0.0) for xv in x_union]
            bottoms = list(cumulative)
            cumulative = [c + v for c, v in zip(cumulative, values, strict=True)]
            stacked_bands.append((label, x_union, bottoms, list(cumulative)))
        x_domain = (x_union[0], x_union[-1])
        y_domain_values = [0.0, *cumulative]
    else:
        x_domain = (min(all_x), max(all_x))
        y_domain_values = [0.0, *all_y]

    y_domain = (min(y_domain_values), max(y_domain_values))
    x_domain = apply_limit(x_domain, xlim)
    y_domain = apply_limit(y_domain, ylim)

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

    baseline_y = pixel_y_scale(0.0)
    series_classes: list[str] = []
    legend_entries: list[tuple[str, str]] = []

    if do_stack:
        for label, xs, bottoms, tops in stacked_bands:
            series_class = document.semantic_class("series")
            series_classes.append(series_class)
            pixel_xs = [pixel_x_scale(value) for value in xs]
            pixel_tops = [pixel_y_scale(value) for value in tops]
            pixel_bottoms = [pixel_y_scale(value) for value in bottoms]
            document.add_node(
                None,
                "path",
                attrib={"d": _stacked_band_path_data(pixel_xs, pixel_tops, pixel_bottoms)},
                classes=[series_class, "area-series"],
            )
            if label is not None:
                legend_entries.append((str(label), series_class))
    else:
        for label, points in series_points:
            series_class = document.semantic_class("series")
            series_classes.append(series_class)
            if points:
                pixel_xs = [pixel_x_scale(px) for px, _ in points]
                pixel_ys = [pixel_y_scale(py) for _, py in points]
                document.add_node(
                    None,
                    "path",
                    attrib={"d": _closed_path_data(pixel_xs, pixel_ys, baseline_y)},
                    classes=[series_class, "area-series"],
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

    return Chart(document, domains=Domains(x=x_domain, y=y_domain))
