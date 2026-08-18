"""Gaussian kernel density estimation, in pure stdlib.

``binning.py`` is this package's only numpy consumer; ``interpolate.py`` and ``box.py``
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
    return numbers


def _standard_deviation(numbers: list[float]) -> float:
    """Sample standard deviation (Bessel-corrected), matching what both rules assume."""
    mean = math.fsum(numbers) / len(numbers)
    variance = math.fsum((number - mean) ** 2 for number in numbers) / (len(numbers) - 1)
    return math.sqrt(variance)


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


def kde(values: list[float], *, bandwidth: float | str = "scott", grid: int = 200, cut: float = 3.0) -> KdeCurve:
    """Estimate a Gaussian kernel density over ``values``.

    The curve is evaluated on ``grid`` evenly spaced points spanning
    ``[min - cut * h, max + cut * h]``, so the tails are given ``cut`` bandwidths of room
    to decay (seaborn's default of 3 leaves less than 1% of each kernel's mass outside).

    A numeric ``bandwidth`` is used as given and bypasses rule selection entirely; a
    string picks one of :data:`BANDWIDTH_RULES`.

    Raises:
        ValueError: if ``values`` is empty, holds a non-number or non-finite value, has
            fewer than 2 or more than :data:`_MAX_POINTS` entries, or has zero variance
            while a named rule is in use; if ``bandwidth`` is an unknown rule name or a
            non-positive/non-finite number; if ``grid`` is below 2 or above
            :data:`_MAX_GRID`; or if ``cut`` is negative or non-finite.
    """
    numbers = _require_finite_values(values)

    if grid < 2:
        raise ValueError(f"grid must be at least 2 to span a range, got {grid}")
    if grid > _MAX_GRID:
        raise ValueError(f"grid must be at most {_MAX_GRID}, got {grid}")

    try:
        extension = float(cut)
    except (TypeError, ValueError) as error:
        raise ValueError(f"cut must be a number, got {cut!r}") from error
    if not math.isfinite(extension):
        raise ValueError(f"cut must be finite, got {cut!r}")
    if extension < 0.0:
        raise ValueError(f"cut must not be negative, got {cut!r}")

    width = _resolve_bandwidth(bandwidth, numbers)

    lower = min(numbers) - extension * width
    upper = max(numbers) + extension * width
    step = (upper - lower) / (grid - 1)
    xs = [lower + index * step for index in range(grid)]

    # Normalising once outside the loop keeps the inner sum to an exp() per value.
    norm = _INV_SQRT_TAU / (len(numbers) * width)
    ys = [norm * math.fsum(math.exp(-0.5 * ((x - number) / width) ** 2) for number in numbers) for x in xs]

    return KdeCurve(x=xs, y=ys, bandwidth=width)
