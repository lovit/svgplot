"""``theme.corner_radius``: what ``Theme`` accepts, and what the three rounding charts do with it.

One rule -- "round only for a radius greater than zero" -- was written three times, and two of
the three asked a different question than they meant to. ``barplot`` tested ``> 0``; ``histplot``
and ``boxplot`` tested truthiness. ``-5.0`` is truthy, so both emitted ``rx="-5"``, which is not
a valid SVG attribute value. ``nan`` split the three a third way: truthy, so it reached
``format_coord`` and raised in two charts, while ``> 0`` is false for ``nan`` and ``barplot``
drew square corners without a word. Nothing in ``tests/`` had ever passed a value that was not
``0.0`` or a small positive number, so all three spellings looked equivalent (#258).

The fix has two halves and this file checks both. ``Theme.__post_init__`` refuses the values --
that is where the failure belongs, next to the ``opacity`` checks that exist for the same reason
(a nonsense-but-finite value sails past ``format_coord`` and surfaces at render time far from
the ``Theme`` that caused it). :func:`charts._layout.corner_radius_attr` is the single expression
of the rendering rule, and the parity test below is what stops the three charts drifting again:
it compares them to *each other*, not to a recorded string, so a chart that stops rounding fails
even if its own per-chart test is updated to match.
"""

from __future__ import annotations

import dataclasses
import math
import re
from importlib import import_module

import pytest

import svgplot as sp
from svgplot.charts._layout import corner_radius_attr, format_coord
from svgplot.charts._legend import _SWATCH_HEIGHT, _SWATCH_WIDTH
from svgplot.theme.base import Theme

_ROUNDS = ("barplot", "boxplot", "histplot")
"""The charts whose rectangles take ``rx``, per :attr:`Theme.corner_radius`'s docstring."""

_IGNORES = ("treemap", "heatmap", "violinplot")
"""The three rectangles the same docstring says ignore it -- two by decision (a tile's
neighbours are its own edges, and rounding opens gaps that read as gaps in the data), one by
inconsistency (``violinplot(inner="box")``'s quartile box, which ``violin.py`` never reads the
field for). Pinned so the docstring cannot quietly become false in either direction."""

_DATA = {
    "구간": ["가", "가", "나", "나", "다", "다"],
    "값": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
    "행": ["위", "아래", "위", "아래", "위", "아래"],
}

_CALLS = {
    "barplot": {"x": "구간", "y": "값"},
    "boxplot": {"x": "구간", "y": "값"},
    "histplot": {"x": "값"},
    "treemap": {"labels": "구간", "values": "값"},
    "heatmap": {"x": "구간", "y": "행", "values": "값"},
    "violinplot": {"x": "구간", "y": "값", "inner": "box"},
}


def _radii(name: str, radius: float) -> list[str]:
    """Every distinct ``rx`` value in one chart drawn at ``radius``."""
    svg = getattr(sp, name)(_DATA, theme=Theme(corner_radius=radius), **_CALLS[name]).to_string()
    assert "<rect" in svg, f"{name} drew no rectangle, so it cannot show whether rx is applied"
    return sorted(set(re.findall(r'rx="([^"]*)"', svg)))


