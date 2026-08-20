"""``xscale=``/``yscale="log"`` — the scale three of the four benchmarked libraries have (#134).

The properties worth pinning are not "it draws": they are that decades land evenly, that a
narrow domain still gets an axis, and that a value a logarithm cannot place is refused by name
rather than masked or clipped into a different chart.
"""

from __future__ import annotations

import math
import random
import re
from itertools import pairwise

import pytest

import svgplot as sp
from svgplot.charts._layout import resolve_axis_scale, value_scale
from svgplot.scales import _MIN_TICKS, LinearScale, LogScale, make_ticks

DECADES = {"x": [1.0, 10.0, 100.0, 1000.0], "y": [1.0, 10.0, 100.0, 1000.0]}


def _tick_texts(svg: str) -> list[str]:
    return re.findall(r">([^<>]+)</text>", svg)


# --- the scale itself ------------------------------------------------------------------


def test_each_decade_takes_the_same_number_of_pixels() -> None:
    """What a log axis *is*. Anything else -- a linear axis of the logarithms' round numbers,
    say -- would still be monotonic and still be wrong."""
    scale = LogScale((1.0, 1000.0), (0.0, 300.0))

    assert [scale(value) for value in (1.0, 10.0, 100.0, 1000.0)] == [0.0, 100.0, 200.0, 300.0]


def test_a_single_point_domain_maps_to_the_middle() -> None:
    """The same answer ``LinearScale`` gives, for the same reason: there is no ratio to take,
    and putting the one value at an end would imply a direction the data does not have."""
    assert LogScale((5.0, 5.0), (0.0, 300.0))(5.0) == 150.0


@pytest.mark.parametrize("value", [0.0, -1.0, -1e300])
def test_a_value_a_logarithm_cannot_place_is_refused(value: float) -> None:
    """matplotlib offers ``nonpositive="mask"|"clip"``. This package refuses instead: masking
    drops rows the caller still counted and clipping invents a value they never had, and both
    draw a chart that is not the data."""
    with pytest.raises(ValueError, match="strictly positive"):
        LogScale((value, 100.0), (0.0, 300.0))


# --- the ticks -------------------------------------------------------------------------


def test_ticks_stand_on_powers_of_ten() -> None:
    """Not ``_nice_linear_ticks`` on the exponents, which would put one at 10**0.5 = 3.162..."""
    assert make_ticks(LogScale((1.0, 1000.0), (0.0, 300.0)), count=5) == [1.0, 10.0, 100.0, 1000.0]


def test_a_domain_inside_one_decade_still_gets_an_axis() -> None:
    """One power of ten is not an axis, and on 3..9 there is not even one of them inside the
    domain -- the ladder has to subdivide rather than report the single ``10`` next door."""
    ticks = make_ticks(LogScale((3.0, 9.0), (0.0, 300.0)), count=5)

    assert len(ticks) >= _MIN_TICKS
    assert all(3.0 <= tick <= 9.0 for tick in ticks)


def test_a_domain_too_narrow_for_round_mantissas_falls_back_to_the_linear_ladder() -> None:
    """2 to 3 offers exactly two round leading digits. Over a ratio that small the log axis is
    visually almost linear, so linear round numbers are both reachable and readable -- where
    subdividing the mantissas further would print 2.15443469."""
    ticks = make_ticks(LogScale((2.0, 3.0), (0.0, 300.0)), count=5)

    assert len(ticks) >= _MIN_TICKS
    assert ticks == [round(tick, 10) for tick in ticks], ticks


def test_the_tick_floor_holds_across_every_magnitude_and_ratio() -> None:
    """The count is a request everywhere in ``scales``; the floor is not. Swept because the
    two ladders hand off to each other and the seam is where a degenerate axis hid: a request
    of two over 1e-10..1.5e-10 came back with two until the fallback stepped instead of asking
    once."""
    rng = random.Random("log-ticks")
    lows = [10.0**exponent for exponent in range(-14, 15)] + [rng.uniform(1e-6, 1e6) for _ in range(60)]
    checked = 0
    for low in lows:
        for ratio in (1.0001, 1.001, 1.05, 1.5, 2.0, 3.0, 9.9, 10.0, 100.0, 1e3, 1e6, 1e12):
            high = low * ratio
            if not math.isfinite(high) or high <= low:
                continue
            for count in (2, 3, 5, 8, 12):
                scale = LogScale((low, high), (0.0, 400.0))
                ticks = make_ticks(scale, count=count)
                checked += 1
                assert len(ticks) >= _MIN_TICKS, (low, high, count, ticks)
                assert ticks == sorted(set(ticks)), (low, high, count, ticks)
                # A round tick may sit an ULP outside a domain built by multiplication.
                assert all(low * (1 - 1e-12) <= tick <= high * (1 + 1e-12) for tick in ticks)
                assert all(-1e-6 <= scale(tick) <= 400.0 + 1e-6 for tick in ticks)
    assert checked > 1000, "the sweep collapsed; it proves nothing at this size"


# --- the charts ------------------------------------------------------------------------


def test_linear_is_the_default_and_leaves_the_chart_alone() -> None:
    """The whole feature is opt-in, so a call that does not mention it must be unchanged."""
    assert (
        sp.lineplot(DECADES, x="x", y="y").to_string()
        == sp.lineplot(DECADES, x="x", y="y", xscale="linear", yscale="linear").to_string()
    )


