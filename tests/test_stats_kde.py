from __future__ import annotations

import math
import random
from itertools import pairwise

import pytest

from svgplot.stats.kde import _MAX_GRID, _MAX_POINTS, BANDWIDTH_RULES, kde
from svgplot.stats.quantile import quantile


def _normal_sample(n: int = 1000, *, seed: int = 42) -> list[float]:
    """A fixed pseudo-random normal sample. Seeded, because "same input -> same output"
    is this package's contract and a flaky density test would undermine it."""
    generator = random.Random(seed)
    return [generator.gauss(0.0, 1.0) for _ in range(n)]


def _sample_deviation(numbers: list[float]) -> float:
    mean = math.fsum(numbers) / len(numbers)
    return math.sqrt(math.fsum((number - mean) ** 2 for number in numbers) / (len(numbers) - 1))


# ---------------------------------------------------------------------------
# curve shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rule", BANDWIDTH_RULES)
def test_kde_curve_is_a_density_over_the_requested_grid(rule: str) -> None:
    """The three properties that make the result a density rather than an arbitrary
    curve: it has exactly ``grid`` samples, it is never negative, and it integrates to 1
    (up to the truncation at ``cut`` bandwidths)."""
    curve = kde(_normal_sample(), bandwidth=rule, grid=256)

    assert len(curve.x) == len(curve.y) == 256
    assert min(curve.y) >= 0.0
    step = curve.x[1] - curve.x[0]
    assert math.fsum(curve.y) * step == pytest.approx(1.0, abs=1e-2)


def test_kde_grid_spans_cut_bandwidths_beyond_the_data() -> None:
    """The tails need room to decay, so the grid must extend ``cut * bandwidth`` past the
    extremes -- not stop at min/max, which would clip visible mass off both ends."""
    sample = _normal_sample(n=200)
    curve = kde(sample, bandwidth=0.4, cut=2.5)

    assert curve.x[0] == pytest.approx(min(sample) - 2.5 * 0.4)
    assert curve.x[-1] == pytest.approx(max(sample) + 2.5 * 0.4)


def test_kde_grid_is_evenly_spaced() -> None:
    curve = kde(_normal_sample(n=100), grid=64)
    steps = [b - a for a, b in pairwise(curve.x)]

    assert max(steps) == pytest.approx(min(steps))


def test_kde_cut_zero_stops_exactly_at_the_data_range() -> None:
    sample = _normal_sample(n=100)
    curve = kde(sample, cut=0.0)

    assert curve.x[0] == pytest.approx(min(sample))
    assert curve.x[-1] == pytest.approx(max(sample))


def test_kde_peaks_where_the_data_is_dense() -> None:
    """A two-cluster sample must produce two local maxima near the clusters -- the check
    that the kernel is actually centred on each value rather than smeared uniformly."""
    sample = [0.0 + 0.05 * i for i in range(50)] + [10.0 + 0.05 * i for i in range(50)]
    curve = kde(sample, bandwidth=0.3, grid=512)

    peak_x = curve.x[curve.y.index(max(curve.y))]
    left_mass = math.fsum(y for x, y in zip(curve.x, curve.y, strict=True) if x < 5.0)
    right_mass = math.fsum(y for x, y in zip(curve.x, curve.y, strict=True) if x >= 5.0)

    assert min(abs(peak_x - 1.25), abs(peak_x - 11.25)) < 1.5
    assert left_mass == pytest.approx(right_mass, rel=0.05)


def test_kde_is_deterministic() -> None:
    sample = _normal_sample(n=200)

    assert kde(sample).y == kde(sample).y


# ---------------------------------------------------------------------------
# bandwidth selection
# ---------------------------------------------------------------------------


def test_scott_bandwidth_matches_the_published_formula() -> None:
    """h = sd * n**(-1/5). Pinned exactly, because a rule that is merely "in the right
    ballpark" is indistinguishable from a wrong exponent on any smooth sample."""
    sample = _normal_sample(n=500)
    expected = _sample_deviation(sample) * len(sample) ** -0.2

    assert kde(sample, bandwidth="scott").bandwidth == pytest.approx(expected)


