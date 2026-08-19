from __future__ import annotations

import math
import re
from itertools import pairwise

import pytest

from _svg_probe import tags as _tags
from svgplot.charts._polar import polar_point
from svgplot.charts.gauge import (
    _END_ANGLE,
    _MIN_RING_THICKNESS,
    _START_ANGLE,
    _SWEEP,
    gaugeplot,
)
from svgplot.scales import LinearScale, make_ticks

DATA = {"name": ["a", "b", "c"], "score": [30.0, 60.0, 90.0]}

# Geometry gaugeplot derives from its fixed canvas/margins (800x600, margin
# top/right/bottom/left = 30/180/30/30): centre (325, 300), and an outer radius of
# min(590, 540)/2 - 28 (the reserved tick-label margin).
_CX, _CY = 325.0, 300.0
_OUTER_RADIUS = 242.0

_PATH_RE = re.compile(r'<path[^>]*\sd="([^"]+)"[^>]*\sclass="([^"]+)"')
_TEXT_RE = re.compile(r'<text[^>]*\sclass="([^"]+)"[^>]*>([^<]*)</text>')
_LINE_RE = re.compile(r'<line x1="(-?[\d.]+)" y1="(-?[\d.]+)" x2="(-?[\d.]+)" y2="(-?[\d.]+)" class="tick-line"')
# ring_path emits: M x1,y1 A R,R 0 large sweep x2,y2 L ...
_RING_RE = re.compile(
    r"^M (-?[\d.]+),(-?[\d.]+) A ([\d.]+),[\d.]+ 0 (\d) (\d) (-?[\d.]+),(-?[\d.]+) L (-?[\d.]+),(-?[\d.]+) A ([\d.]+),"
)


def _svg(data: object = DATA, **kwargs: object) -> str:
    return gaugeplot(data, "score", **kwargs).to_string()  # type: ignore[arg-type]


def _paths(svg: str, css_class: str) -> list[str]:
    return [d for d, classes in _PATH_RE.findall(svg) if css_class in classes.split()]


def _texts(svg: str, css_class: str) -> list[str]:
    return [text for classes, text in _TEXT_RE.findall(svg) if css_class in classes.split()]


def _angle(x: float, y: float) -> float:
    """The gauge angle of a point, unwrapped into the sweep's own interval.

    ``atan2`` answers in ``(-pi, pi]``, but the sweep starts at -210 degrees, so a raw
    answer for a point on the left half comes back a full turn too high.
    """
    theta = math.atan2(y - _CY, x - _CX)
    while theta > _END_ANGLE + 1e-9:
        theta -= 2 * math.pi
    return theta


def _ring(d: str) -> dict[str, float]:
    """Outer radius, start/end angle and inner radius of one ``ring_path``."""
    match = _RING_RE.match(d)
    assert match is not None, f"not a ring path: {d!r}"
    x1, y1, outer, large, sweep, x2, y2, ix2, iy2, inner = (float(group) for group in match.groups())
    return {
        "outer": outer,
        "inner": inner,
        "start": _angle(x1, y1),
        "end": _angle(x2, y2),
        "large_arc": large,
        "sweep_flag": sweep,
    }


def _value_sweep(svg: str) -> float:
    """The single value arc's swept angle. Zero when no arc was emitted at all."""
    arcs = _paths(svg, "gauge-value")
    if not arcs:
        return 0.0
    assert len(arcs) == 1
    ring = _ring(arcs[0])
    return ring["end"] - ring["start"]


# ---------------------------------------------------------------------------
# the sweep encodes the value
# ---------------------------------------------------------------------------


def test_vmin_draws_nothing_and_vmax_draws_the_whole_sweep() -> None:
    assert _value_sweep(_svg({"score": [0.0]}, vmin=0, vmax=100)) == 0.0
    assert _value_sweep(_svg({"score": [100.0]}, vmin=0, vmax=100)) == pytest.approx(_SWEEP)


@pytest.mark.parametrize("value", [0.0, 12.5, 25.0, 50.0, 75.0, 99.0, 100.0])
def test_the_sweep_is_the_value_s_own_fraction_of_the_range(value: float) -> None:
    """A ratio, not just the two ends: a scale that saturated in the middle, or one that
    mapped through the wrong pair of angles, still hits 0 and full at the extremes."""
    sweep = _value_sweep(_svg({"score": [value]}, vmin=0, vmax=100))

    assert sweep == pytest.approx(_SWEEP * value / 100)


