from __future__ import annotations

import random
import re

import pytest

from _svg_probe import style_rule, tags as _tags, texts as _texts
from svgplot.charts._layout import DEFAULT_HEIGHT, DEFAULT_WIDTH, MARGIN_WITHOUT_LEGEND, plot_area
from svgplot.charts.box import NO_HUE
from svgplot.charts.violin import _EVALUATION_GRID, _VIOLIN_PADDING, _group_by_x, shared_grid_range, violinplot
from svgplot.scales import CategoricalScale, LinearScale
from svgplot.stats.box import box_stats
from svgplot.stats.kde import kde

AREA = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=MARGIN_WITHOUT_LEGEND)

_VERTEX_RE = re.compile(r"[ML] (-?[\d.]+),(-?[\d.]+)")

CATEGORIES = ["a", "b", "c"]


_SPREADS = {"a": 1.0, "b": 0.5, "c": 2.0}
"""Standard deviations per category, with the *densest* (``b``, the narrowest spread)
deliberately in the middle of the sorted order. With it at either end, taking the peak from
a fixed position in the list is right by accident and the mutation survives -- exactly what
happened here before, and in ``charts/kde.py`` before that."""


def _category_values(category: str) -> list[float]:
    generator = random.Random(11 + ord(category))
    return [generator.gauss(0.0, _SPREADS[category]) for _ in range(40)]


def _three_groups() -> dict[str, list]:
    values: list[float] = []
    labels: list[str] = []
    for category in CATEGORIES:
        values.extend(_category_values(category))
        labels.extend([category] * 40)
    return {"grp": labels, "v": values}


def _x_scale(categories: list[str] | None = None) -> CategoricalScale:
    return CategoricalScale(categories or CATEGORIES, (AREA.left, AREA.right), padding=_VIOLIN_PADDING)


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

    band = abs(_x_scale().bandwidth)
    peaks = {category: max(kde(_category_values(category)).y) for category in CATEGORIES}
    shared_peak = max(peaks.values())

    assert max(peaks, key=peaks.get) == "b"  # densest is neither first nor last
    assert max(widths) == pytest.approx(band, abs=1e-6)
    # Each violin's drawn width is its own peak as a share of the shared one. Asserting
    # only "the widest fills the band" cannot tell a shared peak from one lifted off
    # whichever category happens to be densest.
    for category, width in zip(CATEGORIES, widths, strict=True):
        assert width / band == pytest.approx(peaks[category] / shared_peak, rel=0.05)


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
        stats = box_stats(groups[(category, NO_HUE)])
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


# ---------------------------------------------------------------------------
# bandwidth reaches the estimator
# ---------------------------------------------------------------------------


def test_an_explicit_bandwidth_sets_the_shared_span() -> None:
    """With a numeric bandwidth the span is just ``min - 3h`` .. ``max + 3h``, so it can be
    written out by hand rather than taken from the helper under test."""
    data = _three_groups()
    groups = _group_by_x(data, "grp", "v")

    low, high = shared_grid_range(groups, 0.5)

    assert low == pytest.approx(min(min(values) for values in groups.values()) - 3.0 * 0.5)
    assert high == pytest.approx(max(max(values) for values in groups.values()) + 3.0 * 0.5)


@pytest.mark.parametrize("bandwidth", ["silverman", 0.5, 2.0])
def test_the_bandwidth_argument_changes_the_chart(bandwidth: float | str) -> None:
    """It is part of the published signature and it does change the picture, but nothing
    failed when the parameter was dropped on the floor and ``"scott"`` used instead."""
    data = _three_groups()

    assert violinplot(data, x="grp", y="v", bandwidth=bandwidth).to_string() != violinplot(data, x="grp", y="v").to_string()


