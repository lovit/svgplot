from __future__ import annotations

import math
import re
from itertools import pairwise

import pytest

from svgplot.charts._layout import DEFAULT_HEIGHT, DEFAULT_WIDTH, plot_area
from svgplot.charts.radar import (
    _LABEL_GAP,
    _MARGIN_WITH_LEGEND,
    _MARGIN_WITHOUT_LEGEND,
    _MIN_CATEGORIES,
    _label_anchor,
    radarplot,
)
from svgplot.scales import LinearScale, make_ticks

AREA = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=_MARGIN_WITHOUT_LEGEND)
CENTRE = ((AREA.left + AREA.right) / 2, (AREA.top + AREA.bottom) / 2)
OUTER = min(AREA.right - AREA.left, AREA.bottom - AREA.top) / 2 - _LABEL_GAP

HUED_AREA = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=_MARGIN_WITH_LEGEND)
HUED_CENTRE = ((HUED_AREA.left + HUED_AREA.right) / 2, (HUED_AREA.top + HUED_AREA.bottom) / 2)
HUED_OUTER = min(HUED_AREA.right - HUED_AREA.left, HUED_AREA.bottom - HUED_AREA.top) / 2 - _LABEL_GAP

CATEGORIES = ["a", "b", "c", "d", "e"]

_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')
_VERTEX_RE = re.compile(r"[ML] (-?[\d.]+),(-?[\d.]+)")


def _two_series() -> dict[str, list]:
    return {
        "stat": CATEGORIES * 2,
        "v": [8.0, 6.0, 7.0, 5.0, 4.0, 5.0, 9.0, 4.0, 8.0, 6.0],
        "who": ["A"] * 5 + ["B"] * 5,
    }


def _one_series() -> dict[str, list]:
    return {"stat": CATEGORIES, "v": [8.0, 6.0, 7.0, 5.0, 4.0]}


def _tags(svg: str, element: str, css_class: str) -> list[dict[str, str]]:
    tags = [dict(_ATTR_RE.findall(tag)) for tag in re.findall(rf"<{element}\b[^>]*?/?>", svg)]
    # Token-wise, not substring: "grid-line" must not also match a future "grid-line-major".
    return [tag for tag in tags if css_class in tag.get("class", "").split()]


def _vertices(tag: dict[str, str]) -> list[tuple[float, float]]:
    return [(float(vx), float(vy)) for vx, vy in _VERTEX_RE.findall(tag["d"])]


def _rings(svg: str) -> list[dict[str, str]]:
    return _tags(svg, "path", "grid-line")


def _series(svg: str) -> list[dict[str, str]]:
    return _tags(svg, "path", "radar-series")


def _radius(point: tuple[float, float], centre: tuple[float, float] = CENTRE) -> float:
    return math.hypot(point[0] - centre[0], point[1] - centre[1])


# ---------------------------------------------------------------------------
# the polar frame
# ---------------------------------------------------------------------------


def test_one_spoke_per_category() -> None:
    svg = radarplot(_one_series(), x="stat", y="v").to_string()

    assert len(_tags(svg, "line", "grid-line")) == len(CATEGORIES)


def test_spokes_start_at_the_centre_and_end_on_the_outer_radius() -> None:
    svg = radarplot(_one_series(), x="stat", y="v").to_string()

    for spoke in _tags(svg, "line", "grid-line"):
        assert (float(spoke["x1"]), float(spoke["y1"])) == pytest.approx(CENTRE)
        assert _radius((float(spoke["x2"]), float(spoke["y2"]))) == pytest.approx(OUTER)


def test_the_first_spoke_points_straight_up() -> None:
    """Radars are read clockwise from twelve o'clock; starting anywhere else silently
    rotates every chart in the package."""
    svg = radarplot(_one_series(), x="stat", y="v").to_string()
    first = _tags(svg, "line", "grid-line")[0]

    assert float(first["x2"]) == pytest.approx(CENTRE[0])
    assert float(first["y2"]) < CENTRE[1]


def test_spokes_are_evenly_spaced_around_the_circle() -> None:
    svg = radarplot(_one_series(), x="stat", y="v").to_string()
    angles = [
        math.atan2(float(spoke["y2"]) - CENTRE[1], float(spoke["x2"]) - CENTRE[0]) for spoke in _tags(svg, "line", "grid-line")
    ]
    gaps = [(second - first) % (2 * math.pi) for first, second in pairwise(angles)]

    assert all(gap == pytest.approx(2 * math.pi / len(CATEGORIES)) for gap in gaps)


