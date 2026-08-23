"""Plot-area layout math shared by every chart type.

Three responsibilities: (1) the default canvas size and margin presets every
chart starts from, (2) a CSS-box-model-like margin (single value applies
to all 4 sides, or a 4-tuple for per-side control — pygal precedent,
docs-research/12-aesthetics.md:31) resolved into a plot-area rect, and
(3) SVG-literal coordinate formatting, so every chart's path/line/rect
coordinates stay clean literals rather than floating-point noise (mirrors
``_svg.py``'s private ``_format_number`` — that function isn't reusable
outside its own module, so this is a deliberate, minimal duplication of its
rounding rule, kept in one place here rather than repeated in every
``charts/*.py`` file).

Private/internal — not re-exported from ``svgplot.charts``.
"""

from __future__ import annotations

import math
import numbers
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass

from svgplot._svg import SvgDocument
from svgplot.scales import LinearScale, LogScale

Margin = float | tuple[float, float, float, float]

DEFAULT_WIDTH = 800.0
DEFAULT_HEIGHT = 600.0
"""Default canvas size. Every chart type starts here; ``layout.sizing.apply_size``
and ``chart.composition`` scale from it rather than each chart choosing its own."""

MARGIN_WITH_LEGEND = (30.0, 160.0, 50.0, 60.0)  # top, right, bottom, left
MARGIN_WITHOUT_LEGEND = (30.0, 40.0, 50.0, 60.0)
"""The two margin presets an axed chart picks between: the wide right margin reserves
legend space, the narrow one doesn't. Both leave the same room at bottom/left for tick
labels. A chart with no axes (see ``charts/pie.py``) needs neither and defines its own.

``MARGIN_WITHOUT_LEGEND`` is also what a chart that never draws a legend uses (e.g.
``charts/box.py``, which labels its categories on the x-axis instead) — so retuning it
for a legend-capable chart's benefit would silently move those charts too."""

LEGEND_X_OFFSET = 20.0
"""Gap between the plot area's right edge and the legend's left edge."""

SPARKLINE_WIDTH = 120.0
SPARKLINE_HEIGHT = 24.0
"""Canvas size for ``charts/sparkline.py``, the one chart that can't start from
``DEFAULT_WIDTH``/``DEFAULT_HEIGHT``. A sparkline is meant to sit inline in a line of
prose or a table cell, so its size is bounded by the surrounding text rather than
chosen for readable axis labels — and it draws no axes, legend or labels at all, so
the margin presets above have nothing to reserve space for."""


MIN_WIDTH = 240.0
MIN_HEIGHT = 180.0
"""The smallest canvas this package will draw an axed chart on.

**Where 240 comes from.** Two measured floors, and a round number above both. The binding
constraint on a narrow canvas is the legend gutter -- not the plot area, which stays a fixed
share of the width, and not the ticks, which thin out. The right margin after
:func:`fit_margin` is ``160 * (MAX_MARGIN_FRACTION * width / 220)``, of which
:data:`LEGEND_X_OFFSET` (20), the swatch (16) and its gap (6) are fixed. Solving that against
``charts._legend.minimum_legend_text_width(11.0)`` -- the room below which shortening a label
stops helping -- gives **209.0 px**; solving it against ``charts._textwidth.text_width`` of a
five-character label gives **227.5 px**, the width at which such a label renders whole rather
than shortened. 240 is above both, and pairs with :data:`MIN_HEIGHT` at the same 4:3 the
package's 800 x 600 default uses. A test pins the two floors and that this clears them.

It is deliberately not itself a boundary. An earlier version claimed it was, deriving 239.25
from a hand-rolled estimate of 0.55 em per character on the premise that a label's width was
"unknowable here". Both halves were wrong: ``charts/_textwidth.py`` measures it, and 0.55 sat
below a digit's own 0.556, so the estimate under-reserved exactly where a label overflows.

A caller whose legend labels are longer than the gutter does **not** need a wider canvas:
``render_legend`` shortens the label with an ellipsis and keeps the full text in a ``<title>``
child, which assistive technology reads. At 240 a five-character label renders whole and a
nine-character one comes out as ``sou…`` with ``southeast`` in its title (measured).

**Where 180 comes from.** The same 4:3, applied to the width. Nothing vertical binds anywhere
near it: at 180 the plot area is still 100 px tall, four times the 24 px that two tick labels
need at a 1.2 line height.

**Refused, not clamped or warned about.** ``gaugeplot``'s precedent, for geometry that would
render but not be readable — "a silently unreadable chart is worse than a message naming the
limit" — rather than ``heatmap``'s, which warns because its output is still correct, just
large. A caller who asked for 100 px and silently got 240 would have a chart that does not
fit where they meant to put it, and no way to find out except by measuring the file.

``sparkline`` is exempt and always has been: it draws no axes, legend or labels, so none of
the above applies. Its own 120 x 24 default is well under these numbers."""