def test_the_bandwidth_reaches_both_passes() -> None:
    """It is used twice -- to size the shared grid, and to evaluate on it. Comparing whole
    SVGs cannot separate those: forwarding it to either one alone already changes the
    output. Undoing the pixel mapping pins the density itself, and the span check pins the
    grid, so each pass is asserted on its own."""
    data = _three_groups()
    groups = _group_by_x(data, "grp", "v")
    low = min(min(values) for values in groups.values()) - 3.0 * 0.5
    high = max(max(values) for values in groups.values()) + 3.0 * 0.5
    y_scale = LinearScale((low, high), (AREA.bottom, AREA.top))

    svg = violinplot(data, x="grp", y="v", bandwidth=0.5).to_string()
    bodies = _tags(svg, "path", "violin-body")
    scale = _x_scale()

    # The grid: the outline spans exactly the hand-computed shared range.
    drawn_y = [float(vy) for _, vy in _VERTEX_RE.findall(bodies[0]["d"])]
    assert min(drawn_y) == pytest.approx(y_scale(high), abs=1e-6)
    assert max(drawn_y) == pytest.approx(y_scale(low), abs=1e-6)

    # The evaluation: half-widths are the densities at that same bandwidth, scaled by the
    # shared peak.
    peaks = {category: max(kde(values, bandwidth=0.5, grid_range=(low, high)).y) for category, values in groups.items()}
    shared_peak = max(peaks.values())
    expected = kde(groups[("a", NO_HUE)], bandwidth=0.5, grid_range=(low, high))
    half_band = abs(scale.bandwidth) / 2
    left, right = _flanks(bodies[0])
    drawn_half = [(rx - lx) / 2 for (lx, _), (rx, _) in zip(left, right, strict=True)]

    assert drawn_half == pytest.approx([half_band * value / shared_peak for value in expected.y], abs=1e-6)


def test_a_bad_bandwidth_names_the_category() -> None:
    with pytest.raises(ValueError, match=r"category 'a'.*must be positive"):
        violinplot(_three_groups(), x="grp", y="v", bandwidth=-1.0)


def test_each_violin_carries_the_full_evaluation_grid() -> None:
    """200 written out, not imported: a test that reads the constant follows whatever the
    code says and cannot notice the grid being coarsened."""
    bodies = _tags(violinplot(_three_groups(), x="grp", y="v").to_string(), "path", "violin-body")

    assert _EVALUATION_GRID == 200
    for body in bodies:
        assert len(_VERTEX_RE.findall(body["d"])) == 400


# ---------------------------------------------------------------------------
# the inner marks stay in their own band
# ---------------------------------------------------------------------------


def test_the_inner_marks_stay_inside_their_band() -> None:
    """``test_no_violin_spills_outside_its_band`` only looks at the outline, so a median
    tick wide enough to reach into the neighbouring category went unnoticed."""
    svg = violinplot(_three_groups(), x="grp", y="v").to_string()
    scale = _x_scale()
    half_band = abs(scale.bandwidth) / 2

    for category, box, tick in zip(
        CATEGORIES, _tags(svg, "rect", "violin-box"), _tags(svg, "line", "violin-median"), strict=True
    ):
        centre = scale.center(category)
        assert float(box["x"]) >= centre - half_band - 1e-6
        assert float(box["x"]) + float(box["width"]) <= centre + half_band + 1e-6
        assert float(tick["x1"]) >= centre - half_band - 1e-6
        assert float(tick["x2"]) <= centre + half_band + 1e-6


def test_the_inner_marks_are_a_fixed_share_of_the_step() -> None:
    """Pinned as literals, not through the constants: importing them would let the tests
    follow whatever the code says."""
    svg = violinplot(_three_groups(), x="grp", y="v").to_string()
    step = abs(_x_scale().step)
    box = _tags(svg, "rect", "violin-box")[0]
    tick = _tags(svg, "line", "violin-median")[0]

    assert float(box["width"]) == pytest.approx(step * 0.12, abs=1e-6)
    assert float(tick["x2"]) - float(tick["x1"]) == pytest.approx(step * 0.2, abs=1e-6)


def test_neighbouring_violins_do_not_touch() -> None:
    """The gutter is what ``padding`` buys; without it adjacent densities merge visually."""
    svg = violinplot(_three_groups(), x="grp", y="v", inner=None).to_string()
    bodies = _tags(svg, "path", "violin-body")
    rights = [max(rx for rx, _ in _flanks(body)[1]) for body in bodies]
    lefts = [min(lx for lx, _ in _flanks(body)[0]) for body in bodies]

    assert all(right < left for right, left in zip(rights[:-1], lefts[1:], strict=True))
    assert abs(_x_scale().step) - abs(_x_scale().bandwidth) == pytest.approx(abs(_x_scale().step) * 0.2)


# ---------------------------------------------------------------------------
# theme and grouping
# ---------------------------------------------------------------------------


def test_the_theme_reaches_the_output() -> None:
    """Nothing rendered this chart with a ``theme=`` before, so replacing the resolved
    theme with the default changed nothing that any test looked at."""
    data = _three_groups()

    assert violinplot(data, x="grp", y="v", theme="dark").to_string() != violinplot(data, x="grp", y="v").to_string()


