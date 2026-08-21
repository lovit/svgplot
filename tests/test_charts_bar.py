from __future__ import annotations

import re

import pytest

from svgplot.charts.bar import barplot
from svgplot.scales import CategoricalScale

SINGLE_SERIES = {"category": ["a", "b", "c"], "value": [10.0, 20.0, 15.0]}
HUE_SERIES = {
    "category": ["a", "b", "c", "a", "b", "c"],
    "value": [10.0, 20.0, 15.0, 5.0, 8.0, 12.0],
    "group": ["x", "x", "x", "y", "y", "y"],
}

# charts/bar.py's canvas + margins, mirrored here so geometry assertions can state
# expected absolute coordinates instead of re-deriving them from the implementation.
_AREA_LEFT, _AREA_TOP, _AREA_BOTTOM = 60.0, 30.0, 550.0
_AREA_RIGHT_WITH_LEGEND = 640.0
_AREA_RIGHT_WITHOUT_LEGEND = 760.0

# charts/_legend.py's fill-mode swatch is a fixed-size <rect>; bars in these datasets
# never coincidentally match it, so this size is a safe discriminator.
_SWATCH_SIZE = (16.0, 10.0)


def _rect_count(svg: str) -> int:
    return svg.count("<rect")


def _rects(svg: str) -> list[dict]:
    """Parse every <rect> into {x, y, width, height, class} (numbers as floats)."""
    parsed = []
    for tag in re.findall(r"<rect\b[^>]*>", svg):
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', tag))
        parsed.append(
            {
                "x": float(attrs["x"]),
                "y": float(attrs["y"]),
                "width": float(attrs["width"]),
                "height": float(attrs["height"]),
                "class": attrs.get("class", ""),
            }
        )
    return parsed


def _bars(svg: str) -> list[dict]:
    """Data-mark rects only — drops the plot background and the legend swatches."""
    return [
        rect for rect in _rects(svg) if rect["class"].startswith("series-") and (rect["width"], rect["height"]) != _SWATCH_SIZE
    ]


def _bars_by_category_position(svg: str, *, axis: str) -> dict[float, list[dict]]:
    """Group bars by their position along the category axis ("x" for vertical bars,
    "y" for horizontal), which is what stacked segments of one category share.
    """
    grouped: dict[float, list[dict]] = {}
    for bar in _bars(svg):
        grouped.setdefault(bar[axis], []).append(bar)
    return grouped


# plot-background (1) + one legend swatch per hue group (fill-mode swatches are
# <rect>s too, per charts/_legend.py) -- every "with hue" test must account for both.
_BACKGROUND_RECT = 1
_HUE_GROUP_COUNT = 2  # len(set(HUE_SERIES["group"]))


# ---------------------------------------------------------------------------
# 4 explicit AC modes: v-grouped, v-stacked, h-grouped, h-stacked
# ---------------------------------------------------------------------------


def test_barplot_vertical_grouped() -> None:
    chart = barplot(HUE_SERIES, x="category", y="value", hue="group", orient="v", stacked=False)
    svg = chart.to_string()
    assert _rect_count(svg) == _BACKGROUND_RECT + 6 + _HUE_GROUP_COUNT  # 3 categories x 2 hue groups
    assert "series-1" in svg
    assert "series-2" in svg


def test_barplot_grouped_bars_sit_side_by_side_inside_their_category_band() -> None:
    """Counting rects can't tell dodge from overlap: this pins that the two hue bars
    of one category are laid out left-to-right without overlapping each other, and
    that neither escapes the category's band.
    """
    chart = barplot(HUE_SERIES, x="category", y="value", hue="group", orient="v", stacked=False)
    bars = sorted(_bars(chart.to_string()), key=lambda bar: bar["x"])
    scale = CategoricalScale(["a", "b", "c"], (_AREA_LEFT, _AREA_RIGHT_WITH_LEGEND))

    for category in ("a", "b", "c"):
        band_start = scale(category)
        band_end = band_start + scale.bandwidth
        in_band = [bar for bar in bars if band_start <= bar["x"] < band_end]
        assert len(in_band) == 2, f"category {category!r} should hold one bar per hue group"
        first, second = in_band
        assert first["x"] + first["width"] <= second["x"]  # no overlap
        assert second["x"] + second["width"] <= band_end  # no overflow past the band
        assert band_start <= first["x"]


