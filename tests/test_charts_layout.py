from __future__ import annotations

import pytest

from svgplot.charts._layout import (
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    MARGIN_WITH_SIDE_LEGEND,
    format_coord,
    format_value_label,
    new_canvas,
    plot_area,
    resolve_margin,
)


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


def test_a_new_canvas_carries_the_background_every_theme_styles() -> None:
    """The part of the preamble worth centralising. Fifteen charts wrote these six lines and
    the background rect is the one a chart could plausibly forget -- nothing else breaks, the
    chart simply renders on whatever the host page's background happens to be, which nobody
    notices until the page is dark."""
    document, _ = new_canvas(60.0)
    svg = document.to_string()

    assert svg.count('class="plot-background"') == 1
    assert f'width="{format_coord(DEFAULT_WIDTH)}"' in svg
    assert f'height="{format_coord(DEFAULT_HEIGHT)}"' in svg


@pytest.mark.parametrize("margin", [60.0, (30.0, 40.0, 50.0, 60.0), MARGIN_WITH_SIDE_LEGEND])
def test_the_area_a_new_canvas_returns_is_the_one_the_margin_asks_for(margin: object) -> None:
    """The helper returns both halves, so the margin has to reach the area and not only the
    document -- a version that ignored it would still draw a correct-looking background."""
    _, area = new_canvas(margin)  # type: ignore[arg-type]

    assert area == plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=margin)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "expected"),
    [(30.0, "30"), (30.5, "30.5"), (1e-7, "1e-07"), (0.123456789, "0.123456789"), (-0.0, "0")],
)
def test_a_value_label_keeps_the_value_it_names(value: float, expected: str) -> None:
    """Not ``format_coord``, which rounds to six decimals because it formats *coordinates*.
    Rounding a label rewrites the data it names -- ``1e-7`` becomes ``"0"`` -- and a pie slice
    labelled zero is a lie about the row it came from. Integral values still lose the ``.0``
    so the common case reads as ``30``."""
    assert format_value_label(value) == expected


def test_a_value_label_and_a_coordinate_are_formatted_differently_on_purpose() -> None:
    """The two were separate functions in two charts each, and merging them into one would be
    the obvious next simplification and the wrong one."""
    assert format_value_label(0.123456789) != format_coord(0.123456789)
    assert format_coord(0.123456789) == "0.123457"