def test_the_series_style_keeps_a_stroke_and_a_translucent_fill() -> None:
    """One series class carries the body, the inner box and the median tick. A plain
    ``"fill"`` style emits ``stroke: none``, which erases the outline and the tick."""
    rule = style_rule(violinplot(_three_groups(), x="grp", y="v").to_string(), ".series-1")

    assert "stroke: #" in rule
    assert "fill-opacity" in rule
    assert "stroke: none" not in rule


def test_a_nan_category_label_drops_the_row() -> None:
    """``boxplot``'s hand-rolled grouping keeps a NaN x as the literal category ``'nan'``;
    this one treats it as missing, which is the rule the rest of the package uses. Pinned
    so the difference is a decision on record rather than an accident."""
    data = {"grp": [float("nan"), "a", "a", "a"], "v": [1.0, 2.0, 3.0, 4.0]}

    assert sorted(_group_by_x(data, "grp", "v")) == [("a", NO_HUE)]


def test_every_category_is_named_on_the_axis() -> None:
    """The assertion the old helper made unwritable.

    ``violinplot``'s copy of ``_tags`` matched ``.../>`` only, so a ``<text>`` element was
    invisible to it -- and the file went on to contain no assertion about text at all, which
    reads as "nothing to check here" rather than as "the tool cannot see it". A violin whose
    categories are unlabelled is three shapes in a row with no way to tell which is which."""
    data = {"c": ["가", "가", "가", "나", "나", "나"], "v": [1.0, 2.0, 3.0, 4.0, 5.0, 7.0]}
    svg = violinplot(data, x="c", y="v").to_string()
    drawn = _texts(svg, "text", "tick-label")

    # Through the probe, not a hand-written class regex. ``class="[^"]*tick-label[^"]*"`` is
    # the substring form this consolidation exists to remove, and reintroducing it here would
    # have made the argument in the same diff that disproves it.
    assert drawn, "the probe cannot see a tag with content"
    assert {"가", "나"} <= set(drawn), f"a category went unnamed: {drawn}"


# --------------------------------------------------------------------------------- tooltips


def _marks(svg: str) -> list[tuple[str, str | None]]:
    """Every drawn mark as ``(class, its <title> text or None)``, in document order.

    Through the parsed tree, so a mark that lost its ``<title>`` shows up as ``None`` rather
    than dropping out of the list -- which mark *has* one is the whole question here. The
    chart's own ``<title>`` is a child of the root ``<svg>``, which carries no series class.
    """
    import xml.etree.ElementTree as ET

    root = ET.fromstring(svg)
    marks = []
    for element in root.iter():
        classes = (element.get("class") or "").split()
        if not any(name.startswith("series-") for name in classes):
            continue
        title = element.find("{http://www.w3.org/2000/svg}title")
        marks.append((classes[-1], None if title is None else title.text))
    return marks


def test_a_violin_tooltip_says_the_quartiles_the_outline_cannot_show() -> None:
    """The y axis gives the range and the width gives a density scaled against the chart's
    shared peak, so nothing drawn says where the middle half of the data sits."""
    data = {"g": ["a"] * 6 + ["b"] * 6, "v": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0]}
    said = {title for _, title in _marks(violinplot(data, x="g", y="v", tooltip=True).to_string())}

    assert said == {
        "g: a · v: Q1 2.25 · median 3.5 · Q3 4.75 · 6 observations",
        "g: b · v: Q1 12.5 · median 15 · Q3 17.5 · 6 observations",
    }


def test_every_mark_of_a_violin_says_the_same_thing_and_none_is_left_silent() -> None:
    """The pointer stops at the topmost element under it, so an untitled inner box is a hole in
    the middle of a violin that otherwise responds. Three marks per violin under the default
    ``inner="box"``: body, box, median tick.

    Asserted as "every mark has one, and each violin's are equal" rather than against the
    number three, so it stays true if a violin grows a fourth mark."""
    data = {"g": ["a"] * 6 + ["b"] * 6, "v": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0]}
    marks = _marks(violinplot(data, x="g", y="v", tooltip=True).to_string())

    assert marks, "the fixture stopped drawing anything"
    assert all(title is not None for _, title in marks), "a mark was left without a tooltip"
    assert len(marks) == 6, "two violins, three marks each"
    assert len({title for _, title in marks}) == 2, "and one sentence per violin, repeated"