def test_barplot_vertical_stacked() -> None:
    chart = barplot(HUE_SERIES, x="category", y="value", hue="group", orient="v", stacked=True)
    svg = chart.to_string()
    assert _rect_count(svg) == _BACKGROUND_RECT + 6 + _HUE_GROUP_COUNT  # still one segment per (category, group)


def test_barplot_horizontal_grouped() -> None:
    chart = barplot(HUE_SERIES, x="category", y="value", hue="group", orient="h", stacked=False)
    svg = chart.to_string()
    assert _rect_count(svg) == _BACKGROUND_RECT + 6 + _HUE_GROUP_COUNT


def test_barplot_horizontal_grows_rightward_from_the_left_edge() -> None:
    """Rect *counts* are identical for both orientations, so an implementation that
    ignored orient= would pass every mode test. This pins the actual axis swap:
    horizontal bars all start at the plot area's left edge, encode their value in
    width (not height), and share one constant thickness.
    """
    chart = barplot(HUE_SERIES, x="category", y="value", hue="group", orient="h", stacked=False)
    bars = _bars(chart.to_string())

    assert all(bar["x"] == pytest.approx(_AREA_LEFT) for bar in bars)
    assert len({round(bar["height"], 6) for bar in bars}) == 1  # one bar thickness
    assert len({round(bar["width"], 6) for bar in bars}) > 1  # value varies the length


def test_barplot_horizontal_puts_category_labels_on_the_left_axis() -> None:
    svg = barplot(HUE_SERIES, x="category", y="value", hue="group", orient="h").to_string()
    left_axis_labels = re.findall(r'<text[^>]*text-anchor="end"[^>]*class="tick-label">([^<]*)</text>', svg)
    assert left_axis_labels == ["a", "b", "c"]


def test_barplot_vertical_puts_category_labels_on_the_bottom_axis() -> None:
    """The mirror of the horizontal case — together these two prove the category axis
    genuinely moves between orientations rather than always rendering in one place.
    """
    svg = barplot(HUE_SERIES, x="category", y="value", hue="group", orient="v").to_string()
    bottom_axis_labels = re.findall(r'<text[^>]*text-anchor="middle"[^>]*class="tick-label">([^<]*)</text>', svg)
    assert bottom_axis_labels[:3] == ["a", "b", "c"]


def test_barplot_horizontal_stacked() -> None:
    chart = barplot(HUE_SERIES, x="category", y="value", hue="group", orient="h", stacked=True)
    svg = chart.to_string()
    assert _rect_count(svg) == _BACKGROUND_RECT + 6 + _HUE_GROUP_COUNT


# ---------------------------------------------------------------------------
# plain single-series (no hue)
# ---------------------------------------------------------------------------


def test_barplot_plain_vertical_single_series() -> None:
    chart = barplot(SINGLE_SERIES, x="category", y="value", orient="v")
    svg = chart.to_string()
    assert _rect_count(svg) - _BACKGROUND_RECT == 3
    assert "series-1" in svg
    assert "series-2" not in svg


def test_barplot_plain_horizontal_single_series() -> None:
    chart = barplot(SINGLE_SERIES, x="category", y="value", orient="h")
    svg = chart.to_string()
    assert _rect_count(svg) - _BACKGROUND_RECT == 3


