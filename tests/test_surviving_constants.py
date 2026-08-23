"""Five constants and one predicate that thirty-odd mutations could not touch (#262).

A mutation sweep left six survivors. Three were caught by nothing at all; three were caught
only by ``test_gallery.py``'s byte comparison, which reports ``stale: ['boxplot.html',
'index.html']`` and says nothing about *what* moved -- so a reviewer who re-ran the build
instead of reading the diff would have committed the regression. (The sixth, ``_cubic``'s
``/6``, turned out to be a real defect and is fixed in #268; its guard lives in
``test_stats.py``.)

What the five have in common is that the value is a **threshold or a proportion**, and every
existing test used data comfortably on one side of it. Each check below is built the other way
round: pick the input where the current value and the mutated one give **different** answers,
and assert the arithmetic rather than a recorded string.
"""

from __future__ import annotations

import math
import re

import pytest

import svgplot as sp
from svgplot.charts._layout import DEFAULT_HEIGHT, DEFAULT_WIDTH, MARGIN_WITHOUT_LEGEND, plot_area
from svgplot.charts._polar import FULL_CIRCLE_TOLERANCE, _large_arc_flag
from svgplot.charts.box import _BOX_WIDTH_FRACTION
from svgplot.data.semantic import extract_channels
from svgplot.scales import LinearScale, _nice_step, make_ticks
from svgplot.stats.box import box_stats

# ---------------------------------------------------------------------------
# data/semantic.py -- the missing-channel filter, which was completely unguarded
# ---------------------------------------------------------------------------


def test_a_row_missing_any_one_channel_is_dropped() -> None:
    """``any`` versus ``all``, and the two are the same question until a row is *partly* missing.

    The module docstring says a row is dropped when **any** requested channel is missing, and
    the only test reading that used a single channel -- where ``any`` and ``all`` cannot differ.
    The multi-channel test used a fixture with no missing values at all. So flipping ``any`` to
    ``all`` left 4,007 tests green while rows with one good channel and one missing joined
    groups keyed on ``None``.

    The path is real: ``layout/facet.py`` calls ``extract_channels(data, col=col, row=row)``,
    so a faceted chart over a frame with holes is exactly this case.
    """
    data = {
        "지역": ["동", "동", None, "서"],
        "분기": ["1Q", None, "2Q", "2Q"],
        "값": [1.0, 2.0, 3.0, 4.0],
    }

    groups = extract_channels(data, hue="지역", col="분기")

    assert set(groups) == {("동", "1Q"), ("서", "2Q")}
    assert all(None not in key for key in groups), f"a key holds a missing value: {sorted(map(str, groups))}"


def test_a_row_missing_every_channel_is_dropped_too() -> None:
    """The other end of the same rule, so a predicate that dropped only *fully* missing rows --
    which is what ``all`` means -- cannot satisfy the check above by dropping nothing."""
    data = {"지역": ["동", None], "분기": ["1Q", None], "값": [1.0, 2.0]}

    assert set(extract_channels(data, hue="지역", col="분기")) == {("동", "1Q")}


@pytest.mark.parametrize("hole", ["지역", "분기", "행"])
def test_every_one_of_three_channels_can_be_the_missing_one(hole: str) -> None:
    """The filter reads *all* the key parts, not the first two.

    ``extract_channels`` takes ``hue``/``col``/``row`` and the two-channel check above leaves the
    third unexercised: a review measured that narrowing the predicate to ``key_parts[:2]`` --
    ignoring the third channel's missing values entirely -- passed all 4,304 tests. That is the
    same defect this file exists to close, hiding one channel further along.

    Parametrized over which channel holds the hole so no position is the covered one by accident.
    """
    data = {
        "지역": ["동", "동"],
        "분기": ["1Q", "1Q"],
        "행": ["위", "위"],
        "값": [1.0, 2.0],
    }
    data[hole] = [data[hole][0], None]

    groups = extract_channels(data, hue="지역", col="분기", row="행")

    assert len(groups) == 1, f"a row with a missing {hole} became its own group: {sorted(map(str, groups))}"
    assert all(None not in key for key in groups), f"a key holds a missing value: {sorted(map(str, groups))}"