def test_rings_are_polygons_through_the_spokes() -> None:
    """Circular rings would make a reader interpolate between spokes to place a value; an
    n-gon crosses each spoke exactly at the value its tick names."""
    svg = radarplot(_one_series(), x="stat", y="v").to_string()
    rings = _rings(svg)

    assert rings
    for ring in rings:
        assert ring["d"].endswith("Z")
        assert len(_vertices(ring)) == len(CATEGORIES)


def test_ring_radii_come_from_make_ticks() -> None:
    """The rings are the radial axis. Inventing their own spacing would put the grid and
    any future radial labels on different scales."""
    values = _one_series()["v"]
    radial = LinearScale((0.0, max(values)), (0.0, OUTER))
    expected = [radial(float(tick)) for tick in make_ticks(radial) if radial(float(tick)) > 0]

    rings = _rings(radarplot(_one_series(), x="stat", y="v").to_string())
    drawn = sorted(_radius(_vertices(ring)[0]) for ring in rings)

    assert drawn == pytest.approx(sorted(expected))


def test_the_zero_ring_is_not_drawn() -> None:
    """A ring of radius zero is a dot on the origin -- ink with no meaning."""
    rings = _rings(radarplot(_one_series(), x="stat", y="v").to_string())

    assert all(_radius(_vertices(ring)[0]) > 0 for ring in rings)


# ---------------------------------------------------------------------------
# labels
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("degrees", "anchor"),
    [
        (-90, "middle"),
        (90, "middle"),
        (0, "start"),
        (45, "start"),
        (-45, "start"),
        (180, "end"),
        (135, "end"),
        (-135, "end"),
    ],
)
def test_the_label_anchor_follows_the_quadrant(degrees: float, anchor: str) -> None:
    """Chosen from the angle, never from a measured text width -- this package has no font
    metrics, and the side a label belongs on is fully determined by its half of the circle.
    Straight up and straight down get ``middle`` because neither side is nearer."""
    assert _label_anchor(math.radians(degrees)) == anchor


def test_all_three_anchors_appear_on_a_real_chart() -> None:
    svg = radarplot(_one_series(), x="stat", y="v").to_string()
    anchors = {label["text-anchor"] for label in _tags(svg, "text", "tick-label")}

    assert anchors == {"start", "middle", "end"}


def test_one_label_per_category_outside_the_rings() -> None:
    svg = radarplot(_one_series(), x="stat", y="v").to_string()
    labels = _tags(svg, "text", "tick-label")

    assert len(labels) == len(CATEGORIES)
    for label in labels:
        assert _radius((float(label["x"]), float(label["y"]))) == pytest.approx(OUTER + _LABEL_GAP)
        # A label sits *on* its spoke's end, so it has to be centred on that point
        # vertically as well as horizontally -- the default baseline hangs it below.
        assert label["dominant-baseline"] == "middle"


def test_category_labels_are_the_category_names() -> None:
    svg = radarplot(_one_series(), x="stat", y="v").to_string()

    assert re.findall(r'class="tick-label"[^>]*>([^<]+)<', svg) == CATEGORIES


# ---------------------------------------------------------------------------
# series polygons
# ---------------------------------------------------------------------------


def test_one_closed_polygon_per_series() -> None:
    svg = radarplot(_two_series(), x="stat", y="v", hue="who").to_string()
    polygons = _series(svg)

    assert len(polygons) == 2
    for polygon in polygons:
        assert polygon["d"].endswith("Z")
        assert len(_vertices(polygon)) == len(CATEGORIES)


def test_a_vertex_sits_at_its_value_s_radius() -> None:
    """The whole reading of the chart: distance from the centre *is* the value."""
    values = _one_series()["v"]
    radial = LinearScale((0.0, max(values)), (0.0, OUTER))
    polygon = _series(radarplot(_one_series(), x="stat", y="v").to_string())[0]

    assert [_radius(point) for point in _vertices(polygon)] == pytest.approx([radial(value) for value in values])


