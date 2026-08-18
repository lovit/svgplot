from __future__ import annotations

import random
import re

import pytest

from svgplot.charts._layout import DEFAULT_HEIGHT, DEFAULT_WIDTH, MARGIN_WITHOUT_LEGEND, plot_area
from svgplot.charts.violin import _VIOLIN_PADDING, _group_by_x, shared_grid_range, violinplot
from svgplot.scales import CategoricalScale, LinearScale
from svgplot.stats.box import box_stats
from svgplot.stats.kde import kde

AREA = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=MARGIN_WITHOUT_LEGEND)

_VERTEX_RE = re.compile(r"[ML] (-?[\d.]+),(-?[\d.]+)")
_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')

CATEGORIES = ["a", "b", "c"]


def _three_groups() -> dict[str, list]:
    generator = random.Random(11)
    return {
        "grp": ["a"] * 40 + ["b"] * 40 + ["c"] * 40,
        "v": [generator.gauss(0.0, 1.0) for _ in range(40)]
        + [generator.gauss(3.0, 2.0) for _ in range(40)]
        + [generator.gauss(1.0, 0.5) for _ in range(40)],
    }


def _x_scale(categories: list[str] | None = None) -> CategoricalScale:
    return CategoricalScale(categories or CATEGORIES, (AREA.left, AREA.right), padding=_VIOLIN_PADDING)


def _tags(svg: str, element: str, css_class: str) -> list[dict[str, str]]:
    return [dict(_ATTR_RE.findall(tag)) for tag in re.findall(rf"<{element}\b[^>]*/>", svg) if css_class in tag]


def _flanks(body: dict[str, str]) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """The outline split back into its left and right halves, both bottom-to-top."""
    points = [(float(vx), float(vy)) for vx, vy in _VERTEX_RE.findall(body["d"])]
    half = len(points) // 2
    return points[:half], points[half:][::-1]


# ---------------------------------------------------------------------------
# symmetry and shape
# ---------------------------------------------------------------------------


def test_each_violin_is_symmetric_about_its_band_centre() -> None:
    """Both flanks come from one offset, so they cannot drift apart -- the tolerance here
    is ``format_coord``'s six-decimal rounding, not a modelling allowance."""
    bodies = _tags(violinplot(_three_groups(), x="grp", y="v").to_string(), "path", "violin-body")
    scale = _x_scale()

    for category, body in zip(CATEGORIES, bodies, strict=True):
        centre = scale.center(category)
        left, right = _flanks(body)
        assert all((centre - lx) == pytest.approx(rx - centre, abs=1e-6) for (lx, _), (rx, _) in zip(left, right, strict=True))


def test_each_violin_is_a_closed_outline() -> None:
    svg = violinplot(_three_groups(), x="grp", y="v").to_string()

    for body in _tags(svg, "path", "violin-body"):
        assert body["d"].endswith("Z")


def test_one_violin_is_drawn_per_category() -> None:
    svg = violinplot(_three_groups(), x="grp", y="v").to_string()

    assert len(_tags(svg, "path", "violin-body")) == 3


def test_categories_keep_their_first_seen_order() -> None:
    """``boxplot``'s rule, kept so the two charts are interchangeable on the same data."""
    data = {"grp": ["z", "z", "z", "a", "a", "a"], "v": [1.0, 2.0, 3.0, 4.0, 6.0, 5.0]}
    svg = violinplot(data, x="grp", y="v", inner=None).to_string()
    centres = [_flanks(body)[0][0][0] for body in _tags(svg, "path", "violin-body")]

    assert centres[0] < centres[1]
    assert re.findall(r'class="tick-label"[^>]*>([^<]+)<', svg)[:2] == ["z", "a"]


# ---------------------------------------------------------------------------
# the shared scales
# ---------------------------------------------------------------------------


