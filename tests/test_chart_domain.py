"""Tests for the domain value object charts record and callers union."""

from __future__ import annotations

import pytest

from svgplot.chart._domain import Domains, apply_limit, require_categories, union


def test_a_chart_with_no_axes_records_nothing() -> None:
    """``pieplot``/``treemap``/``gaugeplot`` report this, and ``facet`` reads it as "there is
    nothing to share" -- so the all-``None`` default has to stay all-``None``."""
    assert Domains() == Domains(x=None, y=None, x_step=None, categories=None, categories_axis="x")


def test_the_union_takes_the_outermost_bounds_of_each_axis() -> None:
    merged = union([Domains(x=(0.0, 10.0), y=(5.0, 6.0)), Domains(x=(-3.0, 4.0), y=(1.0, 2.0))])

    assert merged.x == (-3.0, 10.0)
    assert merged.y == (1.0, 6.0)


@pytest.mark.parametrize("axis", ["x", "y"])
def test_a_panel_that_recorded_nothing_does_not_drag_an_axis_to_zero(axis: str) -> None:
    """An empty panel in a facet grid records no domain. Treating that as ``(0, 0)`` would
    pull every shared axis down to include zero, which silently rescales the panels that did
    have data. Both axes: the y branch is separate code and was not covered."""
    merged = union([Domains(**{axis: (100.0, 200.0)}), Domains(), Domains(**{axis: (150.0, 250.0)})])

    assert getattr(merged, axis) == (100.0, 250.0)


def test_axes_are_unioned_independently() -> None:
    """A chart can have one axis and not the other -- ``barplot`` has ``y`` and categories
    but no numeric ``x``. Requiring both would drop the half that exists."""
    merged = union([Domains(y=(0.0, 1.0), categories=("a",)), Domains(x=(2.0, 3.0))])

    assert (merged.x, merged.y, merged.categories) == ((2.0, 3.0), (0.0, 1.0), ("a",))


def test_categories_union_as_a_set_in_first_seen_order() -> None:
    """Not min/max, and not sorted: two panels showing ``[a, b]`` and ``[b, c]`` share all
    three, and a reader's own ordering survives rather than being alphabetised."""
    merged = union([Domains(categories=("b", "a")), Domains(categories=("a", "c"))])

    assert merged.categories == ("b", "a", "c")


def test_the_union_of_nothing_is_refused() -> None:
    """An all-``None`` result would read as "this chart has no axes", which is a different
    claim from "nobody asked"."""
    with pytest.raises(ValueError, match="union of no domains"):
        union([])


# ---------------------------------------------------------------------------
# apply_limit
# ---------------------------------------------------------------------------


def test_no_override_keeps_what_the_chart_computed() -> None:
    assert apply_limit((1.0, 2.0), None) == (1.0, 2.0)


def test_an_override_replaces_rather_than_widens() -> None:
    """Widening would make a shared axis impossible to narrow: a caller asking for
    ``(0, 100)`` on data spanning 0..300 means to clip the view, not to be told 300."""
    assert apply_limit((0.0, 300.0), (0.0, 100.0)) == (0.0, 100.0)
    assert apply_limit((0.0, 300.0), (500.0, 900.0)) == (500.0, 900.0)


def test_integer_bounds_become_floats() -> None:
    """The scales downstream compare and divide these; a stray ``int`` would work until it
    met a ``Fraction`` or a numpy scalar."""
    assert apply_limit((0.0, 1.0), (0, 5)) == (0.0, 5.0)
    assert all(isinstance(bound, float) for bound in apply_limit((0.0, 1.0), (0, 5)))


@pytest.mark.parametrize("bad", [(3.0, 1.0), (1.0, 1.0), (0.0, -1.0)])
def test_a_reversed_or_degenerate_range_is_refused(bad: tuple[float, float]) -> None:
    """``LinearScale`` answers the midpoint of its range for a zero-width domain, so a
    degenerate pair draws a chart that looks rendered and shows one value everywhere."""
    with pytest.raises(ValueError, match="must be increasing"):
        apply_limit((0.0, 1.0), bad)


@pytest.mark.parametrize("bad", [(float("nan"), 1.0), (0.0, float("inf")), (True, 2.0), ("0", "1")])
def test_a_non_finite_or_non_real_bound_is_refused(bad: object) -> None:
    with pytest.raises(ValueError, match="must be finite numbers"):
        apply_limit((0.0, 1.0), bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["01", (1.0,), (1.0, 2.0, 3.0), 5.0, None.__class__])
def test_something_that_is_not_a_pair_is_refused(bad: object) -> None:
    """Strings are the trap: ``"01"`` has length 2 and unpacks, so a plain length check
    without a type check would accept it and hand ``"0"`` to a scale."""
    with pytest.raises(ValueError, match="must be a \\(low, high\\) pair|must be finite numbers"):
        apply_limit((0.0, 1.0), bad)  # type: ignore[arg-type]


def test_the_union_takes_the_narrowest_bin_width_not_the_largest_count() -> None:
    """A count means nothing away from the range it was chosen for.

    Two panels of three bars each, one over 1..3 and one over 100..102, both chose 3. Three
    bins across the shared 1..102 puts every value of each panel into one bar -- measured,
    3 bars per panel on ``main`` became 1. The width survives the change of range: 0.667
    across 1..102 is 151 divisions, and each panel still resolves its own three."""
    narrow = Domains(x=(1.0, 3.0), x_step=2.0 / 3)
    wide = Domains(x=(100.0, 102.0), x_step=2.0 / 1)

    assert union([narrow, wide]).x_step == pytest.approx(2.0 / 3)
    assert union([wide, narrow]).x_step == pytest.approx(2.0 / 3)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ((), "at least one"),
        ("ab", "single string"),
        ((1, 2), "sequence of names"),
        (5, "sequence of names"),
    ],
)
def test_a_categories_override_that_would_draw_nothing_says_so(value: object, message: str) -> None:
    """The same reasoning ``apply_limit`` uses to refuse a zero-width window: a chart that
    renders axes and a legend and no marks is worse than one that says why.

    ``"ab"`` is the case worth naming -- it reads as one category and unpacks into two, so
    without this it silently draws bars for ``a`` and ``b`` that the caller never asked for.
    A non-string member otherwise reaches the scale, which raises ``KeyError: "category not
    found in scale: '1'"`` about an internal lookup."""
    with pytest.raises(ValueError, match=message):
        require_categories(value)


def test_a_categories_override_naming_absent_categories_is_allowed() -> None:
    """Not an error, and this is the case the parameter exists for: a facet panel is handed
    every category any panel drew, and the ones it has no rows for are meant to leave a gap
    in the axis rather than shift its neighbours."""
    assert require_categories(("a", "z")) == ("a", "z")
