from __future__ import annotations

import inspect
import math
import random

import pytest

from svgplot.stats import regression
from svgplot.stats.regression import (
    _MAX_BOOTSTRAP_SAMPLES,
    _MAX_GRID,
    _MAX_POINTS,
    _MAX_SPAN,
    _MIN_POINTS,
    confidence_band,
    linear_fit,
)


def _noisy_line(n: int = 80, *, seed: int = 7) -> tuple[list[float], list[float]]:
    """A seeded sample from ``y = 2x + 1 + noise``. Seeded because this package's
    contract is "same input -> same SVG"; a flaky band test would undermine it."""
    generator = random.Random(seed)
    xs = [generator.uniform(0.0, 10.0) for _ in range(n)]
    return xs, [2.0 * x + 1.0 + generator.gauss(0.0, 2.0) for x in xs]


# ---------------------------------------------------------------------------
# linear_fit
# ---------------------------------------------------------------------------


def test_linear_fit_reproduces_a_hand_computed_line() -> None:
    """x=[1,2,3,4], y=[2,4,5,4]: Sxx=5, Sxy=3.5, so slope=0.7 and intercept=2.0. Worked
    out by hand so the test pins the estimator itself, not the code's own output."""
    fit = linear_fit([1.0, 2.0, 3.0, 4.0], [2.0, 4.0, 5.0, 4.0])

    assert fit.slope == pytest.approx(0.7, abs=1e-9)
    assert fit.intercept == pytest.approx(2.0, abs=1e-9)


def test_linear_fit_is_exact_on_a_perfectly_linear_sample() -> None:
    fit = linear_fit([1.0, 2.0, 3.0, 4.0], [3.0, 5.0, 7.0, 9.0])

    assert fit.slope == pytest.approx(2.0, abs=1e-9)
    assert fit.intercept == pytest.approx(1.0, abs=1e-9)
    assert fit.predict(10.0) == pytest.approx(21.0, abs=1e-9)


@pytest.mark.parametrize("span", [1e155, 1e200, 1e308])
def test_a_span_too_wide_for_the_arithmetic_is_a_value_error(span: float) -> None:
    """Every value is finite and inside the point cap, but squaring the deviations raises
    ``OverflowError`` past ~1.3e154 -- an exception the ``Raises:`` contract does not list,
    so a caller catching ``ValueError`` would crash on it."""
    with pytest.raises(ValueError, match="too wide"):
        linear_fit([0.0, span / 2, span], [1.0, 2.0, 3.0])


def test_a_span_just_inside_the_cap_still_fits() -> None:
    assert linear_fit([0.0, _MAX_SPAN / 2, _MAX_SPAN], [1.0, 2.0, 3.0]).slope > 0.0


def test_linear_fit_rejects_a_vertical_sample() -> None:
    """Sxx == 0 means every x is identical: a vertical line, which has no least-squares
    slope. Without the guard this divides by zero."""
    with pytest.raises(ValueError, match="vertical"):
        linear_fit([2.0, 2.0, 2.0], [1.0, 2.0, 3.0])


