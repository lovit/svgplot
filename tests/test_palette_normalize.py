from __future__ import annotations

import pytest

from svgplot.palette.normalize import Normalize

# ---------------------------------------------------------------------------
# plain (single-slope) mapping
# ---------------------------------------------------------------------------


def test_maps_the_domain_endpoints_and_middle() -> None:
    normalize = Normalize(0, 10)

    assert normalize(0) == 0.0
    assert normalize(10) == 1.0
    assert normalize(5) == 0.5


@pytest.mark.parametrize(("value", "expected"), [(-5, 0.0), (-1e300, 0.0), (15, 1.0), (1e300, 1.0)])
def test_out_of_domain_values_saturate_instead_of_extrapolating(value: float, expected: float) -> None:
    """The fraction becomes a colormap level index, so a value past the domain must
    stop at the end color rather than index past the end of the color list. This is the
    behavior LinearScale deliberately does *not* have — it extrapolates, which is right
    for pixels and wrong for a bounded palette.
    """
    assert Normalize(0, 10)(value) == expected


def test_a_negative_domain_still_maps_left_to_right() -> None:
    normalize = Normalize(-10, -2)

    assert normalize(-10) == 0.0
    assert normalize(-6) == pytest.approx(0.5)
    assert normalize(-2) == 1.0


# ---------------------------------------------------------------------------
# two-slope (center=) mapping
# ---------------------------------------------------------------------------


def test_center_lands_on_the_midpoint_even_when_off_centre_in_the_domain() -> None:
    """The whole point of the two-slope mapping: a diverging colormap's neutral band sits
    on the value the data diverges around, not on the domain's arithmetic middle (which
    here would be 5, not 2).
    """
    normalize = Normalize(0, 10, center=2)

    assert normalize(2) == 0.5
    assert normalize(0) == 0.0
    assert normalize(10) == 1.0


def test_each_side_of_the_center_gets_its_own_slope() -> None:
    """Below the centre 2 units span half the output; above it 8 units do."""
    normalize = Normalize(0, 10, center=2)

    assert normalize(1) == pytest.approx(0.25)
    assert normalize(6) == pytest.approx(0.75)


def test_a_center_on_a_domain_edge_collapses_that_half_without_dividing_by_zero() -> None:
    at_low = Normalize(0, 10, center=0)
    at_high = Normalize(0, 10, center=10)

    assert at_low(0) == 0.5
    assert at_low(5) == pytest.approx(0.75)
    assert at_high(10) == 0.5
    assert at_high(5) == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# degenerate domain
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [5, 99, -99])
def test_a_zero_width_domain_answers_the_midpoint_for_every_value(value: float) -> None:
    """Mirrors LinearScale's range-midpoint answer for a zero-width domain rather than
    dividing by zero — every value really is equally "middle" here.
    """
    assert Normalize(5, 5)(value) == 0.5


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), "0", None, True])
def test_rejects_a_non_finite_or_non_real_vmin(bad: object) -> None:
    with pytest.raises(ValueError, match="vmin"):
        Normalize(bad, 10)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "10", None, True])
def test_rejects_a_non_finite_or_non_real_vmax(bad: object) -> None:
    with pytest.raises(ValueError, match="vmax"):
        Normalize(0, bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "5", True])
def test_rejects_a_non_finite_or_non_real_center(bad: object) -> None:
    with pytest.raises(ValueError, match="center"):
        Normalize(0, 10, center=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("center", [-1, 11])
def test_rejects_a_center_outside_the_domain(center: float) -> None:
    with pytest.raises(ValueError, match="center must lie within"):
        Normalize(0, 10, center=center)


def test_rejects_an_inverted_domain() -> None:
    """Unlike LinearScale (which allows inversion so a chart can flip SVG's y-axis), a
    0-1 colormap fraction has no "flip" meaning — reverse the color list instead. Allowing
    it would also make the center range check vacuous.
    """
    with pytest.raises(ValueError, match="vmin must not exceed vmax"):
        Normalize(10, 0)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "3", None])
