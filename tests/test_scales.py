"""Tests for svgplot.scales."""

from __future__ import annotations

from datetime import datetime

import pytest

from svgplot.scales import CategoricalScale, LinearScale, TimeScale, make_ticks

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
