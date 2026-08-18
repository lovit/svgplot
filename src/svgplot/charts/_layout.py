"""Plot-area layout math shared by every chart type.

Two responsibilities: (1) a CSS-box-model-like margin (single value applies
to all 4 sides, or a 4-tuple for per-side control — pygal precedent,
docs/research/12-aesthetics.md:31) resolved into a plot-area rect, and
(2) SVG-literal coordinate formatting, so every chart's path/line/rect
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
