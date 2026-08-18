from __future__ import annotations

import math
import re
from itertools import pairwise

import pytest

from svgplot.charts._layout import DEFAULT_HEIGHT, DEFAULT_WIDTH, plot_area
from svgplot.charts.radar import _LABEL_GAP, _MARGIN, _MIN_CATEGORIES, _START_ANGLE, _label_anchor, radarplot
from svgplot.scales import LinearScale, make_ticks

AREA = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=_MARGIN)
CENTRE = ((AREA.left + AREA.right) / 2, (AREA.top + AREA.bottom) / 2)
OUTER = min(AREA.right - AREA.left, AREA.bottom - AREA.top) / 2 - _LABEL_GAP

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
    return [dict(_ATTR_RE.findall(tag)) for tag in re.findall(rf"<{element}\b[^>]*?/?>", svg) if css_class in tag]


def _vertices(tag: dict[str, str]) -> list[tuple[float, float]]:
    return [(float(vx), float(vy)) for vx, vy in _VERTEX_RE.findall(tag["d"])]


def _rings(svg: str) -> list[dict[str, str]]:
    return _tags(svg, "path", "grid-line")


def _series(svg: str) -> list[dict[str, str]]:
    return _tags(svg, "path", "radar-series")


def _radius(point: tuple[float, float]) -> float:
    return math.hypot(point[0] - CENTRE[0], point[1] - CENTRE[1])


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
    assert pytest.approx(-math.pi / 2) == _START_ANGLE


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
    peaks = [max(_radius(point) for point in _vertices(polygon)) for polygon in polygons]

    assert max(peaks) == pytest.approx(OUTER)
    assert min(peaks) < OUTER


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
        (None, {"theme": "not-a-preset"}, KeyError, "unknown theme preset"),
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