def test_every_polygon_vertex_sits_on_a_spoke() -> None:
    """A polygon whose corners fall between the spokes is unreadable -- the reader lines a
    corner up with the axis that names it. Half a band's offset is enough to break that
    and leaves every other property (vertex count, closure, radii) intact."""
    svg = radarplot(_one_series(), x="stat", y="v").to_string()
    spoke_angles = sorted(
        round(math.atan2(float(spoke["y2"]) - CENTRE[1], float(spoke["x2"]) - CENTRE[0]) % (2 * math.pi), 9)
        for spoke in _tags(svg, "line", "grid-line")
    )
    vertex_angles = sorted(
        round(math.atan2(point[1] - CENTRE[1], point[0] - CENTRE[0]) % (2 * math.pi), 9)
        for point in _vertices(_series(svg)[0])
    )

    assert vertex_angles == pytest.approx(spoke_angles, abs=1e-6)


def test_ring_vertices_sit_on_the_spokes_too() -> None:
    svg = radarplot(_one_series(), x="stat", y="v").to_string()
    spoke_angles = sorted(
        round(math.atan2(float(spoke["y2"]) - CENTRE[1], float(spoke["x2"]) - CENTRE[0]) % (2 * math.pi), 9)
        for spoke in _tags(svg, "line", "grid-line")
    )
    ring_angles = sorted(
        round(math.atan2(point[1] - CENTRE[1], point[0] - CENTRE[0]) % (2 * math.pi), 9) for point in _vertices(_rings(svg)[0])
    )

    assert ring_angles == pytest.approx(spoke_angles, abs=1e-6)


def test_the_largest_value_reaches_the_outer_ring() -> None:
    polygon = _series(radarplot(_one_series(), x="stat", y="v").to_string())[0]

    assert max(_radius(point) for point in _vertices(polygon)) == pytest.approx(OUTER)


def test_series_share_one_radial_scale() -> None:
    """Per-series scaling would make a weak series look identical to a strong one -- the
    comparison a radar exists for."""
    data = _two_series()
    polygons = _series(radarplot(data, x="stat", y="v", hue="who").to_string())
    peaks = [max(_radius(point, HUED_CENTRE) for point in _vertices(polygon)) for polygon in polygons]

    assert max(peaks) == pytest.approx(HUED_OUTER)
    assert min(peaks) < HUED_OUTER


# ---------------------------------------------------------------------------
# fill and legend
# ---------------------------------------------------------------------------


def _series_rule(svg: str) -> str:
    return next(line.strip() for line in svg.splitlines() if line.strip().startswith(".series-1 {"))


def test_filling_uses_the_outlined_mark_style() -> None:
    rule = _series_rule(radarplot(_one_series(), x="stat", y="v", fill=True).to_string())

    assert "stroke: #" in rule
    assert "fill-opacity" in rule


def test_not_filling_leaves_the_outline_alone() -> None:
    rule = _series_rule(radarplot(_one_series(), x="stat", y="v", fill=False).to_string())

    assert "fill: none" in rule


@pytest.mark.parametrize("fill", [True, False])
def test_a_hued_chart_renders_with_and_without_fill(fill: bool) -> None:
    """The legend swatch understands ``"stroke"`` and ``"fill"`` only, so handing it the
    series' ``"outlined"`` style raises -- a break only the hue+fill combination reaches."""
    svg = radarplot(_two_series(), x="stat", y="v", hue="who", fill=fill).to_string()
    swatches = re.findall(r"<(rect|line)\b[^>]*class=\"[^\"]*series-1[^\"]*\"", svg)

    assert svg.count('class="legend-text"') == 2
    assert swatches == (["rect"] if fill else ["line"])


def test_a_legend_appears_only_with_a_hue() -> None:
    assert 'class="legend-text"' not in radarplot(_one_series(), x="stat", y="v").to_string()


# ---------------------------------------------------------------------------
# rejected input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("count", [1, 2])
def test_too_few_categories_is_refused(count: int) -> None:
    """Two spokes make a line, not a radar -- the shape has no interior to read."""
    data = {"stat": CATEGORIES[:count], "v": [1.0] * count}

    with pytest.raises(ValueError, match=f"at least {_MIN_CATEGORIES} categories"):
        radarplot(data, x="stat", y="v")


