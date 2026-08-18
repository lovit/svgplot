"""Ordinary least squares with a bootstrapped confidence band, in pure stdlib.

The band is a percentile bootstrap rather than the closed-form
``yhat +- t(1-a/2, n-2) * s * sqrt(1/n + (x-xbar)^2/Sxx)``. That formula needs a
Student-t quantile, and the three ways to get one without scipy -- hand-rolling the
continued fraction, embedding a degrees-of-freedom table, or falling back to a normal
approximation -- are each more code and less accurate than resampling. Resampling also
reuses ``stats.quantile`` and generalises to the error bars in the follow-up backlog.

Linear only. ``logistic``/``robust``/``lowess`` need statsmodels, and polynomial
``order > 1`` is outside the scope this package settled on.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from svgplot.stats.quantile import quantiles

_MAX_POINTS = 2_000
"""Upper bound on the sample size, matching ``interpolate._MAX_POINTS``/``kde._MAX_POINTS``.
The fit itself is linear in it, but every bootstrap resample refits, so this is one of the
two factors in the band's cost."""

_MAX_BOOTSTRAP_SAMPLES = 1_000
"""Upper bound on resample count -- deliberately equal to the default.

Measured here: at ``_MAX_POINTS`` a band costs 0.491 s with 1,000 resamples and 0.989 s
with 2,000. The house rule set by ``interpolate._MAX_TRIGONOMETRIC_POINTS`` is that no
single call should be slower than the 0.59 s/0.68 s worst cases already accepted there,
and 2,000 resamples would make this the slowest path in the package. 1,000 is also the
standard recommendation for a percentile bootstrap -- more resamples buy a sharper
estimate of the percentile, not a better band -- so ``n_boot`` exists mainly to be turned
*down* for interactive work."""

_MAX_GRID = 1_000
"""Upper bound on the output grid. Cost is ``grid * n_boot`` predictions, so an unbounded
grid would let a single call allocate and spin without limit regardless of the two caps
above; at both this and ``_MAX_BOOTSTRAP_SAMPLES`` the prediction pass adds 0.05 s."""

_MAX_SPAN = 1e150
"""Widest ``max - min`` either axis may have. ``_fit`` squares deviations, and Python's
``**`` raises ``OverflowError`` rather than saturating once they pass roughly 1.3e154 --
an exception this module's ``Raises:`` does not promise, so a caller catching
``ValueError`` would crash on it. Measured: 1e150 fits comfortably, 1e155 does not."""

_MIN_POINTS = 3
"""Two points fit a line exactly with zero residual, so a band around them would be a
line of zero width claiming certainty. Three is the smallest sample that can disagree
with its own fit."""


@dataclass(frozen=True)
class LinearFit:
    """An ordinary-least-squares line."""

    slope: float
    intercept: float

    def predict(self, x: float) -> float:
        return self.slope * x + self.intercept


@dataclass(frozen=True)
class RegressionBand:
    """A fitted line sampled on a grid, with a confidence band around it.

    ``lower[i] <= y[i] <= upper[i]`` holds at every index -- see ``confidence_band``.
    """

    x: list[float]
    y: list[float]
    lower: list[float]
    upper: list[float]


def _require_finite_pairs(x: list[float], y: list[float]) -> tuple[list[float], list[float]]:
    if len(x) != len(y):
        raise ValueError(f"x and y must have the same length, got {len(x)} and {len(y)}")
    if len(x) < _MIN_POINTS:
        raise ValueError(f"a regression needs at least {_MIN_POINTS} points, got {len(x)}")
    if len(x) > _MAX_POINTS:
        raise ValueError(f"a regression supports at most {_MAX_POINTS} points, got {len(x)}")

    xs: list[float] = []
    ys: list[float] = []
    for axis, values, target in (("x", x, xs), ("y", y, ys)):
        for value in values:
            try:
                number = float(value)
            except (TypeError, ValueError) as error:
                raise ValueError(f"regression {axis} values must be numbers, got {value!r}") from error
            if not math.isfinite(number):
                raise ValueError(f"cannot fit a regression through a non-finite {axis} value: {value!r}")
            target.append(number)

    # Each value is finite, but a span beyond ~1.3e154 makes the squared deviations in
    # ``_fit`` raise ``OverflowError`` -- an exception neither entry point documents, so a
    # caller catching ValueError would crash on it. ``interpolate`` guards the same way,
    # and ``quantile`` documents avoiding this exact difference form.
    for axis, values in (("x", xs), ("y", ys)):
        span = max(values) - min(values)
        if not math.isfinite(span) or span > _MAX_SPAN:
            raise ValueError(f"regression {axis} range (max - min = {span!r}) is too wide for this arithmetic")
    return xs, ys


def _fit(xs: list[float], ys: list[float]) -> LinearFit | None:
    """OLS over already-validated values, or ``None`` if ``x`` has no spread.

    Returning ``None`` rather than raising is what lets ``confidence_band`` skip the
    occasional degenerate resample without conflating it with invalid user input.
    """
    n = len(xs)
    mean_x = math.fsum(xs) / n
    mean_y = math.fsum(ys) / n
    sxx = math.fsum((value - mean_x) ** 2 for value in xs)
    if sxx <= 0.0:
        return None
    sxy = math.fsum((vx - mean_x) * (vy - mean_y) for vx, vy in zip(xs, ys, strict=True))
    slope = sxy / sxx
    return LinearFit(slope=slope, intercept=mean_y - slope * mean_x)


