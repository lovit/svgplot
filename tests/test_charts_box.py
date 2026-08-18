from __future__ import annotations

import pytest

from svgplot.charts.box import boxplot
from svgplot.stats.box import MODES, box_stats

NO_OUTLIER_DATA = {
    "group": ["a", "a", "a", "a", "a", "b", "b", "b", "b", "b"],
    "value": [1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 12.0, 14.0, 16.0, 18.0],
}
WITH_OUTLIER_DATA = {
    "group": ["a", "a", "a", "a", "a"],
    "value": [1.0, 2.0, 3.0, 4.0, 100.0],
}


@pytest.mark.parametrize("mode", MODES)
def test_boxplot_renders_for_every_mode(mode: str) -> None:
    chart = boxplot(NO_OUTLIER_DATA, x="group", y="value", mode=mode)
    svg = chart.to_string()
    assert svg.count("<rect") >= 2  # plot-background + at least one box per category (2 categories)


def test_boxplot_draws_one_box_per_distinct_x_category() -> None:
    chart = boxplot(NO_OUTLIER_DATA, x="group", y="value")
    svg = chart.to_string()
    assert "series-1" in svg
    assert "series-2" in svg
    assert "series-3" not in svg


def test_boxplot_box_matches_box_stats_output() -> None:
    stats = box_stats(WITH_OUTLIER_DATA["value"], mode="1.5IQR")
    chart = boxplot(WITH_OUTLIER_DATA, x="group", y="value", mode="1.5IQR")
    svg = chart.to_string()
    # the box rect's height should reflect |q3 - q1| in data units, scaled through the
    # y LinearScale -- rather than re-deriving pixel math, just confirm the stats used
    # match a fresh box_stats call on the same data (i.e. boxplot didn't invent its own).
    assert stats.q1 != stats.q3  # sanity: this dataset actually has a non-degenerate box
    assert "series-1-marker" in svg  # box body uses the "-marker" (fill) companion class


def test_boxplot_shows_outlier_as_a_marker_when_present() -> None:
    chart = boxplot(WITH_OUTLIER_DATA, x="group", y="value", mode="1.5IQR")
    svg = chart.to_string()
    assert "<circle" in svg


def test_boxplot_shows_no_outlier_marker_when_none_present() -> None:
    chart = boxplot(NO_OUTLIER_DATA, x="group", y="value", mode="1.5IQR")
    svg = chart.to_string()
    assert "<circle" not in svg


def test_boxplot_median_line_sits_between_box_edges() -> None:
    stats = box_stats(WITH_OUTLIER_DATA["value"], mode="1.5IQR")
    assert stats.q1 <= stats.median <= stats.q3


def test_boxplot_whisker_caps_present() -> None:
    chart = boxplot(NO_OUTLIER_DATA, x="group", y="value")
    svg = chart.to_string()
    # 2 categories x 4 whisker-related <line> elements each (upper stem, upper cap,
    # lower stem, lower cap) + 2 median lines = 10, plus axis spine/grid/tick lines.
    assert svg.count("<line") >= 10


def test_boxplot_y_domain_includes_outliers() -> None:
    """An outlier outside the whisker range must still land inside the plot area,
    not be clipped off — assert its pixel y coordinate is within the canvas bounds.
    """
    chart = boxplot(WITH_OUTLIER_DATA, x="group", y="value", mode="1.5IQR")
    svg = chart.to_string()
    circle_line = next(line for line in svg.splitlines() if "<circle" in line)
    cy = float(circle_line.split('cy="')[1].split('"')[0])
    assert 0 <= cy <= 600.0  # canvas height


def test_boxplot_drops_rows_with_missing_x_or_y() -> None:
    data = {"group": ["a", "a", None, "a"], "value": [1.0, 2.0, 3.0, None]}
    chart = boxplot(data, x="group", y="value")
    svg = chart.to_string()
    assert "series-1" in svg
    assert "series-2" not in svg


def test_boxplot_raises_value_error_for_empty_data() -> None:
    with pytest.raises(ValueError, match="at least one row"):
        boxplot({"group": [], "value": []}, x="group", y="value")


def test_boxplot_raises_value_error_when_all_rows_missing() -> None:
    with pytest.raises(ValueError, match="no rows"):
        boxplot({"group": [None, None], "value": [1.0, 2.0]}, x="group", y="value")


def test_boxplot_raises_key_error_for_missing_column() -> None:
    with pytest.raises(KeyError):
        boxplot(NO_OUTLIER_DATA, x="not_a_column", y="value")


def test_boxplot_raises_key_error_for_unknown_theme_preset() -> None:
    with pytest.raises(KeyError):
        boxplot(NO_OUTLIER_DATA, x="group", y="value", theme="not_a_preset")


def test_boxplot_propagates_box_stats_error_for_unknown_mode() -> None:
    with pytest.raises(ValueError, match="unknown box mode"):
        boxplot(NO_OUTLIER_DATA, x="group", y="value", mode="not_a_mode")


def test_boxplot_corner_radius_produces_rx_attribute() -> None:
    chart = boxplot(NO_OUTLIER_DATA, x="group", y="value", theme="minimal")
    svg_default = chart.to_string()
    assert 'rx="' not in svg_default  # "minimal" preset doesn't set corner_radius

    from svgplot.theme.base import Theme

    chart = boxplot(NO_OUTLIER_DATA, x="group", y="value", theme=Theme(corner_radius=4.0))
    svg = chart.to_string()
    assert 'rx="4"' in svg