def test_every_category_shares_one_y_domain() -> None:
    """Per-category y scaling would let two violins of different spread look identical --
    the comparison the chart exists to support."""
    bodies = _tags(violinplot(_three_groups(), x="grp", y="v").to_string(), "path", "violin-body")
    spans = {
        (
            round(min(float(vy) for _, vy in _VERTEX_RE.findall(body["d"])), 6),
            round(max(float(vy) for _, vy in _VERTEX_RE.findall(body["d"])), 6),
        )
        for body in bodies
    }

    assert len(spans) == 1


def test_the_shared_y_span_is_the_union_of_the_per_category_spans() -> None:
    """Not the first category's span, and not one computed from the pooled values. Each
    category picks its own bandwidth, so the span has to grow to whichever category
    reaches furthest in each direction -- otherwise a category's tail is simply cut off."""
    # Chosen so each end is contributed by a *different* category: the tight low group
    # reaches furthest down, the spread group furthest up. A fixture where one category
    # dominates both ends cannot tell a union from that category's own span.
    low_group = [-100.0, -99.8, -100.2, -99.9, -100.1]
    spread_group = [10.0, 30.0, 50.0, 70.0, 90.0]
    groups = {"low": low_group, "spread": spread_group}

    low, high = shared_grid_range(groups, "scott")
    low_width = kde(low_group, grid=2).bandwidth
    spread_width = kde(spread_group, grid=2).bandwidth

    assert low == pytest.approx(min(low_group) - 3.0 * low_width)
    assert high == pytest.approx(max(spread_group) + 3.0 * spread_width)
    # Neither end comes from the same category, which is what makes this a union.
    assert low < min(spread_group) - 3.0 * spread_width
    assert high > max(low_group) + 3.0 * low_width


def test_widths_are_scaled_against_one_shared_peak() -> None:
    """The densest category fills its band and the rest are drawn in proportion. Scaling
    each violin to its own peak would make every category look equally dense."""
    bodies = _tags(violinplot(_three_groups(), x="grp", y="v").to_string(), "path", "violin-body")
    widths = []
    for body in bodies:
        left, right = _flanks(body)
        widths.append(max(rx - lx for (lx, _), (rx, _) in zip(left, right, strict=True)))

    assert max(widths) == pytest.approx(abs(_x_scale().bandwidth), abs=1e-6)
    assert min(widths) < max(widths)


def test_no_violin_spills_outside_its_band() -> None:
    bodies = _tags(violinplot(_three_groups(), x="grp", y="v").to_string(), "path", "violin-body")
    scale = _x_scale()
    half_band = abs(scale.bandwidth) / 2

    for category, body in zip(CATEGORIES, bodies, strict=True):
        centre = scale.center(category)
        left, right = _flanks(body)
        assert min(lx for lx, _ in left) >= centre - half_band - 1e-6
        assert max(rx for rx, _ in right) <= centre + half_band + 1e-6


# ---------------------------------------------------------------------------
# the inner box
# ---------------------------------------------------------------------------


def test_the_inner_box_lands_exactly_on_the_quartiles() -> None:
    """The binding cross-check: the annotation is computed from ``stats.quantile`` while
    ``boxplot`` draws ``stats.box``'s hinges. Comparing against ``box_stats`` is what keeps
    the two charts telling the same story -- if those two ever diverge, this fails.

    Asserted in pixel space against the chart's own y mapping, rebuilt from
    ``shared_grid_range``, rather than by eyeballing the drawn numbers."""
    data = _three_groups()
    groups = _group_by_x({"grp": data["grp"], "v": data["v"]}, "grp", "v")
    y_scale = LinearScale(shared_grid_range(groups, "scott"), (AREA.bottom, AREA.top))
    svg = violinplot(data, x="grp", y="v").to_string()

    for category, box, median_line in zip(
        CATEGORIES, _tags(svg, "rect", "violin-box"), _tags(svg, "line", "violin-median"), strict=True
    ):
        stats = box_stats(groups[category])
        top, height = float(box["y"]), float(box["height"])

        assert top == pytest.approx(y_scale(stats.q3), abs=1e-6)
        assert top + height == pytest.approx(y_scale(stats.q1), abs=1e-6)
        assert float(median_line["y1"]) == pytest.approx(y_scale(stats.median), abs=1e-6)
        assert float(median_line["y1"]) == pytest.approx(float(median_line["y2"]))


