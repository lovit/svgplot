from __future__ import annotations

import random
import re

import pytest

from svgplot.charts._layout import DEFAULT_HEIGHT, DEFAULT_WIDTH, MARGIN_WITHOUT_LEGEND, plot_area
from svgplot.charts.regression import regplot

AREA = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=MARGIN_WITHOUT_LEGEND)

_VERTEX_RE = re.compile(r"[ML] (-?[\d.]+),(-?[\d.]+)")
_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')


def _noisy_line(n: int = 60, *, seed: int = 7) -> dict[str, list[float]]:
    generator = random.Random(seed)
    xs = [generator.uniform(0.0, 10.0) for _ in range(n)]
    return {"x": xs, "y": [2.0 * value + 1.0 + generator.gauss(0.0, 2.0) for value in xs]}


def _paths(svg: str, css_class: str) -> list[list[tuple[float, float]]]:
    tags = [dict(_ATTR_RE.findall(tag)) for tag in re.findall(r"<path\b[^>]*/>", svg)]
    return [
        [(float(vx), float(vy)) for vx, vy in _VERTEX_RE.findall(tag["d"])]
        for tag in tags
        if css_class in tag.get("class", "")
    ]


def _raw_path(svg: str, css_class: str) -> str:
    return next(dict(_ATTR_RE.findall(tag))["d"] for tag in re.findall(r"<path\b[^>]*/>", svg) if css_class in tag)


# ---------------------------------------------------------------------------
# the band
# ---------------------------------------------------------------------------


def test_the_band_is_one_closed_region() -> None:
    """Two separate open edges would need their own fill rule to become a region, and the
    gap between them would not be fillable at all -- so it has to be a single closed path,
    the same shape ``area`` uses for a stacked band."""
    svg = regplot(_noisy_line(), x="x", y="y").to_string()

    assert _raw_path(svg, "regression-band").endswith("Z")
    assert len(_paths(svg, "regression-band")[0]) == 200


def test_the_band_runs_out_along_the_top_and_back_along_the_bottom() -> None:
    """Order matters: interleaving the two edges would draw a bow tie, which fills as two
    triangles rather than the ribbon between the edges."""
    svg = regplot(_noisy_line(), x="x", y="y").to_string()
    (band,) = _paths(svg, "regression-band")
    outbound = [x for x, _ in band[:100]]
    inbound = [x for x, _ in band[100:]]

    assert outbound == sorted(outbound)
    assert inbound == sorted(inbound, reverse=True)
    assert outbound == list(reversed(inbound))


def test_the_band_encloses_the_fit_line_at_every_grid_position() -> None:
    """The band describes the line, so a line escaping it renders as a ribbon floating off
    the curve. Pixel y grows downward, so "above" is the smaller number."""
    svg = regplot(_noisy_line(), x="x", y="y").to_string()
    (band,) = _paths(svg, "regression-band")
    (line,) = _paths(svg, "regression-line")
    upper = [y for _, y in band[:100]]
    lower = [y for _, y in reversed(band[100:])]

    assert all(up <= mid <= low + 1e-9 for up, mid, low in zip(upper, [y for _, y in line], lower, strict=True))


def test_the_band_is_widest_at_the_extremes() -> None:
    """The hourglass that ``stats.regression`` produces has to survive the pixel mapping --
    a band of constant drawn width would mean the geometry flattened it."""
    svg = regplot(_noisy_line(), x="x", y="y").to_string()
    (band,) = _paths(svg, "regression-band")
    upper = [y for _, y in band[:100]]
    lower = [y for _, y in reversed(band[100:])]
    widths = [low - up for up, low in zip(upper, lower, strict=True)]

    assert widths[0] > min(widths)
    assert widths[-1] > min(widths)


def test_the_y_domain_covers_the_whole_band() -> None:
    """Scaling to the fit line alone would push the band's own edges past the plot area,
    where they are clipped -- the widest part of the band is exactly what a reader needs
    to see. With the points off, the band's extremes are the domain, so they must land
    precisely on the floor and the ceiling."""
    svg = regplot(_noisy_line(), x="x", y="y", scatter=False).to_string()
    (band,) = _paths(svg, "regression-band")
    ys = [y for _, y in band]

    assert min(ys) == pytest.approx(AREA.top)
    assert max(ys) == pytest.approx(AREA.bottom)


def test_the_y_domain_covers_the_points_as_well() -> None:
    """With the observations drawn they scatter well past the band, so the domain has to
    grow to them too -- otherwise the outlying points are clipped off the canvas."""
    data = _noisy_line()
    svg = regplot(data, x="x", y="y").to_string()
    centres = [float(match) for match in re.findall(r'<circle[^>]*cy="(-?[\d.]+)"', svg)]

    assert min(centres) >= AREA.top - 1e-6
    assert max(centres) <= AREA.bottom + 1e-6
    assert min(centres) == pytest.approx(AREA.top) or max(centres) == pytest.approx(AREA.bottom)


def test_no_band_is_emitted_without_a_ci() -> None:
    """``ci=None`` also has to skip the work, not just the drawing -- the band is the
    expensive part."""
    svg = regplot(_noisy_line(), x="x", y="y", ci=None).to_string()

    assert "regression-band" not in svg
    assert _paths(svg, "regression-line")