@pytest.mark.parametrize(
    ("x", "y", "match"),
    [
        ([1.0, 2.0, 3.0], [1.0, 2.0], "same length"),
        ([1.0, 2.0], [1.0, 2.0], f"at least {_MIN_POINTS} points"),
        ([0.0] * (_MAX_POINTS + 1), [0.0] * (_MAX_POINTS + 1), f"at most {_MAX_POINTS}"),
        ([1.0, 2.0, float("nan")], [1.0, 2.0, 3.0], "non-finite x"),
        ([1.0, 2.0, 3.0], [1.0, 2.0, float("inf")], "non-finite y"),
        ([1.0, 2.0, "x"], [1.0, 2.0, 3.0], "x values must be numbers"),
    ],
)
def test_linear_fit_rejects_unusable_samples(x: list[object], y: list[object], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        linear_fit(x, y)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# confidence_band
# ---------------------------------------------------------------------------


def test_band_brackets_the_fitted_line_everywhere() -> None:
    """A band that excludes the line it describes renders as a ribbon floating off the
    curve, so this has to hold at every grid point, not on average."""
    band = confidence_band(*_noisy_line())

    assert all(lo <= y <= up for lo, y, up in zip(band.lower, band.y, band.upper, strict=True))


def test_band_extends_to_both_sides_of_the_fitted_line() -> None:
    """Bracketing alone is too weak an assertion: because the band is widened to include
    the point estimate, a band computed from two *identical* percentiles still satisfies
    ``lower <= y <= upper`` -- it just hangs entirely below the line, which renders as a
    ribbon glued to one side. On a well-behaved sample the interval has to straddle the
    line strictly at every grid point."""
    band = confidence_band(*_noisy_line())

    assert all(lo < y for lo, y in zip(band.lower, band.y, strict=True))
    assert all(y < up for y, up in zip(band.y, band.upper, strict=True))


def test_band_arrays_all_match_the_requested_grid() -> None:
    band = confidence_band(*_noisy_line(), grid=37)

    assert len(band.x) == len(band.y) == len(band.lower) == len(band.upper) == 37


def test_band_spans_exactly_the_observed_x_range() -> None:
    xs, ys = _noisy_line()
    band = confidence_band(xs, ys)

    assert band.x[0] == pytest.approx(min(xs))
    assert band.x[-1] == pytest.approx(max(xs))


def test_band_centre_line_is_the_point_estimate() -> None:
    """``y`` must be the fit through the *original* sample, not the mean of the
    resamples -- otherwise the drawn line disagrees with ``linear_fit``."""
    xs, ys = _noisy_line()
    fit = linear_fit(xs, ys)
    band = confidence_band(xs, ys)

    assert band.y == [pytest.approx(fit.predict(position)) for position in band.x]


def test_a_wider_level_gives_a_strictly_wider_band() -> None:
    xs, ys = _noisy_line()
    narrow = confidence_band(xs, ys, level=0.80)
    wide = confidence_band(xs, ys, level=0.99)

    narrow_widths = [up - lo for lo, up in zip(narrow.lower, narrow.upper, strict=True)]
    wide_widths = [up - lo for lo, up in zip(wide.lower, wide.upper, strict=True)]

    assert all(a < b for a, b in zip(narrow_widths, wide_widths, strict=True))


def test_band_is_narrowest_near_the_mean_of_x() -> None:
    """The classic hourglass: a resample that reweights the extremes pivots the line
    about its centroid, so uncertainty is smallest there and flares outward. A band of
    constant width would mean the resampling never varied the *slope*."""
    xs, ys = _noisy_line()
    band = confidence_band(xs, ys)
    widths = [up - lo for lo, up in zip(band.lower, band.upper, strict=True)]

    mean_x = math.fsum(xs) / len(xs)
    narrowest_x = band.x[widths.index(min(widths))]
    span = max(xs) - min(xs)

    assert abs(narrowest_x - mean_x) < 0.1 * span
    assert widths[0] > 1.3 * min(widths)
    assert widths[-1] > 1.3 * min(widths)


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------


def test_the_same_seed_reproduces_the_band_exactly() -> None:
    xs, ys = _noisy_line()

    assert confidence_band(xs, ys, seed=3).lower == confidence_band(xs, ys, seed=3).lower


def test_a_different_seed_gives_a_different_band() -> None:
    """If it did not, ``seed`` would be decorative and the bootstrap would not be
    resampling at all."""
    xs, ys = _noisy_line()

    assert confidence_band(xs, ys, seed=3).lower != confidence_band(xs, ys, seed=4).lower


def test_the_band_ignores_the_global_random_state() -> None:
    """The module must own a ``random.Random(seed)``. If it reached for the module-level
    RNG instead, reseeding it here would change the output and every snapshot test in
    this package would become order-dependent."""
    xs, ys = _noisy_line()

    random.seed(1)
    first = confidence_band(xs, ys).lower
    random.seed(999)
    second = confidence_band(xs, ys).lower

    assert first == second


def test_the_module_uses_no_numpy_and_no_global_rng() -> None:
    """Pinned as source text because both are architectural decisions recorded in the
    issue, and either could be reintroduced by an edit that still passes every other
    test here."""
    source = inspect.getsource(regression)

    assert "numpy" not in source
    for global_call in ("random.random(", "random.randrange(", "random.choice(", "random.seed("):
        assert global_call not in source


# ---------------------------------------------------------------------------
# rejected parameters
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"level": 0.0}, "strictly between 0 and 1"),
        ({"level": 1.0}, "strictly between 0 and 1"),
        ({"level": 1.5}, "strictly between 0 and 1"),
        ({"level": -0.5}, "strictly between 0 and 1"),
        ({"level": float("nan")}, "strictly between 0 and 1"),
        ({"n_boot": 0}, "at least 1"),
        ({"n_boot": -1}, "at least 1"),
        ({"n_boot": _MAX_BOOTSTRAP_SAMPLES + 1}, f"at most {_MAX_BOOTSTRAP_SAMPLES}"),
        ({"grid": 1}, "at least 2"),
        ({"grid": _MAX_GRID + 1}, f"at most {_MAX_GRID}"),
    ],
)
def test_confidence_band_rejects_unusable_parameters(kwargs: dict[str, object], match: str) -> None:
    xs, ys = _noisy_line(n=20)
    with pytest.raises(ValueError, match=match):
        confidence_band(xs, ys, **kwargs)  # type: ignore[arg-type]


def test_confidence_band_rejects_a_vertical_sample() -> None:
    with pytest.raises(ValueError, match="vertical"):
        confidence_band([2.0, 2.0, 2.0, 2.0], [1.0, 2.0, 3.0, 4.0])


def test_the_caps_admit_their_own_boundary() -> None:
    """An off-by-one in a cap would reject the size its docstring promises to serve."""
    xs, ys = _noisy_line(n=20)

    assert len(confidence_band(xs, ys, grid=_MAX_GRID).x) == _MAX_GRID
    assert len(confidence_band(xs, ys, n_boot=_MAX_BOOTSTRAP_SAMPLES).x) == 100

    at_cap_x = [float(index) for index in range(_MAX_POINTS)]
    at_cap_y = [2.0 * value for value in at_cap_x]
    assert linear_fit(at_cap_x, at_cap_y).slope == pytest.approx(2.0)