def test_a_single_channel_still_drops_its_missing_rows() -> None:
    """Non-vacuity for both: the single-channel case is the one that was already covered, and it
    must keep working -- a filter that dropped every row would satisfy the two checks above."""
    groups = extract_channels({"지역": ["동", None, "서"], "값": [1.0, 2.0, 3.0]}, hue="지역")

    assert set(groups) == {"동", "서"}


# ---------------------------------------------------------------------------
# charts/_polar.py -- FULL_CIRCLE_TOLERANCE
# ---------------------------------------------------------------------------


def test_a_sweep_just_over_half_a_circle_is_a_large_arc() -> None:
    """The tolerance is a threshold, and no fixture sat near it.

    ``_large_arc_flag`` asks ``abs(sweep) > pi + FULL_CIRCLE_TOLERANCE``. At ``1e-9`` a sweep of
    ``pi + 2e-9`` is a large arc; widen the slack to ``1e-6`` -- the mutation that survived --
    and the same sweep becomes a small one, which draws the *short* way round and hands the
    reader a slice that is 359 degrees wrong.

    Both sides are asserted, because a tolerance that is too *narrow* is the failure its own
    docstring warns about: a mathematically-exact half circle landing a few ULP over would flip
    on float noise.
    """
    assert _large_arc_flag(math.pi + 2e-9) == 1, "a sweep past the tolerance must be a large arc"
    assert _large_arc_flag(math.pi + FULL_CIRCLE_TOLERANCE) == 0, "a sweep within the tolerance must not be"
    assert _large_arc_flag(math.pi - 2e-9) == 0


def test_the_tolerance_is_small_enough_to_be_slack_and_not_a_rule() -> None:
    """What the constant is *for*: absorbing accumulated float error, not reclassifying arcs.

    A degree is ``pi/180 ~ 0.0175`` radians. The slack has to be many orders of magnitude below
    that or it stops being noise-absorption and starts changing which arcs are drawn -- the
    ``1e-6`` mutation is a thousandfold step in that direction, and this states the direction
    rather than pinning the exact literal.
    """
    assert 0 < FULL_CIRCLE_TOLERANCE < math.radians(1) / 1_000_000


def test_a_half_circle_slice_draws_the_short_way_round() -> None:
    """The constant reaching a chart. Two equal slices make each exactly ``pi``, which is the
    sweep the tolerance exists to classify, and ``pieplot`` is one of the three charts sharing
    this module."""
    svg = sp.pieplot({"l": ["가", "나"], "v": [1.0, 1.0]}, labels="l", values="v").to_string()
    flags = re.findall(r"A [\d.]+,[\d.]+ 0 (\d) \d", svg)

    assert flags, "no arc commands in the pie"
    assert set(flags) == {"0"}, f"an exact half-circle slice took the long way round: {flags}"


# ---------------------------------------------------------------------------
# scales.py -- _nice_step's 1/2/5 branch points
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rough", "expected"),
    [
        (1.49, 1.0),  # just below the 1 -> 2 branch
        (1.5, 2.0),  # exactly on it
        (1.4, 1.0),  # the mutated boundary: 1.4 must still round *down*
        (2.99, 2.0),
        (3.0, 5.0),
        (6.99, 5.0),
        (7.0, 10.0),
    ],
)
def test_the_tick_step_branches_where_the_d3_rule_says(rough: float, expected: float) -> None:
    """d3's 1/2/5 ladder, pinned at each branch point rather than in the middle of a band.

    Every existing test used a domain whose residual sat comfortably inside a band, so moving
    the first branch from ``1.5`` to ``1.4`` changed no test's answer. ``1.4`` is in the list
    for exactly that reason: it is the value the mutation moves the boundary *to*, so it
    separates the two.
    """
    assert _nice_step(rough) == pytest.approx(expected)


def test_the_tick_step_scales_with_the_magnitude() -> None:
    """The branch points are on the *residual*, so the same ladder has to appear at every power
    of ten -- a check pinned only at magnitude 1 would pass for an implementation that ignored
    ``magnitude`` entirely."""
    assert _nice_step(14.9) == pytest.approx(10.0)
    assert _nice_step(15.0) == pytest.approx(20.0)
    assert _nice_step(149.0) == pytest.approx(100.0)
    assert _nice_step(150.0) == pytest.approx(200.0)


