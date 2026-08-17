"""Curve interpolation: quadratic/cubic/hermite/lagrange/trigonometric (pygal precedent, docs/research/01-pygal.md A7).

Display-only smoothing, not a statistical fit (pygal's own framing: "원값 사이를
매끄럽게 잇는 표시용 기능이지 통계 추정이 아니다") — each method is a legitimate,
standard textbook member of its named family, not a bit-for-bit port of pygal's
undocumented internals.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

METHODS = ("quadratic", "cubic", "hermite", "lagrange", "trigonometric")

_MAX_PRECISION = 10_000
"""Sane upper bound on requested output-point count — keeps a careless
``precision=10**9`` from exhausting memory/CPU, matching the spirit of
``_MAX_CUBEHELIX_MAGNITUDE``/``_MAX_SPEC_LENGTH`` elsewhere in this package."""

_MAX_POINTS = 2_000
"""Sane upper bound on input point count for the 4 non-``lagrange`` methods (all O(n) or
O(n log n) in the point count) — generous enough for real chart data (e.g. a daily
time series spanning several years) while still bounding memory/CPU for a single call."""

_MAX_LAGRANGE_POINTS = 50
"""Much stricter cap for ``lagrange`` specifically: it's an O(n^2 * precision) CPU-DoS
vector (n=2000, precision=1000 takes ~2 minutes; even n=200 with a large precision takes
several seconds) AND numerically meaningless well before that (Runge's phenomenon makes
it diverge past roughly this many points anyway) — so this cap costs nothing for a method
that's only ever practical on a handful of points."""


@dataclass(frozen=True)
class InterpolatedCurve:
    """A dense ``(x, y)`` point sequence for smooth line rendering."""

    x: list[float]
    y: list[float]

    def __len__(self) -> int:
        return len(self.x)


def interpolate(x: list[float], y: list[float], method: str = "cubic", precision: int = 250) -> InterpolatedCurve:
    """Interpolate (x, y) points for smooth line rendering. Display-only, not a statistical fit.

    Raises:
        ValueError: if ``method`` isn't one of :data:`METHODS`, if ``precision`` is out of
            range, if ``x``/``y`` differ in length, have fewer than 2 or more than
            :data:`_MAX_POINTS` points (or, for ``method="lagrange"`` specifically, more
            than the much stricter :data:`_MAX_LAGRANGE_POINTS`), contain a non-numeric or
            non-finite coordinate, if ``x`` isn't strictly increasing, if ``x``'s span
            (``x[-1] - x[0]``) isn't finite, or if the interpolated output itself contains
            a non-finite value —
            individually-finite ``x``/``y`` coordinates can still make an intermediate
            spline/DFT computation overflow (e.g. a finite-but-extreme ``y`` difference),
            so the final output is validated too rather than only the raw inputs.
    """
    if method not in METHODS:
        raise ValueError(f"unknown interpolation method: {method!r} (available: {METHODS})")
    if not isinstance(precision, int) or isinstance(precision, bool) or precision < 2 or precision > _MAX_PRECISION:
        raise ValueError(f"precision must be an int in [2, {_MAX_PRECISION}], got {precision!r}")
    if len(x) != len(y):
        raise ValueError(f"x and y must have the same length, got {len(x)} and {len(y)}")
    if len(x) < 2:
        raise ValueError(f"need at least 2 points to interpolate, got {len(x)}")
    if len(x) > _MAX_POINTS:
        raise ValueError(f"too many points to interpolate ({len(x)}), max {_MAX_POINTS}")
    if method == "lagrange" and len(x) > _MAX_LAGRANGE_POINTS:
        raise ValueError(
            f"too many points for lagrange interpolation ({len(x)}), max {_MAX_LAGRANGE_POINTS} (see _MAX_LAGRANGE_POINTS docstring)"
        )
    for value in (*x, *y):
        try:
            finite = math.isfinite(value)
        except TypeError as error:
            raise ValueError(f"x/y coordinates must be numbers, got {value!r}") from error
        if not finite:
            raise ValueError(f"cannot interpolate a non-finite coordinate: {value!r}")
    for previous, current in pairwise(x):
        if current <= previous:
            raise ValueError("x must be strictly increasing")
    if not math.isfinite(x[-1] - x[0]):
        raise ValueError(f"x range (x[-1] - x[0] = {x[-1] - x[0]!r}) must be finite")

    if method == "quadratic":
        result = _quadratic(x, y, precision)
    elif method == "cubic":
        result = _cubic(x, y, precision)
    elif method == "hermite":
        result = _hermite(x, y, precision)
    elif method == "lagrange":
        result = _lagrange(x, y, precision)
    else:
        result = _trigonometric(x, y, precision)

    for value in (*result.x, *result.y):
        if not math.isfinite(value):
            raise ValueError(
                f"interpolation produced a non-finite value: {value!r} — the input "
                "coordinates likely span too extreme a range for this method's arithmetic"
            )
    return result


