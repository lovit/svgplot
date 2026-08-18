from __future__ import annotations

import random
import re

import pytest

from svgplot.charts._layout import DEFAULT_HEIGHT, DEFAULT_WIDTH, MARGIN_WITHOUT_LEGEND, plot_area
from svgplot.charts.regression import regplot
from svgplot.scales import LinearScale
from svgplot.stats.regression import confidence_band, fit_curve

AREA = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=MARGIN_WITHOUT_LEGEND)

_VERTEX_RE = re.compile(r"[ML] (-?[\d.]+),(-?[\d.]+)")
_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')


def _noisy_line(n: int = 60, *, seed: int = 7) -> dict[str, list[float]]:
    generator = random.Random(seed)
    xs = [generator.uniform(0.0, 10.0) for _ in range(n)]
    return {"x": xs, "y": [2.0 * value + 1.0 + generator.gauss(0.0, 2.0) for value in xs]}


def _xy(data: dict[str, list[float]]) -> tuple[list[float], list[float]]:
    return data["x"], data["y"]


def _band_widths(svg: str) -> list[float]:
    (band,) = _paths(svg, "regression-band")
    upper = [y for _, y in band[:100]]
    lower = [y for _, y in reversed(band[100:])]
    return [low - up for up, low in zip(upper, lower, strict=True)]


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


# ---------------------------------------------------------------------------
# the ci=None path shares its geometry with the ci path
# ---------------------------------------------------------------------------


def test_the_fit_line_is_identical_with_and_without_a_band() -> None:
    """Both paths take the line from ``stats.regression``'s own grid helper, so an edit to
    either must move both. Before that sharing, ``ci=None`` rebuilt the grid by hand and a
    fit that dropped its intercept passed the whole suite."""
    data = _noisy_line()
    with_band = _raw_path(regplot(data, x="x", y="y").to_string(), "regression-line")
    without = _raw_path(regplot(data, x="x", y="y", ci=None).to_string(), "regression-line")

    assert with_band == without


def test_the_ci_none_line_carries_the_full_grid() -> None:
    (line,) = _paths(regplot(_noisy_line(), x="x", y="y", ci=None).to_string(), "regression-line")

    assert len(line) == 100
    assert line[0][0] == pytest.approx(AREA.left)
    assert line[-1][0] == pytest.approx(AREA.right)


def test_the_grid_spans_the_data_even_when_the_input_is_unsorted() -> None:
    """The grid runs ``min(x)..max(x)``, not ``x[0]..x[-1]`` -- rows arrive in input order,
    and assuming they are sorted silently truncates the line."""
    ordered = {"x": [1.0, 2.0, 3.0, 4.0, 5.0], "y": [2.0, 4.1, 5.9, 8.2, 9.8]}
    shuffled = {"x": [3.0, 5.0, 1.0, 4.0, 2.0], "y": [5.9, 9.8, 2.0, 8.2, 4.1]}

    assert _raw_path(regplot(ordered, x="x", y="y", ci=None).to_string(), "regression-line") == _raw_path(
        regplot(shuffled, x="x", y="y", ci=None).to_string(), "regression-line"
    )


def test_ci_none_does_not_run_the_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    """The docstring promises the work is skipped, not just the drawing. Only replacing the
    bootstrap with something that explodes can show that."""
    import svgplot.charts.regression as module

    def explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("confidence_band must not be called when ci is None")

    monkeypatch.setattr(module, "confidence_band", explode)

    assert regplot(_noisy_line(), x="x", y="y", ci=None).to_string()


def test_ci_none_leaves_the_band_channels_unaliased() -> None:
    """Three names for one list is a trap for whoever first edits band coordinates in
    place; the fit path hands back independent copies."""
    band = fit_curve(*_xy(_noisy_line()), grid=10)

    assert band.lower is not band.upper
    assert band.lower is not band.y


# ---------------------------------------------------------------------------
# the bootstrap's parameters actually reach it
# ---------------------------------------------------------------------------


def test_more_resamples_change_the_band() -> None:
    """Forwarding ``n_boot`` is not enough -- a silently clamped value passes every
    "did it raise" check while narrowing the band by half."""
    narrow = _band_widths(regplot(_noisy_line(), x="x", y="y", n_boot=10).to_string())
    wide = _band_widths(regplot(_noisy_line(), x="x", y="y", n_boot=1000).to_string())

    assert max(narrow) != pytest.approx(max(wide), rel=0.02)


def test_the_seed_reaches_the_bootstrap_unchanged() -> None:
    """ "same seed matches, different seeds differ" is satisfied by any injective mapping,
    so an offset seed survives it. Comparing against ``stats.regression`` directly does
    not."""
    data = _noisy_line()
    expected = confidence_band(data["x"], data["y"], level=0.95, n_boot=1000, seed=3, grid=100)
    (band,) = _paths(regplot(data, x="x", y="y", seed=3).to_string(), "regression-band")

    y_scale = LinearScale(
        (min([*expected.lower, *expected.upper, *data["y"]]), max([*expected.lower, *expected.upper, *data["y"]])),
        (AREA.bottom, AREA.top),
    )
    drawn_upper = [y for _, y in band[:100]]

    assert drawn_upper == pytest.approx([y_scale(value) for value in expected.upper], abs=1e-6)


# ---------------------------------------------------------------------------
# theme wiring
# ---------------------------------------------------------------------------


def test_the_series_style_keeps_both_a_stroke_and_a_translucent_fill() -> None:
    """One series class carries the band, the line and the points. A plain ``"fill"`` style
    emits ``stroke: none``, which erases the fit line entirely."""
    rule = next(
        line.strip()
        for line in regplot(_noisy_line(), x="x", y="y").to_string().splitlines()
        if line.strip().startswith(".series-1 {")
    )

    assert "stroke: #" in rule
    assert "fill-opacity" in rule
    assert "stroke: none" not in rule


def test_the_marker_radius_comes_from_the_theme() -> None:
    from svgplot.theme.base import Theme

    default = Theme()
    radii = set(re.findall(r'<circle[^>]*r="([\d.]+)"', regplot(_noisy_line(n=10), x="x", y="y").to_string()))

    assert radii == {str(int(default.marker_size)) if default.marker_size.is_integer() else str(default.marker_size)}


@pytest.mark.parametrize(("theme", "expected"), [(None, 4.0), ("minimal", 0.0)])
def test_tick_length_comes_from_the_theme(theme: str | None, expected: float) -> None:
    """Measured off the drawn tick, not inferred from the two themes differing: a hardcoded
    length also makes them differ, just at the wrong size. ``minimal`` asks for 0."""
    kwargs = {} if theme is None else {"theme": theme}
    svg = regplot(_noisy_line(n=10), x="x", y="y", ci=None, **kwargs).to_string()
    tick = next(tag for tag in re.findall(r"<line\b[^>]*/>", svg) if "tick-line" in tag)
    ends = dict(_ATTR_RE.findall(tick))

    assert abs(float(ends["y2"]) - float(ends["y1"])) == pytest.approx(expected)


def test_points_are_drawn_in_input_order() -> None:
    """The docstring says input order; sorting would silently reorder the emitted marks."""
    data = {"x": [3.0, 1.0, 2.0, 5.0, 4.0], "y": [6.0, 2.0, 4.0, 10.0, 8.0]}
    svg = regplot(data, x="x", y="y", ci=None).to_string()
    centres = [float(match) for match in re.findall(r'<circle[^>]*cx="(-?[\d.]+)"', svg)]

    assert centres != sorted(centres)