def test_barplot_stacked_without_hue_is_a_plain_single_series() -> None:
    """stacked=True with no hue has nothing to stack -- should not error, and should
    render exactly like the unstacked plain case (one bar per category).
    """
    chart = barplot(SINGLE_SERIES, x="category", y="value", stacked=True)
    svg = chart.to_string()
    assert _rect_count(svg) - _BACKGROUND_RECT == 3


# ---------------------------------------------------------------------------
# stacked segments actually stack (cumulative offsets, not overlapping)
# ---------------------------------------------------------------------------


def test_barplot_vertical_stacked_segments_are_cumulative() -> None:
    """A stack is only a stack if each segment starts exactly where the one below it
    ended. Asserting merely that the two segments' y values *differ* would also pass
    if both were drawn from the baseline (different values -> different heights), so
    this pins the cumulative invariant itself: upper.y + upper.height == lower.y, and
    the bottom-most segment rests on the zero baseline.
    """
    chart = barplot(HUE_SERIES, x="category", y="value", hue="group", orient="v", stacked=True)
    by_category = _bars_by_category_position(chart.to_string(), axis="x")
    assert len(by_category) == 3

    for segments in by_category.values():
        # bottom-most first: larger y is lower on screen
        segments = sorted(segments, key=lambda bar: bar["y"], reverse=True)
        assert len(segments) == 2
        lower, upper = segments
        assert lower["y"] + lower["height"] == pytest.approx(_AREA_BOTTOM)  # rests on 0
        assert upper["y"] + upper["height"] == pytest.approx(lower["y"])  # stacks on top


def test_barplot_horizontal_stacked_segments_are_cumulative() -> None:
    chart = barplot(HUE_SERIES, x="category", y="value", hue="group", orient="h", stacked=True)
    by_category = _bars_by_category_position(chart.to_string(), axis="y")
    assert len(by_category) == 3

    for segments in by_category.values():
        segments = sorted(segments, key=lambda bar: bar["x"])
        assert len(segments) == 2
        first, second = segments
        assert first["x"] == pytest.approx(_AREA_LEFT)  # starts at 0
        assert first["x"] + first["width"] == pytest.approx(second["x"])  # stacks rightward


def test_barplot_value_axis_is_anchored_at_zero_not_the_data_minimum() -> None:
    """Every bar must reach the zero baseline: a bar chart whose value axis started at
    the data minimum would silently exaggerate small differences.
    """
    svg = barplot(SINGLE_SERIES, x="category", y="value", orient="v").to_string()
    for bar in _bars(svg):
        assert bar["y"] + bar["height"] == pytest.approx(_AREA_BOTTOM)


# ---------------------------------------------------------------------------
# legend
# ---------------------------------------------------------------------------


def test_barplot_generates_a_legend_entry_per_hue_value() -> None:
    chart = barplot(HUE_SERIES, x="category", y="value", hue="group")
    svg = chart.to_string()
    assert svg.count('class="legend-text"') == 2
    assert ">x<" in svg
    assert ">y<" in svg


def test_barplot_draws_no_legend_without_hue() -> None:
    chart = barplot(SINGLE_SERIES, x="category", y="value")
    svg = chart.to_string()
    assert 'class="legend-text"' not in svg


# ---------------------------------------------------------------------------
# theme.corner_radius
# ---------------------------------------------------------------------------


def test_barplot_applies_theme_corner_radius_to_bars() -> None:
    from svgplot.theme.base import Theme

    chart = barplot(SINGLE_SERIES, x="category", y="value", theme=Theme(corner_radius=4.0))
    svg = chart.to_string()
    assert 'rx="4"' in svg


def test_barplot_omits_rx_when_corner_radius_is_zero() -> None:
    chart = barplot(SINGLE_SERIES, x="category", y="value")
    svg = chart.to_string()
    assert "rx=" not in svg


# ---------------------------------------------------------------------------
# edge cases / errors
# ---------------------------------------------------------------------------


