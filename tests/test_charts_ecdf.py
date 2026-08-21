from __future__ import annotations

import re
from itertools import pairwise

import pytest

from _svg_probe import tags
from svgplot.charts._layout import DEFAULT_HEIGHT, DEFAULT_WIDTH, MARGIN_WITH_LEGEND, MARGIN_WITHOUT_LEGEND, plot_area
from svgplot.charts.ecdf import ecdfplot

SINGLE_SERIES = {"value": [1.0, 2.0, 3.0, 4.0]}
HUE_SERIES = {
    "value": [1.0, 2.0, 3.0, 4.0, 1.0, 2.0],
    "group": ["a", "a", "a", "a", "b", "b"],
}

_VERTEX_RE = re.compile(r"[ML] (-?[\d.]+),(-?[\d.]+)")

AREA = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=MARGIN_WITHOUT_LEGEND)
AREA_WITH_LEGEND = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=MARGIN_WITH_LEGEND)


def _series_vertices(svg: str) -> list[list[tuple[float, float]]]:
    """The (x, y) pixel vertices of every ``ecdf-series`` path, in document order."""
    return [[(float(vx), float(vy)) for vx, vy in _VERTEX_RE.findall(path["d"])] for path in tags(svg, "path", "ecdf-series")]


# ---------------------------------------------------------------------------
# step geometry
# ---------------------------------------------------------------------------


def test_ecdfplot_staircase_starts_at_the_baseline_and_reaches_the_top() -> None:
    """The y axis runs 0..1 over the inverted pixel range, so a proportion ECDF must
    begin exactly on the plot floor and finish exactly on its ceiling."""
    (vertices,) = _series_vertices(ecdfplot(SINGLE_SERIES, x="value").to_string())

    assert vertices[0][1] == pytest.approx(AREA.bottom)
    assert vertices[-1][1] == pytest.approx(AREA.top)


def test_ecdfplot_is_monotonically_non_decreasing() -> None:
    """Pixel y grows downward, so a non-decreasing distribution is a non-increasing
    sequence of pixel y values."""
    (vertices,) = _series_vertices(ecdfplot(SINGLE_SERIES, x="value").to_string())

    ys = [y for _, y in vertices]
    assert all(later <= earlier for earlier, later in pairwise(ys))
    xs = [x for x, _ in vertices]
    assert all(later >= earlier for earlier, later in pairwise(xs))


def test_ecdfplot_alternates_horizontal_treads_and_vertical_risers() -> None:
    """Every segment is axis-aligned: a staircase never emits a diagonal."""
    (vertices,) = _series_vertices(ecdfplot(SINGLE_SERIES, x="value").to_string())

    for (x1, y1), (x2, y2) in pairwise(vertices):
        assert x1 == pytest.approx(x2) or y1 == pytest.approx(y2)


def test_ecdfplot_ties_produce_one_riser_of_the_combined_height() -> None:
    """The classic ECDF bug: stepping per *value* rather than per *distinct* value
    puts k risers of 1/n at the same x, which draws as overlapping zero-width
    segments instead of the single 2/n riser the data actually has.

    [1, 1, 2] has two distinct values, so exactly 4 vertices — start, riser to 2/3,
    tread, riser to 1.0 — and the riser at x=1 must land two thirds of the way up.
    """
    (vertices,) = _series_vertices(ecdfplot({"value": [1.0, 1.0, 2.0]}, x="value").to_string())

    assert len(vertices) == 4
    two_thirds_up = AREA.bottom + (2 / 3) * (AREA.top - AREA.bottom)
    assert vertices == [
        pytest.approx((AREA.left, AREA.bottom)),
        pytest.approx((AREA.left, two_thirds_up)),
        pytest.approx((AREA.right, two_thirds_up)),
        pytest.approx((AREA.right, AREA.top)),
    ]


