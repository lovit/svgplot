from __future__ import annotations

import math

import pytest

from svgplot.stats.binning import histogram_bins
from svgplot.stats.box import MODES as BOX_MODES, box_stats
from svgplot.stats.interpolate import METHODS, interpolate

# --- interpolate ---------------------------------------------------------

X = [0.0, 1.0, 2.0, 3.0, 4.0]
Y = [0.0, 1.0, 0.0, -1.0, 0.0]


@pytest.mark.parametrize("method", METHODS)
def test_interpolate_output_point_count_and_range(method: str) -> None:
    curve = interpolate(X, Y, method=method, precision=100)
    assert len(curve) == 100
    assert curve.x[0] == pytest.approx(X[0])
    assert curve.x[-1] == pytest.approx(X[-1])
    assert all(math.isfinite(v) for v in curve.y)


@pytest.mark.parametrize("method", METHODS)
def test_interpolate_passes_through_original_points_at_matching_x(method: str) -> None:
    """Every spline/polynomial method should reproduce the original y at its own x
    (within floating-point tolerance) when precision is dense enough to land on it."""
    curve = interpolate(X, Y, method=method, precision=401)
    for xi, yi in zip(X, Y, strict=True):
        index = curve.x.index(pytest.approx(xi))
        assert curve.y[index] == pytest.approx(yi, abs=1e-6)


def test_interpolate_two_points_works_for_every_method() -> None:
    for method in METHODS:
        curve = interpolate([0.0, 1.0], [0.0, 2.0], method=method, precision=10)
        assert len(curve) == 10
        assert curve.y[0] == pytest.approx(0.0)
        assert curve.y[-1] == pytest.approx(2.0)


def test_interpolate_rejects_unknown_method() -> None:
    with pytest.raises(ValueError, match="unknown interpolation method"):
        interpolate(X, Y, method="bogus")


def test_interpolate_rejects_out_of_range_precision() -> None:
    with pytest.raises(ValueError, match="precision"):
        interpolate(X, Y, precision=1)
    with pytest.raises(ValueError, match="precision"):
        interpolate(X, Y, precision=10**9)


def test_interpolate_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        interpolate([0.0, 1.0], [0.0])


def test_interpolate_rejects_too_few_points() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        interpolate([0.0], [0.0])


def test_interpolate_rejects_non_increasing_x() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        interpolate([0.0, 1.0, 1.0], [0.0, 1.0, 2.0])
    with pytest.raises(ValueError, match="strictly increasing"):
        interpolate([0.0, 2.0, 1.0], [0.0, 1.0, 2.0])


def test_interpolate_rejects_non_finite_coordinates() -> None:
    with pytest.raises(ValueError, match="finite"):
        interpolate([0.0, float("nan")], [0.0, 1.0])
    with pytest.raises(ValueError, match="finite"):
        interpolate([0.0, 1.0], [0.0, float("inf")])


def test_interpolate_handles_extreme_but_finite_coordinates_without_overflow() -> None:
    """Large-but-finite y-values shouldn't blow up spline arithmetic (same overflow
    class of bug fixed in palette.sequential.cubehelix_sequence)."""
    for method in METHODS:
        curve = interpolate([0.0, 1.0, 2.0], [1e300, -1e300, 1e300], method=method, precision=20)
        assert all(math.isfinite(v) for v in curve.y)


@pytest.mark.parametrize("method", METHODS)
def test_interpolate_rejects_extreme_but_finite_x_span_instead_of_overflowing(method: str) -> None:
    """Regression: individual x/y coordinates being finite isn't enough — x[-1]-x[0]
    itself can overflow to inf (e.g. -1e308 to 1e308), silently corrupting every
    output point with nan/inf via _linspace's step calculation instead of raising."""
    with pytest.raises(ValueError, match="finite"):
        interpolate([-1e308, 0.0, 1e308], [0.0, 1.0, 0.0], method=method, precision=10)