def test_the_quartiles_are_said_even_when_no_box_is_drawn() -> None:
    """``inner=None`` switches off the annotation, not the data. The numbers describe the values
    the outline was computed from, which are there either way -- and with the box gone the
    tooltip is the *only* way to read them."""
    data = {"g": ["a"] * 6, "v": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]}
    marks = _marks(violinplot(data, x="g", y="v", inner=None, tooltip=True).to_string())

    assert [cls for cls, _ in marks] == ["violin-body"], "the fixture stopped being the no-box case"
    assert marks[0][1] == "g: a · v: Q1 2.25 · median 3.5 · Q3 4.75 · 6 observations"


def test_the_tooltip_cannot_disagree_with_the_box_or_the_median_tick() -> None:
    """Both come from the same :func:`quantiles` call. Read back the drawn box's own pixels and
    invert the scale: if the tooltip were computed a second way -- a different hinge definition,
    or a mean where a median belongs -- the two would drift and nothing else would notice."""
    data = {"g": ["a"] * 9, "v": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 20.0, 21.0]}
    chart = violinplot(data, x="g", y="v", tooltip=True)
    svg = chart.to_string()
    (box,) = _tags(svg, "rect", "violin-box")
    said = next(title for cls, title in _marks(svg) if cls == "violin-box")
    # The y domain is the shared KDE grid, not min/max of the data, so it is taken from the
    # chart rather than recomputed here -- a second copy of that rule is a second thing to go
    # stale.
    scale = LinearScale(chart.domains.y, (AREA.bottom, AREA.top))

    q1 = float(said.split("Q1 ")[1].split(" ")[0])
    q3 = float(said.split("Q3 ")[1].split(" ")[0])
    median = float(said.split("median ")[1].split(" ")[0])
    (tick,) = _tags(svg, "line", "violin-median")

    assert q1 != q3, "the fixture stopped having a box with height"
    assert median != sum(data["v"]) / len(data["v"]), "the fixture's median and mean stopped differing"
    assert abs(float(box["y"]) - scale(q3)) < 0.01, f"the box top is not where the tooltip's Q3 is: {said}"
    assert abs(float(box["y"]) + float(box["height"]) - scale(q1)) < 0.01, "the box bottom is not the tooltip's Q1"
    assert abs(float(tick["y1"]) - scale(median)) < 0.01, f"the median tick is not where the tooltip's median is: {said}"


def test_a_hued_violin_names_its_group_as_well_as_its_category() -> None:
    data = {
        "g": ["a"] * 6 + ["b"] * 6,
        "v": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0],
        "s": ["l", "r"] * 6,
    }
    said = {title for _, title in _marks(violinplot(data, x="g", y="v", hue="s", tooltip=True).to_string()) if title}

    assert said, "the fixture stopped drawing violins"
    assert all(" · s: " in title for title in said)
    assert {title.split(" · ")[1] for title in said} == {"s: l", "s: r"}


def test_the_default_draws_no_tooltip_and_saying_so_changes_nothing() -> None:
    """What this can check is that ``tooltip=False`` is the same call as not writing it, and
    that neither titles a mark. It is deliberately not named for byte-identity with the version
    before ``tooltip=`` existed, which it cannot see -- both sides are this branch's code.
    ``docs/gallery/*.html`` holds those bytes, and
    ``test_gallery.py::test_the_committed_gallery_is_what_a_fresh_build_produces`` compares
    them."""
    data = _three_groups()
    omitted = violinplot(data, x="grp", y="v").to_string()
    explicit = violinplot(data, x="grp", y="v", tooltip=False).to_string()

    assert omitted == explicit
    assert all(title is None for _, title in _marks(omitted))


def test_a_category_too_long_or_too_blank_to_read_is_left_out_of_the_tooltip() -> None:
    """The category is a string out of the data and it is written once per mark -- three times
    per violin. Uncapped, the two violins below took the file from 36,544 bytes to 82,075, with
    four ``<title>`` elements over 4,000 characters and the longest at 5,056; capped it is
    37,030. The axis tick showing the same category is already shortened, and so are the column
    names.

    A category of one tab goes for the other reason: ``"g:  · v: …"`` names the violin with a
    label that is not on screen."""
    data = {"g": ["\uba74" * 5000] * 6 + ["\t"] * 6, "v": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0] * 2}
    chart = violinplot(data, x="g", y="v", tooltip=True)
    said = {title for _, title in _marks(chart.to_string()) if title}

    assert len(chart.to_string().encode()) < 40_000, "the unreadable category was written into the file anyway"
    assert said == {"v: Q1 2.25 · median 3.5 · Q3 4.75 · 6 observations"}