def test_the_sweep_is_strictly_monotone_across_the_range() -> None:
    sweeps = [_value_sweep(_svg({"score": [float(value)]}, vmin=0, vmax=100)) for value in range(5, 100, 5)]

    assert sweeps == sorted(sweeps)
    assert all(later > earlier for earlier, later in pairwise(sweeps))


def test_the_range_can_start_somewhere_other_than_zero() -> None:
    """``vmin`` has to shift the mapping, not merely gate it -- an implementation that
    divided by ``vmax`` alone answers 0.75 here instead of 0.5."""
    sweep = _value_sweep(_svg({"score": [150.0]}, vmin=100, vmax=200))

    assert sweep == pytest.approx(_SWEEP / 2)


def test_the_arc_starts_at_the_low_end_of_the_scale() -> None:
    ring = _ring(_paths(_svg({"score": [40.0]}, vmin=0, vmax=100), "gauge-value")[0])

    assert ring["start"] == pytest.approx(_START_ANGLE)
    assert ring["end"] < _END_ANGLE


# ---------------------------------------------------------------------------
# clamping
# ---------------------------------------------------------------------------


def test_a_value_past_the_top_clamps_instead_of_winding_past_the_end() -> None:
    """Unclamped, 250 out of 100 sweeps 600 degrees, which lands the arc's endpoint where
    240 degrees would -- but with the large-arc flag flipped, so it draws *less* than a
    value of 100 does. Reporting a smaller arc for a bigger number is the failure this
    guards; asserting the endpoint alone would not catch it."""
    over = _paths(_svg({"score": [250.0]}, vmin=0, vmax=100), "gauge-value")[0]
    full = _paths(_svg({"score": [100.0]}, vmin=0, vmax=100), "gauge-value")[0]

    assert _ring(over) == _ring(full)
    assert _value_sweep(_svg({"score": [250.0]}, vmin=0, vmax=100)) == pytest.approx(_SWEEP)


def test_a_value_below_the_bottom_clamps_to_no_arc() -> None:
    assert _paths(_svg({"score": [-40.0]}, vmin=0, vmax=100), "gauge-value") == []


def test_a_clamped_value_still_prints_its_real_number() -> None:
    """The arc is clamped because the geometry has nowhere else to go; the datum is not.
    Rewriting the printed value to the bound would report data the caller never gave."""
    assert _texts(_svg({"score": [250.0]}, vmin=0, vmax=100), "legend-text") == ["250"]


# ---------------------------------------------------------------------------
# bounds validation and defaults
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("vmin", "vmax"), [(100, 100), (100, 50), (0.0, 0.0), (5, -5)])
def test_rejects_an_empty_or_inverted_range(vmin: float, vmax: float) -> None:
    with pytest.raises(ValueError, match="non-empty and increasing"):
        _svg({"score": [1.0]}, vmin=vmin, vmax=vmax)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), "10", None.__class__, True])
def test_rejects_a_non_finite_or_non_real_bound(bad: object) -> None:
    with pytest.raises(ValueError, match="vmin must be a finite number"):
        _svg({"score": [1.0]}, vmin=bad, vmax=100)
    with pytest.raises(ValueError, match="vmax must be a finite number"):
        _svg({"score": [1.0]}, vmin=0, vmax=bad)


def test_the_default_range_is_anchored_at_zero() -> None:
    """Not ``[min(values), max(values)]``: a gauge answers "how far along", and a floor
    that floats up to the smallest datum draws 50 and 100 as an empty and a full arc."""
    svg = _svg({"score": [50.0, 100.0]})

    assert _value_sweep_of(svg, index=0) == pytest.approx(_SWEEP / 2)
    assert _value_sweep_of(svg, index=1) == pytest.approx(_SWEEP)


def test_a_negative_value_pulls_the_default_floor_down_to_itself() -> None:
    """Otherwise the value sits below ``vmin`` and clamps to nothing, so the chart would
    silently draw an empty gauge for data it was given."""
    svg = _svg({"score": [-50.0, 50.0]})

    assert _value_sweep_of(svg, index=0) == 0.0
    assert _value_sweep_of(svg, index=1) == pytest.approx(_SWEEP)


def test_an_explicit_bound_is_not_widened_by_the_data() -> None:
    """``vmax=50`` with a datum of 100 must clamp, not silently re-fit the scale."""
    assert _value_sweep(_svg({"score": [100.0]}, vmin=0, vmax=50)) == pytest.approx(_SWEEP)
    assert _texts(_svg({"score": [100.0]}, vmin=0, vmax=50), "tick-label")[-1] == "50"