def _linspace(start: float, stop: float, n: int) -> list[float]:
    if n == 1:
        return [start]
    step = (stop - start) / (n - 1)
    return [start + i * step for i in range(n - 1)] + [stop]


def _quadratic(x: list[float], y: list[float], precision: int) -> InterpolatedCurve:
    """Piecewise quadratic: each segment uses the parabola through the nearest 3 knots."""
    n = len(x)
    x_out = _linspace(x[0], x[-1], precision)
    y_out = []
    segment = 0
    for xi in x_out:
        while segment < n - 2 and xi > x[segment + 1]:
            segment += 1
        # Anchor the triple so the last segment still has 3 points to fit.
        i0 = min(segment, n - 3) if n >= 3 else 0
        triple_x, triple_y = x[i0 : i0 + 3], y[i0 : i0 + 3]
        if n < 3:
            # Only 2 points total: fall back to linear (a degenerate "quadratic").
            t = (xi - x[0]) / (x[-1] - x[0])
            y_out.append(y[0] + t * (y[1] - y[0]))
        else:
            y_out.append(_lagrange_eval(triple_x, triple_y, xi))
    return InterpolatedCurve(x=x_out, y=y_out)


def _lagrange_eval(xs: list[float], ys: list[float], xi: float) -> float:
    total = 0.0
    for j, xj in enumerate(xs):
        term = ys[j]
        for k, xk in enumerate(xs):
            if k != j:
                term *= (xi - xk) / (xj - xk)
        total += term
    return total


def _lagrange(x: list[float], y: list[float], precision: int) -> InterpolatedCurve:
    """Single global Lagrange polynomial through all points.

    Numerically unstable for many points (Runge's phenomenon) — matching pygal's own
    known behavior, this is intended for small point counts.
    """
    x_out = _linspace(x[0], x[-1], precision)
    y_out = [_lagrange_eval(x, y, xi) for xi in x_out]
    return InterpolatedCurve(x=x_out, y=y_out)


def _natural_cubic_spline_coeffs(x: list[float], y: list[float]) -> list[float]:
    """Second derivatives at each knot for a natural cubic spline (standard tridiagonal solve)."""
    n = len(x)
    if n == 2:
        return [0.0, 0.0]
    h = [x[i + 1] - x[i] for i in range(n - 1)]
    # Thomas algorithm for the tridiagonal system defining the natural spline's
    # second derivatives (m[0] = m[n-1] = 0 boundary condition).
    alpha = [0.0] * n
    for i in range(1, n - 1):
        alpha[i] = 3 * ((y[i + 1] - y[i]) / h[i] - (y[i] - y[i - 1]) / h[i - 1])
    ell = [1.0] * n
    mu = [0.0] * n
    z = [0.0] * n
    for i in range(1, n - 1):
        ell[i] = 2 * (x[i + 1] - x[i - 1]) - h[i - 1] * mu[i - 1]
        mu[i] = h[i] / ell[i]
        z[i] = (alpha[i] - h[i - 1] * z[i - 1]) / ell[i]
    m = [0.0] * n
    for i in range(n - 2, 0, -1):
        m[i] = z[i] - mu[i] * m[i + 1]
    return m