def test_interpolate_rejects_too_many_points() -> None:
    with pytest.raises(ValueError, match="too many points"):
        interpolate([float(i) for i in range(2500)], [float(i) for i in range(2500)], method="cubic")


def test_interpolate_lagrange_has_a_much_stricter_point_cap() -> None:
    """lagrange is O(n^2 * precision) and numerically unstable past a small point count,
    so it gets a much lower cap than the linear-in-n methods — a point count that's
    fine for cubic/hermite should still be rejected for lagrange specifically."""
    x = [float(i) for i in range(100)]
    y = [float(i % 3) for i in range(100)]
    interpolate(x, y, method="cubic", precision=10)  # under _MAX_POINTS: fine
    with pytest.raises(ValueError, match="lagrange"):
        interpolate(x, y, method="lagrange", precision=10)


def test_interpolate_trigonometric_has_a_stricter_point_cap_than_the_linear_methods() -> None:
    """trigonometric's DFT is the naive O(n^2) form, so it is not linear in the point
    count the way cubic/hermite are. Under the shared _MAX_POINTS it was the slowest
    path in the package (~3.5x the already-capped lagrange worst case), so it needs its
    own cap — a point count fine for cubic must still be rejected for trigonometric."""
    x = [float(i) for i in range(600)]
    y = [float(i % 5) for i in range(600)]
    interpolate(x, y, method="cubic", precision=10)  # under _MAX_POINTS: fine
    with pytest.raises(ValueError, match="trigonometric"):
        interpolate(x, y, method="trigonometric", precision=10)


def test_interpolate_trigonometric_accepts_a_point_count_at_its_cap() -> None:
    """The cap bounds cost without rejecting realistic input: exactly _MAX_TRIGONOMETRIC_POINTS
    must still work, so the boundary is inclusive rather than off by one."""
    n = 500
    x = [float(i) for i in range(n)]
    y = [float(i % 5) for i in range(n)]
    curve = interpolate(x, y, method="trigonometric", precision=10)
    assert len(curve) == 10


@pytest.mark.parametrize("method", ("cubic", "hermite"))
def test_interpolate_rejects_extreme_but_finite_y_span_instead_of_overflowing(method: str) -> None:
    """Regression: the x-span finiteness check alone isn't enough — cubic's spline
    coefficients and hermite's finite-difference tangents both compute differences of
    y-values (e.g. (y[i+1]-y[i-1])/h), which can overflow to inf even when x[-1]-x[0]
    and every individual y value are finite (e.g. y jumping between -1e308 and 1e308).
    The final output is validated for finiteness to catch this and any similar path."""
    with pytest.raises(ValueError, match="non-finite"):
        interpolate([0.0, 0.5, 1.0], [-1e308, 0.0, 1e308], method=method, precision=5)


def test_interpolate_rejects_non_numeric_coordinates() -> None:
    with pytest.raises(ValueError, match="numbers"):
        interpolate([0.0, "a"], [0.0, 1.0])  # type: ignore[list-item]


# --- histogram_bins --------------------------------------------------------


def test_histogram_bins_auto_returns_sorted_edges_spanning_the_data() -> None:
    edges = histogram_bins([1.0, 2.0, 2.0, 3.0, 10.0], bins="auto")
    assert edges == sorted(edges)
    assert edges[0] <= 1.0
    assert edges[-1] >= 10.0


def test_histogram_bins_accepts_explicit_bin_count() -> None:
    edges = histogram_bins([0.0, 1.0, 2.0, 3.0, 4.0], bins=4)
    assert len(edges) == 5  # 4 bins -> 5 edges
    assert edges[0] == pytest.approx(0.0)
    assert edges[-1] == pytest.approx(4.0)


def test_histogram_bins_rejects_empty_values() -> None:
    with pytest.raises(ValueError, match="empty"):
        histogram_bins([])


def test_histogram_bins_rejects_non_finite_values() -> None:
    with pytest.raises(ValueError, match="finite"):
        histogram_bins([1.0, float("nan"), 3.0])
    with pytest.raises(ValueError, match="finite"):
        histogram_bins([1.0, float("inf")])


