"""regplot — a least-squares fit with a bootstrapped confidence band.

Delegates every number to ``svgplot.stats.regression``; this module only turns the fit
and the band into geometry.
"""

from __future__ import annotations

from svgplot.chart._domain import Domains, apply_limit
from svgplot.chart.base import Chart
from svgplot.charts._axes import fit_left_margin, render_x_axis, render_y_axis
from svgplot.charts._describe import describe, number, plural, span
from svgplot.charts._layout import (
    MARGIN_WITHOUT_LEGEND,
    TICK_SPACING_X,
    TICK_SPACING_Y,
    fit_margin,
    format_coord,
    new_canvas,
    resolve_size,
    ticks_for,
)
from svgplot.charts._theme_resolve import resolve_theme
from svgplot.charts._tooltip import add_tooltip, clause, format_number
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


def _band_tooltip(*, ci: float, n_boot: int) -> str:
    """What the band's ``<title>`` says: which interval it is, and how it was estimated.

    **The band is a mark that is neither a datum nor labelled, and this chart is the first to
    give one a name.** (``kdeplot``'s outline and ``violinplot``'s body are the same shape of
    thing; neither took ``tooltip=`` when this was written.) The line
    is obviously the fit and a point is obviously an observation, but a translucent region
    around a line reads as decoration until something names it -- and the ``<desc>`` names it
    once for the whole chart, which a reader pointing at the band is not being read.

    ``n_boot`` is part of the answer rather than an implementation detail: this is a *bootstrap*
    interval, so it is an estimate whose own precision depends on that number, and two charts
    of the same data with different ``n_boot`` draw different bands.

    Spelled as a percentage because ``ci=`` is a level rather than a measurement -- ``0.95``
    reads ``95%``. Through :func:`~svgplot.charts._describe.number`, **the same function the
    chart's own ``<desc>`` uses for this number**, because the two are halves of one claim: the
    ``<desc>`` says it once for the picture and this says it to the reader pointing at the band.
    Formatted two ways they disagreed -- ``ci=0.9501`` read ``95.01%`` in one and ``95%`` in the
    other, and ``ci=0.95`` and ``ci=0.9501`` produced *identical* tooltips for two charts that
    draw different bands.

    **Rounding to one decimal was worse than long.** It saturated at both ends: ``ci=0.999999``
    read ``100% confidence band`` while ``ci=1.0`` is refused outright by
    :func:`~svgplot.stats.regression.confidence_band` (``level must be strictly between 0 and
    1``), so the mark's *accessible name* asserted a certainty the package will not draw.
    ``ci=1e-07`` read ``0%`` the same way.

    ``seed=`` also changes the band and is deliberately not said. It changes *which* resamples
    were drawn, not what the interval estimates or how precisely -- ``n_boot`` is the one that
    sets the estimate's own precision, which is why it is here and the seed is not.

    ``float(ci)`` because the chart itself is more permissive than its type hint:
    ``confidence_band`` coerces, so ``ci="0.95"`` renders today, and this clause should not be
    the thing that turns a chart that draws into a ``TypeError``.
    """
    return f"{number(float(ci) * 100)}% confidence band · {plural(n_boot, 'bootstrap resample')}"


def _point_tooltip(*, x: str, y: str, xv: float, yv: float) -> str:
    """A point is one observation, so it reads its own row back -- the same thing
    ``scatterplot``'s tooltip says, from the same two channels."""
    return f"{clause(x, format_number(xv))} · {clause(y, format_number(yv))}"


