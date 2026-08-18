"""Polar geometry shared by the charts drawn on a circle (pie, radar, gauge).

Owns angle-to-point conversion and the SVG arc-path strings those charts emit.
Deliberately *geometry only*: turning a data value into an angle belongs to
``scales.py``, not here.

**There is no ``PolarScale`` and there should not be one.** Neither
``LinearScale`` nor ``CategoricalScale`` contains a pixel assumption, so both
work unchanged as angular scales: ``LinearScale((vmin, vmax), (start_angle,
end_angle))`` *is* a gauge's angular scale, and ``CategoricalScale(categories,
(-pi/2, -pi/2 + 2*pi))`` *is* a radar's — its ``__call__`` returns the band
start, which is exactly the equally-spaced spoke angle, and its ``bandwidth`` is
the angular step. ``make_ticks`` already dispatches on both and needs no new
branch. A polar scale type would duplicate all of that to no benefit.

Angles are radians in SVG's y-down coordinate system, so they advance clockwise
on screen and ``-pi/2`` is 12 o'clock — the conventional start for a pie or a
radar.

Private/internal — not re-exported from ``svgplot.charts``.
"""

from __future__ import annotations

import math

from svgplot.charts._layout import format_coord

FULL_CIRCLE_TOLERANCE = 1e-9
"""Slack for comparing a sweep against pi or 2*pi.

Angles here are accumulated by repeated division and multiplication (a slice's
share of the whole), so a sweep that is mathematically exactly pi or 2*pi lands a
few ULP either side of it. Without the slack, a half-circle slice would flip its
large-arc-flag on float noise and a full-circle slice would sometimes miss the
two-arc path below.
"""


def polar_point(cx: float, cy: float, r: float, angle: float) -> tuple[float, float]:
    """The point at ``angle`` radians on the circle of radius ``r`` about ``(cx, cy)``."""
    return (cx + r * math.cos(angle), cy + r * math.sin(angle))


def _large_arc_flag(sweep: float) -> int:
    """The SVG ``A`` command's large-arc-flag: 1 when the sweep exceeds a half circle."""
    return 1 if abs(sweep) > math.pi + FULL_CIRCLE_TOLERANCE else 0


def _circle_loop(cx: float, cy: float, r: float) -> str:
    """One closed circle, drawn as two 180-degree arcs: 9 o'clock -> 3 o'clock -> back.

    Each arc must *end* somewhere other than where it started -- an ``A`` whose start
    and end points coincide is dropped entirely by the renderer (SVG spec F.6.2), so
    sweeping straight back to the start point silently yields half a circle.
    """
    return f"M {format_coord(cx - r)},{format_coord(cy)} " + " ".join(
        f"A {format_coord(r)},{format_coord(r)} 0 1 1 {format_coord(x)},{format_coord(y)}"
        for x, y in (polar_point(cx, cy, r, 0.0), polar_point(cx, cy, r, math.pi))
    )


def full_ring_path(cx: float, cy: float, outer_r: float, inner_r: float) -> str:
    """A 360-degree slice degenerates for a single ``A`` arc command (its start and
    end points coincide), so a full circle is drawn as two 180-degree arcs instead
    -- and, for a donut, the inner boundary is a second such loop combined via
    ``fill-rule="evenodd"`` to punch the hole.
    """
    outer_loop = _circle_loop(cx, cy, outer_r)
    if inner_r <= 0:
        return outer_loop + " Z"
    return f"{outer_loop} Z {_circle_loop(cx, cy, inner_r)} Z"


def ring_path(cx: float, cy: float, outer_r: float, inner_r: float, start_angle: float, end_angle: float) -> str:
    """A closed, fillable sector between two angles.

    With ``inner_r <= 0`` this is a wedge anchored at the centre (a pie slice); with
    ``inner_r > 0`` it is an annulus sector — outer arc forward, inward, inner arc
    backward, closed. A donut built from these needs ``fill-rule="evenodd"`` on the
    element so the hole reads as a hole.

    For a sweep of a full turn use :func:`full_ring_path` instead; a single ``A``
    covering 360 degrees would start and end at the same point and be dropped
    entirely (SVG spec F.6.2, see :func:`_circle_loop`).
    """
    large_arc = _large_arc_flag(end_angle - start_angle)
    x1, y1 = polar_point(cx, cy, outer_r, start_angle)
    x2, y2 = polar_point(cx, cy, outer_r, end_angle)
    if inner_r <= 0:
        return (
            f"M {format_coord(cx)},{format_coord(cy)} L {format_coord(x1)},{format_coord(y1)} "
            f"A {format_coord(outer_r)},{format_coord(outer_r)} 0 {large_arc} 1 {format_coord(x2)},{format_coord(y2)} Z"
        )
    ix1, iy1 = polar_point(cx, cy, inner_r, start_angle)
    ix2, iy2 = polar_point(cx, cy, inner_r, end_angle)
    return (
        f"M {format_coord(x1)},{format_coord(y1)} "
        f"A {format_coord(outer_r)},{format_coord(outer_r)} 0 {large_arc} 1 {format_coord(x2)},{format_coord(y2)} "
        f"L {format_coord(ix2)},{format_coord(iy2)} "
        f"A {format_coord(inner_r)},{format_coord(inner_r)} 0 {large_arc} 0 {format_coord(ix1)},{format_coord(iy1)} Z"
    )


def arc_path(cx: float, cy: float, r: float, start_angle: float, end_angle: float) -> str:
    """An open arc, for stroking — no closing segment and no anchor at the centre.

    ``end_angle`` below ``start_angle`` sweeps the other way (the SVG sweep-flag
    follows the sign). A sweep of a full turn is emitted as the two-arc loop
    :func:`_circle_loop` builds, for the SVG F.6.2 reason documented there; that loop
    starts at 9 o'clock, so ``start_angle`` stops mattering once the arc closes on
    itself — which it doesn't, geometrically.
    """
    sweep = end_angle - start_angle
    if abs(sweep) >= 2 * math.pi - FULL_CIRCLE_TOLERANCE:
        return _circle_loop(cx, cy, r)
    x1, y1 = polar_point(cx, cy, r, start_angle)
    x2, y2 = polar_point(cx, cy, r, end_angle)
    sweep_flag = 1 if sweep >= 0 else 0
    return (
        f"M {format_coord(x1)},{format_coord(y1)} "
        f"A {format_coord(r)},{format_coord(r)} 0 {_large_arc_flag(sweep)} {sweep_flag} "
        f"{format_coord(x2)},{format_coord(y2)}"
    )