def test_rejects_a_non_finite_value_at_call_time(bad: object) -> None:
    """A nan here would silently become a nan fraction and then a nonsense level index."""
    with pytest.raises(ValueError, match="value"):
        Normalize(0, 10)(bad)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# from_values
# ---------------------------------------------------------------------------


def test_from_values_spans_the_data_range() -> None:
    normalize = Normalize.from_values([3.0, 1.0, 7.0])

    assert (normalize.vmin, normalize.vmax) == (1.0, 7.0)
    assert normalize(1.0) == 0.0
    assert normalize(7.0) == 1.0


def test_from_values_forwards_the_center() -> None:
    normalize = Normalize.from_values([0.0, 10.0], center=2.0)

    assert normalize(2.0) == 0.5


def test_from_values_rejects_an_empty_list() -> None:
    with pytest.raises(ValueError, match="empty"):
        Normalize.from_values([])


def test_from_values_rejects_a_non_finite_entry() -> None:
    with pytest.raises(ValueError, match="value"):
        Normalize.from_values([1.0, float("nan")])


def test_from_values_rejects_a_center_outside_the_data_range() -> None:
    with pytest.raises(ValueError, match="center must lie within"):
        Normalize.from_values([1.0, 5.0], center=9.0)


# ---------------------------------------------------------------------------
# inverse
# ---------------------------------------------------------------------------


def test_inverse_names_the_value_a_position_came_from() -> None:
    normalize = Normalize(0, 10)

    assert normalize.inverse(0.0) == 0.0
    assert normalize.inverse(0.5) == 5.0
    assert normalize.inverse(1.0) == 10.0


def test_inverse_follows_both_slopes_of_a_centred_scale() -> None:
    """The whole reason this method exists. ``center=2`` squeezes [0, 2] into the lower
    half and stretches [2, 10] over the upper half, so a single-slope inverse -- ``vmin +
    position * (vmax - vmin)`` -- answers 5.0 at the midpoint where the truth is 2.0, and
    is wrong at every position except the two endpoints."""
    normalize = Normalize(0, 10, center=2)

    assert normalize.inverse(0.5) == 2.0
    assert normalize.inverse(0.25) == 1.0  # halfway up the short side, not 2.5
    assert normalize.inverse(0.75) == 6.0  # halfway up the long side, not 7.5
    assert (normalize.inverse(0.0), normalize.inverse(1.0)) == (0.0, 10.0)


@pytest.mark.parametrize("center", [None, 2.0, 8.0])
@pytest.mark.parametrize("value", [0.0, 1.5, 2.0, 4.0, 7.25, 10.0])
def test_inverse_round_trips_with_the_forward_mapping(center: float | None, value: float) -> None:
    normalize = Normalize(0, 10, center=center)

    assert normalize.inverse(normalize(value)) == pytest.approx(value)


def test_inverse_of_a_centred_edge_case_does_not_divide_by_zero() -> None:
    """``center == vmin`` collapses the lower half, so every position below 0.5 has the
    same answer rather than an undefined one."""
    normalize = Normalize(0, 10, center=0)

    assert normalize.inverse(0.0) == 0.0
    assert normalize.inverse(0.5) == 0.0
    assert normalize.inverse(1.0) == 10.0


@pytest.mark.parametrize("bad", [-0.01, 1.01, 2.0, -1.0])
def test_inverse_rejects_a_position_outside_the_unit_interval(bad: float) -> None:
    """Extrapolating would name a value the scale never shows, and the caller that asks
    for one is looking at an off-by-one level index."""
    with pytest.raises(ValueError, match="position must be in"):
        Normalize(0, 10).inverse(bad)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "0.5", None])
def test_inverse_rejects_a_non_finite_or_non_real_position(bad: object) -> None:
    with pytest.raises(ValueError, match="position"):
        Normalize(0, 10).inverse(bad)  # type: ignore[arg-type]
