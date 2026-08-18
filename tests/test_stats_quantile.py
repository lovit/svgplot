from __future__ import annotations

import importlib

import pytest

from svgplot.stats import quantile, quantiles
from svgplot.stats.box import box_stats

# `from svgplot.stats import quantile` binds the re-exported *function*, which shadows
# the submodule of the same name (as `interpolate` already does), so monkeypatching the
# module's globals needs an explicit module lookup rather than an attribute access.
_quantile_module = importlib.import_module("svgplot.stats.quantile")

# ---------------------------------------------------------------------------
# core behavior
# ---------------------------------------------------------------------------


def test_quantile_sorts_unsorted_input_itself() -> None:
    """Callers pass raw column data, which is in whatever order the source had."""
    assert quantile([5.0, 1.0, 3.0, 2.0, 4.0], 0.5) == 3.0


def test_quantile_endpoints_return_the_extremes() -> None:
    values = [4.0, 1.0, 9.0, 2.0]
    assert quantile(values, 0.0) == 1.0
    assert quantile(values, 1.0) == 9.0


def test_quantile_interpolates_between_neighbours() -> None:
    """Hand-checked: n=5, rank = 0.25*(5-1) = 1.0, which lands exactly on index 1."""
    assert quantile([1.0, 2.0, 3.0, 4.0, 5.0], 0.25) == 2.0
    # rank = 0.4*(5-1) = 1.6 -> 2.0*0.4 + 3.0*0.6
    assert quantile([1.0, 2.0, 3.0, 4.0, 5.0], 0.4) == pytest.approx(2.6)


def test_quantile_of_a_single_value_is_that_value() -> None:
    for q in (0.0, 0.25, 0.5, 1.0):
        assert quantile([7.5], q) == 7.5


def test_quantiles_matches_repeated_single_calls() -> None:
    values = [3.0, 1.0, 4.0, 1.0, 5.0, 9.0, 2.0, 6.0]
    probabilities = (0.0, 0.25, 0.5, 0.75, 1.0)

    assert quantiles(values, probabilities) == [quantile(values, q) for q in probabilities]


def test_quantiles_sorts_the_values_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """The sort dominates the cost, so K probabilities must not pay for it K times.
    Asserted structurally by counting sort calls rather than by timing.
    """
    calls = 0
    real_sorted = sorted

    def counting_sorted(iterable, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return real_sorted(iterable, **kwargs)

    monkeypatch.setattr(_quantile_module, "sorted", counting_sorted, raising=False)

    quantiles([5.0, 1.0, 3.0, 2.0], (0.1, 0.25, 0.5, 0.75, 0.9))

    assert calls == 1


# ---------------------------------------------------------------------------
# the overflow property the weighted form exists for
# ---------------------------------------------------------------------------


def test_quantile_survives_a_span_that_overflows_the_difference_form() -> None:
    """Regression for issue #34's fix, now carried into this module: `lo + f*(up-lo)`
    forms up-lo, which overflows to inf on this span even though the answer
    (-5e307) is perfectly representable. The weighted form never builds a value
    larger than its own endpoints.
    """
    result = quantile([-1e308, 1e308], 0.25)

    assert result == pytest.approx(-5e307)
    assert result == -1e308 * 0.75 + 1e308 * 0.25


def test_quantile_is_exact_at_both_interpolation_endpoints() -> None:
    """The comment claims the weighted form is exact at f=0 *and* f=1, where the
    difference form is only exact at f=0 — pin both ends.
    """
    values = [0.1, 0.7]
    assert quantile(values, 0.0) == 0.1
    assert quantile(values, 1.0) == 0.7


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_q", [-0.1, 1.1, 2.0, -1.0])
def test_quantile_rejects_a_probability_outside_the_unit_interval(bad_q: float) -> None:
    with pytest.raises(ValueError, match=r"in \[0, 1\]"):
        quantile([1.0, 2.0], bad_q)


@pytest.mark.parametrize("bad_q", [float("nan"), float("inf"), float("-inf")])
def test_quantile_rejects_a_non_finite_probability(bad_q: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        quantile([1.0, 2.0], bad_q)


def test_quantile_rejects_a_non_numeric_probability() -> None:
    with pytest.raises(ValueError, match="must be a number"):
        quantile([1.0, 2.0], "0.5")  # type: ignore[arg-type]


def test_quantile_rejects_empty_values() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        quantile([], 0.5)


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_quantile_rejects_a_non_finite_value(bad_value: float) -> None:
    with pytest.raises(ValueError, match="non-finite"):
        quantile([1.0, bad_value, 3.0], 0.5)


def test_quantile_rejects_a_non_numeric_value() -> None:
    with pytest.raises(ValueError, match="must be numbers"):
        quantile([1.0, "two", 3.0], 0.5)  # type: ignore[list-item]


def test_quantiles_validates_every_probability_not_just_the_first() -> None:
    with pytest.raises(ValueError, match=r"in \[0, 1\]"):
        quantiles([1.0, 2.0], (0.5, 0.75, 5.0))


def test_quantiles_rejects_empty_values() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        quantiles([], (0.5,))


# ---------------------------------------------------------------------------
# box_stats still agrees, now that it delegates here
# ---------------------------------------------------------------------------


def test_box_stats_quartiles_match_this_module() -> None:
    """box_stats no longer owns a percentile implementation — it must produce
    exactly what this module does for the same data.
    """
    values = [3.0, 1.0, 4.0, 1.0, 5.0, 9.0, 2.0, 6.0]

    stats = box_stats(values, mode="1.5IQR")

    assert stats.q1 == quantile(values, 0.25)
    assert stats.q3 == quantile(values, 0.75)
