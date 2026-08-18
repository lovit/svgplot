from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from svgplot.chart.base import Chart
from svgplot.charts._layout import plot_area
from svgplot.charts.box import boxplot
from svgplot.scales import LinearScale
from svgplot.stats.box import MODES, BoxStats, box_stats

NO_OUTLIER_DATA = {
    "group": ["a", "a", "a", "a", "a", "b", "b", "b", "b", "b"],
    "value": [1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 12.0, 14.0, 16.0, 18.0],
}
WITH_OUTLIER_DATA = {
    "group": ["a", "a", "a", "a", "a"],
    "value": [1.0, 2.0, 3.0, 4.0, 100.0],
}

# Mirrors boxplot()'s own canvas/margin constants, so a test can recompute the
# pixel coordinates a given stat *should* map to instead of just asserting an
# element exists.
_AREA = plot_area(800.0, 600.0, margin=(30.0, 40.0, 50.0, 60.0))


def _elements(chart: Chart, tag: str, class_prefix: str = "") -> list[dict[str, str]]:
    """Attributes of every ``tag`` element whose class starts with ``class_prefix``.

    Re-parsing the serialized SVG namespaces the tags, hence the ``}``-strip.
    """
    root = ET.fromstring(chart.to_string(pretty=False))
    return [
        element.attrib
        for element in root.iter()
        if element.tag.split("}")[-1] == tag and (element.get("class") or "").startswith(class_prefix)
    ]


def _y_scale(stats_by_category: list[BoxStats]) -> LinearScale:
    """Rebuild the y scale boxplot() derives from the rendered stats — the domain
    spans every whisker *and* every outlier, which is what keeps outliers on-canvas.
    """
    lows = [s.whisker_low for s in stats_by_category] + [o for s in stats_by_category for o in s.outliers]
    highs = [s.whisker_high for s in stats_by_category] + [o for s in stats_by_category for o in s.outliers]
    return LinearScale((min(lows), max(highs)), (_AREA.bottom, _AREA.top))


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


def test_boxplot_box_spans_exactly_q1_to_q3_in_pixels() -> None:
    """Pins the rect against the pixel positions q1/q3 map to, so swapping the two
    (or scaling either wrongly) fails — asserting only that a rect exists would not.
    """
    stats = box_stats(WITH_OUTLIER_DATA["value"], mode="1.5IQR")
    assert stats.q1 != stats.q3  # sanity: this dataset has a non-degenerate box
    chart = boxplot(WITH_OUTLIER_DATA, x="group", y="value", mode="1.5IQR")

    y_scale = _y_scale([stats])
    (box,) = _elements(chart, "rect", "series-1-marker")
    assert float(box["y"]) == pytest.approx(y_scale(stats.q3))  # q3 is the *top* edge (y grows downward)
    assert float(box["y"]) + float(box["height"]) == pytest.approx(y_scale(stats.q1))


def test_boxplot_shows_outlier_as_a_marker_when_present() -> None:
    chart = boxplot(WITH_OUTLIER_DATA, x="group", y="value", mode="1.5IQR")
    svg = chart.to_string()
    assert "<circle" in svg


def test_boxplot_shows_no_outlier_marker_when_none_present() -> None:
    chart = boxplot(NO_OUTLIER_DATA, x="group", y="value", mode="1.5IQR")
    svg = chart.to_string()
    assert "<circle" not in svg


def test_boxplot_median_line_sits_between_box_edges() -> None:
    """Renders and inspects the actual median <line> — the previous version only
    re-checked a box_stats invariant, so it passed without drawing anything.
    """
    stats = box_stats(WITH_OUTLIER_DATA["value"], mode="1.5IQR")
    chart = boxplot(WITH_OUTLIER_DATA, x="group", y="value", mode="1.5IQR")

    (box,) = _elements(chart, "rect", "series-1-marker")
    median_line = _elements(chart, "line", "series-1")[0]  # median is drawn before the whiskers
    top, bottom = float(box["y"]), float(box["y"]) + float(box["height"])
    assert top <= float(median_line["y1"]) <= bottom
    assert float(median_line["y1"]) == pytest.approx(_y_scale([stats])(stats.median))


