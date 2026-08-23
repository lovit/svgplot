from __future__ import annotations

import math

import pytest

from svgplot.stats.binning import MAX_BINS, histogram_bins
from svgplot.stats.box import MODES as BOX_MODES, box_stats
from svgplot.stats.interpolate import METHODS, _natural_cubic_spline_coeffs, interpolate

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


def _solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting.

    Deliberately a *dense* solve, where the implementation uses the Thomas algorithm: a second
    copy of the same recurrence would agree with a transcription error in the first. This one
    is written from the linear system itself, so the two share only the mathematics.
    """
    size = len(matrix)
    augmented = [row[:] + [rhs[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda r: abs(augmented[r][column]))
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        for row in range(column + 1, size):
            factor = augmented[row][column] / augmented[column][column]
            for k in range(column, size + 1):
                augmented[row][k] -= factor * augmented[column][k]
    solution = [0.0] * size
    for row in range(size - 1, -1, -1):
        total = sum(augmented[row][k] * solution[k] for k in range(row + 1, size))
        solution[row] = (augmented[row][size] - total) / augmented[row][row]
    return solution


def _natural_spline_reference(xs: list[float], ys: list[float], query: float) -> float:
    """A natural cubic spline evaluated at ``query``, from the textbook system.

    ``h[i-1]*M[i-1] + 2*(h[i-1]+h[i])*M[i] + h[i]*M[i+1] = 6*((y[i+1]-y[i])/h[i] - (y[i]-y[i-1])/h[i-1])``
    with ``M[0] = M[n-1] = 0``, then the standard evaluation. ``M`` is the second derivative at
    each knot -- the quantity ``_natural_cubic_spline_coeffs``'s own docstring names.
    """
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    matrix = [[0.0] * n for _ in range(n)]
    rhs = [0.0] * n
    matrix[0][0] = matrix[n - 1][n - 1] = 1.0
    for i in range(1, n - 1):
        matrix[i][i - 1], matrix[i][i], matrix[i][i + 1] = h[i - 1], 2 * (h[i - 1] + h[i]), h[i]
        rhs[i] = 6 * ((ys[i + 1] - ys[i]) / h[i] - (ys[i] - ys[i - 1]) / h[i - 1])
    second = _solve(matrix, rhs)
    segment = next(i for i in range(n - 1) if xs[i] <= query <= xs[i + 1])
    width = h[segment]
    a = (xs[segment + 1] - query) / width
    b = (query - xs[segment]) / width
    return (
        a * ys[segment]
        + b * ys[segment + 1]
        + ((a**3 - a) * second[segment] + (b**3 - b) * second[segment + 1]) * width * width / 6
    )


def test_the_cubic_coefficients_are_second_derivatives_as_named() -> None:
    """``_natural_cubic_spline_coeffs`` returned **half** the second derivative (#268).

    It solves the Burden-Faires system (``alpha = 3 * ...``), whose unknown is ``S''/2`` and
    whose companion evaluation is ``a + b*t + c*t^2 + d*t^3``. ``_cubic`` evaluates the
    Numerical Recipes way instead -- ``((a^3-a)*m_i + (b^3-b)*m_{i+1}) * h^2/6`` -- which
    requires the full second derivative. Half of one formula and half of the other, so the
    curve carried exactly half the curvature it should.

    ``x=[0,1,2], y=[0,1,0]`` is the smallest case that pins it, and it solves by hand: one
    interior equation, ``4*M1 = 6*((0-1)/1 - (1-0)/1) = -12``, so ``M1 = -3``. The buggy version
    answered ``-1.5``.
    """
    assert _natural_cubic_spline_coeffs([0.0, 1.0, 2.0], [0.0, 1.0, 0.0]) == pytest.approx([0.0, -3.0, 0.0])


def test_the_cubic_curve_matches_the_hand_solved_spline() -> None:
    """The same case carried through to a drawn point. With ``M1 = -3`` and ``a = b = 0.5``:
    ``0.5*0 + 0.5*1 + ((0.125-0.5)*0 + (0.125-0.5)*(-3)) * 1/6 = 0.6875``. The buggy version
    drew ``0.59375`` -- and passed every test in this file, because the midpoint of a symmetric
    fixture is not a knot and nothing looked anywhere but at knots."""
    curve = interpolate([0.0, 1.0, 2.0], [0.0, 1.0, 0.0], method="cubic", precision=5)

    assert curve.x[1] == pytest.approx(0.5)
    assert curve.y[1] == pytest.approx(0.6875)


@pytest.mark.parametrize("query", [0.5, 1.25, 1.5, 2.5, 3.75])
def test_the_cubic_curve_matches_an_independent_solve_away_from_the_knots(query: float) -> None:
    """Away from the knots is the only place this can be checked at all.

    At a knot ``a = 1`` and ``b = 0``, so ``(a^3 - a)`` and ``(b^3 - b)`` are both zero and the
    entire coefficient term cancels: the curve passes through every knot whatever ``m`` holds --
    half the truth, zero, or noise. That cancellation is why
    :func:`test_interpolate_passes_through_original_points_at_matching_x` stayed green through
    this defect, and it is the same cancellation that makes a ``/6`` -> ``/3`` mutation invisible
    (#262).

    Five samples rather than one because a single one can land where the wrong answer and the
    right one coincide. That is not a hypothetical: on ``x=[0,1,2,3], y=[0,1,0,1]`` -- symmetric
    about ``x=1.5`` -- both the halved and the correct spline answer ``0.5`` there, and
    :func:`test_a_symmetric_midpoint_cannot_tell_the_two_apart` pins that so the reason for
    spreading the samples stays on the record. On *this* fixture all five separate the two
    (e.g. ``x=0.5``: 0.59375 halved, 0.6875 correct).
    """
    xs, ys = [0.0, 1.0, 2.0, 3.0, 4.0], [0.0, 1.0, 0.0, -1.0, 0.0]
    curve = interpolate(xs, ys, method="cubic", precision=1601)
    index = min(range(len(curve.x)), key=lambda i: abs(curve.x[i] - query))

    assert curve.x[index] == pytest.approx(query, abs=1e-9)
    assert curve.y[index] == pytest.approx(_natural_spline_reference(xs, ys, query), abs=1e-9)


def test_a_symmetric_midpoint_agrees_with_the_reference_for_the_wrong_reason() -> None:
    """The sample that proves nothing, kept as an executable fact about why the checks above
    spread out instead of picking one point.

    ``x=[0,1,2,3], y=[0,1,0,1]`` is symmetric about ``x=1.5``, and **both** splines answer
    ``0.5`` there -- measured on the defective implementation as well as this one. So this
    assertion passing is not evidence the curve is right; a reviewer who verified the fix at
    this one point would have seen agreement either way.

    It is deliberately the only assertion here. An earlier draft added an off-centre sample
    alongside it, which made the whole test fail under the original defect -- and a test that
    catches the bug cannot also be the record of a sample that does not. The catching is
    :func:`test_the_cubic_curve_matches_an_independent_solve_away_from_the_knots`'s job, which
    is why its ``query`` list has five entries and none of them is this one.

    The blindness is structural, not luck, and it has a boundary. With ``m0 = m3 = 0`` and
    uniform spacing the system forces ``m2 = -m1`` for *any* scaling of ``alpha`` -- the
    right-hand side is antisymmetric and the coefficient matrix is symmetric -- and ``x=1.5``
    is the midpoint of its segment, where ``(a^3-a)`` and ``(b^3-b)`` are equal. So the
    curvature term is ``-0.375*(m1 + m2) = 0`` whatever the coefficients are scaled by, which
    is exactly why every ``alpha`` and ``/6`` mutation is invisible here. Break the *symmetry*
    instead -- a mutation to the Thomas recurrence itself -- and ``m2 = -m1`` no longer holds,
    so this point does start failing. Blind to the scale of the coefficients, not to their
    structure.
    """
    xs, ys = [0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 0.0, 1.0]
    curve = interpolate(xs, ys, method="cubic", precision=1601)
    midpoint = min(range(len(curve.x)), key=lambda i: abs(curve.x[i] - 1.5))

    assert curve.x[midpoint] == pytest.approx(1.5, abs=1e-9), "the grid must land on the midpoint"
    assert curve.y[midpoint] == pytest.approx(0.5, abs=1e-9)
    assert curve.y[midpoint] == pytest.approx(_natural_spline_reference(xs, ys, 1.5), abs=1e-9)


def test_the_cubic_curve_has_a_continuous_first_derivative_at_its_knots() -> None:
    """The property that *defines* a cubic spline, and the one a knot check cannot see.

    Measured as the gap between the finite-difference slopes just either side of a knot. The
    fixture spans 3 units at ``precision=1601``, so the grid step is ``3/1600 = 0.001875`` and a
    smooth curve leaves a gap of ``0.022`` from the discretisation alone; the defect left
    ``1.011`` at the same spacing. The ``0.1`` threshold sits between them with roughly a factor
    of 4 below and 10 above -- it separates the two states, and is not a smoothness tolerance.
    """
    xs, ys = [0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 0.0, 1.0]
    curve = interpolate(xs, ys, method="cubic", precision=1601)

    for knot in xs[1:-1]:
        index = min(range(len(curve.x)), key=lambda i: abs(curve.x[i] - knot))
        left = (curve.y[index - 1] - curve.y[index - 2]) / (curve.x[index - 1] - curve.x[index - 2])
        right = (curve.y[index + 2] - curve.y[index + 1]) / (curve.x[index + 2] - curve.x[index + 1])
        assert abs(left - right) < 0.1, f"first derivative jumps by {abs(left - right):.4f} at knot x={knot}"


def test_the_cubic_spline_is_flat_at_its_ends() -> None:
    """The "natural" in natural cubic spline: zero second derivative at both endpoints. Pinned
    separately because it is the boundary condition the tridiagonal system is built around, and
    it held true even while the interior coefficients were halved."""
    assert _natural_cubic_spline_coeffs(X, Y)[0] == 0.0
    assert _natural_cubic_spline_coeffs(X, Y)[-1] == 0.0


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


@pytest.mark.parametrize("strategy", ["auto", "fd", "doane", "scott", "rice", "sturges", "sqrt"])
def test_every_strategy_numpy_accepted_is_still_accepted(strategy: str) -> None:
    """The list is the public surface. Delegating meant numpy decided it; now this module
    does, and dropping one turns a working call into a ``ValueError``.

    One *was* dropped, deliberately: numpy's ``stone`` does leave-one-out cross-validation over
    a range of candidate counts, which is a different order of work from the closed-form
    seven. It is a breaking change and the CHANGELOG says so; this test's job is to keep the
    remaining seven from following it by accident."""
    assert len(histogram_bins([float(index % 13) for index in range(200)], strategy)) > 1


def test_an_unknown_strategy_says_what_the_known_ones_are() -> None:
    """numpy used to answer this, with its own vocabulary. Now the message has to come from
    here, and a message that only says "no" leaves the caller to guess."""
    with pytest.raises(ValueError, match="doane, fd, rice, scott, sqrt, sturges") as raised:
        histogram_bins([1.0, 2.0, 3.0], "freedman")

    assert "freedman" in str(raised.value)


def test_a_constant_column_gets_one_bin_widened_around_its_value() -> None:
    """The case the two spans come apart on. The edges are widened by half a unit either side
    so the bar has somewhere to be drawn, but the *selectors* still see a span of zero -- feed
    them the widened span instead and a constant column comes back with five bins of nothing."""
    assert histogram_bins([3.5] * 10, "sturges") == [3.0, 4.0]
    assert histogram_bins([3.5], "auto") == [3.0, 4.0]


def test_the_last_edge_is_the_maximum_and_not_a_float_that_drifted_past_it() -> None:
    """Accumulating the step would leave the last edge slightly short of the data's maximum,
    and a value sitting exactly on that maximum would fall outside every bin."""
    values = [index * 0.1 for index in range(1000)]
    edges = histogram_bins(values, 7)

    assert edges[0] == min(values)
    assert edges[-1] == max(values)
    assert len(edges) == 8


def test_scotts_coefficient_is_the_exact_one_and_not_the_rounded_3_49() -> None:
    """``(24 * sqrt(pi)) ** (1/3)`` is 3.4908, and every textbook writes it as 3.49. The two
    differ by 0.024% and disagree about the bin *count* whenever the quotient lands near an
    integer -- ``range(224)`` gives six bins by the exact coefficient and seven by 3.49.

    Nothing else here notices: every other dataset in this file and in the numpy-parity sweep
    rounds the same way either way, so the rounded constant survives them all."""
    values = [float(index) for index in range(224)]

    assert len(histogram_bins(values, "scott")) - 1 == 6


def test_the_strategies_this_module_dropped_are_the_ones_it_meant_to() -> None:
    """A guard against silent narrowing. ``stone`` is absent on purpose; anything else going
    missing would be an accident, and the only way to notice is to compare against the list
    numpy actually offers."""
    numpy = pytest.importorskip("numpy", reason="install the numpy-parity extra to check this")
    from numpy.lib import _histograms_impl

    from svgplot.stats.binning import _STRATEGIES

    assert set(_histograms_impl._hist_bin_selectors) - set(_STRATEGIES) == {"stone"}
    assert set(_STRATEGIES) - set(_histograms_impl._hist_bin_selectors) == set()
    assert numpy is not None


# ---------------------------------------------------------------------------
# binning at the edges of the float grid (issue #116 review)
# ---------------------------------------------------------------------------


def test_a_span_too_wide_to_divide_returns_the_single_edge_numpy_returns() -> None:
    """``_bin_width`` saturates to infinity rather than raising, so the count comes out
    below one -- and ``linspace(low, high, 1)`` is one edge, which is as much as such data
    supports. Uncovered until a review measured it: the branch existed and nothing entered
    it."""
    assert histogram_bins([1e307 * (1 + index * 0.01) for index in range(30)], "scott") == [1e307]
    assert histogram_bins([-1e307, 1e307], "scott") == [-1e307]


def test_an_overflowing_mean_does_not_escape_as_an_overflow_error() -> None:
    """``histogram_bins`` documents ``ValueError`` and nothing else. ``doane`` recomputed the
    mean with a bare ``math.fsum`` and a column around ``1e307`` came back as an
    ``OverflowError`` from inside it -- 7.4% of near-float-max inputs."""
    edges = histogram_bins([1e307 * (1 + index * 0.01) for index in range(30)], "doane")

    assert len(edges) == 2
    assert all(math.isfinite(edge) for edge in edges)


@pytest.mark.parametrize("values", [[1e300] * 10, [float(2**53)]])
def test_a_value_too_large_to_widen_is_refused_rather_than_drawn_empty(values: list[float]) -> None:
    """Past ``2**53`` the half-unit widening a single distinct value gets is a no-op, so the
    two edges land on the same number and the bin between them can hold nothing. A chart with
    no bars is worse than a message saying why."""
    with pytest.raises(ValueError, match="too many bins for the data range"):
        histogram_bins(values, "fd")


def test_an_integer_column_gets_numpy_s_unit_width_floor() -> None:
    """numpy raises a sub-unit width to 1 for an integer dtype -- a histogram of counts has
    nothing to say between 0 and 1. Without it, 18% of integer-list inputs differed from
    numpy; ``[0,0,1,0,2,0,1,0,0,1]`` under ``fd`` came back with three bins, not two."""
    assert histogram_bins([0, 0, 1, 0, 2, 0, 1, 0, 0, 1], "fd") == [0.0, 1.0, 2.0]


def test_the_floor_is_keyed_on_the_type_not_the_value() -> None:
    """``[1.0, 2.0]`` is a float array to numpy and gets no floor, so testing
    ``value == int(value)`` would apply it where numpy does not."""
    assert histogram_bins([0.0, 0.0, 1.0, 0.0, 2.0, 0.0, 1.0, 0.0, 0.0, 1.0], "fd") != [0.0, 1.0, 2.0]


def test_two_integers_either_side_of_the_float_grid_are_refused_not_drawn_empty() -> None:
    """``2**53`` and ``2**53 + 1`` differ by exactly 1 as integers and collapse to one float.
    Measuring the span on the raw values left the selectors a real span to divide and the
    edges nothing to divide it into -- ``ceil(0 / width)`` bins, answered with a single edge:
    a chart with **no bars**, which the degenerate-edge check exists to refuse. numpy raises
    there and so does this."""
    for strategy in ("auto", "sturges", "rice", "sqrt", "fd", "scott", "doane"):
        with pytest.raises(ValueError, match="too many bins for the data range"):
            histogram_bins([2**53, 2**53 + 1], strategy)


def test_a_slightly_wider_integer_column_at_the_same_magnitude_still_bins() -> None:
    """The refusal above is about the float grid, not about the magnitude."""
    assert len(histogram_bins([2**53, 2**53 + 4], "auto")) == 3


def test_a_boolean_column_gets_the_integer_width_floor_too() -> None:
    """The one place this package's usual "a bool is not a number" rule does not apply: numpy
    casts a boolean array to ``uint8``, which its own ``issubdtype(..., integer)`` accepts, so
    the floor is applied there. Excluding it made 71% of boolean columns disagree."""
    assert histogram_bins([False, True], "fd") == [0.0, 1.0]
    assert histogram_bins([False, False, True, True, False], "sturges") == [0.0, 1.0]


def test_an_integer_too_large_for_a_float_is_refused_as_a_value_error() -> None:
    """``math.isfinite`` refuses to convert it and raises ``OverflowError``, which this
    function's ``Raises:`` does not mention -- the same contract ``_saturating`` keeps for the
    arithmetic further down."""
    with pytest.raises(ValueError, match="too large to be a float"):
        histogram_bins([10**400, 1, 2], "fd")


def test_histogram_bins_over_a_stated_range_ignores_the_values_extremes() -> None:
    """Two charts binned separately land their boundaries in different places, so a "count
    of 3" covers a different amount of data in each -- which is the comparison a shared axis
    promises and would otherwise not deliver."""
    edges = histogram_bins([1.0, 2.0, 3.0, 4.0], bins=4, bin_range=(1.0, 92.0))

    assert edges == [1.0, 23.75, 46.5, 69.25, 92.0]
    assert histogram_bins([1.0, 2.0, 3.0, 4.0], bins=4) == [1.0, 1.75, 2.5, 3.25, 4.0]


def test_two_samples_binned_over_one_range_get_identical_edges() -> None:
    """The property the range exists for, stated directly."""
    span = (0.0, 100.0)

    assert histogram_bins([1.0, 2.0], bins=5, bin_range=span) == histogram_bins([90.0, 99.0], bins=5, bin_range=span)


@pytest.mark.parametrize("bad", [(5.0, 5.0), (5.0, 1.0), (float("nan"), 1.0), (0.0, float("inf"))])
def test_histogram_bins_rejects_a_degenerate_or_non_finite_range(bad: tuple[float, float]) -> None:
    """numpy accepts a reversed range and returns edges that run backwards, which draws bars
    at negative widths rather than failing."""
    with pytest.raises(ValueError, match="bin_range must be an increasing pair"):
        histogram_bins([1.0, 2.0], bins=4, bin_range=bad)


def test_a_strategy_may_choose_more_bins_than_a_caller_is_allowed_to_ask_for() -> None:
    """Two ceilings, because two different things are being judged. A caller writing 15,885
    wants something a chart cannot show; ``fd`` handed a spiked column arrives at that number
    honestly, and a facet panel that did so renders on ``main``. Capping the strategy at
    ``MAX_BINS`` refused that panel, naming a number the caller never wrote."""
    spike = [n / 500.0 for n in range(500)] + [2000.0]

    chosen = len(histogram_bins(spike, "fd")) - 1

    assert chosen > MAX_BINS
    with pytest.raises(ValueError, match="bins must be between 1"):
        histogram_bins(spike, chosen)
