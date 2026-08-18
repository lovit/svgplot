from __future__ import annotations

import pytest

from svgplot.charts._layout import format_coord, plot_area, resolve_margin


def test_resolve_margin_single_number_applies_to_all_four_sides() -> None:
    assert resolve_margin(60.0) == (60.0, 60.0, 60.0, 60.0)


def test_resolve_margin_four_tuple_gives_each_side_independently() -> None:
    assert resolve_margin((1.0, 2.0, 3.0, 4.0)) == (1.0, 2.0, 3.0, 4.0)


def test_resolve_margin_rejects_malformed_input() -> None:
    with pytest.raises(ValueError, match="margin"):
        resolve_margin((1.0, 2.0, 3.0))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="margin"):
        resolve_margin("60")  # type: ignore[arg-type]


def test_plot_area_computes_the_rect_inside_the_margin() -> None:
    area = plot_area(800.0, 600.0, margin=(30.0, 40.0, 50.0, 60.0))
    assert area.left == 60.0
    assert area.top == 30.0
    assert area.right == 800.0 - 40.0
    assert area.bottom == 600.0 - 50.0
    assert area.width == area.right - area.left
    assert area.height == area.bottom - area.top


def test_plot_area_rejects_a_margin_too_large_for_the_canvas() -> None:
    with pytest.raises(ValueError, match="non-positive"):
        plot_area(100.0, 100.0, margin=60.0)


def test_format_coord_rejects_non_finite() -> None:
    with pytest.raises(ValueError, match="finite"):
        format_coord(float("nan"))
    with pytest.raises(ValueError, match="finite"):
        format_coord(float("inf"))


def test_format_coord_rejects_non_numeric() -> None:
    with pytest.raises(ValueError):
        format_coord("not a number")  # type: ignore[arg-type]


def test_format_coord_formats_clean_literals() -> None:
    assert format_coord(120.0) == "120"
    assert format_coord(120.5) == "120.5"
