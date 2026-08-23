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
import re
from importlib import import_module

import pytest

import svgplot as sp
from svgplot.charts._layout import corner_radius_attr
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
def test_a_legend_swatch_does_not_share_its_marks_rounding(name: str) -> None:
    """Recorded as it is, not as it arguably should be.

    With ``hue=``, ``barplot`` and ``histplot`` draw rounded bars and then a legend swatch --
    another ``<rect>``, in the same series class, naming the same colour -- with square corners.
    A reader gets a rounded bar pointed at by a square key. Nothing in :attr:`Theme.corner_radius`'s
    docstring mentions swatches either way, so this is an inconsistency rather than a decision,
    and it is out of scope for #258, which is about a radius that cannot be written at all.

    It is pinned rather than left unmentioned because the parity work above is exactly what would
    otherwise make it invisible: the three charts agree with *each other* about their marks while
    all three disagree with their own legends. If swatches are later made to round, this test
    fails and its replacement records that decision.
    """
    svg = getattr(sp, name)(_DATA, theme=Theme(corner_radius=4.0), hue="행", **_CALLS[name]).to_string()
    swatches = [rect for rect in re.findall(r"<rect[^>]*>", svg) if 'class="series-' in rect and "legend" not in rect]
    marks = [rect for rect in swatches if 'rx="4"' in rect]
    squares = [rect for rect in swatches if "rx=" not in rect]
    assert marks, f"{name} rounded nothing, so this test is not comparing marks to swatches"
    assert squares, f"{name} now rounds its legend swatch too -- decide and update this test"


def test_the_shared_helper_is_what_the_charts_ask() -> None:
    """The helper's own contract, separate from the charts that call it -- so that a change to
    the rule is a change to one readable expression rather than something inferred from SVG."""
    assert corner_radius_attr(4.0) == "4"
    assert corner_radius_attr(0.5) == "0.5"
    assert corner_radius_attr(0.0) is None
    # Reachable only past the constructor -- ``Theme`` is frozen, but ``object.__setattr__``
    # is not locked away, and this is the half of the fix that holds when it is used.
    assert corner_radius_attr(-5.0) is None


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


def test_a_theme_smuggled_past_the_constructor_still_draws_square_corners() -> None:
    """Both halves are load-bearing, and this is what proves the second one is.

    ``dataclasses.replace`` re-runs ``__post_init__``, so it cannot be used to build the bad
    theme -- which is the validator working. ``object.__setattr__`` bypasses both the frozen
    flag and the validator, and it is the route by which a ``-5.0`` could still reach a
    renderer. With the guard only in ``Theme``, this is the case that emits ``rx="-5"``.
    """
    with pytest.raises(ValueError, match="corner_radius"):
        dataclasses.replace(Theme(), corner_radius=-5.0)

    smuggled = Theme()
    object.__setattr__(smuggled, "corner_radius", -5.0)
    for name in _ROUNDS:
        svg = getattr(sp, name)(_DATA, theme=smuggled, **_CALLS[name]).to_string()
        assert 'rx="' not in svg, f"{name} wrote an rx for a negative radius that skipped the constructor"