def _grid_positions(xs: list[float], grid: int) -> list[float]:
    """``grid`` evenly spaced positions spanning the observed x range, endpoints included."""
    low, high = min(xs), max(xs)
    step = (high - low) / (grid - 1)
    return [low + index * step for index in range(grid)]


def _require_grid(grid: int) -> None:
    if grid < 2:
        raise ValueError(f"grid must be at least 2 to span a range, got {grid}")
    if grid > _MAX_GRID:
        raise ValueError(f"grid must be at most {_MAX_GRID}, got {grid}")


def fit_curve(x: list[float], y: list[float], *, grid: int = 100) -> RegressionBand:
    """The fitted line sampled on a grid, with a zero-width band around it.

    What a caller wants when it needs the line's geometry but not the uncertainty around
    it -- ``regplot(ci=None)``. Returning the same ``RegressionBand`` shape as
    :func:`confidence_band`, from the same grid helper, is what keeps the two paths from
    drifting: the line is identical either way.

    Raises:
        ValueError: for anything :func:`linear_fit` rejects, or if ``grid`` isn't an int in
            ``[2, _MAX_GRID]``.
    """
    _require_grid(grid)
    fit = linear_fit(x, y)
    xs, _ = _require_finite_pairs(x, y)
    grid_x = _grid_positions(xs, grid)
    grid_y = [fit.predict(position) for position in grid_x]
    # Separate list objects: nothing mutates them today, but three aliases of one list is a
    # trap for whoever first edits band coordinates in place.
    return RegressionBand(x=grid_x, y=grid_y, lower=list(grid_y), upper=list(grid_y))


def linear_fit(x: list[float], y: list[float]) -> LinearFit:
    """Fit ``y = slope * x + intercept`` by ordinary least squares.

    Raises:
        ValueError: if ``x``/``y`` differ in length, hold a non-number or non-finite
            value, or have fewer than :data:`_MIN_POINTS` or more than
            :data:`_MAX_POINTS` points; or if every ``x`` is the same value, which is a
            vertical line and has no least-squares slope.
    """
    xs, ys = _require_finite_pairs(x, y)
    fit = _fit(xs, ys)
    if fit is None:
        raise ValueError(f"cannot fit a line through a vertical set of points (every x is {xs[0]!r})")
    return fit


def confidence_band(
    x: list[float],
    y: list[float],
    *,
    level: float = 0.95,
    n_boot: int = 1000,
    seed: int = 0,
    grid: int = 100,
) -> RegressionBand:
    """Fit a line and bootstrap a ``level`` confidence band around it.

    Each of ``n_boot`` resamples draws ``len(x)`` (x, y) *pairs* with replacement and
    refits; the band at each grid point is the percentile interval of those refits. The
    band is therefore narrowest near the mean of ``x`` and flares toward the extremes --
    the classic hourglass -- because a resample that reweights the ends pivots the line
    about its centroid.

    ``seed`` is a parameter, not an implementation detail: this package's contract is
    "same input -> same SVG", so the RNG is a local ``random.Random(seed)`` and the module
    never touches the global RNG.

    Raises:
        ValueError: for anything :func:`linear_fit` rejects; if ``level`` isn't strictly
            inside ``(0, 1)``; if ``n_boot`` is below 1 or above
            :data:`_MAX_BOOTSTRAP_SAMPLES`; if ``grid`` is below 2 or above
            :data:`_MAX_GRID`; or if too few resamples produced a usable fit.
    """
    xs, ys = _require_finite_pairs(x, y)

    try:
        confidence = float(level)
    except (TypeError, ValueError) as error:
        raise ValueError(f"level must be a number, got {level!r}") from error
    if not math.isfinite(confidence) or not 0.0 < confidence < 1.0:
        raise ValueError(f"level must be strictly between 0 and 1, got {level!r}")

    if n_boot < 1:
        raise ValueError(f"n_boot must be at least 1, got {n_boot}")
    if n_boot > _MAX_BOOTSTRAP_SAMPLES:
        raise ValueError(f"n_boot must be at most {_MAX_BOOTSTRAP_SAMPLES}, got {n_boot}")
    _require_grid(grid)

    point_fit = _fit(xs, ys)
    if point_fit is None:
        raise ValueError(f"cannot fit a line through a vertical set of points (every x is {xs[0]!r})")

    generator = random.Random(seed)
    size = len(xs)
    resampled: list[LinearFit] = []
    for _ in range(n_boot):
        indices = [generator.randrange(size) for _ in range(size)]
        # A resample can draw the same x repeatedly and end up vertical; that resample
        # carries no slope information, so drop it rather than let it fail the call.
        fit = _fit([xs[index] for index in indices], [ys[index] for index in indices])
        if fit is not None:
            resampled.append(fit)
    if not resampled:
        raise ValueError("every bootstrap resample was degenerate; the x values have too little spread to resample")

    lower_q = (1.0 - confidence) / 2.0
    upper_q = 1.0 - lower_q

    grid_x = _grid_positions(xs, grid)

    grid_y: list[float] = []
    band_lower: list[float] = []
    band_upper: list[float] = []
    for position in grid_x:
        centre = point_fit.predict(position)
        low, high = quantiles([fit.predict(position) for fit in resampled], (lower_q, upper_q))
        # The point estimate is not one of the resamples, so with few resamples the
        # percentile interval can land entirely to one side of it. Widening to include it
        # keeps the band from rendering as a ribbon floating off the line it describes.
        grid_y.append(centre)
        band_lower.append(min(low, centre))
        band_upper.append(max(high, centre))

    return RegressionBand(x=grid_x, y=grid_y, lower=band_lower, upper=band_upper)