@pytest.mark.parametrize("bad", [-5.0, -0.001, float("nan"), float("inf"), float("-inf"), True, "3", None])
def test_theme_refuses_a_corner_radius_that_cannot_become_an_rx(bad: object) -> None:
    """By name, at construction. ``rx`` is a length on a ``<rect>``: negative is invalid SVG,
    and ``inf``/``nan`` cannot be written as an attribute value at all.

    ``True`` is in the list for the reason it is in the ``fill_opacity`` list -- ``bool`` is a
    subclass of ``int``, so a bare numeric check accepts it and ``corner_radius=True`` becomes a
    one-pixel rounding nobody asked for.
    """
    with pytest.raises(ValueError, match="corner_radius"):
        Theme(corner_radius=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("good", [0.0, 0.5, 3.0, 4.0, 1e6])
def test_theme_accepts_any_non_negative_finite_corner_radius(good: float) -> None:
    """The other half of the range, including the two ends that matter: ``0.0`` is the default
    and must stay legal, and there is deliberately no upper bound -- SVG itself clamps a radius
    past half the rectangle's side, so there is no largest sensible value for this to guess at.
    """
    assert Theme(corner_radius=good).corner_radius == good


@pytest.mark.parametrize("radius", [0.0, 0.5, 3.0, 4.0])
def test_the_rounding_charts_all_answer_the_same_way(radius: float) -> None:
    """The assertion the three divergent copies could not fail: compare them to *each other*.

    Not to a recorded ``rx="4"`` -- a per-chart expectation is exactly what let ``boxplot`` and
    ``histplot`` keep a rule ``barplot`` did not share, since each chart's own test was written
    against the chart's own behaviour and all three passed.
    """
    answers = {name: _radii(name, radius) for name in _ROUNDS}
    assert len(set(map(tuple, answers.values()))) == 1, f"the rounding charts disagree at corner_radius={radius}: {answers}"


@pytest.mark.parametrize("name", _ROUNDS)
def test_a_positive_radius_rounds_and_zero_does_not(name: str) -> None:
    """Non-vacuity for the parity test above, which three charts that all ignored the field
    entirely would satisfy. Stated per chart so the failure names which one stopped."""
    assert _radii(name, 4.0) == ["4"], f"{name} did not round at corner_radius=4.0"
    assert _radii(name, 0.0) == [], f"{name} emitted an rx at corner_radius=0.0"


@pytest.mark.parametrize("name", _IGNORES)
def test_the_charts_documented_as_square_stay_square(name: str) -> None:
    assert _radii(name, 4.0) == [], f"{name} rounded, but Theme.corner_radius's docstring says it does not"


_OTHERS = {
    "areaplot": {"x": "값", "y": "값"},
    "ecdfplot": {"x": "값"},
    "gaugeplot": {"values": "값", "labels": "구간"},
    "kdeplot": {"x": "값"},
    "lineplot": {"x": "값", "y": "값"},
    "pieplot": {"values": "값", "labels": "구간"},
    "radarplot": {"x": "구간", "y": "값", "hue": "행"},
    "regplot": {"x": "값", "y": "값"},
    "scatterplot": {"x": "값", "y": "값"},
    "sparkline": {"y": "값"},
}
"""The ten charts the table above says nothing about. Several of them do draw rectangles --
``gaugeplot`` and ``pieplot`` emit seven each -- so the check below has to ask about ``rx``
rather than about rectangles."""


def test_no_chart_outside_the_table_rounds_anything() -> None:
    """The registry check: a seventeenth chart, or a sixteenth that grows a rounded rectangle,
    has to be classified here rather than slipping past both lists.

    Counting ``<rect>`` is what this asked first, on the assumption that a chart outside the
    table draws only the plot background. That is false -- ``gaugeplot`` and ``pieplot`` draw
    seven rectangles each (a background and six legend swatches), and ``radarplot`` three. So
    the question is ``rx``, which is the thing this file is actually about.
    """
    assert set(_OTHERS) | set(_CALLS) == set(sp.charts.__all__), set(_OTHERS) ^ set(_CALLS) ^ set(sp.charts.__all__)
    assert set(_ROUNDS) | set(_IGNORES) == set(_CALLS)

    theme = Theme(corner_radius=4.0)
    rounded = {
        name: re.findall(r'rx="([^"]*)"', getattr(sp, name)(_DATA, theme=theme, **kwargs).to_string())
        for name, kwargs in _OTHERS.items()
    }
    assert not any(rounded.values()), f"a chart outside the table rounds a rectangle: {rounded}"


@pytest.mark.parametrize("name", ["barplot", "histplot"])
def test_a_legend_swatch_is_rounded_when_its_marks_are(name: str) -> None:
    """A key shaped differently from what it names reads as "not that one".

    This test used to assert the opposite, and said so: ``Theme.corner_radius``'s docstring named
    the three rectangles that ignore the field and gave a reason for each, but said nothing about
    swatches either way -- so the square swatch beside a rounded bar was an inconsistency rather
    than a decision, and #258 pinned it as it was with a note that the day it changed, this was
    where the decision would be written. #265 made it, and this is it.

    The assertion is that the swatch is rounded at all, not that it carries the mark's number:
    the radius is scaled to the swatch, for the reason the companion test measures.
    """
    svg = getattr(sp, name)(_DATA, theme=Theme(corner_radius=4.0), hue="행", **_CALLS[name]).to_string()
    in_series = [rect for rect in re.findall(r"<rect[^>]*>", svg) if 'class="series-' in rect]

    assert in_series, f"{name} drew no series rectangles"
    assert all(
        "rx=" in rect for rect in in_series
    ), f"{name} left a series rectangle square while the others round: {[r for r in in_series if 'rx=' not in r]}"


@pytest.mark.parametrize("radius", [1.0, 2.0, 2.5])
def test_a_small_radius_reaches_the_swatch_unchanged(radius: float) -> None:
    """Below the cap the swatch takes the mark's radius exactly -- the scaling is a ceiling, not
    a constant reduction, so an almost-square theme gives an almost-square swatch."""
    svg = sp.barplot(_DATA, theme=Theme(corner_radius=radius), hue="행", **_CALLS["barplot"]).to_string()
    radii = {re.search(r'rx="([^"]*)"', rect)[1] for rect in re.findall(r"<rect[^>]*>", svg) if "rx=" in rect}  # type: ignore[index]

    assert radii == {format_coord(radius)}, f"mark and swatch disagree at radius {radius}: {radii}"


@pytest.mark.parametrize("radius", [8.0, 20.0, 100.0])
def test_a_large_radius_does_not_turn_the_swatch_into_an_ellipse(radius: float) -> None:
    """Why the radius is scaled rather than copied, measured.

    A first version passed the mark's radius through unchanged, arguing that SVG clamps ``rx`` at
    half the shorter side so anything big enough to round the swatch away had already done the
    same to the bars. A review measured that and it is false: the swatch is a fixed 16x10, so its
    clamp sits at a constant 5px, and **every** radius from 5 up turned it into a full ellipse --
    at radius 8 the bar was plainly still a bar at every figure size measured. The mismatch this
    change exists to remove, in a new shape.

    Half the short side is where SVG's clamp lands, so staying strictly under it is what keeps
    the swatch a rectangle at any theme setting. The companion below measures what that does
    *not* buy.
    """
    svg = sp.barplot(_DATA, theme=Theme(corner_radius=radius), hue="행", **_CALLS["barplot"]).to_string()
    swatches = [
        rect
        for rect in re.findall(r"<rect[^>]*>", svg)
        if f'width="{_SWATCH_WIDTH:g}"' in rect and f'height="{_SWATCH_HEIGHT:g}"' in rect
    ]

    assert swatches, "no swatch found -- the fixture stopped drawing a legend"
    for swatch in swatches:
        drawn = float(re.search(r'rx="([\d.]+)"', swatch)[1])  # type: ignore[index]
        assert drawn < _SWATCH_HEIGHT / 2, f"swatch radius {drawn} reaches SVG's clamp at {_SWATCH_HEIGHT / 2}"


def test_the_cap_gives_a_floor_and_not_parity() -> None:
    """What a constant fraction cannot do, pinned so it stays a decision.

    The swatch is a fixed 16x10; a bar is whatever the figure size and the category count leave
    it. Crowd a small figure and the bars come out **thinner than the swatch** -- so the bar hits
    its own clamp and turns into a lozenge while the swatch, capped at a quarter, stays a rounded
    rectangle. That is the reverse of the mismatch #265 set out to remove, and no single fraction
    can close both ends: parity would need the swatch to know the mark's size.

    What is guaranteed is the floor -- the swatch never stops reading as a rounded rectangle.
    This test measures the far end so that "the swatch always matches the mark" is never written
    down as if it were true.
    """
    crowded = {
        "열": [f"c{i}" for i in range(20) for _ in range(5)],
        "행": [f"h{j}" for _ in range(20) for j in range(5)],
        "값": [1 + ((i * 5 + j) % 7) for i in range(20) for j in range(5)],
    }
    svg = sp.barplot(crowded, x="열", y="값", hue="행", theme=Theme(corner_radius=8.0), width=320, height=240).to_string()
    rects = re.findall(r"<rect[^>]*>", svg)
    swatch_box = (f'width="{_SWATCH_WIDTH:g}"', f'height="{_SWATCH_HEIGHT:g}"')
    swatches = [rect for rect in rects if all(part in rect for part in swatch_box)]
    bars = [rect for rect in rects if 'class="series-' in rect and not all(part in rect for part in swatch_box)]

    assert swatches and bars, "the crowded fixture stopped drawing a legend or its bars"
    thinnest = min(
        min(float(re.search(r'width="([\d.]+)"', bar)[1]), float(re.search(r'height="([\d.]+)"', bar)[1]))  # type: ignore[index]
        for bar in bars
    )
    assert thinnest < _SWATCH_HEIGHT, f"the fixture stopped crowding: thinnest bar {thinnest} is not under {_SWATCH_HEIGHT}"

    drawn = float(re.search(r'rx="([\d.]+)"', swatches[0])[1])  # type: ignore[index]
    assert drawn < _SWATCH_HEIGHT / 2, f"swatch radius {drawn} reaches SVG's clamp at {_SWATCH_HEIGHT / 2}"
    assert (
        thinnest / 2 < drawn
    ), f"the fixture no longer shows the reverse case: bar clamps at {thinnest / 2}, swatch draws {drawn}"


@pytest.mark.parametrize("name", ["barplot", "histplot"])
def test_a_legend_swatch_stays_square_when_the_marks_do(name: str) -> None:
    """The other half, and the one that keeps the default untouched: at ``corner_radius=0`` the
    swatch must carry no ``rx`` at all -- not ``rx="0"`` -- so every existing chart is byte for
    byte what it was."""
    svg = getattr(sp, name)(_DATA, theme=Theme(corner_radius=0.0), hue="행", **_CALLS[name]).to_string()
    in_series = [rect for rect in re.findall(r"<rect[^>]*>", svg) if 'class="series-' in rect]

    assert in_series, f"{name} drew no series rectangles"
    assert all("rx=" not in rect for rect in in_series), f"{name} wrote an rx at corner_radius=0"


@pytest.mark.parametrize("bad", [-5.0, float("nan"), float("inf"), float("-inf")], ids=["negative", "nan", "inf", "-inf"])
def test_a_swatch_refuses_what_its_marks_refuse(bad: float) -> None:
    """The scaling must not accept a radius the mark rejects.

    ``inf`` found this: ``min(inf, 2.5)`` is ``2.5``, a perfectly drawable number, so capping
    turned a value ``corner_radius_attr`` refuses into one the swatch took -- a **square bar
    beside a rounded swatch**, this defect wearing its own fix inside out. The cap has to come
    after the finiteness question, not before it.

    Reachable only past ``Theme``'s constructor, which refuses all four -- the same route
    :func:`test_a_theme_smuggled_past_the_constructor_still_draws_square_corners` uses.
    """
    smuggled = Theme()
    object.__setattr__(smuggled, "corner_radius", bad)

    svg = sp.barplot(_DATA, theme=smuggled, hue="행", **_CALLS["barplot"]).to_string()

    assert "rx=" not in svg, f"a swatch rounded for {bad!r} while its marks stayed square"


def test_a_chart_whose_legend_is_drawn_with_lines_is_unaffected() -> None:
    """``boxplot`` takes ``hue=`` and rounds its boxes, and has no swatch to round: its legend
    is ``mark_style="stroke"``, so ``render_legend`` draws a ``<line>`` per entry. Pinned so the
    scope of the change above is a measured fact rather than an assumption about which charts
    have swatches."""
    svg = sp.boxplot(_DATA, theme=Theme(corner_radius=4.0), hue="행", **_CALLS["boxplot"]).to_string()

    assert "<line" in svg
    assert all(
        "-marker" in rect for rect in re.findall(r'<rect[^>]*class="series-[^"]*"[^>]*>', svg)
    ), "boxplot grew a rect swatch -- decide whether it rounds and extend the tests above"


def test_the_shared_helper_is_what_the_charts_ask() -> None:
    """The helper's own contract, separate from the charts that call it -- so that a change to
    the rule is a change to one readable expression rather than something inferred from SVG."""
    assert corner_radius_attr(4.0) == "4"
    assert corner_radius_attr(0.5) == "0.5"
    assert corner_radius_attr(0.0) is None
    # Reachable only past the constructor -- ``Theme`` is frozen, but ``object.__setattr__``
    # is not locked away, and this is the half of the fix that holds when it is used.
    assert corner_radius_attr(-5.0) is None


@pytest.mark.parametrize("radius", [1e-10, 1e-7, 5e-7])
def test_a_radius_too_small_to_survive_formatting_writes_no_rx(radius: float) -> None:
    """ "Greater than zero" and "rounds to something" are different questions at six decimals.

    ``format_coord`` rounds a coordinate to six places, so a small enough positive radius formats
    to ``"0"``. Returning that would ship ``rx="0"``, which draws precisely what no ``rx`` draws
    -- two spellings of square corners, differing in bytes only.

    ``5e-7`` is the largest value here and it is the interesting one: it looks like the tie that
    banker's rounding would send to zero, but it never gets that far -- the nearest double to
    ``0.0000005`` sits just *below* it, so ``round`` is not choosing between two neighbours at
    all. The first value above it already survives, which is what the companion test pins.
    """
    assert corner_radius_attr(radius) is None
    for name in _ROUNDS:
        assert _radii(name, radius) == [], f"{name} wrote an rx for a radius that formats to zero"


@pytest.mark.parametrize("radius", [math.nextafter(5e-7, math.inf), 5.0000001e-7, 6e-7, 9.999999e-7, 1e-6])
def test_a_radius_that_survives_formatting_still_rounds(radius: float) -> None:
    """The boundary from the other side, so the check above cannot be satisfied by a helper that
    simply stopped rounding small values -- or by one that stopped rounding at all.

    The first version of this test used ``1e-6`` alone and called it "the smallest radius that
    survives the rounding". A review measured that and it is false: everything from just above
    ``5e-7`` already survives, and ``1e-6`` is merely the smallest **output** six-decimal
    rounding can produce -- a grid point, not a threshold. The two are a thousandfold apart, and
    a single sample at ``1e-6`` could not tell them apart. Hence the samples across the gap -- and
    ``nextafter(5e-7, inf)`` first, which is the threshold itself rather than a value near it:
    it is one ULP above the largest radius that formats to zero, so nothing can sit between the
    two and the boundary is pinned exactly rather than bracketed.
    """
    assert corner_radius_attr(radius) == "0.000001"
    for name in _ROUNDS:
        assert _radii(name, radius) == ["0.000001"], f"{name} dropped a radius that does format"


@pytest.mark.parametrize(("name", "module"), [("barplot", "bar"), ("boxplot", "box"), ("histplot", "histogram")])
def test_each_rounding_chart_asks_the_shared_helper(name: str, module: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ "The decision lives in one place" as something a test can fail, rather than as a claim
    about how the code is spelled.

    Every other check in this file compares *outcomes*, and outcomes cannot see this: reverting
    ``bar.py`` to its own ``format_coord(...) if ... > 0 else None`` leaves all twenty-eight of
    them green, because that expression is equivalent to the helper **today**. It is the next
    change to the rule that splits them, which is precisely the failure #258 is about -- three
    copies that agreed until one of them didn't.

    So: replace the helper in the chart's own namespace and require the chart to follow. A chart
    that computes its own answer keeps emitting ``rx="4"`` (or none) and fails here. The stub
    ignores its argument, so a chart that still applies its own ``> 0`` test in front of the
    call fails too.
    """
    chart_module = import_module(f"svgplot.charts.{module}")
    assert hasattr(chart_module, "corner_radius_attr"), f"{module}.py does not import the shared helper at all"
    monkeypatch.setattr(chart_module, "corner_radius_attr", lambda radius: "9")

    for radius in (0.0, 4.0):
        svg = getattr(sp, name)(_DATA, theme=Theme(corner_radius=radius), **_CALLS[name]).to_string()
        assert 'rx="9"' in svg, f"{name} did not take the helper's answer at corner_radius={radius}"


@pytest.mark.parametrize("radius", [-5.0, float("nan"), float("inf"), float("-inf")])
def test_a_theme_smuggled_past_the_constructor_still_draws_square_corners(radius: float) -> None:
    """Both halves are load-bearing, and this is what proves the second one is.

    ``dataclasses.replace`` re-runs ``__post_init__``, so it cannot be used to build the bad
    theme -- which is the validator working. ``object.__setattr__`` bypasses both the frozen flag
    and the validator, and it is the route by which a ``-5.0`` could still reach a renderer. With
    the guard only in ``Theme``, this is the case that emits ``rx="-5"``.

    ``nan`` and ``inf`` are here because a review found that only ``-5.0`` was, and the other
    three did not behave like it: an ordering comparison neither accepts nor refuses ``nan``, so
    ``inf`` reached ``format_coord`` and raised, and a later rewrite sent ``nan`` there too. The
    helper now asks ``isfinite`` and every one of the four draws square corners, which is what
    its docstring claims and what this parametrization is here to keep true.
    """
    with pytest.raises(ValueError, match="corner_radius"):
        dataclasses.replace(Theme(), corner_radius=radius)

    smuggled = Theme()
    object.__setattr__(smuggled, "corner_radius", radius)
    for name in _ROUNDS:
        svg = getattr(sp, name)(_DATA, theme=smuggled, **_CALLS[name]).to_string()
        assert 'rx="' not in svg, f"{name} wrote an rx for {radius!r}, which skipped the constructor"