def test_the_minimum_number_of_categories_is_accepted() -> None:
    data = {"stat": CATEGORIES[:_MIN_CATEGORIES], "v": [1.0] * _MIN_CATEGORIES}

    assert len(_vertices(_series(radarplot(data, x="stat", y="v").to_string())[0])) == _MIN_CATEGORIES


def test_a_series_missing_a_category_is_refused() -> None:
    """A polygon with a gap is not a smaller polygon -- it silently redraws the shape."""
    data = {"stat": ["a", "b", "c", "a", "b"], "v": [1.0, 2.0, 3.0, 4.0, 5.0], "who": ["A"] * 3 + ["B"] * 2}

    with pytest.raises(ValueError, match=r"series 'B' has no value for 'c'"):
        radarplot(data, x="stat", y="v", hue="who")


@pytest.mark.parametrize(
    ("data", "kwargs", "error", "match"),
    [
        ({"stat": [], "v": []}, {}, ValueError, "at least one row"),
        (None, {"x": "nope"}, KeyError, "x column not found"),
        (None, {"y": "nope"}, KeyError, "column not found"),
        (None, {"theme": "not-a-preset"}, KeyError, "unknown theme preset"),
        (None, {"theme": 123}, TypeError, "theme must be"),
        ({"stat": CATEGORIES, "v": [1.0] * 5, "who": [None] * 5}, {"hue": "who"}, ValueError, "non-missing 'who'"),
        ({"stat": CATEGORIES, "v": [1.0] * 5}, {"hue": "nope"}, KeyError, "not found"),
    ],
)
def test_radarplot_rejects_unusable_input(data: dict | None, kwargs: dict, error: type[Exception], match: str) -> None:
    payload = _one_series() if data is None else data
    call_kwargs = {"x": "stat", "y": "v", **kwargs}
    with pytest.raises(error, match=match):
        radarplot(payload, **call_kwargs)


def test_radarplot_is_deterministic() -> None:
    data = _two_series()

    assert radarplot(data, x="stat", y="v", hue="who").to_string() == radarplot(data, x="stat", y="v", hue="who").to_string()


# ---------------------------------------------------------------------------
# legend placement
# ---------------------------------------------------------------------------


def test_the_legend_sits_beside_the_dial_and_inside_the_canvas() -> None:
    """``_MARGIN_WITH_LEGEND`` reserves 180px on the right *for this*, and nothing checked
    that the reservation was actually used. Shrinking it to 40 put the legend text at
    x=802 on an 800px canvas and every existing assertion still passed -- they counted
    legend rows and looked at swatch tags, never at where either landed."""
    svg = radarplot(_two_series(), x="stat", y="v", hue="who").to_string()
    texts = _tags(svg, "text", "legend-text")
    swatches = _tags(svg, "rect", "series-1")

    assert texts and swatches
    for tag in (*texts, *swatches):
        assert float(tag["x"]) > HUED_AREA.right
        assert float(tag["x"]) < DEFAULT_WIDTH
    assert min(float(text["y"]) for text in texts) == pytest.approx(HUED_AREA.top, abs=_LABEL_GAP)


def test_dropping_the_hue_reclaims_the_reserved_legend_space() -> None:
    """With no legend to draw there is nothing to reserve for, and keeping the reservation
    pushes the dial 70px left of the canvas centre with blank space beside it."""
    without = _series(radarplot(_one_series(), x="stat", y="v").to_string())[0]
    with_hue = _series(radarplot(_two_series(), x="stat", y="v", hue="who").to_string())[0]

    assert max(x for x, _ in _vertices(without)) > max(x for x, _ in _vertices(with_hue))
    # The dial's own centre, read off a rendered spoke rather than recomputed from the
    # margin constant the chart used -- otherwise both sides of the comparison move
    # together and the assertion holds whatever the margin is.
    spokes = _tags(radarplot(_one_series(), x="stat", y="v").to_string(), "line", "grid-line")
    assert float(spokes[0]["x1"]) == pytest.approx(DEFAULT_WIDTH / 2)


# ---------------------------------------------------------------------------
# how rows become spokes
# ---------------------------------------------------------------------------