def test_a_single_resample_still_produces_a_usable_band() -> None:
    """``n_boot=1`` is the degenerate low end: one resample means the percentile interval
    collapses to a point, and only the widening to include the point estimate keeps the
    band from inverting."""
    band = confidence_band(*_noisy_line(n=20), n_boot=1)

    assert all(lo <= y <= up for lo, y, up in zip(band.lower, band.y, band.upper, strict=True))


def test_a_near_degenerate_sample_survives_resampling() -> None:
    """Most resamples of a sample whose x values nearly all coincide come out vertical
    and get dropped. The call must still return a band from the survivors rather than
    crashing on an empty percentile input.

    Asserting ``lower <= upper`` here would be vacuous -- the widening step makes it true
    by construction whatever the percentiles are. What is worth pinning is that dropping
    the degenerate resamples is *conservative*: with a single x carrying all the leverage,
    the band has to admit substantial uncertainty. Counting the dropped resamples as the
    point estimate instead would pretend to a confidence the data does not support, and
    measurably narrows the band (4.25 -> 3.46 on this fixture)."""
    xs = [1.0] * 12 + [5.0]
    ys = [float(index) for index in range(13)]
    band = confidence_band(xs, ys, n_boot=200)
    widths = [up - lo for lo, up in zip(band.lower, band.upper, strict=True)]

    assert all(math.isfinite(value) for value in (*band.lower, *band.upper))
    assert max(widths) > 0.3 * (max(ys) - min(ys))


def test_every_resample_degenerate_is_reported_as_such() -> None:
    """Reachable, not theoretical: with a single resample of a sample whose x values are
    nearly all identical, this fires for many seeds. Without the guard the user gets
    ``quantiles``' unrelated "values must not be empty" instead."""
    xs = [1.0] * 12 + [5.0]
    ys = [float(index) for index in range(13)]

    degenerate_seeds = []
    for seed in range(30):
        try:
            confidence_band(xs, ys, n_boot=1, seed=seed)
        except ValueError as error:
            if "degenerate" in str(error):
                degenerate_seeds.append(seed)

    assert degenerate_seeds, "expected at least one seed to draw only vertical resamples"


# ---------------------------------------------------------------------------
# calibration
# ---------------------------------------------------------------------------
#
# The tests above pin the band's *shape* -- monotone in ``level``, hourglass, two-sided.
# None of them pin its *width*, and width is the entire product: turning the two-sided
# percentiles into one-sided ones, or halving the resample size, leaves every shape
# property intact while turning a nominal 95% band into something else.
#
# The oracle is the closed-form OLS standard error, used here only as a *test* reference.
# That is not a reversal of the module's decision to bootstrap: the objection to the
# closed form was that it needs a Student-t quantile, and these assertions are calibrated
# at sample sizes large enough that the normal quantile is the right constant.

_Z_95 = 1.959964
_Z_68 = 0.994458


def test_band_width_scales_with_the_normal_quantile_of_the_level() -> None:
    """Asymptotically the band is ``+- z(level) * se``, so the ratio of two levels' widths
    is the ratio of their z values -- 1.971 for 95% over 68% -- independent of the data.
    A one-sided quantile leaves the band monotone in ``level`` but lands this near 3.5."""
    xs, ys = _noisy_line(n=300)
    wide = confidence_band(xs, ys, level=0.95, n_boot=1000)
    narrow = confidence_band(xs, ys, level=0.68, n_boot=1000)

    middle = len(wide.x) // 2
    ratio = (wide.upper[middle] - wide.lower[middle]) / (narrow.upper[middle] - narrow.lower[middle])

    assert ratio == pytest.approx(_Z_95 / _Z_68, rel=0.10)


def test_band_width_at_the_centroid_matches_the_closed_form_standard_error() -> None:
    """At ``xbar`` the OLS prediction's standard error is ``s / sqrt(n)``, so a 95% band is
    ``2 * z * s / sqrt(n)`` wide there. This is what fixes the *absolute* scale: halving
    the resample size inflates the bootstrap spread by ~sqrt(2) and shows up here while
    every shape assertion stays green."""
    xs, ys = _noisy_line(n=300)
    fit = linear_fit(xs, ys)
    residuals = [y - fit.predict(x) for x, y in zip(xs, ys, strict=True)]
    standard_error = math.sqrt(math.fsum(value**2 for value in residuals) / (len(xs) - 2))

    band = confidence_band(xs, ys, level=0.95, n_boot=1000)
    mean_x = math.fsum(xs) / len(xs)
    at_centroid = min(range(len(band.x)), key=lambda index: abs(band.x[index] - mean_x))
    width = band.upper[at_centroid] - band.lower[at_centroid]

    assert width == pytest.approx(2 * _Z_95 * standard_error / math.sqrt(len(xs)), rel=0.10)
