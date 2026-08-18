from __future__ import annotations

import pytest

from svgplot.charts.scatter import scatterplot

PLAIN = {"x": [1, 2, 3, 4, 5], "y": [2.0, 4.0, 1.0, 5.0, 3.0]}
HUE_DATA = {
    "x": [1, 2, 3, 4, 5, 1, 2, 3, 4, 5],
    "y": [2.0, 4.0, 1.0, 5.0, 3.0, 6.0, 8.0, 5.0, 9.0, 7.0],
    "group": ["a", "a", "a", "a", "a", "b", "b", "b", "b", "b"],
}
SIZE_DATA = {"x": [1, 2, 3, 4, 5], "y": [2.0, 4.0, 1.0, 5.0, 3.0], "weight": [1.0, 5.0, 3.0, 2.0, 4.0]}
HUE_AND_SIZE_DATA = {**HUE_DATA, "weight": [1.0, 5.0, 3.0, 2.0, 4.0, 4.0, 2.0, 3.0, 5.0, 1.0]}


# ---------------------------------------------------------------------------
# plain scatter (neither hue nor size)
# ---------------------------------------------------------------------------


def test_scatterplot_renders_a_point_per_row_with_default_theme() -> None:
    chart = scatterplot(PLAIN, x="x", y="y")
    svg = chart.to_string()
    assert svg.count("<circle") == len(PLAIN["x"])
    assert "series-1" in svg


def test_scatterplot_draws_no_legend_without_hue_or_size() -> None:
    chart = scatterplot(PLAIN, x="x", y="y")
    svg = chart.to_string()
    assert 'class="legend-text"' not in svg


# ---------------------------------------------------------------------------
# hue= only
# ---------------------------------------------------------------------------


def test_scatterplot_colors_points_by_hue_group() -> None:
    chart = scatterplot(HUE_DATA, x="x", y="y", hue="group")
    svg = chart.to_string()
    assert svg.count("<circle") == len(HUE_DATA["x"])
    assert "series-1" in svg
    assert "series-2" in svg


def test_scatterplot_generates_a_legend_entry_per_hue_value() -> None:
    chart = scatterplot(HUE_DATA, x="x", y="y", hue="group")
    svg = chart.to_string()
    assert svg.count('class="legend-text"') == 2
    assert ">a<" in svg
    assert ">b<" in svg


# ---------------------------------------------------------------------------
# size= only
# ---------------------------------------------------------------------------


def test_scatterplot_maps_size_to_marker_radius() -> None:
    chart = scatterplot(SIZE_DATA, x="x", y="y", size="weight")
    svg = chart.to_string()
    # 5 data points + 3 size-legend samples (min/mid/max)
    assert svg.count("<circle") == 5 + 3


def test_scatterplot_size_legend_shows_min_mid_max_labels() -> None:
    chart = scatterplot(SIZE_DATA, x="x", y="y", size="weight")
    svg = chart.to_string()
    assert svg.count('class="legend-text"') == 3
    assert ">1<" in svg  # min
    assert ">5<" in svg  # max
    assert ">3<" in svg  # mid


def test_scatterplot_constant_size_column_does_not_crash() -> None:
    """min == max in the size column has no ratio to scale by — every marker
    (and every legend sample) should collapse to the theme's base marker size
    rather than raising a ZeroDivisionError.
    """
    chart = scatterplot({"x": [1, 2], "y": [1.0, 2.0], "s": [5.0, 5.0]}, x="x", y="y", size="s")
    svg = chart.to_string()
    assert svg.count("<circle") == 2 + 1  # samples dedupe to a single legend row


# ---------------------------------------------------------------------------
# hue= and size= combined
# ---------------------------------------------------------------------------


def test_scatterplot_supports_hue_and_size_together() -> None:
    chart = scatterplot(HUE_AND_SIZE_DATA, x="x", y="y", hue="group", size="weight")
    svg = chart.to_string()
    assert svg.count("<circle") == len(HUE_AND_SIZE_DATA["x"]) + 3
    # both legends present: 2 hue rows + 3 size rows
    assert svg.count('class="legend-text"') == 2 + 3