def test_histogram_bins_rejects_invalid_bins_spec() -> None:
    with pytest.raises((ValueError, TypeError)):
        histogram_bins([1.0, 2.0, 3.0], bins="not-a-real-strategy")


def test_histogram_bins_rejects_excessive_bin_count() -> None:
    """Regression: an unbounded int `bins` (e.g. 10**8) returns ~800MB of edges from
    a single call — a memory-exhaustion DoS."""
    with pytest.raises(ValueError, match="10000|10_000"):
        histogram_bins([1.0, 2.0, 3.0], bins=10**8)


def test_histogram_bins_rejects_non_str_int_bins() -> None:
    """Regression: a list `bins` silently passed straight through to numpy and got
    treated as explicit bin edges instead of being rejected by our own type contract."""
    with pytest.raises(ValueError, match="string or int"):
        histogram_bins([1.0, 2.0, 3.0], bins=[0, 1, 2])  # type: ignore[arg-type]


def test_histogram_bins_rejects_non_numeric_values() -> None:
    with pytest.raises(ValueError, match="numbers"):
        histogram_bins([1.0, "a", 3.0])  # type: ignore[list-item]


def test_histogram_bins_rejects_extreme_but_finite_span_instead_of_overflowing() -> None:
    """Regression: -1e308 and 1e308 are each individually finite, but their span
    (max - min) overflows to inf when numpy computes the bin range internally, which
    otherwise surfaces as numpy's own confusing internal error instead of a clear one."""
    with pytest.raises(ValueError, match="span"):
        histogram_bins([-1e308, 1e308])


# --- box_stats ---------------------------------------------------------


DATA_WITH_OUTLIER = [1.0, 2.0, 2.0, 3.0, 3.0, 4.0, 4.0, 5.0, 100.0]


def test_box_stats_extremes_uses_min_max_and_never_reports_outliers() -> None:
    stats = box_stats(DATA_WITH_OUTLIER, mode="extremes")
    assert stats.whisker_low == 1.0
    assert stats.whisker_high == 100.0
    assert stats.outliers == []


def test_box_stats_1_5_iqr_flags_the_far_point_as_an_outlier() -> None:
    stats = box_stats(DATA_WITH_OUTLIER, mode="1.5IQR")
    assert stats.outliers == [100.0]
    assert stats.whisker_high < 100.0
    assert stats.q1 < stats.median < stats.q3


def test_box_stats_tukey_uses_hinge_quartiles_and_flags_outlier() -> None:
    stats = box_stats(DATA_WITH_OUTLIER, mode="tukey")
    assert stats.outliers == [100.0]
    # Tukey hinges on this odd-length (9) dataset exclude the median (index 4, value 3.0)
    # from both halves: lower half (indices 0-3) [1,2,2,3] -> hinge 2.0; upper half
    # (indices 5-8) [4,4,5,100] -> hinge (4+5)/2 = 4.5 (the outlier is still part of the
    # upper half by rank — Tukey hinges are computed before outliers are identified).
    assert stats.q1 == pytest.approx(2.0)
    assert stats.q3 == pytest.approx(4.5)


def test_box_stats_stdev_and_pstdev_differ_for_the_same_data() -> None:
    """Concrete expected values (computed via statistics.stdev/pstdev on
    DATA_WITH_OUTLIER: mean=13.7778, stdev=32.3565, pstdev=30.5060) rather than a
    relative comparison, so a mean/mode-swap regression can't slip through."""
    stdev_stats = box_stats(DATA_WITH_OUTLIER, mode="stdev")
    assert stdev_stats.whisker_low == pytest.approx(-18.578743, abs=1e-5)
    assert stdev_stats.whisker_high == pytest.approx(46.134299, abs=1e-5)
    assert stdev_stats.outliers == [100.0]

    pstdev_stats = box_stats(DATA_WITH_OUTLIER, mode="pstdev")
    assert pstdev_stats.whisker_low == pytest.approx(-16.728243, abs=1e-5)
    assert pstdev_stats.whisker_high == pytest.approx(44.283798, abs=1e-5)
    assert pstdev_stats.outliers == [100.0]


