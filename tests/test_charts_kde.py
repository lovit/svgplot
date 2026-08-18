from __future__ import annotations

import random
import re

import pytest

from svgplot.charts._layout import DEFAULT_HEIGHT, DEFAULT_WIDTH, MARGIN_WITH_LEGEND, MARGIN_WITHOUT_LEGEND, plot_area
from svgplot.charts.kde import _shared_grid_range, kdeplot
from svgplot.stats.kde import kde

AREA = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=MARGIN_WITHOUT_LEGEND)
AREA_WITH_LEGEND = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=MARGIN_WITH_LEGEND)

_VERTEX_RE = re.compile(r"[ML] (-?[\d.]+),(-?[\d.]+)")
_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')


def _sample(n: int = 150, *, mean: float = 0.0, seed: int = 3) -> list[float]:
    generator = random.Random(seed)
    return [generator.gauss(mean, 1.0) for _ in range(n)]


def _two_groups() -> dict[str, list]:
    return {"v": _sample(seed=3) + _sample(mean=5.0, seed=4), "grp": ["a"] * 150 + ["b"] * 150}


def _curves(svg: str) -> list[list[tuple[float, float]]]:
    """The (x, y) vertices of every ``kde-series`` path, in document order."""
    paths = [dict(_ATTR_RE.findall(tag)) for tag in re.findall(r"<path\b[^>]*/>", svg)]
    return [
        [(float(vx), float(vy)) for vx, vy in _VERTEX_RE.findall(path["d"])]
        for path in paths
        if "kde-series" in path.get("class", "")
    ]


def _style_rule(svg: str, selector: str) -> str:
    return next(line.strip() for line in svg.splitlines() if line.strip().startswith(selector))


# ---------------------------------------------------------------------------
# curve shape
# ---------------------------------------------------------------------------


def test_the_curve_has_one_vertex_per_grid_point() -> None:
    (curve,) = _curves(kdeplot({"v": _sample()}, x="v").to_string())

    assert len(curve) == 200


def test_the_curve_never_dips_below_the_baseline() -> None:
    """Density is non-negative, and the y scale runs 0..peak over an inverted pixel range,
    so no vertex may sit below the plot floor."""
    (curve,) = _curves(kdeplot({"v": _sample()}, x="v").to_string())

    assert max(y for _, y in curve) <= AREA.bottom + 1e-9


def test_the_curve_spans_the_full_plot_width() -> None:
    (curve,) = _curves(kdeplot({"v": _sample()}, x="v").to_string())

    assert curve[0][0] == pytest.approx(AREA.left)
    assert curve[-1][0] == pytest.approx(AREA.right)


def test_the_peak_reaches_the_top_of_the_plot() -> None:
    """The y domain is 0..peak, so the densest point must land exactly on the ceiling --
    otherwise the curve is being drawn against some other scale."""
    (curve,) = _curves(kdeplot({"v": _sample()}, x="v").to_string())

    assert min(y for _, y in curve) == pytest.approx(AREA.top)


# ---------------------------------------------------------------------------
# the shared grid
# ---------------------------------------------------------------------------


def test_every_hue_group_is_evaluated_on_one_shared_grid() -> None:
    """The point of the two-pass evaluation. Per-group grids would put each curve on its
    own x positions, so a reader could not trace a vertical line across the groups -- the
    same comparability ``histplot`` gets from sharing one set of bin edges."""
    first, second = _curves(kdeplot(_two_groups(), x="v", hue="grp").to_string())

    assert [x for x, _ in first] == [x for x, _ in second]


def test_the_shared_grid_is_the_union_of_the_per_group_spans() -> None:
    """Not a span computed from the pooled values. Bandwidth is chosen per group, so a
    narrow group beside a wide one needs *its own* ``cut`` bandwidths of room -- pooling
    first would pick one wide bandwidth and push the lower bound far past either group
    (measured: -26.6 pooled against -3.8 for the narrow group's own span)."""
    narrow = _sample(n=60, seed=5)
    wide = [value * 8.0 + 40.0 for value in _sample(n=60, seed=6)]
    data = {"v": narrow + wide, "grp": ["a"] * 60 + ["b"] * 60}

    low, high = _shared_grid_range([("a", narrow), ("b", wide)], "scott", 3.0)
    narrow_width = kde(narrow, grid=2).bandwidth
    wide_width = kde(wide, grid=2).bandwidth

    assert low == pytest.approx(min(narrow) - 3.0 * narrow_width)
    assert high == pytest.approx(max(wide) + 3.0 * wide_width)

    for curve in _curves(kdeplot(data, x="v", hue="grp").to_string()):
        assert curve[0][0] == pytest.approx(AREA_WITH_LEGEND.left)
        assert curve[-1][0] == pytest.approx(AREA_WITH_LEGEND.right)


def test_groups_are_ordered_by_their_label() -> None:
    """Same rule as every other hued chart, so palette assignment is reproducible."""
    svg = kdeplot({"v": _sample(n=40) + _sample(n=40, seed=9), "grp": ["b"] * 40 + ["a"] * 40}, x="v", hue="grp")

    assert re.findall(r'class="legend-text">([^<]+)<', svg.to_string()) == ["a", "b"]


# ---------------------------------------------------------------------------
# fill
# ---------------------------------------------------------------------------