@pytest.mark.parametrize(
    ("rough", "step", "mathematically"),
    [
        (0.15, 0.1, 0.2),  # residual 1.4999999999999998, should be 1.5 -> 2
        (0.3, 0.2, 0.5),  # residual 2.9999999999999996, should be 3 -> 5
        (0.7, 0.5, 1.0),  # residual 6.999999999999999,  should be 7 -> 10
    ],
)
def test_the_residual_is_off_by_an_ulp_at_magnitude_a_tenth(rough: float, step: float, mathematically: float) -> None:
    """Current behaviour, pinned as a **defect** rather than as a rule (#273).

    ``rough / magnitude`` is not exact in binary floating point, so a value sitting
    mathematically *on* a branch point can fall below it: ``0.7 / 0.1`` is
    ``6.999999999999999``, which takes the ``< 7`` branch and yields ``nice=5`` where the
    arithmetic says 10. The visible consequence is that the same data at a different unit gets a
    different axis -- ``(0, 3.5)`` draws 8 ticks and ``(0, 35)`` draws 4.

    An earlier version of this test called that "nothing to fix", generalising from the single
    ``0.15`` sample to "a decimal literal below 1 is not exactly a tenth". A review swept it and
    the generalisation is false in both directions: ``0.015`` divides exactly, and ``0.07``
    errs *upward* (``7.000000000000001``). It is specific to ``magnitude == 0.1`` and its
    direction varies by branch -- which is what makes it a bug rather than a property.

    Kept as a pin, not deleted, so #273 has a test that fails the moment it is fixed. The third
    column records what the answer *should* be.
    """
    assert _nice_step(rough) == pytest.approx(step), "current (defective) behaviour changed -- see #273"
    assert step != mathematically, "this sample no longer separates the defect from the correct answer"


def test_the_same_shape_of_data_gets_a_different_axis_at_a_different_unit() -> None:
    """The user-visible half of #273, so the defect is recorded as an outcome and not only as an
    arithmetic curiosity. Delete this with the fix, not before."""
    ticks_per_domain = {
        top: len(make_ticks(LinearScale((0.0, top), (0.0, 100.0)), count=5)) for top in (0.35, 3.5, 35.0, 350.0)
    }

    assert ticks_per_domain[0.35] == ticks_per_domain[3.5]
    assert ticks_per_domain[35.0] == ticks_per_domain[350.0]
    assert ticks_per_domain[3.5] != ticks_per_domain[35.0], "unit-invariance restored -- #273 is fixed, drop this test"


# ---------------------------------------------------------------------------
# stats/box.py -- the 1.5 in 1.5 x IQR
# ---------------------------------------------------------------------------


def test_the_tukey_fence_is_one_and_a_half_iqrs() -> None:
    """Tukey's constant, pinned by a value that lands *between* the two candidate fences.

    ``q1=30, q3=70`` gives ``IQR=40``, so the upper fence is ``70 + 1.5*40 = 130`` at the real
    constant and ``70 + 1.0*40 = 110`` at the mutated one. ``120`` therefore sits inside the
    whiskers under the correct rule and becomes an outlier under the mutation -- the two answers
    differ in *which list the value is in*, not by a few pixels.

    Only the gallery's byte comparison caught this before, and its failure message names the
    stale page rather than the statistic.
    """
    values = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 120.0]

    stats = box_stats(values, mode="1.5IQR")

    assert (stats.q1, stats.q3) == pytest.approx((30.0, 70.0))
    assert stats.outliers == [], "120 is inside a 1.5xIQR fence of 130 and must not be an outlier"
    assert stats.whisker_high == pytest.approx(120.0)


def test_a_value_past_the_fence_is_still_an_outlier() -> None:
    """The other side, so the check above cannot be satisfied by a rule that never flags
    anything -- which is what a very large multiplier would give."""
    values = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 200.0]

    stats = box_stats(values, mode="1.5IQR")

    assert stats.outliers == [200.0]
    assert stats.whisker_high == pytest.approx(80.0)


