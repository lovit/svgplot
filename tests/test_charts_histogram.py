from __future__ import annotations

import math
import re

import pytest

from svgplot.charts.histogram import histplot

SINGLE_SERIES = {"value": [1.0, 2.0, 2.0, 3.0, 4.0, 5.0, 5.0, 5.0, 6.0, 7.0]}
HUE_SERIES = {
    "value": [1.0, 2.0, 2.0, 3.0, 4.0, 1.5, 2.5, 3.5, 4.5, 5.5],
    "group": ["a", "a", "a", "a", "a", "b", "b", "b", "b", "b"],
}

_RECT_RE = re.compile(r"<rect\b([^>]*)/>")
_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')


def _series_bars(svg: str, series_class: str) -> list[dict[str, float]]:
    """Return the data bars drawn for ``series_class`` as ``{x, y, width, height}``, sorted by x.

    Legend swatches carry the same CSS class as the bars they label, so they're
    filtered out here: a data bar always grows up from the shared baseline, while
    a swatch sits well above it.
    """
    rects = [dict(_ATTR_RE.findall(attrs)) for attrs in _RECT_RE.findall(svg)]
    matching = [
        {key: float(rect[key]) for key in ("x", "y", "width", "height")} for rect in rects if rect.get("class") == series_class
    ]
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