def test_a_wider_ci_draws_a_wider_band() -> None:
    def spread(level: float) -> float:
        (band,) = _paths(regplot(_noisy_line(), x="x", y="y", ci=level).to_string(), "regression-band")
        upper = [y for _, y in band[:100]]
        lower = [y for _, y in reversed(band[100:])]
        return max(low - up for up, low in zip(upper, lower, strict=True))

    assert spread(0.99) > spread(0.80)


# ---------------------------------------------------------------------------
# the line and the points
# ---------------------------------------------------------------------------


def test_the_fit_line_spans_the_observed_x_range() -> None:
    (line,) = _paths(regplot(_noisy_line(), x="x", y="y").to_string(), "regression-line")

    assert line[0][0] == pytest.approx(AREA.left)
    assert line[-1][0] == pytest.approx(AREA.right)


def test_the_fit_line_is_straight() -> None:
    """It is sampled on a grid rather than drawn as two endpoints, so every interior vertex
    must still land on the chord -- otherwise the sampling is picking up something that
    isn't the fit. The tolerance is set by ``format_coord``, which rounds coordinates to
    six decimals: measured worst deviation 1.02e-6, i.e. rounding alone."""
    (line,) = _paths(regplot(_noisy_line(), x="x", y="y").to_string(), "regression-line")
    (x0, y0), (x1, y1) = line[0], line[-1]
    slope = (y1 - y0) / (x1 - x0)

    assert all(y == pytest.approx(y0 + slope * (x - x0), abs=2e-6) for x, y in line)


def test_one_point_is_drawn_per_observation() -> None:
    svg = regplot(_noisy_line(n=25), x="x", y="y").to_string()

    assert svg.count('class="series-1 scatter-point"') == 25


def test_no_points_are_drawn_when_scatter_is_off() -> None:
    assert "<circle" not in regplot(_noisy_line(), x="x", y="y", scatter=False).to_string()


def test_the_line_is_drawn_over_the_band() -> None:
    """Document order is paint order in SVG: a band emitted after the line would cover it."""
    svg = regplot(_noisy_line(), x="x", y="y").to_string()

    assert svg.index("regression-band") < svg.index("regression-line")


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------


def test_the_same_seed_serializes_byte_for_byte() -> None:
    """What makes ``stats.regression``'s seeded bootstrap observable at the chart level --
    and what every snapshot of a ``regplot`` depends on."""
    data = _noisy_line()

    assert regplot(data, x="x", y="y", seed=5).to_string() == regplot(data, x="x", y="y", seed=5).to_string()


def test_a_different_seed_changes_the_band() -> None:
    """Otherwise ``seed`` would be decorative and the resampling would not be happening."""
    data = _noisy_line()

    assert regplot(data, x="x", y="y", seed=5).to_string() != regplot(data, x="x", y="y", seed=6).to_string()


def test_the_seed_only_affects_the_band() -> None:
    """The fit itself is deterministic, so two seeds must still draw the same line."""
    data = _noisy_line()

    assert _paths(regplot(data, x="x", y="y", seed=5).to_string(), "regression-line") == _paths(
        regplot(data, x="x", y="y", seed=6).to_string(), "regression-line"
    )


def test_the_global_random_state_does_not_leak_in() -> None:
    data = _noisy_line()

    random.seed(1)
    first = regplot(data, x="x", y="y").to_string()
    random.seed(999)

    assert regplot(data, x="x", y="y").to_string() == first


# ---------------------------------------------------------------------------
# delegation and rejected input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"ci": 0.0}, "strictly between 0 and 1"),
        ({"ci": 1.0}, "strictly between 0 and 1"),
        ({"ci": -0.5}, "strictly between 0 and 1"),
        ({"n_boot": 0}, "at least 1"),
        ({"n_boot": 100_000}, "at most"),
    ],
)
def test_stats_regression_s_validation_surfaces_unchanged(kwargs: dict, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        regplot(_noisy_line(), x="x", y="y", **kwargs)


@pytest.mark.parametrize("ci", [0.95, None])
def test_a_vertical_sample_is_rejected_with_or_without_a_band(ci: float | None) -> None:
    """``ci=None`` takes a different code path, so it needs its own check that the
    degenerate fit is still refused rather than dividing by zero."""
    with pytest.raises(ValueError, match="vertical"):
        regplot({"x": [1.0, 1.0, 1.0, 1.0], "y": [1.0, 2.0, 3.0, 4.0]}, x="x", y="y", ci=ci)


@pytest.mark.parametrize(
    ("data", "kwargs", "error", "match"),
    [
        ({"x": [], "y": []}, {}, ValueError, "at least one row"),
        ({"x": [None, None], "y": [1.0, 2.0]}, {}, ValueError, "both x and y"),
        ({"x": [1.0, 2.0], "y": [1.0, 2.0]}, {}, ValueError, "at least 3 points"),
        (None, {"x": "nope"}, KeyError, "not found"),
        (None, {"theme": "not-a-preset"}, KeyError, "unknown theme preset"),
    ],
)
def test_regplot_rejects_unusable_input(data: dict | None, kwargs: dict, error: type[Exception], match: str) -> None:
    payload = _noisy_line(n=10) if data is None else data
    call_kwargs = {"x": "x", "y": "y", **kwargs}
    with pytest.raises(error, match=match):
        regplot(payload, **call_kwargs)


def test_rows_missing_either_channel_are_dropped() -> None:
    data = _noisy_line(n=20)
    data["x"] = [*data["x"][:19], None]
    data["y"] = [*data["y"][:19], 5.0]

    assert regplot(data, x="x", y="y").to_string().count('class="series-1 scatter-point"') == 19
