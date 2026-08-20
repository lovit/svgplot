"""Gaussian kernel density estimation, in pure stdlib.

``binning.py`` was this package's only numpy consumer, and is no longer one either (#116); ``interpolate.py`` and ``box.py``
are deliberately hand-written. Measured on this repo's venv, the naive O(n*grid) form
below costs 0.014 s at n=2,000 / grid=200 against numpy's 0.007 s -- a 2x gap on a
already-negligible number, which is not worth widening the dependency surface for.

Out of scope, deliberately: 2D KDE (needs contouring, a whole rendering problem of its
own), ``cumulative=`` (the one part of seaborn's KDE that requires scipy), and per-value
weights.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from svgplot.stats.quantile import quantile

BANDWIDTH_RULES = ("scott", "silverman")
"""Rule-of-thumb bandwidth selectors, by name. Both scale as ``n ** (-1/5)``."""

_MAX_POINTS = 2_000
"""Upper bound on the input sample size. The estimator is linear in it (each grid point
sums one kernel per value), and 2,000 keeps a single call at 0.014 s with the default
grid -- mirroring ``interpolate._MAX_POINTS``, which took the same bound for the same
reason."""

_MAX_GRID = 2_000
"""Upper bound on the output grid size. Also linear, and the two caps compose: at
n=2,000 *and* grid=2,000 a call measures 0.138 s. That is comfortably under the 0.59 s
worst case ``interpolate`` already accepts for ``trigonometric``, so no single call into
``svgplot.stats`` is made slower by this module than by what is already there."""

_SILVERMAN_IQR_SCALE = 1.34
"""Silverman's robust spread estimate divides the IQR by this to put it on the same
footing as a standard deviation (for a normal sample, IQR ~= 1.349 * sd)."""

_INV_SQRT_TAU = 1.0 / math.sqrt(2.0 * math.pi)


def _kernel(x: float, centre: float, width: float) -> float:
    """One standard-normal kernel.

    ``z * z`` saturates to ``inf`` rather than raising, and ``math.exp`` of a large
    negative argument returns 0.0 (it only raises going the other way), so a grid point
    arbitrarily far from ``centre`` contributes the ~0 density it mathematically has
    without any clamping.
    """
    z = (x - centre) / width
    return math.exp(-0.5 * z * z)


@dataclass(frozen=True)
class KdeCurve:
    """A density curve evaluated on a regular grid.

    ``y`` integrates to approximately 1 over ``x`` -- approximately, because the grid is
    truncated at ``cut`` bandwidths beyond the data rather than running to infinity.
    """

    x: list[float]
    y: list[float]
    bandwidth: float


def _require_finite_values(values: list[float]) -> list[float]:
    """Validate the sample and return it as plain floats, in input order."""
    if not values:
        raise ValueError("kde values must not be empty")
    if len(values) > _MAX_POINTS:
        raise ValueError(f"kde supports at most {_MAX_POINTS} values, got {len(values)}")
    numbers: list[float] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"kde values must be numbers, got {value!r}") from error
        if not math.isfinite(number):
            raise ValueError(f"cannot estimate a density from a non-finite value: {value!r}")
        numbers.append(number)
    if len(numbers) < 2:
        raise ValueError("kde needs at least 2 values to estimate a spread, got 1")
    # Each value is finite, but their *span* need not be: -1e308..1e308 overflows to inf,
    # and every downstream difference then produces nan. ``binning``/``interpolate`` guard
    # the same way, and ``quantile`` documents avoiding this exact difference form.
    span = max(numbers) - min(numbers)
    if not math.isfinite(span):
        raise ValueError(f"kde value range (max - min = {span!r}) must be finite")
    return numbers


def _standard_deviation(numbers: list[float]) -> float:
    """Sample standard deviation (Bessel-corrected), matching what both rules assume.

    Deviations are scaled by the largest of them before squaring. Squaring directly
    overflows to ``OverflowError`` for a sample spanning ~1e200, and underflows to a false
    zero -- reported as "zero variance" -- below ~1e-165; both are reachable from inputs
    that pass every other check.
    """
    mean = math.fsum(numbers) / len(numbers)
    deviations = [number - mean for number in numbers]
    largest = max(abs(deviation) for deviation in deviations)
    if largest == 0.0:
        return 0.0
    scaled = math.fsum((deviation / largest) ** 2 for deviation in deviations) / (len(numbers) - 1)
    return largest * math.sqrt(scaled)


def _rule_bandwidth(rule: str, numbers: list[float]) -> float:
    """Bandwidth from a named rule of thumb.

    Raises:
        ValueError: if ``rule`` is unknown, or if the sample has no spread for it to
            scale -- a zero-variance sample is the realistic crash here, and it must
            fail loudly rather than divide by zero or return a bandwidth of 0 (which
            renders as an infinite spike at the repeated value).
    """
    if rule not in BANDWIDTH_RULES:
        raise ValueError(f"bandwidth rule must be one of {BANDWIDTH_RULES}, got {rule!r}")

    deviation = _standard_deviation(numbers)
    if deviation <= 0.0:
        raise ValueError(
            f"cannot choose a bandwidth for a zero-variance sample (every value is {numbers[0]!r}); "
            "pass an explicit positive bandwidth to override the rule"
        )

    scale = len(numbers) ** -0.2
    if rule == "scott":
        return deviation * scale

    spread = quantile(numbers, 0.75) - quantile(numbers, 0.25)
    robust = spread / _SILVERMAN_IQR_SCALE
    # A sample can have positive variance yet a zero IQR (e.g. a tight cluster with one
    # outlier), so take the deviation rather than letting min() collapse to 0.
    return 0.9 * (min(deviation, robust) if robust > 0.0 else deviation) * scale


def _resolve_bandwidth(bandwidth: float | str, numbers: list[float]) -> float:
    if isinstance(bandwidth, str):
        return _rule_bandwidth(bandwidth, numbers)
    try:
        width = float(bandwidth)
    except (TypeError, ValueError) as error:
        raise ValueError(f"bandwidth must be a number or one of {BANDWIDTH_RULES}, got {bandwidth!r}") from error
    if not math.isfinite(width):
        raise ValueError(f"bandwidth must be finite, got {bandwidth!r}")
    if width <= 0.0:
        raise ValueError(f"bandwidth must be positive, got {bandwidth!r}")
    return width


def kde(
    values: list[float],
    *,
    bandwidth: float | str = "scott",
    grid: int = 200,
    cut: float = 3.0,
    grid_range: tuple[float, float] | None = None,
) -> KdeCurve:
    """Estimate a Gaussian kernel density over ``values``.

    The curve is evaluated on ``grid`` evenly spaced points spanning
    ``[min - cut * h, max + cut * h]``, so the tails are given ``cut`` bandwidths of room
    to decay (seaborn's default of 3 leaves less than 1% of each kernel's mass outside).

    A numeric ``bandwidth`` is used as given and bypasses rule selection entirely; a
    string picks one of :data:`BANDWIDTH_RULES`.

    ``grid_range`` overrides that span with an explicit ``(low, high)``, making ``cut``
    irrelevant. It exists for callers that must evaluate several samples on *one* grid --
    ``kdeplot`` with ``hue=`` shares a grid across groups so their curves are directly
    comparable, the same reason ``histplot`` computes one set of bin edges across groups.

    Raises:
        ValueError: if ``values`` is empty, holds a non-number or non-finite value, has
            fewer than 2 or more than :data:`_MAX_POINTS` entries, spans a non-finite
            range, or has zero variance while a named rule is in use; if ``bandwidth`` is
            an unknown rule name or a non-positive/non-finite number; if ``grid`` isn't an
            int in ``[2, _MAX_GRID]``; if ``cut`` is negative or non-finite; if
            ``grid_range`` isn't a finite increasing pair; or if the
            estimate itself comes out non-finite because the inputs span too extreme a
            range. Nothing else escapes -- in particular the arithmetic never surfaces a
            bare ``OverflowError``.
    """
    numbers = _require_finite_values(values)

    # Same shape as ``interpolate``'s ``precision`` check: a float grid would otherwise
    # reach ``range()`` and surface as a TypeError this function never promises.
    if not isinstance(grid, int) or isinstance(grid, bool) or grid < 2 or grid > _MAX_GRID:
        raise ValueError(f"grid must be an int in [2, {_MAX_GRID}], got {grid!r}")

    try:
        extension = float(cut)
    except (TypeError, ValueError) as error:
        raise ValueError(f"cut must be a number, got {cut!r}") from error
    if not math.isfinite(extension):
        raise ValueError(f"cut must be finite, got {cut!r}")
    if extension < 0.0:
        raise ValueError(f"cut must not be negative, got {cut!r}")

    width = _resolve_bandwidth(bandwidth, numbers)

    if grid_range is None:
        lower = min(numbers) - extension * width
        upper = max(numbers) + extension * width
    else:
        lower, upper = (float(bound) for bound in grid_range)
        if not math.isfinite(lower) or not math.isfinite(upper):
            raise ValueError(f"grid_range bounds must be finite, got {grid_range!r}")
        if not lower < upper:
            raise ValueError(f"grid_range must be increasing, got {grid_range!r}")
    step = (upper - lower) / (grid - 1)
    xs = [lower + index * step for index in range(grid)]

    # Normalising once outside the loop keeps the inner sum to an exp() per value.
    norm = _INV_SQRT_TAU / (len(numbers) * width)
    ys = [norm * math.fsum(_kernel(x, number, width) for number in numbers) for x in xs]

    # ``interpolate`` ends the same way: extreme-but-legal inputs can still push the
    # arithmetic out of range, and a non-finite coordinate would otherwise be written
    # straight into an SVG path.
    for value in (*xs, *ys):
        if not math.isfinite(value):
            raise ValueError(
                f"kde produced a non-finite value: {value!r} — the values, bandwidth or "
                "cut likely span too extreme a range for this estimator's arithmetic"
            )

    return KdeCurve(x=xs, y=ys, bandwidth=width)