def test_an_unfilled_curve_is_an_open_polyline() -> None:
    svg = kdeplot({"v": _sample()}, x="v", fill=False).to_string()

    assert "Z" not in _curves(svg)[0] and "Z" not in re.findall(r'd="([^"]+)"', svg)[0]
    assert _style_rule(svg, ".series-1 {") == ".series-1 { stroke: #E69F00; fill: none; stroke-width: 2; opacity: 1; }"


def test_a_filled_curve_closes_down_to_the_baseline() -> None:
    """Closed along the axis rather than straight between the two ends, so the filled
    region is the area *under* the curve."""
    svg = kdeplot({"v": _sample()}, x="v", fill=True).to_string()
    path = next(d for d in re.findall(r'd="([^"]+)"', svg) if d.count("L") > 50)
    curve = _curves(svg)[0]

    assert path.endswith("Z")
    assert curve[-1][1] == pytest.approx(AREA.bottom)
    assert curve[-2][1] == pytest.approx(AREA.bottom)
    assert curve[-1][0] == pytest.approx(AREA.left)
    assert curve[-2][0] == pytest.approx(AREA.right)


def test_filling_switches_the_mark_style_to_outlined() -> None:
    """A filled density with no outline loses its own edge wherever two groups overlap."""
    filled = _style_rule(kdeplot({"v": _sample()}, x="v", fill=True).to_string(), ".series-1 {")

    assert "stroke: #E69F00" in filled
    assert "fill: #E69F00" in filled
    assert "fill-opacity" in filled


# ---------------------------------------------------------------------------
# delegation to stats.kde
# ---------------------------------------------------------------------------


def test_a_numeric_bandwidth_is_passed_straight_through() -> None:
    """Checked against the estimator directly rather than through the rendered geometry:
    the chart rescales every curve to its own peak, so a flatter density draws at the same
    height and the smoothing is invisible in pixels. A forwarded bandwidth is only
    observable in the density itself (measured peak 0.520 at 0.2 against 0.178 at 2.0)."""
    values = _sample()

    assert max(kde(values, bandwidth=0.2).y) > max(kde(values, bandwidth=2.0).y)

    # And the chart must hand it to the *estimate*, not only to the grid's span. Comparing
    # whole SVGs cannot show that: the span is derived from the bandwidth too, so a chart
    # that forwarded it to the span alone still renders differently. Undoing the pixel
    # mapping isolates the density itself.
    curve = _curves(kdeplot({"v": values}, x="v", bandwidth=0.2).to_string())[0]
    drawn = [(AREA.bottom - y) / (AREA.bottom - AREA.top) for _, y in curve]

    expected = kde(values, bandwidth=0.2, grid_range=_shared_grid_range([(None, values)], 0.2, 3.0))
    normalised = [value / max(expected.y) for value in expected.y]

    assert drawn == pytest.approx(normalised, abs=1e-9)


@pytest.mark.parametrize(
    ("kwargs", "data", "match"),
    [
        ({"bandwidth": 0.0}, {"v": _sample()}, "must be positive"),
        ({"bandwidth": -1.0}, {"v": _sample()}, "must be positive"),
        ({"bandwidth": "nope"}, {"v": _sample()}, "bandwidth rule must be one of"),
        ({}, {"v": [3.0] * 10}, "zero-variance"),
        ({}, {"v": [1.0]}, "at least 2 values"),
    ],
)
def test_stats_kde_s_own_validation_surfaces_unchanged(kwargs: dict, data: dict, match: str) -> None:
    """``bandwidth`` is forwarded untouched, so the estimator's refusals are the chart's
    refusals -- notably the zero-variance sample, which would otherwise render as an
    infinite spike."""
    with pytest.raises(ValueError, match=match):
        kdeplot(data, x="v", **kwargs)


# ---------------------------------------------------------------------------
# rejected input
# ---------------------------------------------------------------------------


def test_a_legend_appears_only_with_a_hue() -> None:
    assert 'class="legend-text"' not in kdeplot({"v": _sample()}, x="v").to_string()
    assert kdeplot(_two_groups(), x="v", hue="grp").to_string().count('class="legend-text"') == 2


def test_missing_values_are_dropped_before_estimating() -> None:
    with_holes = {"v": [*_sample(n=40), None, float("nan")]}

    assert len(_curves(kdeplot(with_holes, x="v").to_string())[0]) == 200


@pytest.mark.parametrize(
    ("data", "kwargs", "error", "match"),
    [
        ({"v": []}, {}, ValueError, "at least one row"),
        ({"v": [None, None]}, {}, ValueError, "non-missing x value"),
        ({"v": _sample(n=10)}, {"x": "nope"}, KeyError, "not found"),
        ({"v": _sample(n=10)}, {"theme": "not-a-preset"}, KeyError, "unknown theme preset"),
    ],
)
def test_kdeplot_rejects_unusable_input(data: dict, kwargs: dict, error: type[Exception], match: str) -> None:
    call_kwargs = {"x": "v", **kwargs}
    with pytest.raises(error, match=match):
        kdeplot(data, **call_kwargs)


def test_kdeplot_is_deterministic() -> None:
    data = {"v": _sample()}

    assert kdeplot(data, x="v").to_string() == kdeplot(data, x="v").to_string()