# ---------------------------------------------------------------------------
# missing values / edge cases
# ---------------------------------------------------------------------------


def test_scatterplot_drops_rows_with_missing_x_or_y() -> None:
    chart = scatterplot({"x": [1, None, 3], "y": [1.0, 2.0, None]}, x="x", y="y")
    svg = chart.to_string()
    assert svg.count("<circle") == 1


def test_scatterplot_drops_rows_with_missing_size_value() -> None:
    chart = scatterplot({"x": [1, 2, 3], "y": [1.0, 2.0, 3.0], "s": [1.0, None, 3.0]}, x="x", y="y", size="s")
    svg = chart.to_string()
    assert svg.count("<circle") == 2 + 3  # 2 surviving points + 3 size-legend samples


def test_scatterplot_rejects_data_with_no_rows() -> None:
    with pytest.raises(ValueError, match="at least one row"):
        scatterplot({"x": [], "y": []}, x="x", y="y")


def test_scatterplot_rejects_all_rows_missing() -> None:
    with pytest.raises(ValueError, match="usable x/y"):
        scatterplot({"x": [None, None], "y": [None, None]}, x="x", y="y")


def test_scatterplot_rejects_unknown_x_column() -> None:
    with pytest.raises(KeyError):
        scatterplot(PLAIN, x="nope", y="y")


def test_scatterplot_rejects_unknown_size_column() -> None:
    with pytest.raises(KeyError, match="size"):
        scatterplot(PLAIN, x="x", y="y", size="nope")


def test_scatterplot_rejects_unknown_hue_column() -> None:
    with pytest.raises(KeyError, match="hue"):
        scatterplot(PLAIN, x="x", y="y", hue="nope")


def test_scatterplot_rejects_unknown_theme_preset() -> None:
    with pytest.raises(KeyError, match="unknown theme preset"):
        scatterplot(PLAIN, x="x", y="y", theme="not-a-preset")


def test_scatterplot_rejects_bad_theme_type() -> None:
    with pytest.raises(TypeError):
        scatterplot(PLAIN, x="x", y="y", theme=123)  # type: ignore[arg-type]


def test_size_legend_sits_below_the_hue_legend_even_if_the_row_height_changes(monkeypatch) -> None:
    """scatter stacks its size legend beneath the hue legend. It used to compute the
    offset from a hardcoded copy of _legend._ROW_HEIGHT, so changing that constant
    would silently overlap the two. render_legend now reports its own consumed height,
    which this pins by enlarging the constant and asserting they still don't collide.
    """
    import re

    from svgplot.charts import _legend

    # Far larger than scatter's own _SIZE_LEGEND_GAP, so a stale hardcoded row
    # height cannot be masked by the gap happening to clear the last row.
    monkeypatch.setattr(_legend, "_ROW_HEIGHT", 200.0)
    svg = scatterplot(HUE_AND_SIZE_DATA, x="x", y="y", hue="group", size="weight").to_string()

    # Hue legend rows are the swatch <rect>s carrying a series class (the only other
    # <rect> is the full-canvas plot background). Size samples are the legend <circle>s.
    swatch_ys = [
        float(re.search(r'y="([\d.]+)"', tag).group(1)) for tag in re.findall(r"<rect[^>]*/>", svg) if "series-" in tag
    ]
    sample_ys = [float(cy) for cy in re.findall(r'<circle[^>]*cy="([\d.]+)"[^>]*/>', svg)]
    legend_x = max(float(x) for x in re.findall(r'<rect[^>]*x="([\d.]+)"[^>]*series-', svg) or ["0"])
    sample_ys = [
        float(re.search(r'cy="([\d.]+)"', tag).group(1))
        for tag in re.findall(r"<circle[^>]*/>", svg)
        if float(re.search(r'cx="([\d.]+)"', tag).group(1)) >= legend_x
    ]

    assert len(swatch_ys) == 2, "expected one swatch per hue group"
    assert sample_ys, "expected size-legend sample circles"
    assert min(sample_ys) > max(swatch_ys)
