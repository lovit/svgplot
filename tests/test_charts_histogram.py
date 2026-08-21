from __future__ import annotations

import math
import random
import re

import pytest

from _svg_probe import tags
from svgplot.charts.histogram import histplot

SINGLE_SERIES = {"value": [1.0, 2.0, 2.0, 3.0, 4.0, 5.0, 5.0, 5.0, 6.0, 7.0]}
HUE_SERIES = {
    "value": [1.0, 2.0, 2.0, 3.0, 4.0, 1.5, 2.5, 3.5, 4.5, 5.5],
    "group": ["a", "a", "a", "a", "a", "b", "b", "b", "b", "b"],
}


def _series_bars(svg: str, series_class: str) -> list[dict[str, float]]:
    """Return the data bars drawn for ``series_class`` as ``{x, y, width, height}``, sorted by x.

    Legend swatches carry the same CSS class as the bars they label, so they're
    filtered out here: a data bar always grows up from the shared baseline, while
    a swatch sits well above it.

    Through ``_svg_probe`` rather than a ``/>``-only pattern of its own, for the reason that
    module was written: a bar with a ``<title>`` is no longer ``<rect …/>``, and the old
    pattern stopped seeing it. Here that was loud rather than silent -- flipping ``tooltip=``
    to ``True`` by default took all four tests that call this to failure and none of the other
    twenty-four -- but the failure would have been "no bars were drawn", which is not what
    happened.
    """
    matching = [{key: float(rect[key]) for key in ("x", "y", "width", "height")} for rect in tags(svg, "rect", series_class)]
    if not matching:
        return []
    baseline = max(rect["y"] + rect["height"] for rect in matching)
    bars = [rect for rect in matching if math.isclose(rect["y"] + rect["height"], baseline)]
    return sorted(bars, key=lambda rect: rect["x"])


# ---------------------------------------------------------------------------
# single series
# ---------------------------------------------------------------------------


def test_histplot_renders_with_auto_binning() -> None:
    chart = histplot(SINGLE_SERIES, x="value")
    svg = chart.to_string()
    assert "<rect" in svg
    assert "series-1" in svg


def test_histplot_draws_no_legend_without_hue() -> None:
    chart = histplot(SINGLE_SERIES, x="value")
    svg = chart.to_string()
    assert 'class="legend-text"' not in svg


def test_histplot_accepts_explicit_integer_bins() -> None:
    # 6 values spanning [0, 9.9] with bins=5 -> exactly 5 bins, one point each
    # -> exactly 5 non-empty <rect> data bars for the series (plus the unrelated
    # plot-background rect, hence the +1).
    data = {"value": [0.0, 2.0, 4.0, 6.0, 8.0, 9.9]}
    chart = histplot(data, x="value", bins=5)
    svg = chart.to_string()
    assert svg.count("<rect") == 6  # plot-background + up to 5 non-empty bins


def test_histplot_counts_values_correctly_for_a_hand_checkable_dataset() -> None:
    """bins=2 over [0, 10] -> edges [0, 5, 10]; 3 values in [0, 5), 2 in [5, 10].

    Bar height is proportional to its count, so the two bars' heights must be in
    a 3:2 ratio — counting the bars alone would still pass on a 4/1 miscount.
    """
    data = {"value": [0.0, 1.0, 4.9, 5.0, 10.0]}
    chart = histplot(data, x="value", bins=2)
    bars = _series_bars(chart.to_string(), "series-1")

    assert len(bars) == 2
    assert bars[0]["height"] / bars[1]["height"] == pytest.approx(3 / 2)


def test_histplot_renders_a_single_full_width_bar_for_identical_values() -> None:
    """A zero-width value range still has to produce a drawable bar rather than
    collapsing to nothing or dividing by zero on the degenerate x domain.
    """
    bars = _series_bars(histplot({"value": [3.0, 3.0, 3.0]}, x="value").to_string(), "series-1")

    assert len(bars) == 1
    assert bars[0]["width"] == pytest.approx(700.0)  # the full plot-area span


def test_histplot_last_bin_is_inclusive_of_the_maximum_value() -> None:
    """The maximum value must land in the last bin, not be silently dropped —
    classic off-by-one in binning: edges[i] <= value < edges[i+1] except the
    final bin, which must include its right edge too. With bins=2 over [0, 10],
    edges = [0, 5, 10]; several points sit exactly at the last edge (10.0) and
    must all count into the final bin rather than vanish.
    """
    data = {"value": [0.0, 10.0, 10.0, 10.0]}
    chart = histplot(data, x="value", bins=2)
    svg = chart.to_string()
    # 2 non-empty bins -> plot-background + 2 data bars.
    assert svg.count("<rect") == 3
    assert svg.count('class="series-1"') == 2


