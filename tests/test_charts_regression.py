from __future__ import annotations

import random
import re

import pytest

from _svg_probe import style_rule, tags as _tags
from svgplot.charts._layout import DEFAULT_HEIGHT, DEFAULT_WIDTH, MARGIN_WITHOUT_LEGEND, plot_area
from svgplot.charts.regression import regplot
from svgplot.scales import LinearScale
from svgplot.stats.regression import confidence_band, fit_curve

AREA = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=MARGIN_WITHOUT_LEGEND)

_VERTEX_RE = re.compile(r"[ML] (-?[\d.]+),(-?[\d.]+)")


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
    """The vertices of each matching ``<path>``.

    Through the shared probe. This used to be a fifth copy of ``_tags`` with all three of the
    defects issue #117 names -- ``/>``-only, so a ``<path>`` with content was invisible; and
    substring matching twice over, on the class attribute and on the whole tag. No class in
    this chart triggers the last two today; a ``regression-line-dashed`` would, and adding one
    is a one-line change nobody would think to check this file for.
    """
    return [[(float(vx), float(vy)) for vx, vy in _VERTEX_RE.findall(tag["d"])] for tag in _tags(svg, "path", css_class)]


def _raw_path(svg: str, css_class: str) -> str:
    """The ``d`` of the first matching ``<path>``.

    The substring form here searched the *whole tag*, so a class it was not asked about would
    have it return that path's ``d`` instead -- silently, since a ``d`` is a ``d``.
    """
    return _tags(svg, "path", css_class)[0]["d"]


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
    rule = style_rule(regplot(_noisy_line(), x="x", y="y").to_string(), ".series-1")

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
    ends = _tags(svg, "line", "tick-line")[0]

    assert abs(float(ends["y2"]) - float(ends["y1"])) == pytest.approx(expected)


def test_points_are_drawn_in_input_order() -> None:
    """The docstring says input order; sorting would silently reorder the emitted marks."""
    data = {"x": [3.0, 1.0, 2.0, 5.0, 4.0], "y": [6.0, 2.0, 4.0, 10.0, 8.0]}
    svg = regplot(data, x="x", y="y", ci=None).to_string()
    centres = [float(match) for match in re.findall(r'<circle[^>]*cx="(-?[\d.]+)"', svg)]

    assert centres != sorted(centres)


# --------------------------------------------------------------------------------- tooltips


def _titled(svg: str, css_class: str) -> list[str]:
    """The ``<title>`` text of every element carrying ``css_class``, in document order.

    Through the parsed tree so an element that *lost* its title is visible as a missing entry
    rather than as one fewer match. The chart's own ``<title>`` hangs off the root ``<svg>``,
    which carries no mark class.
    """
    import xml.etree.ElementTree as ET

    root = ET.fromstring(svg)
    found = []
    for element in root.iter():
        if css_class in (element.get("class") or "").split():
            title = element.find("{http://www.w3.org/2000/svg}title")
            found.append(None if title is None else title.text)
    return found


def test_the_band_says_which_interval_it_is_and_how_it_was_estimated() -> None:
    """The band is the one mark here that is neither a datum nor labelled: a translucent region
    around a line reads as decoration until something names it, and the chart's ``<desc>`` names
    it once for the whole picture, which a reader pointing at the band is not being read.

    ``n_boot`` is part of the answer rather than an implementation detail -- a bootstrap
    interval is an estimate whose own precision depends on it, and two charts of the same data
    with different ``n_boot`` draw different bands."""
    data = {"area": [10.0, 20.0, 30.0, 40.0, 50.0], "sales": [12.0, 19.0, 33.0, 38.0, 52.0]}
    svg = regplot(data, x="area", y="sales", tooltip=True).to_string()

    assert _titled(svg, "regression-band") == ["95% confidence band · 1000 bootstrap resamples"]


def test_the_band_says_the_level_it_was_given() -> None:
    """Read back from the file. ``0.95`` reads ``95%``, not ``95.0%``, and a level that needs
    its digits keeps them."""
    data = {"area": [10.0, 20.0, 30.0, 40.0, 50.0], "sales": [12.0, 19.0, 33.0, 38.0, 52.0]}
    said = [
        _titled(regplot(data, x="area", y="sales", ci=level, n_boot=boot, tooltip=True).to_string(), "regression-band")[0]
        for level, boot in ((0.95, 1000), (0.9973, 200), (1 / 3, 1))
    ]

    assert said == [
        "95% confidence band · 1000 bootstrap resamples",
        "99.73% confidence band · 200 bootstrap resamples",
        "33.333333% confidence band · 1 bootstrap resample",
    ]


def test_the_band_never_names_a_level_the_package_refuses_to_draw() -> None:
    """Rounding to one decimal saturated at both ends: ``ci=0.999999`` read ``100% confidence
    band`` while ``ci=1.0`` is refused outright, so the mark's *accessible name* asserted a
    certainty the package will not draw. ``ci=1e-07`` read ``0%`` the same way."""
    data = {"area": [10.0, 20.0, 30.0], "sales": [12.0, 19.0, 33.0]}

    with pytest.raises(ValueError, match="strictly between 0 and 1"):
        regplot(data, x="area", y="sales", ci=1.0)
    for level, refused in ((0.999999, "100%"), (1e-07, "0%")):
        said = _titled(regplot(data, x="area", y="sales", ci=level, tooltip=True).to_string(), "regression-band")[0]
        assert not said.startswith(refused + " "), said