def test_a_missing_value_is_refused_even_with_a_single_series() -> None:
    """It used to lose the whole spoke instead -- a five-sided radar quietly became a
    four-sided one, which is the exact failure the hue= version of this rule refuses. The
    old category filter made the rule depend on how many series there happened to be."""
    data = {"stat": CATEGORIES, "v": [8.0, None, 7.0, 5.0, 4.0]}

    with pytest.raises(ValueError, match=r"the series has no value for 'b'"):
        radarplot(data, x="stat", y="v")


def test_a_row_whose_category_is_missing_is_simply_dropped() -> None:
    """No category, no spoke to be missing from -- unlike a missing *value*, this row names
    no place on the chart, so there is nothing for it to leave a gap in."""
    data = {"stat": [*CATEGORIES, None], "v": [8.0, 6.0, 7.0, 5.0, 4.0, 9.0]}
    svg = radarplot(data, x="stat", y="v").to_string()

    assert re.findall(r'class="tick-label"[^>]*>([^<]+)<', svg) == CATEGORIES


def test_a_repeated_category_takes_its_last_row_s_value() -> None:
    """The documented rule, and until now nothing held it: swapping the assignment for
    ``setdefault`` (first row wins) left every test passing."""
    data = {"stat": [*CATEGORIES, "a"], "v": [1.0, 6.0, 7.0, 5.0, 4.0, 9.0]}
    polygon = _series(radarplot(data, x="stat", y="v").to_string())[0]
    scale = LinearScale((0.0, 9.0), (0.0, OUTER))

    assert _radius(_vertices(polygon)[0]) == pytest.approx(scale(9.0), abs=1e-4)


def test_series_are_ordered_by_label_and_keep_that_order_in_the_legend() -> None:
    """The sort decides which series becomes ``series-1``, which is what pairs a legend
    row with a colour. Reversing it left the row *count* unchanged, so nothing failed."""
    data = {"stat": CATEGORIES * 2, "v": [1.0] * 5 + [9.0] * 5, "who": ["Z"] * 5 + ["A"] * 5}
    svg = radarplot(data, x="stat", y="v", hue="who").to_string()

    assert re.findall(r'class="legend-text"[^>]*>([^<]+)<', svg) == ["A", "Z"]
    # ...and the first legend row's class really is the first polygon's, so the pairing is
    # checked rather than just the order of the labels.
    first = _tags(svg, "path", "series-1")[0]
    assert max(_radius(point, HUED_CENTRE) for point in _vertices(first)) == pytest.approx(HUED_OUTER)


# ---------------------------------------------------------------------------
# values a radial axis cannot draw
# ---------------------------------------------------------------------------


def test_a_negative_value_is_refused_rather_than_reflected() -> None:
    """A negative radius puts the vertex on the *opposite* spoke, where a reader decodes it
    as another category's value -- measured at radius 403 on a 242px dial, off-canvas."""
    data = {"stat": CATEGORIES, "v": [-5.0, 2.0, 3.0, 1.0, 4.0]}

    with pytest.raises(ValueError, match=r"non-negative, got -5.0 for 'a'"):
        radarplot(data, x="stat", y="v")


def test_the_offending_series_is_named_when_a_hue_is_in_play() -> None:
    data = {"stat": CATEGORIES * 2, "v": [1.0] * 5 + [1.0, -2.0, 1.0, 1.0, 1.0], "who": ["A"] * 5 + ["B"] * 5}

    with pytest.raises(ValueError, match=r"for 'b' in series 'B'"):
        radarplot(data, x="stat", y="v", hue="who")


@pytest.mark.parametrize("bad", [float("inf"), float("-inf")])
def test_a_non_finite_value_is_refused_with_its_category_named(bad: float) -> None:
    """``LinearScale`` rejects it too, but its message names a domain value and neither the
    category nor the series it came from."""
    data = {"stat": CATEGORIES, "v": [1.0, bad, 3.0, 1.0, 4.0]}

    with pytest.raises(ValueError, match=r"finite, got .*inf for 'b'"):
        radarplot(data, x="stat", y="v")


def test_an_all_zero_series_is_refused_rather_than_drawn_at_half_scale() -> None:
    """``LinearScale((0, 0), ...)`` answers the midpoint of its range for every input, so
    all-zero data drew a polygon at exactly half the outer radius -- indistinguishable from
    genuine mid-scale values."""
    data = {"stat": CATEGORIES, "v": [0.0] * 5}

    with pytest.raises(ValueError, match="must not all be zero"):
        radarplot(data, x="stat", y="v")