def test_silverman_bandwidth_matches_the_published_formula() -> None:
    """h = 0.9 * min(sd, IQR/1.34) * n**(-1/5)."""
    sample = _normal_sample(n=500)
    spread = (quantile(sample, 0.75) - quantile(sample, 0.25)) / 1.34
    expected = 0.9 * min(_sample_deviation(sample), spread) * len(sample) ** -0.2

    assert kde(sample, bandwidth="silverman").bandwidth == pytest.approx(expected)


def test_the_two_rules_disagree_on_a_normal_sample() -> None:
    """Silverman's 0.9 factor makes it the narrower of the two here; if both rules
    returned the same number, either name would be silently unreachable."""
    sample = _normal_sample(n=500)

    assert kde(sample, bandwidth="silverman").bandwidth < kde(sample, bandwidth="scott").bandwidth


def test_an_explicit_bandwidth_bypasses_rule_selection() -> None:
    assert kde(_normal_sample(n=100), bandwidth=0.75).bandwidth == 0.75


def test_silverman_falls_back_to_the_deviation_when_the_iqr_collapses() -> None:
    """A tight cluster plus one far outlier has a positive standard deviation but a zero
    IQR. Taking min() blindly would hand back a bandwidth of 0 and render an infinite
    spike, so the zero must be rejected in favour of the deviation."""
    sample = [1.0] * 20 + [500.0]

    assert kde(sample, bandwidth="silverman").bandwidth > 0.0


# ---------------------------------------------------------------------------
# rejected input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rule", BANDWIDTH_RULES)
def test_a_zero_variance_sample_is_rejected_by_every_rule(rule: str) -> None:
    """The realistic crash: every value identical. Both rules scale a spread, so a
    bandwidth of 0 would follow -- dividing by zero in the kernel and, if it survived
    that, drawing an infinite spike at the repeated value. It must fail loudly and name
    the repeated value."""
    with pytest.raises(ValueError, match="zero-variance"):
        kde([7.5] * 10, bandwidth=rule)


def test_a_zero_variance_sample_is_still_estimable_with_an_explicit_bandwidth() -> None:
    """The rejection above is about rule *selection*, not about the estimator, so the
    escape hatch the error message advertises has to actually work."""
    curve = kde([7.5] * 10, bandwidth=0.5)

    assert min(curve.y) >= 0.0
    assert curve.x[0] == pytest.approx(7.5 - 3.0 * 0.5)


@pytest.mark.parametrize(
    ("values", "match"),
    [
        ([], "must not be empty"),
        ([1.0], "at least 2 values"),
        ([1.0, float("nan")], "non-finite"),
        ([1.0, float("inf")], "non-finite"),
        ([1.0, "x"], "must be numbers"),
        ([0.0] * (_MAX_POINTS + 1), f"at most {_MAX_POINTS}"),
    ],
)
def test_kde_rejects_unusable_samples(values: list[object], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        kde(values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"grid": 1}, "at least 2"),
        ({"grid": 0}, "at least 2"),
        ({"grid": _MAX_GRID + 1}, f"at most {_MAX_GRID}"),
        ({"cut": -1.0}, "must not be negative"),
        ({"cut": float("nan")}, "must be finite"),
        ({"bandwidth": 0.0}, "must be positive"),
        ({"bandwidth": -0.5}, "must be positive"),
        ({"bandwidth": float("inf")}, "must be finite"),
        ({"bandwidth": "nope"}, "bandwidth rule must be one of"),
    ],
)
def test_kde_rejects_unusable_parameters(kwargs: dict[str, object], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        kde(_normal_sample(n=50), **kwargs)  # type: ignore[arg-type]


def test_the_caps_admit_their_own_boundary() -> None:
    """An off-by-one in either cap would reject a size the docstring promises to serve."""
    assert len(kde([float(i) for i in range(_MAX_POINTS)], grid=2).x) == 2
    assert len(kde(_normal_sample(n=50), grid=_MAX_GRID).x) == _MAX_GRID