def test_barplot_drops_rows_with_missing_category_or_value() -> None:
    data = {"category": ["a", None, "c"], "value": [10.0, 20.0, None]}
    chart = barplot(data, x="category", y="value")
    svg = chart.to_string()
    assert _rect_count(svg) - _BACKGROUND_RECT == 1  # only "a" survives


def test_barplot_rejects_empty_data() -> None:
    with pytest.raises(ValueError, match="at least one row"):
        barplot({"category": [], "value": []}, x="category", y="value")


def test_barplot_rejects_all_missing_categories() -> None:
    with pytest.raises(ValueError, match="category"):
        barplot({"category": [None, None], "value": [1.0, 2.0]}, x="category", y="value")


def test_barplot_rejects_invalid_orient() -> None:
    with pytest.raises(ValueError, match="orient"):
        barplot(SINGLE_SERIES, x="category", y="value", orient="diagonal")


def test_barplot_rejects_negative_values() -> None:
    data = {"category": ["a", "b"], "value": [10.0, -5.0]}
    with pytest.raises(ValueError, match="negative"):
        barplot(data, x="category", y="value")


def test_barplot_rejects_unknown_column() -> None:
    with pytest.raises(KeyError):
        barplot(SINGLE_SERIES, x="category", y="nope")


def test_barplot_rejects_unknown_theme_preset() -> None:
    with pytest.raises(KeyError):
        barplot(SINGLE_SERIES, x="category", y="value", theme="nonexistent")


def test_barplot_all_zero_values_renders_without_error() -> None:
    data = {"category": ["a", "b"], "value": [0.0, 0.0]}
    chart = barplot(data, x="category", y="value")
    svg = chart.to_string()
    assert _rect_count(svg) - _BACKGROUND_RECT == 2


def test_barplot_renders_a_single_category() -> None:
    chart = barplot({"category": ["a"], "value": [10.0]}, x="category", y="value")
    bars = _bars(chart.to_string())
    assert len(bars) == 1
    assert bars[0]["y"] + bars[0]["height"] == pytest.approx(_AREA_BOTTOM)


def test_barplot_renders_a_single_hue_group() -> None:
    data = {"category": ["a", "b"], "value": [10.0, 20.0], "group": ["x", "x"]}
    chart = barplot(data, x="category", y="value", hue="group")
    svg = chart.to_string()
    assert len(_bars(svg)) == 2
    assert "series-2" not in svg


def test_barplot_stacked_skips_categories_absent_from_a_hue_group() -> None:
    """A category present in one group but not another leaves a gap in that group's
    layer rather than drawing a zero-height segment or shifting the stack.
    """
    data = {"category": ["a", "b", "a"], "value": [10.0, 20.0, 5.0], "group": ["x", "x", "y"]}
    chart = barplot(data, x="category", y="value", hue="group", stacked=True)
    by_category = _bars_by_category_position(chart.to_string(), axis="x")

    segment_counts = sorted(len(segments) for segments in by_category.values())
    assert segment_counts == [1, 2]  # "b" only appears in group x


# --------------------------------------------------------------------------- what colour means
#
# The docstring and the gallery page both used to say that this chart rotates its palette per
# category without ``hue=``, and that ``categories=`` gives a rowless category "its place in
# the palette". Neither is true here, and both sentences were copied verbatim from ``boxplot``
# and ``violinplot``, where they *are* true. Executed rather than asserted in prose, because
# reading the sentence next to the code is exactly how it survived.


def _series_classes(svg: str) -> set[str]:
    return {
        name for attribute in re.findall(r'\bclass="([^"]*)"', svg) for name in attribute.split() if name.startswith("series-")
    }


def test_without_hue_every_bar_is_one_series_however_many_categories() -> None:
    """Colour follows ``hue=`` and nothing else. Four categories, one colour.

    Not "the palette happens to have one entry": the point is that a reader cannot take the
    bars' colours to mean anything, because there is only ever one.
    """
    svg = barplot({"category": ["a", "b", "c", "d"], "value": [1.0, 2.0, 3.0, 4.0]}, x="category", y="value").to_string()

    assert _series_classes(svg) == {"series-1"}