def test_the_inner_box_is_centred_on_its_violin() -> None:
    data = _three_groups()
    svg = violinplot(data, x="grp", y="v").to_string()
    scale = _x_scale()

    for category, box, median_line in zip(
        CATEGORIES, _tags(svg, "rect", "violin-box"), _tags(svg, "line", "violin-median"), strict=True
    ):
        centre = scale.center(category)
        assert float(box["x"]) + float(box["width"]) / 2 == pytest.approx(centre, abs=1e-6)
        assert (float(median_line["x1"]) + float(median_line["x2"])) / 2 == pytest.approx(centre, abs=1e-6)


def test_no_inner_marks_when_inner_is_none() -> None:
    svg = violinplot(_three_groups(), x="grp", y="v", inner=None).to_string()

    assert "violin-box" not in svg
    assert "violin-median" not in svg
    assert len(_tags(svg, "path", "violin-body")) == 3


def test_the_inner_box_is_narrower_than_the_median_tick() -> None:
    """The tick has to read as a mark rather than as the box's own edge."""
    svg = violinplot(_three_groups(), x="grp", y="v").to_string()
    box = _tags(svg, "rect", "violin-box")[0]
    tick = _tags(svg, "line", "violin-median")[0]

    assert float(tick["x2"]) - float(tick["x1"]) > float(box["width"])


@pytest.mark.parametrize("inner", ["violin", "quartile", "", "BOX", 0])
def test_an_unknown_inner_style_is_rejected(inner: object) -> None:
    with pytest.raises(ValueError, match="inner must be one of"):
        violinplot(_three_groups(), x="grp", y="v", inner=inner)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# errors name the category
# ---------------------------------------------------------------------------


def test_a_single_value_category_names_itself_in_the_error() -> None:
    """Without the category in the message the caller is told only "got 1" and has to work
    out which of their groups that was."""
    data = {"grp": ["a", "a", "b"], "v": [1.0, 2.0, 5.0]}

    with pytest.raises(ValueError, match=r"category 'b'"):
        violinplot(data, x="grp", y="v")


def test_a_zero_variance_category_names_itself_in_the_error() -> None:
    data = {"grp": ["a"] * 3 + ["b"] * 3, "v": [1.0, 2.0, 3.0, 7.0, 7.0, 7.0]}

    with pytest.raises(ValueError, match=r"category 'b'.*zero-variance"):
        violinplot(data, x="grp", y="v")


@pytest.mark.parametrize(
    ("data", "kwargs", "error", "match"),
    [
        ({"grp": [], "v": []}, {}, ValueError, "at least one row"),
        ({"grp": [None, None], "v": [1.0, 2.0]}, {}, ValueError, "both x and y"),
        (None, {"x": "nope"}, KeyError, "not found"),
        (None, {"theme": "not-a-preset"}, KeyError, "unknown theme preset"),
    ],
)
def test_violinplot_rejects_unusable_input(data: dict | None, kwargs: dict, error: type[Exception], match: str) -> None:
    payload = _three_groups() if data is None else data
    call_kwargs = {"x": "grp", "y": "v", **kwargs}
    with pytest.raises(error, match=match):
        violinplot(payload, **call_kwargs)


def test_violinplot_is_deterministic() -> None:
    data = _three_groups()

    assert violinplot(data, x="grp", y="v").to_string() == violinplot(data, x="grp", y="v").to_string()


def test_the_signature_matches_boxplot_s_leading_parameters() -> None:
    """The two answer the same question about the same data shape, so swapping one for the
    other must not mean rewriting the call."""
    import inspect

    from svgplot.charts.box import boxplot

    violin = list(inspect.signature(violinplot).parameters)
    box = list(inspect.signature(boxplot).parameters)

    assert violin[:3] == box[:3] == ["data", "x", "y"]