# ---------------------------------------------------------------------------
# hue= grouped histograms
# ---------------------------------------------------------------------------


def test_histplot_draws_one_series_per_hue_value_sharing_bin_edges() -> None:
    chart = histplot(HUE_SERIES, x="value", hue="group", bins=4)
    svg = chart.to_string()
    assert "series-1" in svg
    assert "series-2" in svg


def test_histplot_generates_a_legend_entry_per_hue_value() -> None:
    chart = histplot(HUE_SERIES, x="value", hue="group")
    svg = chart.to_string()
    assert svg.count('class="legend-text"') == 2
    assert ">a<" in svg
    assert ">b<" in svg


def test_histplot_hue_groups_share_identical_bin_edges() -> None:
    """Bin edges are computed once across all groups' *combined* values, not per group.

    Group "a" spans [1.0, 4.0] and group "b" spans [1.5, 5.5]; the combined range
    is [1.0, 5.5], which over 4 bins maps onto the plot area's x span [60, 640] as
    145px-wide bins starting at x = 60/205/350/495. Every bar from either group
    must land on one of those shared slots — if edges were computed per group,
    "a" would stretch its own narrower range across the full axis and its bars
    would sit at different x positions with a different width.
    """
    chart = histplot(HUE_SERIES, x="value", hue="group", bins=4)
    svg = chart.to_string()
    first = _series_bars(svg, "series-1")
    second = _series_bars(svg, "series-2")
    shared_slots = [60.0, 205.0, 350.0, 495.0]

    assert first and second
    for bar in first + second:
        assert any(bar["x"] == pytest.approx(slot) for slot in shared_slots)
        assert bar["width"] == pytest.approx(145.0)
    # The bins both groups occupy must be pixel-identical, which only holds when
    # the two histograms were binned against one shared set of edges.
    common = {bar["x"] for bar in first} & {bar["x"] for bar in second}
    assert len(common) >= 2


def test_histplot_counts_each_hue_group_against_the_shared_edges() -> None:
    """Positions alone don't prove the *counts* used the shared edges — a build that
    positioned bars on shared edges while counting against per-group ones would still
    place every bar correctly. Bar height is proportional to count, so pin the counts.

    Shared edges over [1.0, 5.5] are [1.0, 2.125, 3.25, 4.375, 5.5]:
    group "a" (1, 2, 2, 3, 4) -> 3, 1, 1, 0 and group "b" (1.5, 2.5, 3.5, 4.5, 5.5) -> 1, 1, 1, 2.
    """
    chart = histplot(HUE_SERIES, x="value", hue="group", bins=4)
    svg = chart.to_string()
    first = _series_bars(svg, "series-1")
    second = _series_bars(svg, "series-2")
    # The tallest bar is the largest count (3), so one count's worth of height is a third of it.
    unit = max(bar["height"] for bar in first + second) / 3

    assert [round(bar["height"] / unit) for bar in first] == [3, 1, 1]  # zero-count bins draw no bar
    assert [round(bar["height"] / unit) for bar in second] == [1, 1, 1, 2]


# ---------------------------------------------------------------------------
# theme / styling
# ---------------------------------------------------------------------------


def test_histplot_applies_corner_radius_from_theme() -> None:
    from svgplot.theme.base import Theme

    chart = histplot(SINGLE_SERIES, x="value", theme=Theme(corner_radius=3.0))
    svg = chart.to_string()
    assert 'rx="3"' in svg


def test_histplot_uses_fill_mark_style_not_stroke() -> None:
    chart = histplot(HUE_SERIES, x="value", hue="group")
    rule = re.search(r"\.series-1 \{([^}]*)\}", chart.to_string())
    assert rule is not None
    assert "fill: none" not in rule.group(1)


# ---------------------------------------------------------------------------
# error paths
# ---------------------------------------------------------------------------


def test_histplot_drops_rows_with_missing_x() -> None:
    data = {"value": [1.0, None, 3.0, float("nan"), 5.0]}
    chart = histplot(data, x="value")
    assert "<rect" in chart.to_string()


def test_histplot_rejects_empty_data() -> None:
    with pytest.raises(ValueError, match="at least one row"):
        histplot({"value": []}, x="value")


def test_histplot_rejects_all_missing_values() -> None:
    with pytest.raises(ValueError, match="non-missing"):
        histplot({"value": [None, None]}, x="value")


def test_histplot_rejects_unknown_column() -> None:
    with pytest.raises(KeyError):
        histplot(SINGLE_SERIES, x="nope")


