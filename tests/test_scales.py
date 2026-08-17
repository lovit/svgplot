"""Tests for svgplot.scales."""

from __future__ import annotations

import signal
from contextlib import contextmanager
from datetime import datetime, timedelta
from itertools import pairwise

import pytest

from svgplot.scales import CategoricalScale, LinearScale, TimeScale, make_ticks


@contextmanager
def _fail_if_slower_than(seconds: float):
    """Fail the test (instead of hanging forever) if the block doesn't finish in time."""

    def _on_alarm(signum: int, frame: object) -> None:
        raise AssertionError(f"took longer than {seconds}s — likely hung")

    previous_handler = signal.signal(signal.SIGALRM, _on_alarm)
    signal.alarm(int(seconds) or 1)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)


# ---------------------------------------------------------------------------
# LinearScale
# ---------------------------------------------------------------------------


def test_linear_scale_maps_domain_endpoints_to_range_endpoints() -> None:
    scale = LinearScale(domain=(0, 100), range_=(0, 200))

    assert scale(0) == 0
    assert scale(100) == 200


def test_linear_scale_maps_midpoint_proportionally() -> None:
    scale = LinearScale(domain=(0, 100), range_=(0, 200))

    assert scale(50) == 100


def test_linear_scale_handles_reversed_domain() -> None:
    scale = LinearScale(domain=(100, 0), range_=(0, 200))

    assert scale(100) == 0
    assert scale(0) == 200


def test_linear_scale_degenerate_domain_maps_to_range_midpoint() -> None:
    scale = LinearScale(domain=(5, 5), range_=(0, 200))

    assert scale(5) == 100
    assert scale(999) == 100  # any value, since the domain has no span


def test_linear_scale_handles_reversed_range() -> None:
    """Common for SVG y-axes, where pixel-y increases downward."""
    scale = LinearScale(domain=(0, 100), range_=(200, 0))

    assert scale(0) == 200
    assert scale(100) == 0
    assert scale(50) == 100


@pytest.mark.parametrize(
    ("domain", "range_", "value"),
    [
        ((float("nan"), 10), (0, 100), 5),
        ((0, float("inf")), (0, 100), 5),
        ((0, 100), (float("nan"), 200), 5),
        ((0, 100), (0, 200), float("nan")),
        ((0, 100), (0, 200), float("inf")),
    ],
)
def test_linear_scale_rejects_non_finite_domain_range_or_value(domain, range_, value) -> None:
    with pytest.raises(ValueError, match="finite"):
        scale = LinearScale(domain=domain, range_=range_)
        scale(value)


# ---------------------------------------------------------------------------
# CategoricalScale
# ---------------------------------------------------------------------------


def test_categorical_scale_places_categories_in_evenly_spaced_bands() -> None:
    scale = CategoricalScale(["a", "b", "c"], range_=(0, 300))

    assert scale.bandwidth == 100
    assert scale("a") == 0
    assert scale("b") == 100
    assert scale("c") == 200


def test_categorical_scale_center_is_band_midpoint() -> None:
    scale = CategoricalScale(["a", "b"], range_=(0, 200))

    assert scale.center("a") == 50
    assert scale.center("b") == 150


def test_categorical_scale_raises_for_unknown_category() -> None:
    scale = CategoricalScale(["a", "b"], range_=(0, 200))

    with pytest.raises(KeyError, match="unknown"):
        scale("unknown")


def test_categorical_scale_bandwidth_is_zero_for_empty_categories() -> None:
    scale = CategoricalScale([], range_=(0, 200))

    assert scale.bandwidth == 0.0


def test_categorical_scale_single_category_spans_full_range() -> None:
    scale = CategoricalScale(["only"], range_=(0, 200))

    assert scale.bandwidth == 200
    assert scale("only") == 0
    assert scale.center("only") == 100


def test_categorical_scale_adjacent_band_centers_are_exactly_bandwidth_apart() -> None:
    scale = CategoricalScale(["a", "b", "c", "d"], range_=(0, 400))

    centers = [scale.center(category) for category in scale.categories]

    assert [round(second - first, 10) for first, second in pairwise(centers)] == [scale.bandwidth] * 3


def test_categorical_scale_rejects_duplicate_categories() -> None:
    with pytest.raises(ValueError, match="unique"):
        CategoricalScale(["a", "b", "a"], range_=(0, 300))


# ---------------------------------------------------------------------------
# TimeScale
# ---------------------------------------------------------------------------


def test_time_scale_maps_domain_endpoints_to_range_endpoints() -> None:
    start = datetime(2020, 1, 1)
    end = datetime(2020, 1, 11)
    scale = TimeScale(domain=(start, end), range_=(0, 100))

    assert scale(start) == pytest.approx(0)
    assert scale(end) == pytest.approx(100)