MAX_MARGIN_FRACTION = 0.45
"""How much of each dimension the margins may take between them before they are scaled
down. The presets above are absolute pixel values tuned for an 800 x 600 canvas, where
they take 220/800 = 27.5% of the width and 80/600 = 13.3% of the height. Left alone on a
300 px canvas they would take 73%, leaving an 80 px plot area — the issue's own example.

45% is the point at which the plot area still gets the majority of the canvas. It is above
what the default size uses, which is the property that matters most: the clamp cannot
engage at the default size, so every existing chart is byte-identical.

Scaling both sides of a pair by the same factor, rather than trimming the larger one,
keeps the legend gutter in proportion to the tick-label gutter — the two are competing for
the same space and neither is more expendable than the other."""

TICK_SPACING_X = 128.0
TICK_SPACING_Y = 104.0
"""Target pixels per tick, derived from what the package already draws at its default size
so that deriving the count changes nothing there.

Every axed chart passes a fixed ``tick_count=5`` today. At 800 x 600 that count is applied
to a plot area of either 700 x 520 (``MARGIN_WITHOUT_LEGEND``) or 580 x 520
(``MARGIN_WITH_LEGEND``) — two different widths asking for the same five ticks. A single
horizontal spacing has to round both to 5, which pins it to the interval 127.3-128.9;
128 is the round number inside it. Vertically both presets leave 520 px, so 520/5 = 104
falls out directly.

The two differ because the labels do: an x tick label sits *beside* its neighbours and a y
tick label sits *above* its neighbours, so the horizontal axis needs room for a label's
width and the vertical only for its height."""

MIN_TICKS = 2
MAX_TICKS = 10
"""Bounds on the derived tick count. Two is the fewest that still shows a scale (the ends);
ten is where ``scales.make_ticks``' nice-number search stops helping and the labels start
competing for space even on a wide canvas."""


@dataclass(frozen=True)
class PlotArea:
    """The rectangle data marks are drawn into, in SVG pixel coordinates."""

    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top


def resolve_margin(margin: Margin) -> tuple[float, float, float, float]:
    """Resolve a CSS-shorthand-style margin into explicit ``(top, right, bottom, left)``.

    A single number applies to all 4 sides; a 4-tuple gives each side independently.

    Raises:
        ValueError: if ``margin`` is neither a number nor a 4-tuple of numbers.
    """
    if isinstance(margin, int | float) and not isinstance(margin, bool):
        return (float(margin),) * 4
    if isinstance(margin, tuple) and len(margin) == 4:
        return tuple(float(side) for side in margin)
    raise ValueError(f"margin must be a number or a (top, right, bottom, left) 4-tuple, got {margin!r}")


def plot_area(width: float, height: float, margin: Margin = 60.0) -> PlotArea:
    """Compute the plot-area rect for a ``width`` x ``height`` canvas with ``margin``.

    Raises:
        ValueError: if ``margin`` is malformed (see :func:`resolve_margin`), or if the
            resulting plot area would have non-positive width/height (margin too large
            for the canvas size).
    """
    top, right, bottom, left = resolve_margin(margin)
    area = PlotArea(left=left, top=top, right=width - right, bottom=height - bottom)
    if area.width <= 0 or area.height <= 0:
        raise ValueError(f"margin {margin!r} leaves a non-positive plot area for a {width}x{height} canvas")
    return area