def test_a_single_zero_among_real_values_still_draws_at_the_centre() -> None:
    """Zero is a legal value; only an entirely zero *scale* is not."""
    data = {"stat": CATEGORIES, "v": [0.0, 6.0, 7.0, 5.0, 4.0]}
    polygon = _series(radarplot(data, x="stat", y="v").to_string())[0]

    assert _radius(_vertices(polygon)[0]) == pytest.approx(0.0, abs=1e-4)


# ---------------------------------------------------------------------------
# the themed background
# ---------------------------------------------------------------------------


def test_the_background_carries_the_class_the_theme_styles() -> None:
    """A renamed class leaves the panel transparent, which on a dark theme shows the host
    page through the chart."""
    svg = radarplot(_one_series(), x="stat", y="v").to_string()
    background = _tags(svg, "rect", "plot-background")

    assert len(background) == 1
    assert (float(background[0]["width"]), float(background[0]["height"])) == (DEFAULT_WIDTH, DEFAULT_HEIGHT)
    assert ".plot-background {" in svg


def test_the_dial_geometry_is_pinned_to_literal_pixels() -> None:
    """Every other geometry test recomputes its expectation from ``_MARGIN_*``/``_LABEL_GAP``,
    so changing one of those constants moves the expectation with it and nothing fails.
    One literal anchor turns a constant regression into a failing test -- which is exactly
    what happened when ``_LABEL_GAP`` was silently widened from 18 to 24."""
    svg = radarplot(_one_series(), x="stat", y="v").to_string()
    top_label = min(_tags(svg, "text", "tick-label"), key=lambda tag: float(tag["y"]))

    assert (CENTRE, OUTER) == ((400.0, 300.0), 242.0)
    assert (float(top_label["x"]), float(top_label["y"])) == (400.0, 40.0)  # 300 - (242 + 18)


def test_a_label_a_hair_off_vertical_still_picks_a_side() -> None:
    """``_ANCHOR_EPSILON`` exists to absorb float noise, not to claim a wedge of the circle.
    Nothing pinned its size: widening it to 0.7 rad silently turned two of five labels on an
    ordinary chart to ``middle`` and the whole suite stayed green, because the parametrised
    cases stopped at +-45 degrees (|cos| = 0.707) and the on-chart check compared anchors as
    a *set*."""
    assert _label_anchor(-math.pi / 2 + 1e-6) == "start"
    assert _label_anchor(-math.pi / 2 - 1e-6) == "end"
    assert _label_anchor(math.pi / 2 + 1e-6) == "end"


def test_every_label_on_a_real_chart_picks_the_side_its_spoke_is_on() -> None:
    """Per label, not as a set: a set comparison passes as long as all three anchors appear
    somewhere, however they are distributed."""
    svg = radarplot(_one_series(), x="stat", y="v").to_string()
    labels = _tags(svg, "text", "tick-label")

    anchors = [(label["x"], label["text-anchor"]) for label in labels]
    assert [anchor for _, anchor in anchors] == ["middle", "start", "start", "end", "end"]
    for x, anchor in anchors:
        expected = "middle" if float(x) == pytest.approx(CENTRE[0]) else ("start" if float(x) > CENTRE[0] else "end")
        assert anchor == expected


# ---------------------------------------------------------------------------
# rows that name no series
# ---------------------------------------------------------------------------


def test_a_row_with_a_missing_hue_names_no_spoke() -> None:
    """``extract_channels`` drops it from every group, so it belongs to no series and can no
    more name a spoke than a row with a missing ``x`` can. Counting it left a category no
    series could ever fill and blamed the resulting gap on an arbitrary series that never
    had that row -- ``series 'A' has no value for 'f'``, when 'A' was never asked."""
    data = {"stat": [*CATEGORIES, "f"], "v": [8.0, 6.0, 7.0, 5.0, 4.0, 3.0], "who": ["A"] * 5 + [None]}
    svg = radarplot(data, x="stat", y="v", hue="who").to_string()

    assert re.findall(r'class="tick-label"[^>]*>([^<]+)<', svg) == CATEGORIES