def test_the_band_and_the_description_spell_the_level_the_same_way() -> None:
    """They are two halves of one claim -- the ``<desc>`` says it once for the picture and the
    ``<title>`` says it to a reader pointing at the band. Formatted two ways they disagreed:
    ``ci=0.9501`` read ``95.01%`` in one and ``95%`` in the other, and ``0.95`` and ``0.9501``
    produced *identical* tooltips for two charts that draw different bands."""
    data = {"area": [10.0, 20.0, 30.0], "sales": [12.0, 19.0, 33.0]}

    for level in (0.95, 0.9501, 0.999999, 1 / 3):
        svg = regplot(data, x="area", y="sales", ci=level, tooltip=True).to_string()
        described = re.search(r"with a (\S+) confidence band", svg).group(1)
        assert _titled(svg, "regression-band")[0].startswith(described + " confidence band"), (described, svg[:0])

    both = [regplot(data, x="area", y="sales", ci=level, tooltip=True).to_string() for level in (0.95, 0.9501)]
    assert both[0] != both[1], "the fixture stopped drawing two different bands"
    assert _titled(both[0], "regression-band") != _titled(both[1], "regression-band")


def test_a_level_the_band_accepts_as_a_string_does_not_break_the_tooltip() -> None:
    """``confidence_band`` coerces, so ``ci="0.95"`` renders with tooltips off. The clause that
    describes the band should not be the thing that turns a chart that draws into a
    ``TypeError``."""
    data = {"area": [10.0, 20.0, 30.0], "sales": [12.0, 19.0, 33.0]}
    svg = regplot(data, x="area", y="sales", ci="0.95", tooltip=True).to_string()  # type: ignore[arg-type]

    assert _titled(svg, "regression-band") == ["95% confidence band · 1000 bootstrap resamples"]


def test_a_point_reads_its_own_row_back() -> None:
    data = {"area": [10.0, 20.0, 30.0], "sales": [12.0, 19.0, 33.0]}
    svg = regplot(data, x="area", y="sales", tooltip=True).to_string()

    assert _titled(svg, "scatter-point") == ["area: 10 · sales: 12", "area: 20 · sales: 19", "area: 30 · sales: 33"]


def test_a_mark_that_is_not_drawn_gets_no_accessible_name() -> None:
    """``ci=None`` draws no band and ``scatter=False`` draws no points. There is nothing to hang
    a name on either way, and inventing one would name a mark the caller switched off."""
    data = {"area": [10.0, 20.0, 30.0], "sales": [12.0, 19.0, 33.0]}
    no_band = regplot(data, x="area", y="sales", ci=None, tooltip=True).to_string()
    no_points = regplot(data, x="area", y="sales", scatter=False, tooltip=True).to_string()

    # The lists, not their lengths: ``_titled`` yields ``None`` for an untitled element, so
    # ``len([None]) == 1`` passed while the band's tooltip was dropped on this exact path.
    assert _titled(no_band, "regression-band") == []
    assert _titled(no_band, "scatter-point") == ["area: 10 · sales: 12", "area: 20 · sales: 19", "area: 30 · sales: 33"]
    assert _titled(no_points, "scatter-point") == []
    assert _titled(no_points, "regression-band") == ["95% confidence band · 1000 bootstrap resamples"]


def test_the_fit_line_is_left_unnamed_because_the_desc_already_names_it() -> None:
    """A line through a cloud of points is the one mark whose meaning the ``<desc>`` already
    carries -- giving it a ``<title>`` would add an element per chart to say what the reader can
    already see."""
    data = {"area": [10.0, 20.0, 30.0], "sales": [12.0, 19.0, 33.0]}
    svg = regplot(data, x="area", y="sales", tooltip=True).to_string()

    assert _titled(svg, "regression-line") == [None]


def test_the_default_draws_no_tooltip_and_saying_so_changes_nothing() -> None:
    """What this can check is that ``tooltip=False`` is the same call as not writing it, and
    that no mark is titled. It is deliberately not named for byte-identity with the version
    before ``tooltip=`` existed, which it cannot see -- both sides are this branch's code.
    ``docs/gallery/*.html`` holds those bytes."""
    data = {"area": [10.0, 20.0, 30.0], "sales": [12.0, 19.0, 33.0]}
    omitted = regplot(data, x="area", y="sales").to_string()
    explicit = regplot(data, x="area", y="sales", tooltip=False).to_string()

    assert omitted == explicit
    assert _titled(omitted, "scatter-point") == [None, None, None]
    assert _titled(omitted, "regression-band") == [None]


def test_a_column_name_too_long_to_read_is_dropped_from_a_point_tooltip() -> None:
    """A column name is written once per point. Dropped rather than truncated -- half a column
    name is a different column name -- and the value stays, because that is what the reader came
    for."""
    long_name = "면" * 5000
    data = {long_name: [10.0, 20.0, 30.0], "sales": [12.0, 19.0, 33.0]}
    svg = regplot(data, x=long_name, y="sales", tooltip=True).to_string()

    assert _titled(svg, "scatter-point") == ["10 · sales: 12", "20 · sales: 19", "30 · sales: 33"]
    assert long_name not in svg