def test_with_hue_the_palette_follows_the_hue_values() -> None:
    """One entry per group, and a group keeps its entry across every category -- which is what
    makes the legend readable."""
    svg = barplot(HUE_SERIES, x="category", y="value", hue="group").to_string()

    assert _series_classes(svg) == {"series-1", "series-2"}
    assert len(_bars(svg)) == 6, "three categories x two groups"


def test_a_rowless_category_gets_a_band_but_not_a_colour() -> None:
    """``categories=`` lines several charts up on the *axis*. It has nothing to do with colour
    here, which is the half of the inherited sentence that was false.

    ``boxplot``'s and ``violinplot``'s identically-worded paragraphs describe charts that do
    rotate per category, so there a rowless category really does consume a palette entry. The
    difference between the three is #194; this test only pins what ``barplot`` does.
    """
    svg = barplot(
        {"category": ["a", "b"], "value": [1.0, 2.0]}, x="category", y="value", categories=("a", "gap", "b")
    ).to_string()

    assert "gap" in svg, "the rowless category still gets its tick"
    assert len(_bars(svg)) == 2, "and no mark of its own"
    assert _series_classes(svg) == {"series-1"}, "and takes no palette entry with it"


# --------------------------------------------------------------------------------- tooltips


def _titles(svg: str) -> list[str]:
    """Bar tooltips, in document order: the ``<title>`` that is a ``<rect class="series-N">``'s
    first child.

    Matched through the mark rather than by dropping the last one. Two other things in this file
    emit a ``<title>``: the chart's own, which is last, and an axis tick whose label had to be
    shortened, which comes *first* -- so ``findall(...)[:-1]`` returns the tick's title as if it
    were a bar's, and a category of thirty characters is enough to get one. Counting titles
    against bars then passes on a chart that has a spare title and a missing one.
    """
    return re.findall(r'<rect\b[^>]*\bclass="(?:[^"]* )?series-\d+(?: [^"]*)?"[^>]*>\s*<title>([^<]*)</title>', svg)


def test_a_bar_tooltip_names_its_category_and_its_value() -> None:
    svg = barplot(SINGLE_SERIES, x="category", y="value", tooltip=True).to_string()

    assert _titles(svg) == ["category: a · value: 10", "category: b · value: 20", "category: c · value: 15"]


def test_a_hued_bar_tooltip_names_its_group_too() -> None:
    svg = barplot(HUE_SERIES, x="category", y="value", hue="group", tooltip=True).to_string()

    assert "<title>category: a · value: 10 · group: x</title>" in svg
    assert "<title>category: a · value: 5 · group: y</title>" in svg


def test_a_stacked_segment_says_its_own_value_not_the_running_total() -> None:
    """The rectangle is the segment, so that is what its accessible name has to be. Reading the
    cumulative height would name a shape nobody drew -- and would make the top segment of every
    category claim the column's total."""
    # Values chosen so no cumulative total equals any segment: 10+1, 20+2, 30+3 are 11, 22, 33
    # and none of those is a value in the data. With ``HUE_SERIES`` the total for "a" is 15,
    # which is also "c"'s own value -- the wrong implementation and the right one would both
    # put "15" somewhere in the file.
    data = {
        "category": ["a", "b", "c", "a", "b", "c"],
        "value": [10.0, 20.0, 30.0, 1.0, 2.0, 3.0],
        "group": ["x"] * 3 + ["y"] * 3,
    }
    svg = barplot(data, x="category", y="value", hue="group", stacked=True, tooltip=True).to_string()

    assert sorted(_titles(svg)) == sorted(
        f"category: {category} · value: {value} · group: {group}"
        for category, value, group in zip(data["category"], (10, 20, 30, 1, 2, 3), data["group"], strict=True)
    )
    for total in (11, 22, 33):
        assert f"value: {total}" not in svg, "a segment reported the column's running total"