def test_a_missing_y_still_names_its_spoke_and_is_refused() -> None:
    """The other half of the same rule, kept apart from it: unlike a missing hue, a missing
    value does name a place on the chart, and leaving it out would change the shape."""
    data = {"stat": CATEGORIES * 2, "v": [8.0, 6.0, 7.0, 5.0, 4.0, 1.0, None, 1.0, 1.0, 1.0], "who": ["A"] * 5 + ["B"] * 5}

    with pytest.raises(ValueError, match=r"series 'B' has no value for 'b'"):
        radarplot(data, x="stat", y="v", hue="who")


@pytest.mark.parametrize("bad", ["oops", object(), [1.0]])
def test_a_non_numeric_value_is_refused_with_its_category_named(bad: object) -> None:
    """``float()`` raises here anyway, but with a message naming neither the category nor
    the column -- the same reason the finite/non-negative checks live in this module."""
    data = {"stat": CATEGORIES, "v": [1.0, bad, 3.0, 4.0, 5.0]}

    with pytest.raises(ValueError, match=r"radar values must be numbers.*for 'b'"):
        radarplot(data, x="stat", y="v")


def test_the_spoke_set_is_the_union_of_every_series_not_just_the_first() -> None:
    """Building it from one series only leaves the extra categories of the others silently
    off the chart -- the same shape change this rule exists to refuse, and it passed
    because every gap fixture happened to put the *complete* series alphabetically first."""
    data = {
        "stat": ["a", "b", "c", "d", *CATEGORIES],
        "v": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0],
        "who": ["A"] * 4 + ["B"] * 5,
    }

    with pytest.raises(ValueError, match=r"series 'A' has no value for 'e'"):
        radarplot(data, x="stat", y="v", hue="who")


@pytest.mark.parametrize("value", [-0.5, -1e-9, -1.0])
def test_the_negative_boundary_sits_at_zero_not_somewhere_below_it(value: float) -> None:
    """Only -5.0 was tested, so loosening the check to ``value < -1.0`` passed and -0.5
    still rendered -- reflected onto the opposite spoke, which is the whole failure."""
    data = {"stat": CATEGORIES, "v": [1.0, value, 3.0, 4.0, 5.0]}

    with pytest.raises(ValueError, match="non-negative"):
        radarplot(data, x="stat", y="v")


def test_zero_itself_is_on_the_allowed_side_of_that_boundary() -> None:
    """Otherwise the parametrised refusals above would pass for a check that rejected
    everything at or below zero."""
    data = {"stat": CATEGORIES, "v": [0.0, 6.0, 7.0, 5.0, 4.0]}

    assert len(_series(radarplot(data, x="stat", y="v").to_string())) == 1


def test_the_hued_dial_geometry_is_pinned_to_literal_pixels_too() -> None:
    """``test_the_dial_geometry_is_pinned_to_literal_pixels`` anchors only the no-hue
    margin, so ``_MARGIN_WITH_LEGEND`` could move (right 180 to 200, or top/bottom to
    60/20) with every hued assertion following it and nothing failing."""
    svg = radarplot(_two_series(), x="stat", y="v", hue="who").to_string()
    top_label = min(_tags(svg, "text", "tick-label"), key=lambda tag: float(tag["y"]))

    assert (HUED_CENTRE, HUED_OUTER) == ((330.0, 300.0), 242.0)
    assert (float(top_label["x"]), float(top_label["y"])) == (330.0, 40.0)  # 300 - (242 + 18)


def test_spokes_follow_the_order_the_categories_first_appear_in() -> None:
    """Not sorted: the reader's own ordering is data too, and every fixture in this file
    happens to be alphabetical, so sorting them made no test fail."""
    data = {"stat": ["e", "d", "c", "b", "a"], "v": [1.0, 2.0, 3.0, 4.0, 5.0]}
    svg = radarplot(data, x="stat", y="v").to_string()

    assert re.findall(r'class="tick-label"[^>]*>([^<]+)<', svg) == ["e", "d", "c", "b", "a"]


def test_the_gap_message_names_the_first_missing_category() -> None:
    """With one hole, ``missing[0]`` and ``missing[-1]`` are the same category, so which
    end the message reports went unpinned."""
    data = {"stat": CATEGORIES, "v": [1.0, None, 3.0, None, 5.0]}

    with pytest.raises(ValueError, match=r"no value for 'b'"):
        radarplot(data, x="stat", y="v")
