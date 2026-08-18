from __future__ import annotations

from datetime import datetime

import pytest

from svgplot.charts.line import lineplot

SINGLE_SERIES = {"day": [1, 2, 3, 4, 5], "value": [10.0, 15.0, 7.0, 20.0, 12.0]}
HUE_SERIES = {
    "day": [1, 2, 3, 4, 5, 1, 2, 3, 4, 5],
    "value": [10.0, 15.0, 7.0, 20.0, 12.0, 5.0, 8.0, 3.0, 10.0, 6.0],
    "group": ["a", "a", "a", "a", "a", "b", "b", "b", "b", "b"],
}


# ---------------------------------------------------------------------------
# single series
# ---------------------------------------------------------------------------


def test_lineplot_renders_a_single_series_with_default_theme() -> None:
    chart = lineplot(SINGLE_SERIES, x="day", y="value")
    svg = chart.to_string()
    assert "<path" in svg
    assert "series-1" in svg
    assert "series-2" not in svg  # only one series was drawn


def test_lineplot_draws_no_legend_without_hue() -> None:
    chart = lineplot(SINGLE_SERIES, x="day", y="value")
    svg = chart.to_string()
    # theme.css always emits the shared ".legend-text { ... }" CSS rule regardless of
    # whether any legend is drawn -- what must be absent is an actual legend <text> element.
    assert 'class="legend-text"' not in svg


# ---------------------------------------------------------------------------
# hue= multi-series + legend
# ---------------------------------------------------------------------------


def test_lineplot_draws_one_series_per_hue_value() -> None:
    chart = lineplot(HUE_SERIES, x="day", y="value", hue="group")
    svg = chart.to_string()
    assert svg.count("<path") == 2
    assert "series-1" in svg
    assert "series-2" in svg


def test_lineplot_generates_a_legend_entry_per_hue_value() -> None:
    chart = lineplot(HUE_SERIES, x="day", y="value", hue="group")
    svg = chart.to_string()
    assert svg.count('class="legend-text"') == 2
    assert ">a<" in svg
    assert ">b<" in svg


def test_lineplot_colors_each_hue_series_distinctly_via_css() -> None:
    chart = lineplot(HUE_SERIES, x="day", y="value", hue="group")
    svg = chart.to_string()
    style = svg.split("<style>")[1].split("</style>")[0]
    assert ".series-1 { stroke: #E69F00;" in style  # first two colorblind-safe default palette entries
    assert ".series-2 { stroke: #56B4E9;" in style


def test_lineplot_raises_key_error_for_missing_hue_column() -> None:
    with pytest.raises(KeyError):
        lineplot(HUE_SERIES, x="day", y="value", hue="not_a_column")


# ---------------------------------------------------------------------------
# datetime x -> TimeScale
# ---------------------------------------------------------------------------


def test_lineplot_uses_a_time_axis_for_datetime_x_values() -> None:
    data = {"ts": [datetime(2024, 1, 1), datetime(2024, 1, 8), datetime(2024, 1, 15)], "v": [1.0, 5.0, 2.0]}
    chart = lineplot(data, x="ts", y="v")
    svg = chart.to_string()
    assert "2024-01" in svg  # a date-formatted tick label, not a raw numeric one


# ---------------------------------------------------------------------------
# interpolate=
# ---------------------------------------------------------------------------


def test_lineplot_linear_default_connects_raw_points_without_smoothing() -> None:
    chart = lineplot(SINGLE_SERIES, x="day", y="value")
    svg = chart.to_string()
    path_d = svg.split('d="')[1].split('"')[0]
    # "linear" (the default) draws exactly one segment per consecutive pair of raw points:
    # 5 points -> 1 "M" + 4 "L" commands, not a smoothed curve with far more points.
    assert path_d.count("M ") + path_d.count("L ") == 5


def test_lineplot_interpolate_cubic_produces_a_smoothed_curve_with_more_points() -> None:
    chart = lineplot(SINGLE_SERIES, x="day", y="value", interpolate="cubic")
    svg = chart.to_string()
    path_d = svg.split('d="')[1].split('"')[0]
    assert path_d.count("L ") > 4  # smoothing densifies the path well beyond the 5 raw points


def test_lineplot_rejects_unknown_interpolate_method() -> None:
    with pytest.raises(ValueError, match="interpolation method"):
        lineplot(SINGLE_SERIES, x="day", y="value", interpolate="not-a-real-method")


# ---------------------------------------------------------------------------
# .save() produces human-readable (pretty-printed, semantically classed) SVG
# ---------------------------------------------------------------------------


def test_lineplot_save_produces_pretty_printed_svg_with_semantic_classes(tmp_path) -> None:
    chart = lineplot(HUE_SERIES, x="day", y="value", hue="group")
    path = tmp_path / "chart.svg"
    chart.save(str(path))
    content = path.read_text()
    assert content.startswith('<?xml version="1.0"')
    assert "\n  " in content  # indented, i.e. genuinely pretty-printed, not one compact line
    assert 'class="series-1' in content
    assert 'class="series-2' in content


# ---------------------------------------------------------------------------
# theme=
# ---------------------------------------------------------------------------


def test_lineplot_accepts_a_built_in_theme_preset_by_name() -> None:
    chart = lineplot(SINGLE_SERIES, x="day", y="value", theme="dark")
    svg = chart.to_string()
    assert "#1e1e1e" in svg  # theme.presets.PRESETS["dark"].background


def test_lineplot_accepts_an_explicit_theme_instance() -> None:
    from svgplot.theme.base import Theme

    chart = lineplot(SINGLE_SERIES, x="day", y="value", theme=Theme(background="#abcdef"))
    svg = chart.to_string()
    assert "#abcdef" in svg


def test_lineplot_rejects_unknown_theme_preset_name() -> None:
    with pytest.raises(KeyError, match="unknown theme preset"):
        lineplot(SINGLE_SERIES, x="day", y="value", theme="not-a-real-preset")


def test_lineplot_rejects_wrong_type_for_theme() -> None:
    with pytest.raises(TypeError):
        lineplot(SINGLE_SERIES, x="day", y="value", theme=123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# edge cases
# ---------------------------------------------------------------------------


def test_lineplot_rejects_empty_data() -> None:
    with pytest.raises(ValueError, match="at least one row"):
        lineplot({"day": [], "value": []}, x="day", y="value")


def test_lineplot_raises_key_error_for_missing_x_or_y_column() -> None:
    with pytest.raises(KeyError):
        lineplot(SINGLE_SERIES, x="not_a_column", y="value")
    with pytest.raises(KeyError):
        lineplot(SINGLE_SERIES, x="day", y="not_a_column")


def test_lineplot_drops_rows_with_missing_x_or_y() -> None:
    data = {"day": [1, 2, None, 4, 5], "value": [10.0, 15.0, 7.0, None, 12.0]}
    chart = lineplot(data, x="day", y="value")
    svg = chart.to_string()
    path_d = svg.split('d="')[1].split('"')[0]
    # only day=1, day=5 survive (day=2's y is fine but day=3's x is missing and day=4's y is
    # missing) -- wait: day=2/value=15 is fully present, so 3 points survive: 1, 2, 5.
    assert path_d.count("L ") == 2


def test_lineplot_handles_a_single_point_series_without_crashing() -> None:
    chart = lineplot({"day": [1], "value": [10.0]}, x="day", y="value")
    svg = chart.to_string()
    assert "<path" in svg