def _value_sweep_of(svg: str, *, index: int) -> float:
    """The swept angle of the ``index``-th row's arc, matched by its ring radius.

    Rows whose value clamps to nothing emit no arc at all, so the arcs cannot simply be
    read positionally -- they are matched back to their ring by radius.
    """
    tracks = [_ring(d) for d in _paths(svg, "gauge-track")]
    arcs = {round(_ring(d)["outer"], 6): _ring(d) for d in _paths(svg, "gauge-value")}
    ring = arcs.get(round(tracks[index]["outer"], 6))
    return 0.0 if ring is None else ring["end"] - ring["start"]


# ---------------------------------------------------------------------------
# concentric rings
# ---------------------------------------------------------------------------


def test_each_row_gets_its_own_ring_further_in() -> None:
    tracks = [_ring(d) for d in _paths(_svg(), "gauge-track")]

    assert len(tracks) == 3
    radii = [(track["outer"], track["inner"]) for track in tracks]
    assert radii[0][0] == pytest.approx(_OUTER_RADIUS)
    for (_, inner), (outer_next, _) in pairwise(radii):
        # A gap, not merely a different radius: touching rings read as one thick band.
        assert outer_next < inner


def test_every_row_is_measured_against_the_same_range() -> None:
    """Per-row ranges would make the rings incomparable and the one tick ring a lie."""
    svg = _svg(vmin=0, vmax=100)
    sweeps = [_value_sweep_of(svg, index=index) for index in range(3)]

    assert sweeps == [pytest.approx(_SWEEP * fraction) for fraction in (0.3, 0.6, 0.9)]


def test_the_track_spans_the_whole_range_however_small_the_value_is() -> None:
    """The track is what makes a short arc readable -- without it there is nothing on the
    page saying how much of the scale is left."""
    track = _ring(_paths(_svg({"score": [1.0]}, vmin=0, vmax=100), "gauge-track")[0])

    assert track["start"] == pytest.approx(_START_ANGLE)
    assert track["end"] == pytest.approx(_END_ANGLE)


def test_the_value_arc_shares_its_ring_with_its_own_track() -> None:
    svg = _svg(vmin=0, vmax=100)
    tracks = [(_ring(d)["outer"], _ring(d)["inner"]) for d in _paths(svg, "gauge-track")]
    arcs = [(_ring(d)["outer"], _ring(d)["inner"]) for d in _paths(svg, "gauge-value")]

    assert arcs == tracks


@pytest.mark.parametrize(("rows", "thickness"), [(24, 2.72), (30, 1.38), (39, 0.14), (60, -1.31)])
def test_too_many_rows_is_refused_rather_than_drawn_too_thin_to_see(rows: int, thickness: float) -> None:
    """Only the 60-row case was covered, and there the rings come out *negative* -- so the
    whole ``0 < thickness < 3`` band went unchecked and ``_MIN_RING_THICKNESS`` could fall
    to 0.1 with the suite green, quietly rendering 39 rings 0.14px thick."""
    with pytest.raises(ValueError, match="reads as an arc") as caught:
        _svg({"score": [1.0] * rows})

    assert f"{thickness:.2f}px thick" in str(caught.value)