def test_boxplot_draws_exactly_five_series_lines_per_category() -> None:
    """Median + 2 whisker stems + 2 caps, per category. Counting *all* <line>
    elements would not catch a missing box: the axes alone emit 12 of them.
    """
    chart = boxplot(NO_OUTLIER_DATA, x="group", y="value")
    assert len(_elements(chart, "line", "series-1")) == 5
    assert len(_elements(chart, "line", "series-2")) == 5


def test_boxplot_whisker_caps_sit_at_the_whisker_ends() -> None:
    stats = box_stats(NO_OUTLIER_DATA["value"][:5], mode="1.5IQR")
    chart = boxplot(NO_OUTLIER_DATA, x="group", y="value")
    y_scale = _y_scale([stats, box_stats(NO_OUTLIER_DATA["value"][5:], mode="1.5IQR")])

    _median, _upper_stem, upper_cap, _lower_stem, lower_cap = _elements(chart, "line", "series-1")
    for cap, whisker in ((upper_cap, stats.whisker_high), (lower_cap, stats.whisker_low)):
        assert float(cap["y1"]) == float(cap["y2"]) == pytest.approx(y_scale(whisker))  # horizontal, at the whisker end
        assert float(cap["x1"]) < float(cap["x2"])  # non-zero width


def test_boxplot_y_domain_includes_outliers() -> None:
    """An outlier outside the whisker range must still land inside the *plot area*
    (top=30..bottom=550), not merely the canvas — the looser canvas bound (0..600)
    would still pass even if the outlier were drawn over the axis margin.
    """
    stats = box_stats(WITH_OUTLIER_DATA["value"], mode="1.5IQR")
    assert stats.outliers  # sanity: this dataset actually produces an outlier
    chart = boxplot(WITH_OUTLIER_DATA, x="group", y="value", mode="1.5IQR")

    (outlier_marker,) = _elements(chart, "circle", "series-1-marker")
    cy = float(outlier_marker["cy"])
    assert _AREA.top <= cy <= _AREA.bottom
    assert cy == pytest.approx(_y_scale([stats])(stats.outliers[0]))


@pytest.mark.parametrize(
    "values",
    [[5.0], [7.0, 7.0, 7.0, 7.0]],
    ids=["single value", "all identical"],
)
def test_boxplot_degenerate_group_renders_a_zero_height_box(values: list[float]) -> None:
    """Pins today's behavior: when every quartile collapses to one value the box has
    height 0, so it is effectively invisible. Recorded so a future minimum-height
    change is a deliberate decision rather than an unnoticed regression.
    """
    data = {"group": ["a"] * len(values), "value": values}
    chart = boxplot(data, x="group", y="value")

    (box,) = _elements(chart, "rect", "series-1-marker")
    assert float(box["height"]) == 0.0
    assert float(box["width"]) > 0.0  # the box still spans the category band horizontally


def test_boxplot_modes_produce_different_whiskers_for_the_same_data() -> None:
    """ "각 mode별 렌더" is only meaningful if the mode actually changes the output:
    "extremes" stretches the whisker to the max and reports no outlier, while
    "1.5IQR" fences it off and reports the same point as an outlier.
    """
    extremes = box_stats(WITH_OUTLIER_DATA["value"], mode="extremes")
    iqr = box_stats(WITH_OUTLIER_DATA["value"], mode="1.5IQR")
    assert extremes.whisker_high != iqr.whisker_high
    assert extremes.outliers == [] and iqr.outliers == [100.0]

    extremes_chart = boxplot(WITH_OUTLIER_DATA, x="group", y="value", mode="extremes")
    iqr_chart = boxplot(WITH_OUTLIER_DATA, x="group", y="value", mode="1.5IQR")
    assert _elements(extremes_chart, "circle", "series-1-marker") == []
    assert len(_elements(iqr_chart, "circle", "series-1-marker")) == 1


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