def _cubic(x: list[float], y: list[float], precision: int) -> InterpolatedCurve:
    """Natural cubic spline (zero second derivative at both endpoints)."""
    n = len(x)
    m = _natural_cubic_spline_coeffs(x, y)
    x_out = _linspace(x[0], x[-1], precision)
    y_out = []
    segment = 0
    for xi in x_out:
        while segment < n - 2 and xi > x[segment + 1]:
            segment += 1
        h = x[segment + 1] - x[segment]
        a = (x[segment + 1] - xi) / h
        b = (xi - x[segment]) / h
        y_val = a * y[segment] + b * y[segment + 1] + ((a**3 - a) * m[segment] + (b**3 - b) * m[segment + 1]) * (h * h) / 6
        y_out.append(y_val)
    return InterpolatedCurve(x=x_out, y=y_out)


def _hermite(x: list[float], y: list[float], precision: int) -> InterpolatedCurve:
    """Cubic Hermite spline with Catmull-Rom-style finite-difference tangents at each knot."""
    n = len(x)
    tangents = []
    for i in range(n):
        if n == 2:
            tangents.append((y[-1] - y[0]) / (x[-1] - x[0]))
        elif i == 0:
            tangents.append((y[1] - y[0]) / (x[1] - x[0]))
        elif i == n - 1:
            tangents.append((y[-1] - y[-2]) / (x[-1] - x[-2]))
        else:
            tangents.append((y[i + 1] - y[i - 1]) / (x[i + 1] - x[i - 1]))

    x_out = _linspace(x[0], x[-1], precision)
    y_out = []
    segment = 0
    for xi in x_out:
        while segment < n - 2 and xi > x[segment + 1]:
            segment += 1
        h = x[segment + 1] - x[segment]
        t = (xi - x[segment]) / h
        t2, t3 = t * t, t * t * t
        h00 = 2 * t3 - 3 * t2 + 1
        h10 = t3 - 2 * t2 + t
        h01 = -2 * t3 + 3 * t2
        h11 = t3 - t2
        y_val = h00 * y[segment] + h10 * h * tangents[segment] + h01 * y[segment + 1] + h11 * h * tangents[segment + 1]
        y_out.append(y_val)
    return InterpolatedCurve(x=x_out, y=y_out)


def _trigonometric(x: list[float], y: list[float], precision: int) -> InterpolatedCurve:
    """Trigonometric polynomial interpolation via DFT of ``y``, treating points as
    equally-spaced samples by index (not by ``x``-value, since ``x`` need not be evenly
    spaced) and reconstructing at ``precision`` points mapped linearly across the x-range.
    """
    n = len(y)
    x_out = _linspace(x[0], x[-1], precision)
    if n == 1:
        return InterpolatedCurve(x=x_out, y=[y[0]] * precision)

    coeffs = []
    for k in range(n):
        real = sum(y[j] * math.cos(-2 * math.pi * k * j / n) for j in range(n)) / n
        imag = sum(y[j] * math.sin(-2 * math.pi * k * j / n) for j in range(n)) / n
        coeffs.append((real, imag))

    y_out = []
    for xi in x_out:
        # Map xi (in [x[0], x[-1]]) back onto the sample-index domain [0, n-1] — the
        # DFT basis is periodic with period n, but our n points only span n-1 gaps,
        # so sample j must land at t=j, i.e. scale by (n-1), not n.
        t = (xi - x[0]) / (x[-1] - x[0]) * (n - 1) if x[-1] != x[0] else 0.0
        total = 0.0
        for k, (real, imag) in enumerate(coeffs):
            angle = 2 * math.pi * k * t / n
            total += real * math.cos(angle) - imag * math.sin(angle)
        y_out.append(total)
    return InterpolatedCurve(x=x_out, y=y_out)