def test_histplot_rejects_unknown_hue_column() -> None:
    with pytest.raises(KeyError, match="hue column not found"):
        histplot(HUE_SERIES, x="value", hue="nope")


def test_histplot_rejects_unknown_theme_preset() -> None:
    with pytest.raises(KeyError, match="unknown theme preset"):
        histplot(SINGLE_SERIES, x="value", theme="not-a-preset")


def test_histplot_propagates_invalid_bins_error() -> None:
    with pytest.raises(ValueError, match="bins"):
        histplot(SINGLE_SERIES, x="value", bins=10**8)


@pytest.mark.parametrize(
    ("bad", "message"),
    [
        ("ab", "must be a \\(low, high\\) pair"),
        ((1, 2, 3), "must be a \\(low, high\\) pair"),
        ([1], "must be a \\(low, high\\) pair"),
        ((None, 5), "must be finite numbers"),
        ((float("nan"), 5), "must be finite numbers"),
        ((float("-inf"), 5), "must be finite numbers"),
        ((5.0, 5.0), "must be increasing"),
        ((2, 1), "must be increasing"),
    ],
)
def test_an_unusable_xlim_gets_the_same_message_every_other_chart_gives(bad: object, message: str) -> None:
    """``histplot`` reaches ``histogram_bins`` before ``apply_limit`` would normally run, so
    without routing ``xlim`` through the validator first this argument diverges from the ten
    other charts that take one: ``"ab"`` raises ``TypeError: must be real number, not str``,
    ``(1,2,3)`` raises ``ValueError: too many values to unpack``. Both are about an internal
    call rather than about the argument the caller wrote, and neither is documented.

    Nothing pinned this. The fix was in place and deleting it left the whole suite green."""
    with pytest.raises(ValueError, match=message):
        histplot({"v": [1.0, 2.0, 3.0]}, x="v", xlim=bad)  # type: ignore[arg-type]


def test_an_xlim_clips_the_bins_to_the_window_the_caller_asked_for() -> None:
    """The other half: a valid ``xlim`` has to actually reach the binning, or the validation
    above would be the only thing it did."""
    edges = histplot({"v": [1.0, 5.0, 9.0]}, x="v", xlim=(0.0, 10.0), bins=5).domains

    assert edges.x == (0.0, 10.0)
    assert edges.x_step == pytest.approx(2.0)


# --------------------------------------------------------------------------------- tooltips


def _titles(svg: str) -> list[str]:
    """Bar tooltips, in document order: the ``<title>`` that is a bar ``<rect>``'s first child.

    Matched through the mark rather than by taking every ``<title>`` and dropping the last.
    **Not** because an axis tick might carry one -- it cannot here: ``_shown_label`` keeps a
    label whole for any non-``CategoricalScale``, and ``histplot``'s axes are both linear, so no
    histogram emits a tick ``<title>``. ``[:-1]`` would in fact work on every chart this file
    builds.

    The reason is that a positional rule is a claim about the whole document while this one is a
    claim about the mark. ``[:-1]`` stops working the moment anything else in the file grows a
    ``<title>``, and it stops working *silently* -- a spare title cancels a missing one and the
    count still matches.

    ``(?<!/)`` so a self-closing rect followed by an unrelated ``<title>`` sibling is not read
    as a titled bar. Unreachable in today's output, and it is the shape that would let
    ``_titles(svg) == []`` pass while a bar quietly kept its tooltip.
    """
    return re.findall(r'<rect\b[^>]*\bclass="(?:[^"]* )?series-\d+(?: [^"]*)?"[^>]*(?<!/)>\s*<title>([^<]*)</title>', svg)