@pytest.mark.parametrize("mode", BOX_MODES)
def test_box_stats_all_identical_values_degenerates_cleanly(mode: str) -> None:
    stats = box_stats([5.0] * 5, mode=mode)
    assert stats.median == stats.q1 == stats.q3 == 5.0
    assert stats.whisker_low == stats.whisker_high == 5.0
    assert stats.outliers == []


@pytest.mark.parametrize("mode", ("extremes", "1.5IQR", "stdev", "pstdev"))
def test_box_stats_computes_wide_span_quartiles_instead_of_over_rejecting(mode: str) -> None:
    """A span of -1e308..1e308 has a perfectly representable 25th percentile (-5e307),
    but the old percentile formula (``lo + f * (up - lo)``) formed the difference
    ``up - lo`` first, which overflows to inf and tripped the finiteness guard on a
    result that was never actually non-finite. The weighted form
    (``lo * (1 - f) + up * f``) never forms a value larger than its own endpoints,
    so the correct answer survives.

    This pins the *absence* of that spurious rejection. The guard itself is still
    exercised by the tukey/stdev overflow tests below, which use datasets whose
    results genuinely are non-finite."""
    stats = box_stats([-1e308, 1e308], mode=mode)

    # Hand-checked: rank = 0.25 * (2 - 1) = 0.25, so
    # q1 = -1e308 * 0.75 + 1e308 * 0.25 = -5e307 (and q3 mirrors it).
    assert stats.q1 == pytest.approx(-5e307)
    assert stats.q3 == pytest.approx(5e307)
    assert math.isfinite(stats.median)
    assert math.isfinite(stats.whisker_low) and math.isfinite(stats.whisker_high)


def test_box_stats_rejects_extreme_but_finite_values_that_would_overflow_tukey_hinges() -> None:
    """Regression: tukey's hinges (median of each half) overflow when a half's own two
    middle elements sum past float max — e.g. the lower half [-1e308, -1e308] averages
    to -inf via (-1e308 + -1e308) / 2. This dataset doesn't overflow the other 4 modes'
    linear-percentile formula (see the sibling test above), so it needs its own case."""
    with pytest.raises(ValueError, match="finite"):
        box_stats([-1e308, -1e308, 1e308, 1e308], mode="tukey")


def test_box_stats_rejects_extreme_but_finite_values_that_would_overflow_stdev() -> None:
    """Regression: statistics.stdev/pstdev raises a raw OverflowError on finite-but-huge
    input (fsum's internal overflow) instead of the ValueError this module documents."""
    values = [1e308, 1e308, 1e308, -1e308, -1e308, -1e308]
    with pytest.raises(ValueError, match="stdev"):
        box_stats(values, mode="stdev")
    with pytest.raises(ValueError, match="pstdev"):
        box_stats(values, mode="pstdev")


def test_box_stats_rejects_non_numeric_values() -> None:
    with pytest.raises(ValueError, match="numbers"):
        box_stats([1.0, "a", 3.0])  # type: ignore[list-item]


def test_box_stats_single_value_does_not_crash_for_any_mode() -> None:
    for mode in BOX_MODES:
        stats = box_stats([5.0], mode=mode)
        assert stats.median == stats.q1 == stats.q3 == stats.whisker_low == stats.whisker_high == 5.0
        assert stats.outliers == []


def test_box_stats_rejects_empty_values() -> None:
    with pytest.raises(ValueError, match="empty"):
        box_stats([])


def test_box_stats_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="unknown box mode"):
        box_stats([1.0, 2.0, 3.0], mode="bogus")


def test_box_stats_rejects_non_finite_values() -> None:
    with pytest.raises(ValueError, match="finite"):
        box_stats([1.0, float("nan"), 3.0])
