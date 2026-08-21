"""sparkline — a bare inline polyline, no axes/legend/labels/ticks.

Tufte's sparkline is a "datawords"-sized graphic meant to sit inside a line of
prose or a table cell, so it deliberately drops every piece of chart chrome the
other chart types provide: there is no axis, no legend, no tick, no title. That
makes it the only chart here whose canvas isn't ``DEFAULT_WIDTH``/``DEFAULT_HEIGHT``
(see ``charts/_layout.SPARKLINE_WIDTH``), and it is why this module calls neither
``charts/_axes`` nor ``charts/_legend`` — ``charts/pie.py`` is the precedent for an
axis-less chart defining its own margin instead of using the presets.

Out of scope, deliberately: pygal's ``render_sparktext`` (a unicode block-character
rendering) is an *output format* returning ``str``, not a ``Chart``, so it belongs in
``output/`` beside ``svg.py``/``png.py`` as its own issue rather than bundled here.
"""

from __future__ import annotations

from svgplot._svg import SvgDocument
from svgplot.chart.base import Chart
from svgplot.charts._describe import describe, plural, span
from svgplot.charts._layout import SPARKLINE_HEIGHT, SPARKLINE_WIDTH, _finite, format_coord, plot_area
from svgplot.charts._theme_resolve import resolve_theme
from svgplot.data._missing import is_missing
from svgplot.data.ingest import ingest_longform
from svgplot.scales import LinearScale
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style

_MARGIN = 2.0
"""A hairline inset on all four sides so the stroke's own width isn't clipped at the
canvas edge. Deliberately not one of ``_layout``'s presets: those reserve room for tick
labels and a legend, neither of which exists here."""


def _path_data(xs: list[float], ys: list[float]) -> str:
    commands = [f"M {format_coord(xs[0])},{format_coord(ys[0])}"]
    commands.extend(f"L {format_coord(px)},{format_coord(py)}" for px, py in zip(xs[1:], ys[1:], strict=True))
    return " ".join(commands)


def sparkline(
    data: object,
    y: str,
    *,
    width: float = SPARKLINE_WIDTH,
    height: float = SPARKLINE_HEIGHT,
    theme: Theme | str | None = None,
) -> Chart:
    """Draw a sparkline: one polyline over ``y``'s values, in input row order.

    There is no ``x=`` — a sparkline plots a sequence, so position along the x axis is
    the row index. Rows with a missing ``y`` are dropped, and the remaining values are
    plotted in their original order (unlike ``lineplot``, which sorts by ``x``: with no
    x column there is nothing to sort by, and reordering would misrepresent a sequence).

    ``theme=`` takes a :class:`~svgplot.theme.base.Theme`, the name of a preset
    (``"light"``, ``"dark"``, ``"minimal"``, ``"high_contrast"``, ``"print"``), or ``None``
    for the default theme. It is the only styling input -- colours, fonts, widths and
    opacities all come from it, and no render reads or writes global style state, so two
    charts given the same ``Theme`` are styled alike no matter what was drawn in between.

    ``data`` is long-form and only ``y`` is read from it; the rows keep their input order.

    ``width``/``height`` set the canvas in pixels and default to 120x24 -- a size meant to sit
    inside a line of text rather than to be looked into. They are plain floats here, not
    ``None``-means-default like the full-size charts, because there is no margin preset to
    pick: a sparkline draws no axis, no ticks and no legend.

    Raises:
        KeyError: if ``y`` isn't a column in ``data``, or if ``theme`` is a string that
            isn't a registered preset name.
        TypeError: if ``theme`` is neither a ``Theme``, a preset name, nor ``None``.
        ValueError: if ``data`` has no rows, if no rows remain after dropping missing
            values, or if ``width``/``height`` leave no room for the inset margin.
    """
    # The minimum-canvas rule is not sparkline's -- it draws no axes, legend or labels -- but
    # the *validation* is. Without this, `width="120"` came back as a TypeError about `str`
    # minus `float` and `width=nan` as one about an SVG literal, neither naming the argument.
    canvas_width, canvas_height = _finite(width, "width"), _finite(height, "height")
    resolved_theme = resolve_theme(theme)
    longform = ingest_longform(data, y)
    if len(longform) == 0:
        raise ValueError("data must contain at least one row")

    values = [float(value) for value in longform.columns[y] if not is_missing(value)]
    if not values:
        raise ValueError("no rows with a non-missing y value after dropping missing values")

    document = SvgDocument(width=canvas_width, height=canvas_height)
    area = plot_area(canvas_width, canvas_height, margin=_MARGIN)
    document.add_node(
        None,
        "rect",
        attrib={"x": 0, "y": 0, "width": format_coord(canvas_width), "height": format_coord(canvas_height)},
        classes=["plot-background"],
    )

    # A single point has no run to spread across, so pin it at the left edge rather than
    # letting a degenerate index domain resolve to the plot area's midpoint.
    x_scale = LinearScale((0.0, float(len(values) - 1)) if len(values) > 1 else (0.0, 1.0), (area.left, area.right))
    y_scale = LinearScale((min(values), max(values)), (area.bottom, area.top))

    series_class = document.semantic_class("series")
    document.add_node(
        None,
        "path",
        attrib={
            "d": _path_data(
                [x_scale(float(index)) for index in range(len(values))],
                [y_scale(value) for value in values],
            )
        },
        classes=[series_class],
    )

    render_theme_style(document, resolved_theme, [series_class])

    description = describe("Sparkline", plural(len(values), "point"), span("values", min(values), max(values)))
    return Chart(document, description=description)