def test_time_scale_maps_midpoint_proportionally() -> None:
    start = datetime(2020, 1, 1)
    end = datetime(2020, 1, 11)
    midpoint = datetime(2020, 1, 6)
    scale = TimeScale(domain=(start, end), range_=(0, 100))

    assert scale(midpoint) == pytest.approx(50, abs=1)


def test_time_scale_handles_reversed_domain() -> None:
    start = datetime(2020, 1, 1)
    end = datetime(2020, 1, 11)
    scale = TimeScale(domain=(end, start), range_=(0, 100))

    assert scale(end) == pytest.approx(0)
    assert scale(start) == pytest.approx(100)


# ---------------------------------------------------------------------------
# make_ticks
# ---------------------------------------------------------------------------


def test_make_ticks_linear_returns_values_within_domain() -> None:
    scale = LinearScale(domain=(0, 97), range_=(0, 500))

    ticks = make_ticks(scale, count=5)

    assert len(ticks) >= 3
    assert all(0 <= tick <= 97 for tick in ticks)
    assert ticks == sorted(ticks)


def test_make_ticks_linear_produces_round_numbers() -> None:
    scale = LinearScale(domain=(0, 100), range_=(0, 500))

    ticks = make_ticks(scale, count=5)

    assert ticks == [0, 20, 40, 60, 80, 100]


def test_make_ticks_linear_degenerate_domain_returns_single_tick() -> None:
    scale = LinearScale(domain=(5, 5), range_=(0, 500))

    assert make_ticks(scale) == [5]


def test_make_ticks_linear_reversed_domain_returns_ascending_ticks() -> None:
    scale = LinearScale(domain=(100, 0), range_=(0, 500))

    assert make_ticks(scale, count=5) == [0, 20, 40, 60, 80, 100]


def test_make_ticks_linear_negative_domain() -> None:
    scale = LinearScale(domain=(-50, 50), range_=(0, 500))

    ticks = make_ticks(scale, count=5)

    assert all(-50 <= tick <= 50 for tick in ticks)
    assert ticks == sorted(ticks)


@pytest.mark.parametrize("count", [0, -3, 1])
def test_make_ticks_handles_non_positive_or_minimal_count_without_crashing(count: int) -> None:
    scale = LinearScale(domain=(0, 100), range_=(0, 500))

    ticks = make_ticks(scale, count=count)

    assert len(ticks) >= 1
    assert all(0 <= tick <= 100 for tick in ticks)


def test_make_ticks_rejects_excessive_count() -> None:
    scale = LinearScale(domain=(0, 100), range_=(0, 500))

    with pytest.raises(ValueError, match="too large"):
        make_ticks(scale, count=10**9)


def test_make_ticks_never_hangs_on_microsecond_resolution_time_domain() -> None:
    """Regression: cumulative float addition previously stalled and never terminated here."""
    base = datetime(2023, 11, 14, 22, 13, 20)
    with _fail_if_slower_than(5):
        ticks = make_ticks(TimeScale((base, base + timedelta(microseconds=1)), (0, 100)), count=10)

    assert len(ticks) >= 1


@pytest.mark.parametrize(
    ("domain_min", "domain_max"),
    [
        (1e16, 1e16 + 2.0),
        (2**53, 2**53 + 2.0),
        (2**52, 2**52 + 1),
    ],
)
def test_make_ticks_never_hangs_on_large_close_float_domain(domain_min: float, domain_max: float) -> None:
    """Regression: a step smaller than the running value's float precision (ULP)
    previously made `value += step` a no-op, looping forever.
    """
    scale = LinearScale(domain=(domain_min, domain_max), range_=(0, 100))

    with _fail_if_slower_than(5):
        ticks = make_ticks(scale, count=5)

    assert len(ticks) >= 1


def test_make_ticks_tiny_magnitude_domain_produces_distinct_ticks() -> None:
    """Regression: rounding ticks to a fixed 10 decimal places collapsed all ticks to 0.0
    for a domain whose magnitude is far smaller than that.
    """
    scale = LinearScale(domain=(0, 1e-300), range_=(0, 500))

    ticks = make_ticks(scale, count=5)

    assert len(set(ticks)) > 1


def test_make_ticks_categorical_returns_all_categories_in_order() -> None:
    scale = CategoricalScale(["a", "b", "c"], range_=(0, 300))

    assert make_ticks(scale) == ["a", "b", "c"]


def test_make_ticks_time_returns_datetimes_within_domain_and_ascending() -> None:
    start = datetime(2020, 1, 1)
    end = datetime(2020, 1, 11)
    scale = TimeScale(domain=(start, end), range_=(0, 100))

    ticks = make_ticks(scale, count=5)

    assert len(ticks) >= 2
    assert all(isinstance(tick, datetime) for tick in ticks)
    assert all(start <= tick <= end for tick in ticks)
    assert ticks == sorted(ticks)


def test_make_ticks_raises_for_unsupported_scale_type() -> None:
    with pytest.raises(TypeError, match="unsupported scale type"):
        make_ticks(object())