def test_a_folded_bar_says_the_folded_value() -> None:
    """``estimator=`` makes the mark an aggregate of several rows. The tooltip names the
    aggregate because that is what was drawn; naming the rows would describe something the
    chart does not contain."""
    data = {"category": ["a", "a", "b"], "value": [10.0, 20.0, 7.0]}
    svg = barplot(data, x="category", y="value", estimator="mean", tooltip=True).to_string()

    assert _titles(svg) == ["category: a · value: 15", "category: b · value: 7"]


def test_the_default_draws_no_tooltip_and_saying_so_changes_nothing() -> None:
    """What this can check is that ``tooltip=False`` is the same call as not writing it, and
    that neither emits a ``<title>``.

    It is deliberately *not* named for byte-identity with the version before ``tooltip=``
    existed, which it cannot see: both sides here are this branch's code, so any change that
    hits every bar unconditionally passes. ``docs/gallery/*.html`` is the guard that actually
    holds those bytes -- committed output from before this branch, rebuilt and compared by
    ``test_gallery.py::test_the_committed_gallery_is_what_a_fresh_build_produces``. Adding an
    unconditional ``data-mark="bar"`` to every rect leaves all 38 tests in this file green and
    turns that one red.
    """
    omitted = barplot(HUE_SERIES, x="category", y="value", hue="group").to_string()
    explicit = barplot(HUE_SERIES, x="category", y="value", hue="group", tooltip=False).to_string()

    assert omitted == explicit
    assert "<title>" not in omitted.replace("<title>Chart</title>", "")


def test_tooltip_on_gives_every_bar_exactly_one() -> None:
    svg = barplot(HUE_SERIES, x="category", y="value", hue="group", tooltip=True).to_string()

    assert len(_titles(svg)) == len(_bars(svg)) == 6


def test_a_category_too_long_to_read_is_left_out_of_the_tooltip() -> None:
    """The category is the first tooltip *value* in the package that is a string out of the
    data rather than a formatted number, and it is written once per bar. Uncapped, the three
    bars below took the file from 17,959 bytes to 33,081 and put 5,011 characters in one
    ``<title>``; the axis tick showing the same category is already shortened."""
    data = {"category": ["면" * 5000, "b", "c"], "value": [10.0, 20.0, 30.0]}
    svg = barplot(data, x="category", y="value", tooltip=True).to_string()

    assert _titles(svg) == ["value: 10", "category: b · value: 20", "category: c · value: 30"]
    assert len(svg.encode()) < 20_000, "the unreadable category was written into the file anyway"


def test_a_category_that_draws_nothing_is_left_out_too() -> None:
    """``"category:  · value: 1"`` names the bar with a label that is not on screen. A category
    of one tab is data, not a caller's mistake, so the clause goes rather than the chart."""
    data = {"category": ["", "\t", "b"], "value": [1.0, 2.0, 3.0]}

    assert _titles(barplot(data, x="category", y="value", tooltip=True).to_string()) == [
        "value: 1",
        "value: 2",
        "category: b · value: 3",
    ]


def test_a_horizontal_bar_says_the_same_thing_as_a_vertical_one() -> None:
    """``orient="h"`` is the one place the rectangle's geometry is assembled differently, so it
    is the one place a tooltip could pick up the wrong end of the bar. It says the same
    sentence: the tooltip names the category and the value, not the pixels."""
    kwargs = {"x": "category", "y": "value", "hue": "group", "stacked": True, "tooltip": True}
    vertical = barplot(HUE_SERIES, **kwargs).to_string()
    horizontal = barplot(HUE_SERIES, orient="h", **kwargs).to_string()

    assert sorted(_titles(horizontal)) == sorted(_titles(vertical))
    assert "category: a · value: 10 · group: x" in _titles(horizontal)