def format_coord(value: float) -> str:
    """Format a coordinate/length as a clean SVG literal (e.g. ``"120.5"``, not
    ``"120.50000000000001"``) — see this module's docstring for why this duplicates
    ``_svg.py``'s private ``_format_number`` rather than importing it.

    Raises:
        ValueError: if ``value`` isn't finite, or can't be converted to ``float``.
    """
    try:
        number = float(value)
    except (TypeError, OverflowError, ValueError) as error:
        raise ValueError(f"cannot format value as an SVG coordinate literal: {value!r}") from error
    if not math.isfinite(number):
        raise ValueError(f"cannot format a non-finite coordinate: {value!r}")
    rounded = round(number, 6)
    if rounded == int(rounded):
        return str(int(rounded))
    text = f"{rounded:.6f}".rstrip("0").rstrip(".")
    return text


def corner_radius_attr(radius: float) -> str | None:
    """The ``rx`` a rectangle should carry for ``theme.corner_radius``, or ``None`` for none.

    One function because the rule -- "round only for a radius greater than zero" -- was written
    three times and two of the three were wrong. ``barplot`` asked ``> 0``; ``histplot`` and
    ``boxplot`` asked for truthiness, which is a different question: ``-5.0`` is truthy, so both
    emitted ``rx="-5"``, an invalid SVG attribute that renders as nothing in some viewers and as
    an error in others. ``nan`` split them a third way -- truthy, so it reached
    :func:`format_coord` and raised, while ``> 0`` is false for ``nan`` and ``barplot`` drew
    square corners in silence (#258).

    ``Theme.__post_init__`` now refuses those values at construction, which is where the failure
    belongs. This stays as the single expression of the rendering half: it is what makes the
    three charts *agree*, and it still holds if a radius arrives by some route that skips the
    constructor -- ``Theme`` is frozen, but ``object.__setattr__`` is not locked away.
    """
    return format_coord(radius) if radius > 0 else None


MARGIN_WITH_SIDE_LEGEND = (30.0, 180.0, 30.0, 30.0)
"""Margin for a chart that has no axes but does have a legend down the right side.

``pieplot``, ``treemap`` and ``gaugeplot`` all drew from this tuple. Wider on the right than
:data:`MARGIN_WITH_LEGEND` because there is no y axis to leave room for on the left, so the
plot can start further in and give the legend more."""


def format_value_label(value: float) -> str:
    """Render a data value as label text, shortest-round-trip.

    Not :func:`format_coord`: that rounds to 6 decimals because it formats *coordinates*, and
    rounding a label silently rewrites the data it names (``1e-7`` -> ``"0"``, ``0.123456789``
    -> ``"0.123457"``). Integral values still lose the ``.0`` so the common case reads as
    ``30`` rather than ``30.0``.
    """
    return str(int(value)) if value.is_integer() else str(value)


def new_canvas(
    margin: Margin, *, width: float = DEFAULT_WIDTH, height: float = DEFAULT_HEIGHT
) -> tuple[SvgDocument, PlotArea]:
    """A default-sized document with its background drawn, and the plot area inside ``margin``.

    Fifteen charts opened with the same six lines and differed only in the margin. The
    background rect is the part worth centralising: it carries the ``plot-background`` class
    every theme styles, and a chart that forgot it would render on whatever the host page's
    background happens to be -- a difference nobody notices until the page is dark.

    ``width``/``height`` default to the package size, so a caller that does not pass them gets
    exactly what this returned before charts could be given a size (#120).
    """
    document = SvgDocument(width=width, height=height)
    area = plot_area(width, height, margin=margin)
    document.add_node(
        None,
        "rect",
        attrib={"x": 0, "y": 0, "width": format_coord(width), "height": format_coord(height)},
        classes=["plot-background"],
    )
    return document, area


