from __future__ import annotations

from datetime import datetime

from svgplot._svg import SvgDocument
from svgplot.charts._axes import render_x_axis, render_y_axis
from svgplot.charts._layout import plot_area
from svgplot.scales import CategoricalScale, LinearScale, TimeScale

_AREA = plot_area(800.0, 600.0, margin=60.0)


def test_render_x_axis_categorical_places_ticks_at_band_centers_with_raw_labels() -> None:
    """The CategoricalScale path is shared infrastructure future chart types (bar
    in particular) will need very soon, but line charts never exercise it directly.
    """
    scale = CategoricalScale(["a", "b", "c"], (_AREA.left, _AREA.right))
    document = SvgDocument()
    render_x_axis(document, scale, _AREA)

    labels = document.root.findall(".//text[@class='tick-label']")
    assert [label.text for label in labels] == ["a", "b", "c"]

    grid_lines = document.root.findall(".//line[@class='grid-line']")
    assert len(grid_lines) == 3
    expected_x = [str(round(scale.center(category), 6)) for category in ("a", "b", "c")]
    assert [round(float(line.get("x1")), 6) for line in grid_lines] == [float(x) for x in expected_x]


def test_render_y_axis_categorical_places_ticks_at_band_centers_with_raw_labels() -> None:
    scale = CategoricalScale(["low", "mid", "high"], (_AREA.bottom, _AREA.top))
    document = SvgDocument()
    render_y_axis(document, scale, _AREA)

    labels = document.root.findall(".//text[@class='tick-label']")
    assert [label.text for label in labels] == ["low", "mid", "high"]


def test_render_x_axis_categorical_shows_every_category_not_a_sampled_subset() -> None:
    categories = [f"c{i}" for i in range(12)]
    scale = CategoricalScale(categories, (_AREA.left, _AREA.right))
    document = SvgDocument()
    render_x_axis(document, scale, _AREA, tick_count=5)

    labels = document.root.findall(".//text[@class='tick-label']")
    assert [label.text for label in labels] == categories


def test_render_x_axis_linear_labels_are_formatted_coordinates_not_raw_floats() -> None:
    scale = LinearScale((0.0, 100.0), (_AREA.left, _AREA.right))
    document = SvgDocument()
    render_x_axis(document, scale, _AREA)

    labels = [label.text for label in document.root.findall(".//text[@class='tick-label']")]
    assert all("." not in label or not label.endswith("0") for label in labels)


def test_render_x_axis_time_labels_are_iso_dates() -> None:
    scale = TimeScale((datetime(2024, 1, 1), datetime(2024, 1, 31)), (_AREA.left, _AREA.right))
    document = SvgDocument()
    render_x_axis(document, scale, _AREA)

    labels = [label.text for label in document.root.findall(".//text[@class='tick-label']")]
    assert all(label is not None and len(label) == len("2024-01-01") for label in labels)


def test_render_x_axis_tick_length_from_theme_moves_tick_line_and_label() -> None:
    scale = LinearScale((0.0, 100.0), (_AREA.left, _AREA.right))
    document_default = SvgDocument()
    render_x_axis(document_default, scale, _AREA)
    document_custom = SvgDocument()
    render_x_axis(document_custom, scale, _AREA, tick_length=20.0)

    default_tick = document_default.root.findall(".//line[@class='tick-line']")[0]
    custom_tick = document_custom.root.findall(".//line[@class='tick-line']")[0]
    assert float(custom_tick.get("y2")) - float(custom_tick.get("y1")) == 20.0
    assert float(custom_tick.get("y2")) != float(default_tick.get("y2"))


def test_render_y_axis_tick_length_zero_collapses_tick_line() -> None:
    scale = LinearScale((0.0, 100.0), (_AREA.bottom, _AREA.top))
    document = SvgDocument()
    render_y_axis(document, scale, _AREA, tick_length=0.0)

    tick_line = document.root.findall(".//line[@class='tick-line']")[0]
    assert tick_line.get("x1") == tick_line.get("x2")