@pytest.mark.parametrize("plot", [sp.lineplot, sp.scatterplot])
def test_a_log_axis_labels_its_decades(plot) -> None:
    ticks = _tick_texts(plot(DECADES, x="x", y="y", xscale="log", yscale="log").to_string())

    assert {"1", "10", "100", "1000"} <= set(ticks)


def test_an_area_chart_takes_a_log_x_axis_and_offers_no_log_y() -> None:
    """An area chart's filled region *is* the quantity, measured from zero -- which is why
    ``0.0`` is forced into its y domain. A log axis has no zero to measure from, so the fill
    would start somewhere arbitrary and stop being proportional to anything. Offering the
    argument would only let a caller ask for it and be told about their data instead."""
    assert _tick_texts(sp.areaplot(DECADES, x="x", y="y", xscale="log").to_string()).count("1") >= 1

    with pytest.raises(TypeError, match="yscale"):
        sp.areaplot(DECADES, x="x", y="y", yscale="log")


def test_a_log_axis_separates_values_a_linear_one_crushes_together() -> None:
    """Why the scale exists. Four values spanning six decades put three of them within a
    pixel of each other on a linear axis; on a log axis they are spread across the plot."""
    data = {"x": [1.0, 2.0, 3.0, 4.0], "y": [1.0, 100.0, 10000.0, 1000000.0]}

    def gaps(**kwargs: str) -> list[float]:
        svg = sp.lineplot(data, x="x", y="y", **kwargs).to_string()
        path = re.search(r'<path[^>]*\bd="([^"]*)"[^>]*class="[^"]*line-series', svg) or re.search(
            r'<path[^>]*class="[^"]*line-series[^"]*"[^>]*\bd="([^"]*)"', svg
        )
        assert path, "no line path found; the detector, not the chart, is what failed"
        ys = [float(pair.split(",")[1]) for pair in re.findall(r"-?[\d.]+,-?[\d.]+", path.group(1))]
        assert len(ys) == 4, ys
        return [round(abs(later - earlier), 2) for earlier, later in pairwise(ys)]

    linear, logarithmic = gaps(), gaps(yscale="log")

    assert min(linear) < 1.0, linear
    assert min(logarithmic) > 100.0, logarithmic


def test_a_non_positive_value_names_its_column() -> None:
    """The caller has to know *which* column to filter; by the time it reaches ``LogScale``
    the only thing left to report is the number."""
    with pytest.raises(ValueError, match="column 'sales' holds 0.0"):
        sp.lineplot({"t": [1.0, 2.0, 3.0], "sales": [0.0, 10.0, 100.0]}, x="t", y="sales", yscale="log")


def test_an_unknown_scale_name_lists_the_ones_that_exist() -> None:
    with pytest.raises(ValueError, match="yscale must be one of linear, log"):
        sp.lineplot(DECADES, x="x", y="y", yscale="logarithmic")


def test_the_helper_refuses_before_the_scale_does() -> None:
    """``value_scale`` checks the domain itself so the message can name the column. Without
    that, the same input still fails -- but from inside ``LogScale``, which has never heard of
    columns."""
    with pytest.raises(ValueError, match="column 'v'"):
        value_scale("log", (0.0, 10.0), (0.0, 100.0), column="v")
    assert isinstance(value_scale("linear", (0.0, 10.0), (0.0, 100.0), column="v"), LinearScale)
    assert resolve_axis_scale("log", parameter="yscale") == "log"


def test_a_value_outside_a_narrowed_domain_is_still_checked() -> None:
    """``ylim=`` and the data come apart: a limit can exclude a zero the chart still draws,
    and the scale is then asked to place it. Checking only the domain left that to ``LogScale``,
    which refuses correctly but from inside a class that has never heard of columns -- so the
    caller was told a number and left to find which column it came from."""
    data = {"t": [1.0, 2.0, 3.0], "sales": [0.0, 10.0, 100.0]}

    with pytest.raises(ValueError, match="column 'sales' holds 0.0"):
        sp.lineplot(data, x="t", y="sales", yscale="log", ylim=(1.0, 100.0))


def test_the_scale_itself_still_refuses_a_value_it_cannot_place() -> None:
    """The guard behind the guard. ``value_scale`` is the only caller that names columns, so
    ``LogScale`` has to hold the line for anyone constructing one directly."""
    scale = LogScale((1.0, 100.0), (0.0, 300.0))

    with pytest.raises(ValueError, match="strictly positive"):
        scale(0.0)


def test_ticks_inside_one_decade_are_round_leading_digits() -> None:
    """Not merely "at least three, all round": *which* round numbers. Between 1 and 10 the
    mantissa ladder gives 1, 3, 10 while a linear one gives 2, 4, 6, 8, 10 -- both are round
    and only one belongs on an axis whose spacing is logarithmic."""
    ticks = make_ticks(LogScale((1.0, 10.0), (0.0, 300.0)), count=5)

    assert ticks == [1.0, 3.0, 10.0]
    assert make_ticks(LogScale((1.0, 100.0), (0.0, 300.0)), count=5) == [1.0, 10.0, 100.0]