def marks_viewport(document: SvgDocument, area: PlotArea, *, clipped: bool) -> ET.Element | None:
    """The parent a chart should hang its marks on, given whether the view was narrowed.

    Returns a nested ``<svg>`` covering exactly ``area`` when ``clipped``, and ``None`` -- the
    document root, where marks have always gone -- otherwise. A nested ``<svg>`` establishes a
    new viewport and clips to it, so passing it as ``add_node``'s parent is the whole of the
    mechanism: no ``id``, no ``clipPath`` to reference it by, and no CSS. That matters here
    because nothing else this package writes into an SVG carries an ``id``, and a page holding
    two charts would have to be told to keep two of them apart (see ``Chart.set_table_id`` for
    what that costs). The ``viewBox`` repeats the viewport rect so a child's coordinates mean
    the same thing inside as out -- charts compute pixels against ``area`` and must not have to
    know whether they were handed a viewport or the root.

    **Only when the limit narrows the domain**, which is what :func:`~svgplot.chart._domain.narrows`
    decides. An earlier version keyed on "was a limit passed at all" and justified itself by
    saying a widening or identical one "cuts nothing" -- both halves were false. It cuts by the
    outer radius of whatever sits on the boundary, and ``facet`` walks straight into it: sharing
    an axis means handing every panel the *union* of the panels' domains, which covers each
    panel's data by construction, so a caller who passed no limit saw the extreme markers of a
    faceted scatter lose half of themselves. Without a narrowing limit there is no viewport:
    a chart's own domain is computed from its own data and therefore covers it, so a chart that
    could not overflow keeps the bytes it had. With one, ``apply_limit`` *replaces* the domain
    (``chart/_domain.py``), values outside the window map to pixels outside the plot area, and
    until this existed they were drawn there -- over the axis, into the margin, off the canvas.

    **A mark straddling the edge is still cut, not kept.** The viewport is the plot area exactly,
    so a marker whose centre is the last point *inside a narrowed window* loses the half of its
    radius that hangs past the axis, and a stroke loses half its width. That is what clipping
    means and what matplotlib's ``clip_on=True`` does; the caller asked for a smaller view and
    the edge of that view is where the picture stops. What changed is that a chart no longer
    clips when nothing was narrowed -- ``facet``'s shared union narrows nothing, so it produces
    no clip and its extreme markers are whole again. The viewport is still one rect over both
    axes, so narrowing *one* axis also trims the marks overhanging the other; splitting it per
    axis is a separate question this does not answer.

    ``overflow="hidden"`` is the initial value for a nested viewport and is written anyway: it
    is the one attribute that says what this element is for, in a file this package intends to
    be read and hand-edited. The ``plot-clip`` class is the other half of that: a composition
    positions each panel with a nested ``<svg x= y=>`` too, and four test helpers were reading
    exactly that shape to count panels. Position is what separates the two *inside* a
    composition -- a panel is the sheet's own child and a clip is a grandchild, and the class
    is namespaced to ``c0-plot-clip`` there anyway -- but a chart on its own has its clip as a
    direct child of the root, and then only the name tells them apart.
    """
    if not clipped:
        return None
    return document.add_node(
        None,
        "svg",
        attrib={
            "x": format_coord(area.left),
            "y": format_coord(area.top),
            "width": format_coord(area.width),
            "height": format_coord(area.height),
            "viewBox": " ".join(format_coord(value) for value in (area.left, area.top, area.width, area.height)),
            "overflow": "hidden",
        },
        classes=["plot-clip"],
    )


def resolve_size(width: float | None, height: float | None) -> tuple[float, float]:
    """Resolve caller-supplied ``width``/``height`` into a validated canvas size.

    ``None`` means "the package default", so a chart called the way every existing chart
    is called gets :data:`DEFAULT_WIDTH` x :data:`DEFAULT_HEIGHT` and byte-identical output.

    Raises:
        ValueError: if either is not a finite number, or is below :data:`MIN_WIDTH` /
            :data:`MIN_HEIGHT`. Refusing rather than clamping: a caller who asked for 100
            px and silently got 240 would have a chart that does not fit where they meant
            to put it, and no way to find out except by measuring the file.
    """
    resolved_width = DEFAULT_WIDTH if width is None else _finite(width, "width")
    resolved_height = DEFAULT_HEIGHT if height is None else _finite(height, "height")
    if resolved_width < MIN_WIDTH or resolved_height < MIN_HEIGHT:
        raise ValueError(
            f"canvas must be at least {MIN_WIDTH}x{MIN_HEIGHT} for an axed chart, " f"got {resolved_width}x{resolved_height}"
        )
    return resolved_width, resolved_height


def _finite(value: float, name: str) -> float:
    """A caller-supplied length, as a float.

    ``numbers.Real`` rather than ``int | float``: a size very often arrives from the same
    array library the data did, and ``numpy.float32``/``numpy.int64`` are neither of those
    two while being perfectly good lengths. ``bool`` is excluded even though it is ``Real``,
    because ``width=True`` is a mistake, not a request for one pixel.
    """
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ValueError(f"{name} must be a finite number, got {value!r}")
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError) as error:
        # A ``Real`` too large to be a float -- ``Fraction(10**400)``. ``format_coord`` in this
        # same module already normalises that to ``ValueError``; this is the rule, not an
        # exception to it, and ``resolve_size`` documents ``ValueError`` and nothing else.
        raise ValueError(f"{name} must be a finite number, got {value!r}") from error
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number, got {value!r}")
    return number


