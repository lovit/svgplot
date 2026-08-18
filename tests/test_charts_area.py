from __future__ import annotations

import re

import pytest

from svgplot.charts.area import areaplot

SINGLE_SERIES = {"day": [1, 2, 3, 4, 5], "value": [10.0, 15.0, 7.0, 20.0, 12.0]}
HUE_SERIES = {
    "day": [1, 2, 3, 4, 5, 1, 2, 3, 4, 5],
    "value": [10.0, 15.0, 7.0, 20.0, 12.0, 5.0, 8.0, 3.0, 10.0, 6.0],
    "group": ["a", "a", "a", "a", "a", "b", "b", "b", "b", "b"],
}
MISMATCHED_HUE_SERIES = {
    "day": [1, 2, 3, 1, 2, 4],
    "value": [10.0, 20.0, 30.0, 5.0, 8.0, 12.0],
    "group": ["a", "a", "a", "b", "b", "b"],
}


def _path_ds(svg: str) -> list[str]:
    return re.findall(r'<path d="([^"]*)"', svg)


# ---------------------------------------------------------------------------
# single area
# ---------------------------------------------------------------------------


def test_areaplot_renders_a_single_area_with_default_theme() -> None:
    chart = areaplot(SINGLE_SERIES, x="day", y="value")
    svg = chart.to_string()
    assert "<path" in svg
    assert "series-1" in svg
    assert "series-2" not in svg


def test_areaplot_path_is_closed_and_returns_to_baseline() -> None:
    chart = areaplot(SINGLE_SERIES, x="day", y="value")
    (d,) = _path_ds(chart.to_string())
    assert d.startswith("M ")
    assert d.endswith("Z")
    # last two "L" commands close down to the baseline and back to the start x
    commands = d.split(" Z")[0].split(" L")
    baseline_commands = commands[-2:]
    baseline_ys = {cmd.split(",")[1] for cmd in baseline_commands}
    assert len(baseline_ys) == 1  # both baseline points share the same y


def test_areaplot_draws_no_legend_without_hue() -> None:
    chart = areaplot(SINGLE_SERIES, x="day", y="value")
    svg = chart.to_string()
    assert 'class="legend-text"' not in svg


def test_areaplot_uses_fill_based_css_not_stroke() -> None:
    chart = areaplot(SINGLE_SERIES, x="day", y="value")
    style = chart.to_string().split("<style>")[1].split("</style>")[0]
    assert ".series-1 { fill: #E69F00; stroke: none;" in style


# ---------------------------------------------------------------------------
# hue= multi-area (unstacked)
# ---------------------------------------------------------------------------


def test_areaplot_draws_one_area_per_hue_value() -> None:
    chart = areaplot(HUE_SERIES, x="day", y="value", hue="group")
    svg = chart.to_string()
    assert svg.count("<path") == 2
    assert "series-1" in svg
    assert "series-2" in svg


def test_areaplot_generates_a_legend_entry_per_hue_value() -> None:
    chart = areaplot(HUE_SERIES, x="day", y="value", hue="group")
    svg = chart.to_string()
    assert svg.count('class="legend-text"') == 2
    assert ">a<" in svg
    assert ">b<" in svg


def test_areaplot_raises_key_error_for_missing_hue_column() -> None:
    with pytest.raises(KeyError):
        areaplot(HUE_SERIES, x="day", y="value", hue="not_a_column")


# ---------------------------------------------------------------------------
# stacked=True
# ---------------------------------------------------------------------------


def test_areaplot_stacked_without_hue_behaves_as_single_area() -> None:
    chart = areaplot(SINGLE_SERIES, x="day", y="value", stacked=True)
    svg = chart.to_string()
    assert svg.count("<path") == 1


def test_areaplot_stacked_areas_accumulate_above_each_other() -> None:
    """The second series' band must sit strictly above (smaller SVG y, since SVG
    y grows downward) the first series' band at every shared x — i.e. it's drawn
    on top of the running total, not independently from the baseline.
    """
    chart = areaplot(HUE_SERIES, x="day", y="value", hue="group", stacked=True)
    d1, d2 = _path_ds(chart.to_string())

    def top_ys(d: str) -> list[float]:
        # the "top" edge is the first half of the L commands (before the path
        # reverses back along the bottom edge) -- for 5 points that's M + 4 L's.
        points = re.findall(r"([\d.-]+),([\d.-]+)", d)
        return [float(y) for _, y in points[:5]]

    series_a_tops = top_ys(d1)  # group "a" stacks on the baseline (bottom = 0)
    series_b_tops = top_ys(d2)  # group "b" stacks on top of "a"
    # SVG y grows downward, so "above" means a smaller y value
    assert all(b_top < a_top for a_top, b_top in zip(series_a_tops, series_b_tops, strict=True))


def test_areaplot_stacked_handles_mismatched_x_values_as_zero() -> None:
    """group "a" has no row at day=4, group "b" has no row at day=3 -- the union
    of x values (1,2,3,4) is used, and a missing (group, day) pair contributes 0
    to that group's stack rather than raising or dropping the x value.
    """
    chart = areaplot(MISMATCHED_HUE_SERIES, x="day", y="value", hue="group", stacked=True)
    svg = chart.to_string()
    assert svg.count("<path") == 2
    # 4 distinct x values in the union -> 4 top points + 4 bottom points = 8 coordinate pairs
    d = _path_ds(svg)[0]
    assert len(re.findall(r"[\d.-]+,[\d.-]+", d)) == 8


# ---------------------------------------------------------------------------
# missing values / errors
# ---------------------------------------------------------------------------


def test_areaplot_drops_rows_with_missing_x_or_y() -> None:
    data = {"day": [1, 2, None, 4], "value": [10.0, None, 7.0, 20.0]}
    chart = areaplot(data, x="day", y="value")
    (d,) = _path_ds(chart.to_string())
    # only day=1 (value=10) and day=4 (value=20) survive -> M + 1 L + 2 baseline L's + Z
    assert d.count("L") == 3


def test_areaplot_rejects_empty_data() -> None:
    with pytest.raises(ValueError, match="at least one row"):
        areaplot({"day": [], "value": []}, x="day", y="value")


def test_areaplot_raises_key_error_for_missing_x_or_y_column() -> None:
    with pytest.raises(KeyError):
        areaplot(SINGLE_SERIES, x="not_a_column", y="value")
    with pytest.raises(KeyError):
        areaplot(SINGLE_SERIES, x="day", y="not_a_column")


def test_areaplot_rejects_all_rows_missing() -> None:
    data = {"day": [None, None], "value": [None, None]}
    with pytest.raises(ValueError, match="no rows with both x and y"):
        areaplot(data, x="day", y="value")


def test_areaplot_raises_key_error_for_unknown_theme_preset() -> None:
    with pytest.raises(KeyError):
        areaplot(SINGLE_SERIES, x="day", y="value", theme="not_a_preset")
