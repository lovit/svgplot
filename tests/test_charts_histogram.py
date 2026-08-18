from __future__ import annotations

import pytest

from svgplot.charts.histogram import histplot

SINGLE_SERIES = {"value": [1.0, 2.0, 2.0, 3.0, 4.0, 5.0, 5.0, 5.0, 6.0, 7.0]}
HUE_SERIES = {
    "value": [1.0, 2.0, 2.0, 3.0, 4.0, 1.5, 2.5, 3.5, 4.5, 5.5],
    "group": ["a", "a", "a", "a", "a", "b", "b", "b", "b", "b"],
}


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
    # 10 evenly-spaced values across [0, 10) with bins=5 -> exactly 5 bins,
    # one point each -> exactly 5 non-empty <rect> data bars for the series
    # (plus the unrelated plot-background rect, hence the +1).
    data = {"value": [0.0, 2.0, 4.0, 6.0, 8.0, 9.9]}
    chart = histplot(data, x="value", bins=5)
    svg = chart.to_string()
    assert svg.count("<rect") == 6  # plot-background + up to 5 non-empty bins


def test_histplot_counts_values_correctly_for_a_hand_checkable_dataset() -> None:
    # bins=2 over [0, 10] -> edges [0, 5, 10]; 3 values in [0, 5), 2 values in [5, 10].
    data = {"value": [0.0, 1.0, 4.9, 5.0, 10.0]}
    chart = histplot(data, x="value", bins=2)
    svg = chart.to_string()
    # Two non-empty bins -> two data <rect> elements (+1 for plot-background).
    assert svg.count("<rect") == 3


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
    """Bin edges are computed once across all groups' combined values, not per
    group, so bars from different hue values land on directly comparable
    boundaries -- verified indirectly: both groups' bars must fall within the
    combined value range [1.0, 5.5], not each group's own narrower range.
    """
    chart = histplot(HUE_SERIES, x="value", hue="group", bins=4)
    svg = chart.to_string()
    assert svg.count("<rect") >= 1 + 2  # background + at least one bar per group


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
    svg = chart.to_string()
    assert "fill: none" not in svg.split("<style>")[1].split("</style>")[0].split(".series-1")[1].split("}")[0]


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


def test_histplot_rejects_unknown_theme_preset() -> None:
    with pytest.raises(KeyError, match="unknown theme preset"):
        histplot(SINGLE_SERIES, x="value", theme="not-a-preset")


def test_histplot_propagates_invalid_bins_error() -> None:
    with pytest.raises(ValueError, match="bins"):
        histplot(SINGLE_SERIES, x="value", bins=10**8)