def fit_margin(margin: Margin, width: float, height: float) -> tuple[float, float, float, float]:
    """Scale a margin preset down until it leaves the plot area most of the canvas.

    The presets are absolute pixel values chosen for an 800 x 600 canvas. On a small one
    they are the whole chart: at 300 px wide, ``MARGIN_WITH_LEGEND``'s 60 + 160 leaves an
    80 px plot area. Each pair is scaled by one factor so the two sides keep their ratio —
    see :data:`MAX_MARGIN_FRACTION`.

    Never scales *up*. A caller who passes a small margin on a large canvas asked for a
    large plot area and gets one.
    """
    top, right, bottom, left = resolve_margin(margin)
    horizontal = _fit_pair(left, right, width)
    vertical = _fit_pair(top, bottom, height)
    return (vertical[0], horizontal[1], vertical[1], horizontal[0])


def _fit_pair(first: float, second: float, extent: float) -> tuple[float, float]:
    budget = extent * MAX_MARGIN_FRACTION
    total = first + second
    # A negative side is refused rather than scaled. It cannot be scaled sensibly -- the
    # pair's *sum* can sit under the budget while one side is -500, which put the plot area
    # 500 px above the canvas -- and no preset here has one. Refusing keeps this function
    # honest about taking "whatever margin it is given", which its own tests rely on.
    if first < 0 or second < 0:
        raise ValueError(f"margin sides must not be negative, got {first!r} and {second!r}")
    if total <= budget or total <= 0:
        return first, second
    factor = budget / total
    return first * factor, second * factor


def ticks_for(extent: float, spacing: float) -> int:
    """How many ticks a plot-area extent has room for, at :data:`TICK_SPACING_X` /
    :data:`TICK_SPACING_Y` pixels apiece and clamped to :data:`MIN_TICKS`/:data:`MAX_TICKS`.

    This is a *request*: ``scales.make_ticks`` treats its ``count`` as a target and returns
    whatever nice round numbers land near it, which is why the result can be one more or
    one fewer than asked for. What matters here is that the request tracks the canvas.
    """
    return max(MIN_TICKS, min(MAX_TICKS, round(extent / spacing)))


AXIS_SCALES = ("linear", "log")
"""What ``xscale=``/``yscale=`` accept. ``"linear"`` is the default everywhere."""


def resolve_axis_scale(name: object, *, parameter: str) -> str:
    """Validate an axis scale name, refusing anything else by name.

    Named rather than boolean (``pygal``'s ``logarithmic=True``) because a boolean has room
    for exactly two answers and this axis will want more than two -- and because at a call
    site ``yscale="log"`` says which axis and which scale, where ``logarithmic=True`` says
    neither.
    """
    if name not in AXIS_SCALES:
        raise ValueError(f"{parameter} must be one of {', '.join(AXIS_SCALES)}, got {name!r}")
    return str(name)


def value_scale(
    kind: str,
    domain: tuple[float, float],
    pixels: tuple[float, float],
    *,
    column: str,
    values: Iterable[float] = (),
) -> LinearScale | LogScale:
    """The scale a value axis of ``kind`` uses over ``domain``.

    The column is named here so a caller who put a zero in a log axis is told *which* column
    to look at -- the error is about their data, and by the time it reaches ``LogScale`` the
    only thing left to report is the number.

    ``values`` as well as ``domain``, because the two come apart: ``ylim=(1, 100)`` narrows
    the domain past a zero that is still in the data and still gets drawn, and ``LogScale``
    would then be asked to place it. It refuses -- but from inside a class that has never
    heard of columns, so the caller is told a number and left to find it.
    """
    if kind == "linear":
        return LinearScale(domain, pixels)
    for value in (*domain, *values):
        if value <= 0.0:
            raise ValueError(
                f"column {column!r} holds {value!r}, which a log axis cannot place: "
                "a logarithm is undefined at zero and below. Filter those rows, or use the default linear axis."
            )
    return LogScale(domain, pixels)
