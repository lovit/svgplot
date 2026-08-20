"""regplot — a least-squares fit with a bootstrapped confidence band.

Delegates every number to ``svgplot.stats.regression``; this module only turns the fit
and the band into geometry.
"""

from __future__ import annotations

from svgplot._svg import SvgDocument
from svgplot.chart.base import Chart
from svgplot.charts._axes import render_x_axis, render_y_axis
from svgplot.charts._layout import (
    MARGIN_WITHOUT_LEGEND,
    TICK_SPACING_X,
    TICK_SPACING_Y,
    fit_margin,
    format_coord,
    plot_area,
    resolve_size,
    ticks_for,
)
from svgplot.charts._theme_resolve import resolve_theme
from svgplot.data._missing import is_missing
from svgplot.data.ingest import ingest_longform
from svgplot.scales import LinearScale
from svgplot.stats.regression import RegressionBand, confidence_band, fit_curve
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style

_BAND_GRID = 100
"""How many x positions the band is sampled at. ``stats.regression``'s own default; named
here because it also fixes how many vertices the emitted path carries."""


def _xy_pairs(columns: dict[str, list], x: str, y: str) -> tuple[list[float], list[float]]:
    """Rows where both channels are present, in input order."""
    pairs = [
        (float(xv), float(yv))
        for xv, yv in zip(columns[x], columns[y], strict=True)
        if not is_missing(xv) and not is_missing(yv)
    ]
    return [pair[0] for pair in pairs], [pair[1] for pair in pairs]


def _band_path_data(band: RegressionBand, x_scale: LinearScale, y_scale: LinearScale) -> str:
    """The band as one closed region: along the upper edge left-to-right, back along the
    lower edge right-to-left, then ``Z``.

    Same shape as ``area``'s stacked band. Two separate open paths would need their own
    fill rule to become a region, and the gap between them would not be fillable at all.
    """
    upper = [(x_scale(px), y_scale(py)) for px, py in zip(band.x, band.upper, strict=True)]
    lower = [(x_scale(px), y_scale(py)) for px, py in zip(band.x, band.lower, strict=True)]
    commands = [f"M {format_coord(upper[0][0])},{format_coord(upper[0][1])}"]
    commands.extend(f"L {format_coord(px)},{format_coord(py)}" for px, py in upper[1:])
    commands.extend(f"L {format_coord(px)},{format_coord(py)}" for px, py in reversed(lower))
    commands.append("Z")
    return " ".join(commands)


def _line_path_data(band: RegressionBand, x_scale: LinearScale, y_scale: LinearScale) -> str:
    points = [(x_scale(px), y_scale(py)) for px, py in zip(band.x, band.y, strict=True)]
    commands = [f"M {format_coord(points[0][0])},{format_coord(points[0][1])}"]
    commands.extend(f"L {format_coord(px)},{format_coord(py)}" for px, py in points[1:])
    return " ".join(commands)


def regplot(
    data: object,
    x: str,
    y: str,
    *,
    ci: float | None = 0.95,
    n_boot: int = 1000,
    seed: int = 0,
    scatter: bool = True,
    width: float | None = None,
    height: float | None = None,
    theme: Theme | str | None = None,
) -> Chart:
    """Draw a linear fit through long-form data, optionally with a confidence band.

    ``ci=None`` draws the line alone — the band is the expensive part (it refits
    ``n_boot`` times), so turning it off also turns off the work. ``n_boot`` and ``seed``
    are then unused and, having nothing to validate against, unchecked.

    ``seed`` is forwarded to :func:`svgplot.stats.regression.confidence_band`, which makes
    the whole chart reproducible: the same data and seed serialize to byte-identical SVG.

    ``width``/``height`` set the canvas in pixels; ``None`` (the default) means 800x600, so a
    call that does not mention them is byte-identical to one written before they existed. The
    margin presets shrink to keep the plot area the majority of a small canvas and the tick
    count follows the plot extent — see ``charts/_layout.py``. Canvases below 240x180 are
    refused rather than clamped, and a chart may refuse a larger one if its own legend does
    not fit.

    Raises:
        KeyError: if ``x``/``y`` isn't a column in ``data``, or if ``theme`` is a string
            that isn't a registered preset name.
        TypeError: if ``theme`` is neither a ``Theme``, a preset name, nor ``None``.
        ValueError: if ``data`` has no rows, if fewer than three rows have both channels,
            or (via ``stats.regression``) for an unusable ``ci``/``n_boot``, a vertical set
            of points, or a range too wide for the arithmetic.
    """
    resolved_theme = resolve_theme(theme)
    longform = ingest_longform(data, x, y)
    if len(longform) == 0:
        raise ValueError("data must contain at least one row")

    xs, ys = _xy_pairs(longform.columns, x, y)
    if not xs:
        raise ValueError("no rows with both x and y present after dropping missing values")

    if ci is None:
        band = fit_curve(xs, ys, grid=_BAND_GRID)
    else:
        band = confidence_band(xs, ys, level=ci, n_boot=n_boot, seed=seed, grid=_BAND_GRID)

    # The band, where drawn, always contains the line, so the y domain only needs its
    # extremes -- plus the observations when they are on screen.
    y_candidates = [*band.lower, *band.upper, *(ys if scatter else [])]
    x_domain = (min(xs), max(xs))
    y_domain = (min(y_candidates), max(y_candidates))

    canvas_width, canvas_height = resolve_size(width, height)
    document = SvgDocument(width=canvas_width, height=canvas_height)
    area = plot_area(canvas_width, canvas_height, margin=fit_margin(MARGIN_WITHOUT_LEGEND, canvas_width, canvas_height))
    document.add_node(
        None,
        "rect",
        attrib={"x": 0, "y": 0, "width": format_coord(canvas_width), "height": format_coord(canvas_height)},
        classes=["plot-background"],
    )

    pixel_x_scale = LinearScale(x_domain, (area.left, area.right))
    pixel_y_scale = LinearScale(y_domain, (area.bottom, area.top))
    render_x_axis(
        document, pixel_x_scale, area, tick_count=ticks_for(area.width, TICK_SPACING_X), tick_length=resolved_theme.tick_size
    )
    render_y_axis(
        document, pixel_y_scale, area, tick_count=ticks_for(area.height, TICK_SPACING_Y), tick_length=resolved_theme.tick_size
    )

    series_class = document.semantic_class("series")

    if ci is not None:
        # Drawn first so the fit line and the points sit on top of it.
        document.add_node(
            None,
            "path",
            attrib={"d": _band_path_data(band, pixel_x_scale, pixel_y_scale)},
            classes=[series_class, "regression-band"],
        )

    if scatter:
        # ~12 lines duplicated from charts/scatter.py on purpose: with only two consumers a
        # shared charts/_marks.py is not yet earned, matching the precedent set by
        # charts/_layout.format_coord. Extract when a third consumer appears.
        for xv, yv in zip(xs, ys, strict=True):
            document.add_node(
                None,
                "circle",
                attrib={
                    "cx": format_coord(pixel_x_scale(xv)),
                    "cy": format_coord(pixel_y_scale(yv)),
                    "r": format_coord(resolved_theme.marker_size),
                },
                classes=[series_class, "scatter-point"],
            )

    document.add_node(
        None,
        "path",
        attrib={"d": _line_path_data(band, pixel_x_scale, pixel_y_scale)},
        classes=[series_class, "regression-line"],
    )

    # "outlined" is what lets one series class carry all three marks: the band reads as a
    # translucent fill, the line and the points as the same colour at full strength.
    render_theme_style(document, resolved_theme, [series_class], mark_style="outlined")

    return Chart(document)