def test_ecdfplot_untied_values_each_get_their_own_riser() -> None:
    """Counterpart to the tie test: 3 distinct values give 3 risers (6 vertices),
    so the tie collapsing above isn't just dropping steps unconditionally."""
    (vertices,) = _series_vertices(ecdfplot({"value": [1.0, 2.0, 3.0]}, x="value").to_string())

    assert len(vertices) == 6
    riser_heights = [vertices[1][1], vertices[3][1], vertices[5][1]]
    thirds = [AREA.bottom + fraction * (AREA.top - AREA.bottom) for fraction in (1 / 3, 2 / 3, 1.0)]
    assert riser_heights == pytest.approx(thirds)


# ---------------------------------------------------------------------------
# stat= and complementary=
# ---------------------------------------------------------------------------


def test_ecdfplot_count_stat_reaches_n_instead_of_one() -> None:
    """Under stat="count" the top of the axis is n, so the final riser still lands on
    the ceiling — what changes is the tick labels, not the curve's shape."""
    svg = ecdfplot(SINGLE_SERIES, x="value", stat="count").to_string()
    (vertices,) = _series_vertices(svg)

    assert vertices[-1][1] == pytest.approx(AREA.top)
    assert ">4<" in svg  # the y axis is labelled up to n == 4, not up to 1


def test_ecdfplot_complementary_descends_from_the_top_to_zero() -> None:
    (vertices,) = _series_vertices(ecdfplot(SINGLE_SERIES, x="value", complementary=True).to_string())

    assert vertices[0][1] == pytest.approx(AREA.top)
    assert vertices[-1][1] == pytest.approx(AREA.bottom)
    ys = [y for _, y in vertices]
    assert all(later >= earlier for earlier, later in pairwise(ys))


def test_ecdfplot_complementary_mirrors_the_plain_curve() -> None:
    """1 - F is the plain curve reflected about the vertical midpoint, so each vertex's
    pixel y must reflect across the plot area's centre."""
    (plain,) = _series_vertices(ecdfplot(SINGLE_SERIES, x="value").to_string())
    (survival,) = _series_vertices(ecdfplot(SINGLE_SERIES, x="value", complementary=True).to_string())

    assert len(plain) == len(survival)
    for (px, py), (sx, sy) in zip(plain, survival, strict=True):
        assert px == pytest.approx(sx)
        assert py + sy == pytest.approx(AREA.top + AREA.bottom)


# ---------------------------------------------------------------------------
# hue grouping
# ---------------------------------------------------------------------------


def test_ecdfplot_draws_one_series_and_one_legend_row_per_hue_group() -> None:
    svg = ecdfplot(HUE_SERIES, x="value", hue="group").to_string()

    assert len(_series_vertices(svg)) == 2
    assert svg.count('class="legend-text"') == 2
    assert ">a<" in svg
    assert ">b<" in svg


def test_ecdfplot_every_hue_group_reaches_full_height_under_proportion() -> None:
    """Each group is normalised by its own n, so a 4-point and a 2-point group both
    top out at 1.0 — that is what makes proportion curves comparable."""
    series = _series_vertices(ecdfplot(HUE_SERIES, x="value", hue="group").to_string())

    for vertices in series:
        assert vertices[-1][1] == pytest.approx(AREA_WITH_LEGEND.top)


def test_ecdfplot_count_stat_shares_one_axis_across_hue_groups() -> None:
    """Under stat="count" the axis is scaled to the largest group, so the smaller
    group must stop short of the ceiling rather than being rescaled to it."""
    bigger, smaller = _series_vertices(ecdfplot(HUE_SERIES, x="value", hue="group", stat="count").to_string())

    assert bigger[-1][1] == pytest.approx(AREA_WITH_LEGEND.top)
    assert smaller[-1][1] > AREA_WITH_LEGEND.top
    half_up = AREA_WITH_LEGEND.bottom + 0.5 * (AREA_WITH_LEGEND.top - AREA_WITH_LEGEND.bottom)
    assert smaller[-1][1] == pytest.approx(half_up)  # 2 of 4


def test_ecdfplot_draws_no_legend_without_hue() -> None:
    assert 'class="legend-text"' not in ecdfplot(SINGLE_SERIES, x="value").to_string()


# ---------------------------------------------------------------------------
# missing values and validation
# ---------------------------------------------------------------------------


