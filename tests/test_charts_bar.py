from __future__ import annotations

import pytest

from svgplot.charts.bar import barplot

SINGLE_SERIES = {"category": ["a", "b", "c"], "value": [10.0, 20.0, 15.0]}
HUE_SERIES = {
    "category": ["a", "b", "c", "a", "b", "c"],
    "value": [10.0, 20.0, 15.0, 5.0, 8.0, 12.0],
    "group": ["x", "x", "x", "y", "y", "y"],
}


def _rect_count(svg: str) -> int:
    return svg.count("<rect")


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


def test_barplot_vertical_stacked() -> None:
    chart = barplot(HUE_SERIES, x="category", y="value", hue="group", orient="v", stacked=True)
    svg = chart.to_string()
    assert _rect_count(svg) == _BACKGROUND_RECT + 6 + _HUE_GROUP_COUNT  # still one segment per (category, group)


def test_barplot_horizontal_grouped() -> None:
    chart = barplot(HUE_SERIES, x="category", y="value", hue="group", orient="h", stacked=False)
    svg = chart.to_string()
    assert _rect_count(svg) == _BACKGROUND_RECT + 6 + _HUE_GROUP_COUNT


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


def test_barplot_stacked_segments_have_distinct_non_overlapping_positions() -> None:
    import re

    chart = barplot(HUE_SERIES, x="category", y="value", hue="group", orient="v", stacked=True)
    svg = chart.to_string()
    rects = re.findall(r"<rect\b[^/]*/>", svg)
    # legend swatches carry a series class too (fill-mode swatch = <rect>) -- they're
    # always 16x10 (charts/_legend.py's _SWATCH_WIDTH/_SWATCH_HEIGHT), distinct from
    # any bar segment in this dataset, so filter them out by that fixed size.
    series_rects = [r for r in rects if 'class="series-' in r and 'width="16"' not in r]
    assert len(series_rects) == 6
    heights = [float(re.search(r'height="([\d.]+)"', r).group(1)) for r in series_rects]
    assert all(h > 0 for h in heights)
    # category "a"'s two stacked segments (first group=x row, first group=y row) must
    # sit at different y positions -- if they overlapped, the stack wouldn't be a stack.
    category_a_ys = sorted(float(re.search(r'y="([\d.]+)"', r).group(1)) for r in (series_rects[0], series_rects[3]))
    assert category_a_ys[0] != category_a_ys[1]


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