def regplot(
    data: object,
    x: str,
    y: str,
    *,
    ci: float | None = 0.95,
    tooltip: bool = False,
    n_boot: int = 1000,
    seed: int = 0,
    scatter: bool = True,
    width: float | None = None,
    height: float | None = None,
    theme: Theme | str | None = None,
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
) -> Chart:
    """Draw a linear fit through long-form data, optionally with a confidence band.

    ``ci=None`` draws the line alone — the band is the expensive part (it refits
    ``n_boot`` times), so turning it off also turns off the work. ``n_boot`` and ``seed``
    are then unused and, having nothing to validate against, unchecked.

    ``seed`` is forwarded to :func:`svgplot.stats.regression.confidence_band`, which makes
    the whole chart reproducible: the same data and seed serialize to byte-identical SVG.

    ``tooltip=True`` gives every point a ``<title>`` naming its x and y, and gives **the band
    one of its own**. That second half is what this chart adds over the others: the line is
    obviously the fit and a point is obviously an observation, but a translucent region around
    a line reads as decoration until something names it -- and the chart's ``<desc>`` names it
    once for the whole picture, which a reader pointing at the band is not being read. The band
    says which interval it is and how many bootstrap resamples estimated it, because that is an
    estimate whose own precision depends on ``n_boot``. It is also the easiest mark here to
    point at: the band is an area where the line is two pixels wide.

    ``ci=None`` draws no band and so gives it no ``<title>``; ``scatter=False`` draws no points
    and gives them none. There is nothing to hang an accessible name on either way.

    **The fit line stays unnamed and stops taking the pointer.** It is drawn last, so its 2px
    stroke lies over the band along the middle of it, and a hit there would otherwise fall back
    to the nearest titled ancestor -- the root ``<svg>``, i.e. the chart's own name. Giving the
    line a ``<title>`` would not have helped: a title is not hit-testable and changes only what
    text is shown. So with ``tooltip=True`` the line gets ``pointer-events: none`` and the band
    underneath answers, which is the mark that has something to say; the line's meaning is what
    the ``<desc>`` already carries.

    ``tooltip=False`` is the default; off, the file is what it was.

    ``xlim=``/``ylim=`` replace the domain this chart would compute from its own data. They
    exist so several charts can be made to agree -- see :func:`~svgplot.layout.facet.facet`,
    which uses them to give faceted panels one axis -- and replace rather than widen, so a
    caller asking for a narrower view gets one.

    ``width``/``height`` set the canvas in pixels; ``None`` (the default) means 800x600, so a
    call that does not mention them is byte-identical to one written before they existed. The
    margin presets shrink to keep the plot area the majority of a small canvas and the tick
    count follows the plot extent — see ``charts/_layout.py``. Canvases below 240x180 are
    refused rather than clamped, and a chart may refuse a larger one if its own legend does
    not fit.

    ``scatter=False`` draws the fit and its band without the underlying points -- for the case
    where the points are already shown by another chart beside this one, or where there are
    enough of them to hide the line. The fit is computed from every point either way.

    It does move the line, though, which is worth knowing before comparing two such charts: the
    y domain is taken from the band plus the observations *when they are on screen*, so hiding
    them can shrink the axis and redraw the same fit at slightly different coordinates. Pin
    ``ylim`` and the two are identical.

    ``theme=`` takes a :class:`~svgplot.theme.base.Theme`, the name of a preset
    (``"light"``, ``"dark"``, ``"minimal"``, ``"high_contrast"``, ``"print"``), or ``None``
    for the default theme. Fonts, line widths, opacities and the grid/spine/tick colours come
    from it, along with every colour this chart's own arguments do not set. No render reads or
    writes global style state, so two charts given the same ``Theme`` are styled alike no
    matter what was drawn in between.

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
    x_domain = apply_limit(x_domain, xlim)
    y_domain = apply_limit(y_domain, ylim)

    canvas_width, canvas_height = resolve_size(width, height)
    document, area = new_canvas(
        fit_margin(
            fit_left_margin(
                MARGIN_WITHOUT_LEGEND, y_domain, width=canvas_width, font_size=resolved_theme.tick_label_font_size
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

    series_class = document.semantic_class("series")

    if ci is not None:
        # Drawn first so the fit line and the points sit on top of it.
        band_node = document.add_node(
            None,
            "path",
            attrib={"d": _band_path_data(band, pixel_x_scale, pixel_y_scale)},
            classes=[series_class, "regression-band"],
        )
        if tooltip:
            add_tooltip(document, band_node, _band_tooltip(ci=ci, n_boot=n_boot))

    if scatter:
        # ~12 lines duplicated from charts/scatter.py on purpose: with only two consumers a
        # shared charts/_marks.py is not yet earned, matching the precedent set by
        # charts/_layout.format_coord. Extract when a third consumer appears.
        for xv, yv in zip(xs, ys, strict=True):
            point = document.add_node(
                None,
                "circle",
                attrib={
                    "cx": format_coord(pixel_x_scale(xv)),
                    "cy": format_coord(pixel_y_scale(yv)),
                    "r": format_coord(resolved_theme.marker_size),
                },
                classes=[series_class, "scatter-point"],
            )
            if tooltip:
                add_tooltip(document, point, _point_tooltip(x=x, y=y, xv=xv, yv=yv))

    document.add_node(
        None,
        "path",
        attrib={"d": _line_path_data(band, pixel_x_scale, pixel_y_scale)},
        classes=[series_class, "regression-line"],
    )

    # "outlined" is what lets one series class carry all three marks: the band reads as a
    # translucent fill, the line and the points as the same colour at full strength.
    render_theme_style(
        document,
        resolved_theme,
        [series_class],
        mark_style="outlined",
        # The fit line is drawn last, so it is painted over the band and the points and takes
        # the pointer wherever its 2px stroke lies -- which is *inside the band's own area*,
        # along the middle of it. Untitled and still hit-testable, it answers with the nearest
        # ancestor that has a ``<title>``: the root ``<svg>``, i.e. the chart's own name. So the
        # one line a reader is most likely to point at says the least.
        #
        # A ``<title>`` on the line would not have fixed that -- a title is not hit-testable and
        # changes only *what text* is shown, never which element receives the pointer, which an
        # earlier version of this comment had backwards. Taking the line out of the way is what
        # lets the band underneath answer, and the band is the mark with something to say.
        transparent_to_pointer=("regression-line",) if tooltip else (),
    )

    description = describe(
        "Regression plot",
        f'fitted over {plural(len(xs), "point")}',
        span("x", *x_domain),
        span("y", *y_domain),
        f"with a {number(ci * 100)}% confidence band" if ci is not None else "no confidence band",
    )
    return Chart(document, description=description, domains=Domains(x=x_domain, y=y_domain))