def test_a_bar_tooltip_names_the_interval_it_covers_and_how_many_landed_in_it() -> None:
    svg = histplot({"value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]}, x="value", bins=4, tooltip=True).to_string()

    assert _titles(svg) == [
        "value: [1, 2.75) · 2 observations",
        "value: [2.75, 4.5) · 2 observations",
        "value: [4.5, 6.25) · 2 observations",
        "value: [6.25, 8] · 2 observations",
    ]


def test_only_the_last_bin_says_it_includes_its_right_edge() -> None:
    """``_count_in_bins`` closes the final bin and only that one, so the maximum value in the
    data is not silently dropped. The tooltip is where a reader can see which side of a shared
    boundary a bar claims -- ``2.75`` belongs to the second bar, not the first, and a pair of
    tooltips reading ``1 - 2.75`` and ``2.75 - 4.5`` would not say so.

    The count is the half that makes this a claim rather than a spelling: the value ``8`` is
    the maximum and it is in the last bar, which reports two observations rather than one."""
    titles = _titles(
        histplot({"value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]}, x="value", bins=4, tooltip=True).to_string()
    )

    assert [title.count("]") for title in titles] == [0, 0, 0, 1], "exactly one bar closes on the right"
    assert titles[-1] == "value: [6.25, 8] · 2 observations", "and it is the one holding the maximum"


def test_a_hued_bar_tooltip_names_its_group_too() -> None:
    svg = histplot(HUE_SERIES, x="value", hue="group", bins=2, tooltip=True).to_string()

    assert all("group: " in title for title in _titles(svg))
    assert sorted({title.rsplit(" · ", 1)[1] for title in _titles(svg)}) == ["group: a", "group: b"]


def test_a_bar_says_a_count_and_cannot_say_which_rows() -> None:
    """The mark is an aggregate. ``_count_in_bins`` returns counts and the values behind them
    are not carried past it, so there is nothing downstream that *could* name a row -- and a
    tooltip naming one of the ten would be describing a mark nobody drew."""
    svg = histplot({"value": [float(n) for n in range(1, 11)]}, x="value", bins=1, tooltip=True).to_string()

    assert _titles(svg) == ["value: [1, 10] · 10 observations"]


def test_the_default_draws_no_tooltip_and_saying_so_changes_nothing() -> None:
    """What this can check is that ``tooltip=False`` is the same call as not writing it, and
    that neither emits a mark ``<title>``. It is deliberately not named for byte-identity with
    the version before ``tooltip=`` existed, which it cannot see -- both sides are this
    branch's code. ``docs/gallery/*.html`` holds those bytes, and
    ``test_gallery.py::test_the_committed_gallery_is_what_a_fresh_build_produces`` compares
    them."""
    omitted = histplot(HUE_SERIES, x="value", hue="group").to_string()
    explicit = histplot(HUE_SERIES, x="value", hue="group", tooltip=False).to_string()

    assert omitted == explicit
    assert _titles(omitted) == []


def test_tooltip_on_gives_every_drawn_bar_exactly_one() -> None:
    """Counted against the bars rather than a number written here: ``histplot`` skips an empty
    bin instead of drawing a zero-height rect, so how many marks exist is the binning's answer,
    not the fixture's."""
    svg = histplot(HUE_SERIES, x="value", hue="group", tooltip=True).to_string()
    bars = len(_series_bars(svg, "series-1")) + len(_series_bars(svg, "series-2"))

    assert len(_titles(svg)) == bars > 0


def test_an_empty_bin_gets_no_bar_and_so_no_tooltip() -> None:
    """A bin nothing landed in is not drawn, so it has no accessible name either. The gap in
    the picture is the statement; a ``<title>`` reading "0 observations" would need a mark to
    hang on, and inventing one is the thing this chart does not do."""
    svg = histplot({"value": [0.0, 0.0, 10.0]}, x="value", bins=5, tooltip=True).to_string()

    assert len(_titles(svg)) == 2, "five bins, three of them empty"
    assert "0 observations" not in svg


def test_a_narrowing_xlim_leaves_the_clipped_values_out_of_the_bars_too() -> None:
    """The bars, not only what they say. ``xlim=`` narrower than the data is the documented use
    of that argument, and until this was fixed the outermost bars absorbed everything past the
    window -- 98 of these 200 values, which put 80 in a bar covering 24 of them.

    Heights are proportional to counts, so the ratios pin the counts without needing the axis.
    """
    generator = random.Random(3)
    values = [generator.gauss(10.0, 3.0) for _ in range(200)]
    bars = _series_bars(histplot({"v": values}, x="v", xlim=(8.0, 12.0), bins=4).to_string(), "series-1")
    real = [24, 37, 20, 21]

    assert sum(1 for value in values if value < 8.0 or value > 12.0) == 98, "the fixture stopped clipping"
    unit = max(bar["height"] for bar in bars) / max(real)
    assert [round(bar["height"] / unit) for bar in bars] == real


def test_a_narrowing_xlim_drops_the_values_outside_it_rather_than_piling_them_on_the_edges() -> None:
    """``xlim=`` narrower than the data is the documented use of that argument, and until this
    was fixed the outermost bars absorbed everything past the window. The bars were already the
    wrong height on ``main``; ``tooltip=`` is what made them say the wrong number out loud, and
    the interval they named was untrue as well -- a clamped last bin's real membership rule is
    ``value >= edges[-2]``, unbounded above.

    Each bar is checked against the raw values rather than against a number written here, so the
    fixture can change without the expectations going stale."""
    generator = random.Random(3)
    values = [generator.gauss(10.0, 3.0) for _ in range(200)]
    svg = histplot({"v": values}, x="v", xlim=(8.0, 12.0), bins=4, tooltip=True).to_string()

    assert sum(1 for value in values if value < 8.0 or value > 12.0) == 98, "the fixture stopped clipping"
    for title in _titles(svg):
        low, high = (float(number) for number in title.split("v: [")[1].split(")")[0].split("]")[0].split(", "))
        closed = "]" in title
        said = int(title.split(" · ")[1].split(" ")[0])
        real = (
            sum(1 for value in values if low <= value <= high) if closed else sum(1 for value in values if low <= value < high)
        )
        assert said == real, f"{title} against {real}"


def test_the_description_counts_the_observations_it_drew() -> None:
    """The same sentence names the window on its next clause, so "200 observations, x 8 to 12"
    describes a chart nobody drew."""
    generator = random.Random(3)
    values = [generator.gauss(10.0, 3.0) for _ in range(200)]
    chart = histplot({"v": values}, x="v", xlim=(8.0, 12.0), bins=4)

    assert "102 observations in 4 bins, x 8 to 12" in chart.to_string()


def test_a_column_name_too_long_to_read_is_dropped_from_the_tooltip() -> None:
    """A clause naming something the caller typed is written once per bar, so an unreadable one
    would be the largest thing in the file. Dropped rather than truncated -- half a column name
    is a different column name -- and the interval stays, because that is what the reader came
    for. Nothing pinned this: reverting ``clause`` to an f-string left all 3425 tests green."""
    long_name = "면" * 5000
    svg = histplot({long_name: [1.0, 2.0, 3.0, 4.0]}, x=long_name, bins=2, tooltip=True).to_string()

    assert _titles(svg) == ["[1, 2.5) · 2 observations", "[2.5, 4] · 2 observations"]
    assert long_name not in svg


def test_a_hue_label_too_long_to_read_is_dropped_from_the_tooltip() -> None:
    """Same rule, other clause: the legend says the group's name once, a tooltip would say it
    once per bar per series.

    Counted rather than asserted absent -- the legend legitimately keeps the full text in its
    own ``<title>``, once, which is where a reader recovers it."""
    long_label = "온" * 5000
    data = {"v": [1.0, 2.0, 3.0, 4.0], "g": [long_label, long_label, "b", "b"]}
    svg = histplot(data, x="v", hue="g", bins=2, tooltip=True).to_string()

    assert _titles(svg) == ["v: [2.5, 4] · 2 observations · g: b", "v: [1, 2.5) · 2 observations"]
    assert svg.count(long_label) == 1, "the group name is repeated outside the legend"


def test_a_bin_edge_is_spelled_exactly_not_at_pixel_precision() -> None:
    """``format_value_label`` is the axis's spelling and expands scientific notation back into
    digits: with ``1e308`` in the data the three tooltips below become 332, 639 and 640
    characters *each, per bar*. ``format_number`` picks the shorter of two exact spellings, so
    neither rounds and the edge costs at most 24 characters."""
    svg = histplot({"v": [1.0, 1e308]}, x="v", bins=3, tooltip=True).to_string()

    assert max(len(title) for title in _titles(svg)) < 60, _titles(svg)
    assert "e+" in "".join(_titles(svg)), "the fixture stopped needing scientific notation"


def test_an_xlim_that_leaves_nothing_in_range_is_refused() -> None:
    """Reachable only since the clipping fix: before it, the edge bins caught everything and
    ``max_count`` could not be zero. There is nothing to draw, and both things the chart would
    carry away are broken -- ``Domains(y=(0.0, 0.0))`` is a value ``apply_limit`` refuses from a
    caller, so the chart's own domain cannot be replayed onto another one, and the y axis puts
    its single ``0`` tick halfway up an empty plot area.

    Refused rather than widened to ``(0, 1)``: ``xlim`` is the caller's argument and this is the
    one value of it that produces no chart at all."""
    with pytest.raises(ValueError, match="leaves no values in range"):
        histplot({"v": [1.0, 2.0, 3.0, 4.0]}, x="v", xlim=(10.0, 20.0), bins=4)


def test_an_xlim_that_leaves_one_value_still_draws() -> None:
    """The other side of the boundary -- the refusal has to be about *nothing* in range, not
    about clipping at all."""
    chart = histplot({"v": [1.0, 2.0, 3.0, 40.0]}, x="v", xlim=(35.0, 45.0), bins=2)

    assert chart.domains.y == (0.0, 1.0)
    assert "1 observation in 2 bins, x 35 to 45" in chart.to_string()