def test_the_row_count_just_under_the_limit_still_renders() -> None:
    """Pins the refusal to the measured thickness rather than to an arbitrary row count:
    if the ring geometry changes, this fails alongside the test above instead of leaving
    the limit unexercised from below."""
    band = _OUTER_RADIUS * (1.0 - 0.35)
    largest = int((band + 4.0) // (_MIN_RING_THICKNESS + 4.0))

    assert len(_paths(_svg({"score": [1.0] * largest}), "gauge-track")) == largest


# ---------------------------------------------------------------------------
# ticks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("vmin", "vmax"), [(0, 100), (0, 95), (3, 97), (-10, 45), (0, 7)])
def test_ticks_land_where_the_angle_scale_puts_them(vmin: float, vmax: float) -> None:
    """Recomputed from ``make_ticks`` and a fresh scale rather than asserting that some
    ticks exist: a chart that placed them by evenly dividing the sweep would still emit
    the right number of lines with the right labels, at the wrong angles.

    The domains matter as much as the recomputation. On ``(0, 100)`` -- and on any domain
    whose nice ticks happen to land on both ends -- evenly dividing the sweep gives exactly
    the same angles, so that fixture alone lets the very mistake this docstring names walk
    through. ``(0, 95)``, ``(3, 97)`` and ``(-10, 45)`` all leave the ticks short of one end
    or both, which is what separates the two."""
    svg = _svg({"score": [float(vmin)]}, vmin=vmin, vmax=vmax)
    expected_scale = LinearScale((float(vmin), float(vmax)), (_START_ANGLE, _END_ANGLE))
    ticks = make_ticks(expected_scale)
    expected = [expected_scale(float(tick)) for tick in ticks]

    drawn = [_angle(float(x1), float(y1)) for x1, y1, _, _ in _LINE_RE.findall(svg)]
    assert drawn == pytest.approx(expected)
    # ...and at least one of these domains must actually disagree with even division, or
    # the parametrisation is decorative.
    if (vmin, vmax) == (3, 97):
        even = [_START_ANGLE + _SWEEP * index / (len(ticks) - 1) for index in range(len(ticks))]
        assert drawn != pytest.approx(even)


def test_tick_marks_sit_outside_the_outer_ring() -> None:
    svg = _svg({"score": [40.0]}, vmin=0, vmax=100)

    for x1, y1, x2, y2 in _LINE_RE.findall(svg):
        inner = math.hypot(float(x1) - _CX, float(y1) - _CY)
        outer = math.hypot(float(x2) - _CX, float(y2) - _CY)
        assert inner == pytest.approx(_OUTER_RADIUS)
        assert outer > inner


def test_tick_labels_clear_the_tick_marks_they_belong_to() -> None:
    """A label starting where its tick mark ends overlaps it, and this package cannot
    measure the glyph to notice. Checking only that the *ticks* sit outside the ring left
    the gap free to collapse to zero."""
    svg = _svg({"score": [40.0]}, vmin=0, vmax=100)
    tick_ends = [math.hypot(float(x2) - _CX, float(y2) - _CY) for _, _, x2, y2 in _LINE_RE.findall(svg)]
    label_radii = [math.hypot(float(tag["x"]) - _CX, float(tag["y"]) - _CY) for tag in _tags(svg, "text", "tick-label")]

    assert len(label_radii) == len(tick_ends)
    for radius, tip in zip(label_radii, tick_ends, strict=True):
        assert radius > tip + 5.0, f"label at {radius} sits on a tick ending at {tip}"


def test_tick_labels_name_the_tick_values() -> None:
    svg = _svg({"score": [40.0]}, vmin=0, vmax=100)
    expected = make_ticks(LinearScale((0.0, 100.0), (_START_ANGLE, _END_ANGLE)))

    assert _texts(svg, "tick-label") == [str(int(tick)) for tick in expected]  # type: ignore[arg-type]


def test_tick_labels_take_their_side_from_their_own_half_of_the_dial() -> None:
    """A single anchor would push the leftmost labels over the arc and hang the rightmost
    ones off the canvas."""
    svg = _svg({"score": [40.0]}, vmin=0, vmax=100)
    labelled = re.findall(r'<text x="(-?[\d.]+)"[^>]*text-anchor="(\w+)"[^>]*class="tick-label"', svg)

    for x, anchor in labelled:
        assert anchor == ("end" if float(x) < _CX else "start")


# ---------------------------------------------------------------------------
# legend and value text
# ---------------------------------------------------------------------------


def test_the_legend_names_the_labels_column() -> None:
    legend_texts = _texts(_svg(labels="name"), "legend-text")

    assert legend_texts[-3:] == ["a", "b", "c"]


def test_rows_are_numbered_from_one_without_a_labels_column() -> None:
    svg = gaugeplot({"score": [30.0, 60.0]}, "score").to_string()

    assert _texts(svg, "legend-text")[-2:] == ["1", "2"]


def test_a_single_unlabelled_row_gets_no_legend() -> None:
    """Its one entry would read "1" against a chart with nothing to distinguish it from --
    the number is already printed in the middle."""
    svg = _svg({"score": [40.0]}, vmin=0, vmax=100)

    assert _texts(svg, "legend-text") == ["40"]


def test_the_legend_swatch_is_a_filled_rect_not_a_line() -> None:
    """``render_legend`` knows "stroke" (a line swatch) and "fill" (a rect) only, and an
    outlined arc reads as a filled swatch -- passing the series' own "outlined" through
    raises. Nothing checked which of the two it settled on."""
    svg = _svg(labels="name")

    assert _tags(svg, "rect", "series-1")
    assert not _tags(svg, "line", "series-1")


def test_a_single_labelled_row_still_gets_its_legend() -> None:
    svg = gaugeplot({"score": [40.0], "name": ["cpu"]}, "score", labels="name").to_string()

    assert _texts(svg, "legend-text") == ["40", "cpu"]


def test_the_values_are_printed_in_the_hole_in_row_order() -> None:
    svg = _svg(vmin=0, vmax=100)

    assert _texts(svg, "legend-text")[:3] == ["30", "60", "90"]


def test_the_printed_values_are_centred_as_a_block_on_the_dial() -> None:
    """One line or five, the stack has to stay centred -- laid out from the top down it
    would drift below the centre as rows are added."""
    positions = re.findall(r'<text x="325" y="(-?[\d.]+)" text-anchor="middle"[^>]*class="legend-text"', _svg())

    assert [float(y) for y in positions] == pytest.approx([_CY - 18.0, _CY, _CY + 18.0])


@pytest.mark.parametrize(("value", "printed"), [(12.25, "12.25"), (0.123456789, "0.123456789"), (1e-7, "1e-07")])
def test_a_fractional_value_is_printed_without_being_rounded(value: float, printed: str) -> None:
    """``format_coord`` rounds to six places because it formats *coordinates*; using it here
    would silently rewrite the datum. 12.25 alone does not show that -- both functions
    return "12.25" for it -- so the values that actually separate them are what pin it:
    ``format_coord`` answers "0.123457" and, worse, turns 1e-07 into "0"."""
    assert _texts(_svg({"score": [value]}, vmin=0, vmax=100), "legend-text") == [printed]


# ---------------------------------------------------------------------------
# input validation
# ---------------------------------------------------------------------------


def test_rejects_a_missing_value_column() -> None:
    with pytest.raises(KeyError, match="value column not found"):
        gaugeplot({"other": [1.0]}, "score")


def test_rejects_a_missing_labels_column() -> None:
    with pytest.raises(KeyError, match="labels column not found"):
        gaugeplot({"score": [1.0]}, "score", labels="nope")


def test_rejects_data_with_no_rows() -> None:
    with pytest.raises(ValueError, match="at least one row"):
        gaugeplot({"score": []}, "score")


def test_drops_rows_whose_value_is_missing() -> None:
    svg = gaugeplot({"score": [30.0, None, 90.0]}, "score", vmin=0, vmax=100).to_string()

    assert len(_paths(svg, "gauge-track")) == 2
    assert _texts(svg, "legend-text")[:2] == ["30", "90"]


def test_rejects_data_where_every_row_is_missing() -> None:
    with pytest.raises(ValueError, match="after dropping missing values"):
        gaugeplot({"score": [None, None]}, "score")


@pytest.mark.parametrize("bad", [float("inf"), float("-inf")])
def test_rejects_a_non_finite_value(bad: float) -> None:
    """A nan is already dropped as missing; an inf is not, and would become a nan angle
    that only fails later with a message naming a coordinate rather than the row."""
    with pytest.raises(ValueError, match="gauge values must be finite"):
        gaugeplot({"score": [bad]}, "score")


# ---------------------------------------------------------------------------
# styling contract
# ---------------------------------------------------------------------------


def test_every_drawn_class_is_styled_by_the_theme() -> None:
    """The class a mark carries has to be one the ``<style>`` block actually names --
    a bespoke class inherits the browser default and disappears on a dark theme."""
    svg = _svg()
    style = svg[svg.index("<style>") : svg.index("</style>")]
    drawn = {name for _, classes in _PATH_RE.findall(svg) for name in classes.split()}
    drawn |= {name for classes, _ in _TEXT_RE.findall(svg) for name in classes.split()}

    unstyled = {name for name in drawn if f".{name} " not in style}
    assert unstyled <= {"gauge-track", "gauge-value"}, f"unstyled classes: {sorted(unstyled)}"
    # The two semantic markers above are hooks for the reader's own CSS, and each is
    # paired with a class the theme does style, so neither renders unstyled.
    for marker, styled in (("gauge-track", "spine"), ("gauge-value", "series")):
        paired = [classes for _, classes in _PATH_RE.findall(svg) if marker in classes.split()]
        assert paired and all(any(name.startswith(styled) for name in classes.split()) for classes in paired)


def test_the_arcs_are_outlined_so_a_ring_reads_against_its_track() -> None:
    """A flat fill and a stroked-only outline both lose one of the two things a gauge arc
    has to show at once: where it ends, and how much of the track it covers."""
    svg = _svg()
    style = svg[svg.index("<style>") : svg.index("</style>")]
    series_rules = [line for line in style.splitlines() if line.startswith(".series")]

    assert series_rules
    for rule in series_rules:
        assert "stroke:" in rule and "fill:" in rule and "fill-opacity:" in rule
        assert "fill: none" not in rule and "stroke: none" not in rule


@pytest.mark.parametrize("preset", ["light", "dark"])
def test_renders_under_a_theme_preset(preset: str) -> None:
    svg = _svg(theme=preset)

    assert "<style>" in svg
    assert len(_paths(svg, "gauge-value")) == 3


def test_series_classes_are_distinct_per_row() -> None:
    """One shared class would give every ring the same palette colour and make the legend
    entries indistinguishable."""
    svg = _svg()
    classes = [
        next(name for name in classes.split() if name.startswith("series"))
        for _, classes in _PATH_RE.findall(svg)
        if "gauge-value" in classes.split()
    ]

    assert len(set(classes)) == len(classes) == 3


def test_the_dial_geometry_is_pinned_to_literal_pixels() -> None:
    """Every other geometry test derives its expectation from ``_SWEEP``/``_START_ANGLE``,
    so widening or narrowing the dial moves the expectation with it and nothing fails --
    240 degrees could silently become 180. One literal anchor turns a constant regression
    into a failing test.

    The two ends of a full arc, on the 800x600 canvas with margins 30/180/30/30: centre
    (325, 300), outer radius 242, ends at -210 and +30 degrees.
    """
    ring = _ring(_paths(_svg({"score": [100.0]}, vmin=0, vmax=100), "gauge-value")[0])
    start = polar_point(_CX, _CY, ring["outer"], ring["start"])
    end = polar_point(_CX, _CY, ring["outer"], ring["end"])

    assert ring["outer"] == 242.0
    assert (round(start[0], 6), round(start[1], 6)) == (115.421852, 421.0)
    assert (round(end[0], 6), round(end[1], 6)) == (534.578148, 421.0)
    # Both ends level with each other and below the centre: the open third faces down.
    assert start[1] == pytest.approx(end[1]) and start[1] > _CY


def test_a_range_whose_span_overflows_is_named_rather_than_deferred() -> None:
    """Both bounds are finite here; only their difference is not. ``LinearScale`` rejects it
    too, but with a message about a domain span that names neither argument."""
    with pytest.raises(ValueError, match=r"too wide to measure.*vmin=-1e\+308.*vmax=1e\+308"):
        _svg({"score": [0.0]}, vmin=-1e308, vmax=1e308)


def test_an_inverted_range_is_called_inverted_even_when_its_span_also_overflows() -> None:
    """``vmin=1e308, vmax=-1e308`` overflows *and* is backwards. Reporting the width first
    would send the caller to fix the wrong thing."""
    with pytest.raises(ValueError, match="non-empty and increasing"):
        _svg({"score": [0.0]}, vmin=1e308, vmax=-1e308)


def test_a_wide_but_representable_range_still_renders() -> None:
    """Otherwise the guard above could be an unconditional refusal of large ranges."""
    assert _value_sweep(_svg({"score": [0.0]}, vmin=-1e307, vmax=1e307)) == pytest.approx(_SWEEP / 2)


@pytest.mark.parametrize(
    ("vmax", "labels"),
    [
        (3e-7, ["0", "5e-08", "1e-07", "1.5e-07", "2e-07", "2.5e-07", "3e-07"]),
        (1e-5, ["0", "2e-06", "4e-06", "6e-06", "8e-06", "1e-05"]),
    ],
)
def test_tick_labels_survive_a_domain_smaller_than_six_decimal_places(vmax: float, labels: list[str]) -> None:
    """The same reason the printed value avoids ``format_coord``, at the other call site --
    and this one was left unpinned. ``format_coord`` rounds to six places, so on a domain
    this small every tick label collapses to "0" and the whole ring stops naming anything.
    Every other tick assertion in this file uses whole numbers, where the two agree."""
    assert _texts(_svg({"score": [vmax]}, vmin=0, vmax=vmax), "tick-label") == labels