def test_the_fence_is_not_wider_than_one_and_a_half_iqrs_either() -> None:
    """The multiplier is bounded from *both* sides, and the second side needed its own sample.

    ``120`` above separates 1.5 from 1.0; it cannot separate 1.5 from anything *larger*, because
    a value inside the real fence is inside a wider one too. Measured -- with only ``120`` and
    ``200`` in the file, raising the constant to ``3.0`` survived.
    """
    values = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 150.0]

    stats = box_stats(values, mode="1.5IQR")

    assert stats.outliers == [150.0], "150 is past a 1.5xIQR fence of 130 and must be an outlier"
    assert stats.whisker_high == pytest.approx(80.0)


def test_the_fence_multiplier_is_pinned_close_enough_to_exclude_a_plausible_typo() -> None:
    """Both sides again, and much nearer the value -- because "bounded" is not the same as
    "bounded usefully".

    ``120`` and ``150`` bound the multiplier to ``[1.25, 2.0)``: a review measured that ``1.4``
    and ``1.6`` both survive, which are exactly the shapes a typo takes. These two samples sit
    one IQR-tenth either side of the real fence at ``130``:

    * ``127`` is inside at 1.5 (fence 130) and an outlier at 1.4 (fence 126)
    * ``132`` is an outlier at 1.5 and inside at 1.6 (fence 134)

    Together they admit only ``[1.425, 1.55)``.
    """
    inside = box_stats([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 127.0], mode="1.5IQR")
    outside = box_stats([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 132.0], mode="1.5IQR")

    assert inside.outliers == [], "127 is inside a fence of 130 -- the multiplier is below 1.425"
    assert outside.outliers == [132.0], "132 is past a fence of 130 -- the multiplier is 1.55 or more"


# ---------------------------------------------------------------------------
# charts/box.py -- _BOX_WIDTH_FRACTION
# ---------------------------------------------------------------------------


def test_a_box_is_six_tenths_of_its_category_band() -> None:
    """The proportion, read back off the drawn rectangle and divided by the band it sits in.

    Not an expectation of ``210`` -- a recorded pixel width would also change when the margins
    or the canvas default move, so it would fail for reasons that are not this constant. The
    ratio is the thing the constant *is*.
    """
    data = {"구간": ["가", "가", "가", "나", "나", "나"], "값": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]}
    svg = sp.boxplot(data, x="구간", y="값").to_string()
    widths = [float(width) for width in re.findall(r'<rect[^>]*width="([\d.]+)"[^>]*class="series-1-marker"', svg)]
    if not widths:  # attribute order is not guaranteed; fall back to any marker rect
        widths = [
            float(re.search(r'width="([\d.]+)"', rect)[1])  # type: ignore[index]
            for rect in re.findall(r"<rect[^>]*-marker[^>]*>", svg)
        ]

    area = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=MARGIN_WITHOUT_LEGEND)
    band = (area.right - area.left) / 2  # two categories share the plot width

    assert widths, "boxplot drew no box"
    # ``0.6`` written out, **not** ``_BOX_WIDTH_FRACTION``. Comparing the drawing to the constant
    # it was drawn from is comparing the constant to itself: changing it to 0.5 moves both sides
    # and the check stays green. Measured -- that version survived the mutation this file exists
    # to catch.
    assert all(
        width / band == pytest.approx(0.6) for width in widths
    ), f"boxes are {[w / band for w in widths]} of their band, not 0.6"
    assert pytest.approx(0.6) == _BOX_WIDTH_FRACTION, "the constant and the drawing must agree on the same literal"


def test_the_box_fraction_leaves_a_gap_between_neighbouring_categories() -> None:
    """What the constant is *for*, stated so the number is not arbitrary: a box that filled its
    band would touch its neighbour and the two would read as one shape. Pinned as a range rather
    than a literal, so a deliberate 0.55 or 0.65 is a decision to make rather than a test to
    edit -- while 1.0 and 0.2 both fail."""
    assert 0.4 < _BOX_WIDTH_FRACTION < 0.8
