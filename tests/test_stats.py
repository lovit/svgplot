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
    stdev_stats = box_stats(DATA_WITH_OUTLIER, mode="stdev")
    pstdev_stats = box_stats(DATA_WITH_OUTLIER, mode="pstdev")
    assert stdev_stats.whisker_high != pstdev_stats.whisker_high
    assert 100.0 in stdev_stats.outliers
    assert 100.0 in pstdev_stats.outliers


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
