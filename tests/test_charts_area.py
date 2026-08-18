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


def _band_edges(d: str) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Split a stacked band's path into its (x, y) top edge and bottom edge.

    The band runs left-to-right along its top, then right-to-left back along its
    bottom, so the second half of the coordinates is the bottom edge reversed.
    """
    pairs = [(float(px), float(py)) for px, py in re.findall(r"([\d.-]+),([\d.-]+)", d)]
    half = len(pairs) // 2
    return pairs[:half], list(reversed(pairs[half:]))


def test_areaplot_stacked_handles_mismatched_x_values_as_zero() -> None:
    """group "a" has no row at day=4, group "b" has no row at day=3 -- the union
    of x values (1,2,3,4) is used, and a missing (group, day) pair contributes 0
    to that group's stack: its band has zero height there (top == bottom), rather
    than the x value being dropped or an error raised.
    """
    chart = areaplot(MISMATCHED_HUE_SERIES, x="day", y="value", hue="group", stacked=True)
    d_a, d_b = _path_ds(chart.to_string())

    a_tops, a_bottoms = _band_edges(d_a)
    b_tops, b_bottoms = _band_edges(d_b)
    # 4 distinct x values in the union -> every band spans all 4, both groups alike
    assert len(a_tops) == len(b_tops) == 4
    assert [px for px, _ in a_tops] == [px for px, _ in b_tops]

    # group "a" is missing day=4 (union index 3); group "b" is missing day=3 (index 2)
    assert a_tops[3][1] == pytest.approx(a_bottoms[3][1])
    assert b_tops[2][1] == pytest.approx(b_bottoms[2][1])
    # ...and the x values that ARE present still carry real height
    assert a_tops[0][1] < a_bottoms[0][1]  # SVG y grows downward: top above bottom
    assert b_tops[0][1] < b_bottoms[0][1]


# ---------------------------------------------------------------------------
# repeated x values within a series
# ---------------------------------------------------------------------------

DUPLICATE_X_SERIES = {
    "day": [1, 1, 2, 1, 2],
    "value": [10.0, 20.0, 5.0, 1.0, 2.0],
    "group": ["a", "a", "a", "b", "b"],
}


def test_areaplot_sums_rows_sharing_an_x_within_a_series() -> None:
    """Regression: the stacked path looked repeated x values up in a dict, so a
    second row at the same x silently overwrote the first (group "a" day=1 kept
    only 20.0, dropping 10.0). Both rows must contribute: 10 + 20 = 30.
    """
    chart = areaplot(DUPLICATE_X_SERIES, x="day", y="value", hue="group", stacked=True)
    d_a, _ = _path_ds(chart.to_string())
    a_tops, a_bottoms = _band_edges(d_a)

    # Two distinct x values survive aggregation, not three rows' worth of points.
    assert len(a_tops) == 2
    # group "a" spans 0..30 at day=1, so its top sits at the very top of the y
    # domain (max cumulative is 30 + group "b"'s 1 = 31) and its bottom at the
    # baseline. Had the 10.0 been dropped, the top would be lower down.
    baseline_y = a_bottoms[0][1]
    top_y = a_tops[0][1]
    assert baseline_y == pytest.approx(550.0)
    assert top_y == pytest.approx(550.0 - (30.0 / 31.0) * 520.0)


def test_areaplot_sums_repeated_x_identically_stacked_and_unstacked() -> None:
    """Aggregation happens before the stacked/unstacked split, so identical input
    can never mean two different things depending on the mode.
    """
    stacked = areaplot(DUPLICATE_X_SERIES, x="day", y="value", hue="group", stacked=True)
    unstacked = areaplot(DUPLICATE_X_SERIES, x="day", y="value", hue="group", stacked=False)

    # group "b" never repeats an x, so it stacks on nothing and both modes agree
    # exactly; group "a"'s two day=1 rows collapse to one point in both modes.
    stacked_a_tops, _ = _band_edges(_path_ds(stacked.to_string())[0])
    unstacked_a_points = re.findall(r"[\d.-]+,[\d.-]+", _path_ds(unstacked.to_string())[0])
    assert len(stacked_a_tops) == 2
    # M + 1 L along the top, then 2 baseline L's -> 4 pairs, i.e. no vertical
    # jump from a duplicated x
    assert len(unstacked_a_points) == 4


# ---------------------------------------------------------------------------
# degenerate domains
# ---------------------------------------------------------------------------


def test_areaplot_single_point_collapses_to_a_zero_width_path() -> None:
    """A lone point gives x domain (3, 3); LinearScale maps a zero-width domain to
    its range's midpoint, so the area degenerates to a vertical sliver rather than
    raising. Pinned so a future change here is deliberate.
    """
    chart = areaplot({"day": [3], "value": [7.0]}, x="day", y="value")
    (d,) = _path_ds(chart.to_string())
    xs = {px for px, _ in re.findall(r"([\d.-]+),([\d.-]+)", d)}
    assert xs == {"410"}  # every vertex shares the midpoint x
    assert d.endswith("Z")


def test_areaplot_all_zero_values_collapse_to_a_flat_path() -> None:
    """All-zero y gives y domain (0, 0) -- again the midpoint, so the area is flat
    (zero height) instead of filling to the baseline. Pinned as current behavior.
    """
    chart = areaplot({"day": [1, 2, 3], "value": [0.0, 0.0, 0.0]}, x="day", y="value")
    (d,) = _path_ds(chart.to_string())
    ys = {py for _, py in re.findall(r"([\d.-]+),([\d.-]+)", d)}
    assert ys == {"290"}  # every vertex, including the baseline, shares one y
    assert d.endswith("Z")


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