def test_ecdfplot_drops_missing_values_before_counting() -> None:
    """A dropped row must not dilute the proportions: 2 usable rows of 4 still reach
    1.0, at the same heights as a clean 2-row dataset."""
    (with_gaps,) = _series_vertices(ecdfplot({"value": [1.0, None, float("nan"), 2.0]}, x="value").to_string())
    (clean,) = _series_vertices(ecdfplot({"value": [1.0, 2.0]}, x="value").to_string())

    assert with_gaps == pytest.approx(clean)


def test_ecdfplot_rejects_an_unknown_stat() -> None:
    with pytest.raises(ValueError, match="stat must be one of"):
        ecdfplot(SINGLE_SERIES, x="value", stat="density")


def test_ecdfplot_rejects_empty_data() -> None:
    with pytest.raises(ValueError, match="at least one row"):
        ecdfplot({"value": []}, x="value")


def test_ecdfplot_rejects_data_that_is_all_missing() -> None:
    with pytest.raises(ValueError, match="after dropping missing values"):
        ecdfplot({"value": [None, float("nan")]}, x="value")


def test_ecdfplot_rejects_an_unknown_column() -> None:
    with pytest.raises(KeyError, match="x column not found"):
        ecdfplot(SINGLE_SERIES, x="nope")


def test_ecdfplot_rejects_an_unknown_theme_preset() -> None:
    with pytest.raises(KeyError, match="unknown theme preset"):
        ecdfplot(SINGLE_SERIES, x="value", theme="not-a-preset")


def test_ecdfplot_renders_a_single_observation() -> None:
    """One value is a degenerate x domain; LinearScale maps it to the range midpoint
    rather than dividing by zero, so the curve is a single riser there."""
    (vertices,) = _series_vertices(ecdfplot({"value": [7.0]}, x="value").to_string())

    assert len(vertices) == 2
    assert vertices[0][1] == pytest.approx(AREA.bottom)
    assert vertices[1][1] == pytest.approx(AREA.top)


# ---------------------------------------------------------------------------
# what the gallery page claims about hiding a series
# ---------------------------------------------------------------------------


def _uneven() -> dict[str, list]:
    """Two groups of very different size, which is what makes the two stats disagree."""
    return {"v": [float(i) for i in range(200)] + [float(i) for i in range(60)], "g": ["big"] * 200 + ["small"] * 60}


def test_a_proportion_curve_spans_the_whole_axis_whatever_its_group_size() -> None:
    """Each curve is divided by its *own* group's count, so a 60-row group climbs to the top
    exactly as a 200-row one does.

    This is the one chart in the gallery where hiding a series would not make the axis lie --
    and the page says so, which is why it is measured here rather than asserted there.
    """
    svg = ecdfplot(_uneven(), x="v", hue="g").to_string()
    tops = [min(y for _, y in curve) for curve in _series_vertices(svg)]
    bottoms = [max(y for _, y in curve) for curve in _series_vertices(svg)]

    assert len(tops) == 2, "the fixture stopped drawing one curve per group"
    assert tops == pytest.approx([AREA_WITH_LEGEND.top] * 2)
    assert bottoms == pytest.approx([AREA_WITH_LEGEND.bottom] * 2)


def test_a_count_curve_stops_where_its_own_group_ran_out() -> None:
    """``stat="count"`` puts both groups on one axis scaled to the larger, so the smaller one
    stops partway up. Hiding the larger would leave that curve alone under an axis reaching
    three times higher than anything drawn -- the failure ``proportion`` is immune to.

    The two together are why the gallery page dims both rather than hiding either: the
    mechanism cannot be per-page without the reader checking which page they are on.
    """
    svg = ecdfplot(_uneven(), x="v", hue="g", stat="count").to_string()
    tops = sorted(min(y for _, y in curve) for curve in _series_vertices(svg))

    assert len(tops) == 2
    assert tops[0] == pytest.approx(AREA_WITH_LEGEND.top), "the larger group should still reach the top"
    assert tops[1] > AREA_WITH_LEGEND.top + 100, f"the smaller group should stop well short: {tops[1]}"
