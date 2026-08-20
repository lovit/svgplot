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

from svgplot._svg import SvgDocument

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


def new_canvas(margin: Margin) -> tuple[SvgDocument, PlotArea]:
    """A default-sized document with its background drawn, and the plot area inside ``margin``.

    Fifteen charts opened with the same six lines and differed only in the margin. The
    background rect is the part worth centralising: it carries the ``plot-background`` class
    every theme styles, and a chart that forgot it would render on whatever the host page's
    background happens to be -- a difference nobody notices until the page is dark.
    """
    document = SvgDocument(width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT)
    area = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=margin)
    document.add_node(
        None,
        "rect",
        attrib={"x": 0, "y": 0, "width": format_coord(DEFAULT_WIDTH), "height": format_coord(DEFAULT_HEIGHT)},
        classes=["plot-background"],
    )
    return document, area
