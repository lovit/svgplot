"""Plot-area layout math shared by every chart type.

Three responsibilities: (1) the default canvas size and margin presets every
chart starts from, (2) a CSS-box-model-like margin (single value applies
to all 4 sides, or a 4-tuple for per-side control — pygal precedent,
docs/research/12-aesthetics.md:31) resolved into a plot-area rect, and
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
from dataclasses import dataclass

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

**Where 240 comes from.** The binding constraint on a narrow canvas is not the plot area,
which stays a fixed share of the width, and not the ticks, which thin out — it is the
legend gutter, because a legend label's glyphs are the one thing here whose width this
package cannot measure. Solving for it: the right margin after :func:`fit_margin` is
``160 * (MAX_MARGIN_FRACTION * width / 220) = 0.32727 * width``, of which
:data:`LEGEND_X_OFFSET` (20), the swatch (16) and its gap (6) are fixed, leaving
``0.32727 * width - 42`` for text. Setting that equal to
``charts._legend.minimum_legend_text_width(11.0)`` — six characters at the default legend
font size, 36.3 px — gives **239.25 px**. 240 is that boundary rounded up, and a test pins
the derivation so the constant cannot drift away from the calculation that produced it.

A caller whose legend labels are longer than six characters needs a wider canvas than this;
the package cannot tell, because it has no font metrics (docs/research/12-aesthetics.md §3).

**Where 180 comes from.** The same 4:3 the package's default 800 x 600 uses, applied to the
derived width. Nothing vertical binds anywhere near it: at 180 the plot area is still 100 px
tall, four times the 24 px that two tick labels need at a 1.2 line height.

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
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number, got {value!r}")
    return float(value)


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
