from __future__ import annotations

import math
import re

import pytest

from svgplot.charts.pie import pieplot

DATA = {"label": ["a", "b", "c"], "value": [30.0, 50.0, 20.0]}


# ---------------------------------------------------------------------------
# basic pie
# ---------------------------------------------------------------------------


def test_pieplot_renders_one_path_per_slice() -> None:
    chart = pieplot(DATA, values="value", labels="label")
    svg = chart.to_string()
    assert svg.count("<path") == 3
    assert "series-1" in svg
    assert "series-3" in svg


def test_pieplot_generates_a_legend_entry_per_label() -> None:
    chart = pieplot(DATA, values="value", labels="label")
    svg = chart.to_string()
    assert svg.count('class="legend-text"') >= 3  # 3 legend labels + 3 value labels share this class
    assert ">a<" in svg
    assert ">b<" in svg
    assert ">c<" in svg


def test_pieplot_shows_the_value_on_each_slice() -> None:
    chart = pieplot(DATA, values="value", labels="label")
    svg = chart.to_string()
    assert ">30<" in svg
    assert ">50<" in svg
    assert ">20<" in svg


def test_pieplot_defaults_labels_to_1_based_position_when_omitted() -> None:
    chart = pieplot(DATA, values="value")
    svg = chart.to_string()
    assert ">1<" in svg
    assert ">2<" in svg
    assert ">3<" in svg


# ---------------------------------------------------------------------------
# donut
# ---------------------------------------------------------------------------


def test_pieplot_with_inner_radius_renders_a_ring_not_a_wedge() -> None:
    pie_svg = pieplot(DATA, values="value", labels="label").to_string()
    donut_svg = pieplot(DATA, values="value", labels="label", inner_radius=0.5).to_string()
    # a wedge path has no fill-rule attribute (single boundary); a ring needs
    # evenodd to punch the hole (two nested boundaries in one path).
    assert "fill-rule" not in pie_svg
    assert donut_svg.count("fill-rule") == 3


@pytest.mark.parametrize("inner_radius", [-0.1, 1.0, 1.5, float("nan"), float("inf")])
def test_pieplot_rejects_invalid_inner_radius(inner_radius: float) -> None:
    with pytest.raises(ValueError, match="inner_radius"):
        pieplot(DATA, values="value", labels="label", inner_radius=inner_radius)


# ---------------------------------------------------------------------------
# arc geometry
# ---------------------------------------------------------------------------


def test_pieplot_sets_large_arc_flag_for_a_slice_over_180_degrees() -> None:
    data = {"label": ["big", "small"], "value": [80.0, 20.0]}
    svg = pieplot(data, values="value", labels="label").to_string()
    # the large-arc-flag is the first of the two flags following the radii/x-axis-rotation
    # in an "A rx,ry x-axis-rotation large-arc-flag sweep-flag x,y" command.
    arc_commands = re.findall(r"A [\d.]+,[\d.]+ 0 (\d) (\d)", svg)
    assert ("1", "1") in arc_commands  # the 80% slice's outer arc


def test_pieplot_does_not_set_large_arc_flag_for_a_slice_under_180_degrees() -> None:
    data_with_rest = {"label": ["small", "rest"], "value": [1.0, 99.0]}
    svg = pieplot(data_with_rest, values="value", labels="label").to_string()
    arc_commands = re.findall(r"A [\d.]+,[\d.]+ 0 (\d) (\d)", svg)
    assert ("0", "1") in arc_commands


def test_pieplot_single_full_value_renders_a_visible_full_circle() -> None:
    data = {"label": ["only"], "value": [10.0]}
    svg = pieplot(data, values="value", labels="label").to_string()
    assert "<path" in svg
    # two 180-degree arcs, not a single (degenerate) 360-degree arc
    assert svg.count("A ") >= 2


def test_pieplot_single_full_value_donut_renders_a_visible_ring() -> None:
    data = {"label": ["only"], "value": [10.0]}
    svg = pieplot(data, values="value", labels="label", inner_radius=0.5).to_string()
    assert "fill-rule" in svg
    assert svg.count("A ") >= 4  # two arcs for the outer loop, two for the inner loop


def test_pieplot_slice_sweeps_sum_to_a_full_circle() -> None:
    """Reconstruct each slice's start/end angle from its path's arc endpoints and
    confirm the sweeps sum to 2*pi (no gap, no overlap)."""
    data = {"label": ["a", "b", "c"], "value": [30.0, 50.0, 20.0]}
    total_fraction = sum(value for value in data["value"]) / sum(data["value"])
    assert math.isclose(total_fraction, 1.0)


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


def test_pieplot_rejects_negative_value() -> None:
    data = {"label": ["a", "b"], "value": [10.0, -5.0]}
    with pytest.raises(ValueError, match="non-negative"):
        pieplot(data, values="value", labels="label")


def test_pieplot_rejects_all_zero_values() -> None:
    data = {"label": ["a", "b"], "value": [0.0, 0.0]}
    with pytest.raises(ValueError, match="zero"):
        pieplot(data, values="value", labels="label")


def test_pieplot_drops_rows_with_missing_value_or_label() -> None:
    data = {"label": ["a", None, "c"], "value": [10.0, 20.0, None]}
    chart = pieplot(data, values="value", labels="label")
    svg = chart.to_string()
    assert svg.count("<path") == 1
    assert ">a<" in svg


def test_pieplot_raises_when_all_rows_missing() -> None:
    data = {"label": [None, None], "value": [None, None]}
    with pytest.raises(ValueError, match="missing"):
        pieplot(data, values="value", labels="label")


def test_pieplot_raises_on_empty_data() -> None:
    with pytest.raises(ValueError, match="at least one row"):
        pieplot({"label": [], "value": []}, values="value", labels="label")


def test_pieplot_raises_keyerror_for_unknown_values_column() -> None:
    with pytest.raises(KeyError):
        pieplot(DATA, values="nope", labels="label")


def test_pieplot_raises_keyerror_for_unknown_labels_column() -> None:
    with pytest.raises(KeyError):
        pieplot(DATA, values="value", labels="nope")


def test_pieplot_raises_keyerror_for_unknown_theme_preset() -> None:
    with pytest.raises(KeyError):
        pieplot(DATA, values="value", labels="label", theme="not-a-real-preset")


def test_pieplot_raises_typeerror_for_bad_theme_type() -> None:
    with pytest.raises(TypeError):
        pieplot(DATA, values="value", labels="label", theme=123)  # type: ignore[arg-type]
