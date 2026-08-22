"""What ``tooltip=`` has to mean, in every chart that grows one.

#191 built the emitter and named three guards it could not carry, because no chart took a
``tooltip=`` yet and all three would have held over an empty set. This is the file they land
in, and the parametrization below is what makes them non-vacuous: it is built from the
package's own public surface, so each chart that adds the parameter is checked from its first
commit and nobody has to remember to add it here.

The ``skip`` in :func:`test_a_chart_that_takes_tooltip_takes_it_the_agreed_way` is deliberate
and is guarded: :func:`test_at_least_one_chart_takes_tooltip` fails the day the skip becomes
universal, which is the state that would make this whole file a decoration.
"""

from __future__ import annotations

import inspect
import re

import pytest

import svgplot as sp
from _svg_probe import every_tag


def _charts() -> list[str]:
    """Every public chart function.

    ``svgplot.charts.__all__`` rather than ``svgplot.__all__`` minus a list of the things that
    are not charts: that list is the package's own answer to "which sixteen", and two other
    registries already derive themselves from it (``test_charts_describe``,
    ``test_markdown_embedding``). Filtering the top level instead meant a chart callable on the
    package but missing from ``svgplot.__all__`` was invisible here -- and the coverage test
    below claimed to catch exactly that.
    """
    return sorted(sp.charts.__all__)


def _with_tooltip() -> list[str]:
    return [name for name in _charts() if "tooltip" in inspect.signature(getattr(sp, name)).parameters]


_POINTS = {
    "면적": [30.0, 45.0, 60.0, 85.0],
    "매출": [8.0, 14.0, 17.0, 26.0],
    "직원수": [2.0, 3.0, 4.0, 6.0],
    "지역": ["수도권", "수도권", "지방", "지방"],
}


def test_at_least_one_chart_takes_tooltip() -> None:
    """The guard on the guard. Every check below skips a chart with no ``tooltip=``, so with
    none at all the file would pass while asserting nothing -- the shape of the ``<img src>``
    check that survived the gallery losing every ``<img>`` (#185)."""
    assert _with_tooltip(), "no chart takes tooltip= yet, so nothing below is being checked"


@pytest.mark.parametrize("name", _charts())
def test_a_chart_that_takes_tooltip_takes_it_the_agreed_way(name: str) -> None:
    """One spelling across every chart: keyword-only, defaulting to ``False``.

    ``_tooltip.py`` states the convention in prose, and prose is what the next nine charts
    will each be free to ignore. Keyword-only so ``tooltip`` can never be filled by a
    positional argument meant for something else; ``False`` because a ``<title>`` per mark is
    an element per mark, and flipping the default would change every existing caller's bytes.
    """
    parameter = inspect.signature(getattr(sp, name)).parameters.get("tooltip")
    if parameter is None:
        # "does not take one", not "does not take one yet": the six are a decision, and each
        # says so in its own docstring -- see ``test_the_marker_sentence_appears_exactly_where_it_belongs``.
        pytest.skip(f"{name} takes no tooltip=, by design")

    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, f"{name}: tooltip must be keyword-only"
    positional = [
        other
        for other, spec in inspect.signature(getattr(sp, name)).parameters.items()
        if spec.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    ]
    assert "tooltip" not in positional, f"{name}: tooltip drifted in front of the * that keeps it keyword-only"
    assert parameter.default is False, f"{name}: tooltip must default to False, got {parameter.default!r}"


def test_the_default_draws_no_tooltip_and_saying_so_changes_nothing() -> None:
    """The promise to everyone who never asks for this, as far as a test inside the branch can
    state it: the argument omitted and ``False`` passed explicitly are the same call, and
    neither titles a mark.

    Renamed from ``..._is_byte_for_byte_what_it_was``, which is not what it does -- both sides
    are this branch's code, so any change that hits every mark unconditionally passes. The bytes
    from *before* ``tooltip=`` existed are held by ``docs/gallery/*.html``, which
    ``test_gallery.py::test_the_committed_gallery_is_what_a_fresh_build_produces`` rebuilds and
    compares; adding an unconditional attribute to every bar rect leaves all 42 tests in
    ``test_charts_bar.py`` green and turns that one red, and only that one.
    """
    omitted = sp.scatterplot(_POINTS, x="면적", y="매출", hue="지역", size="직원수").to_string()
    explicit = sp.scatterplot(_POINTS, x="면적", y="매출", hue="지역", size="직원수", tooltip=False).to_string()

    assert omitted == explicit
    assert "<title>" not in omitted.replace("<title>Chart</title>", ""), "a mark carries a tooltip with it off"


def test_tooltip_on_gives_every_mark_exactly_one() -> None:
    """Every mark, and one each. "Most of them" is the failure that looks fine in a browser --
    the reader finds a point that says nothing and cannot tell it from a point they missed."""
    svg = sp.scatterplot(_POINTS, x="면적", y="매출", hue="지역", size="직원수", tooltip=True).to_string()
    points = [circle for circle in every_tag(svg, "circle") if "scatter-point" in circle.get("class", "").split()]

    assert len(points) == len(_POINTS["면적"]), "the fixture stopped drawing one point per row"
    assert svg.count("<title>") == len(points) + 1, "one per point, plus the chart's own"


def test_a_tooltip_names_the_columns_its_numbers_came_from() -> None:
    """A tooltip reading ``45 · 14 · 3`` is three numbers with no referent. The point is that
    the reader can tell which is which without going back to the axis."""
    svg = sp.scatterplot(_POINTS, x="면적", y="매출", hue="지역", size="직원수", tooltip=True).to_string()

    assert "<title>면적: 30 · 매출: 8 · 직원수: 2 · 지역: 수도권</title>" in svg


def test_a_tooltip_leaves_out_the_channels_the_chart_was_not_given() -> None:
    """No ``size=``, no size clause -- rather than a clause naming a column that is not there
    or a bare value nobody asked for."""
    svg = sp.scatterplot(_POINTS, x="면적", y="매출", tooltip=True).to_string()

    assert "<title>면적: 30 · 매출: 8</title>" in svg


def test_a_group_label_too_long_to_read_is_dropped_rather_than_repeated() -> None:
    """The column name was capped and the *label* was not, which is the same string arriving by
    a different door -- and the worse door, because a legend says a label once while a tooltip
    says it once per mark.

    Measured before the cap, on a fixture larger than this test needs: 1,000 points, ``x`` and
    ``y`` ``0.0``..``999.0``, one hue group named with 100,000 Hangul characters. Output went
    from 185,050 characters with no tooltips to 100,235,830 with them -- 542 times -- and from
    385,070 bytes to 300,437,850, which is 780, because UTF-8 spends three bytes on each of
    those characters. With the label on half the points instead of all of them it is half of
    that: the multiplier is the mark count, not the label.

    The clause is left out rather than truncated, and the point still says its x and y.
    """
    long_label = "가" * 5000
    data = {"a": [1.0, 2.0], "b": [3.0, 4.0], "g": [long_label, "짧음"]}
    svg = sp.scatterplot(data, x="a", y="b", hue="g", tooltip=True).to_string()

    assert "<title>a: 1 · b: 3</title>" in svg, "the long label's point lost its other clauses too"
    assert "<title>a: 2 · b: 4 · g: 짧음</title>" in svg, "the short label's point lost its clause"


def test_a_tooltip_never_rewrites_the_number_it_names() -> None:
    """The bound must not cost precision, and the first version of it did.

    Capping the *length* and falling back to ``%g`` is six significant figures: measured over
    10,000 uniform samples, **91%** of ordinary values came out rewritten --
    ``13.436424411240122`` became ``13.4364``. Nothing caught it, because every fixture in this
    file used integral floats, where the two spellings agree. This one uses values where they
    do not.

    Round-tripped rather than compared to an expected string: the claim is "this is the same
    number", and only parsing it back says that.
    """
    values = [13.436424411240122, 0.3333333333333333, 123.45678901234567, 0.30000000000000004, 1e-320, 1e308]
    data = {"a": values, "b": [float(index) for index in range(len(values))]}
    svg = sp.scatterplot(data, x="a", y="b", tooltip=True).to_string()
    spoken = [title.split(" · ")[0].removeprefix("a: ") for title in re.findall(r"<title>([^<]*)</title>", svg)[:-1]]

    assert len(spoken) == len(values), "the fixture stopped drawing one point per value"
    assert [float(text) for text in spoken] == values


def test_a_tooltip_number_is_bounded_because_it_is_an_accessible_name() -> None:
    """``1e308`` written as a decimal literal is 309 digits, and a mark's ``<title>`` is its
    accessible name -- so those digits are read out one at a time, once per mark.

    There is no threshold: the rule picks the shorter of two exact spellings, and Python's
    ``repr`` only wins when the decimal literal is expanding scientific notation back into
    digits. An earlier version *did* have a threshold, borrowed from the ``<desc>``, and it is
    what made :func:`test_a_tooltip_never_rewrites_the_number_it_names` necessary.
    """
    svg = sp.scatterplot({"a": [1e308, 1.0], "b": [1.0, 2.0]}, x="a", y="b", tooltip=True).to_string()

    assert "<title>a: 1e+308 · b: 1</title>" in svg
    assert "<title>a: 1 · b: 2</title>" in svg, "an ordinary number stopped reading like the axis"
    assert len(max(re.findall(r"<title>([^<]*)</title>", svg), key=len)) < 40, "something is still unbounded"


def test_a_numeric_group_label_is_spelled_like_the_other_numbers() -> None:
    """One tooltip saying ``a: 1 · g: 1.0`` spells the same kind of value two ways in the same
    breath. The label goes through the same formatter the channels do."""
    data = {"a": [1.0, 2.0], "b": [3.0, 4.0], "g": [1.0, 2.0]}
    svg = sp.scatterplot(data, x="a", y="b", hue="g", tooltip=True).to_string()

    assert "<title>a: 1 · b: 3 · g: 1</title>" in svg


def test_a_column_name_that_draws_nothing_is_dropped_like_one_too_long() -> None:
    """A name of one tab is short enough to fit and reads as ``"\t: 45"`` -- a colon with
    nothing in front of it. Same treatment as a name too long to read: drop the name, keep the
    value."""
    data = {"\t": [1.0, 2.0], "b": [3.0, 4.0]}
    svg = sp.scatterplot(data, x="\t", y="b", tooltip=True).to_string()

    assert "<title>1 · b: 3</title>" in svg


def test_a_column_name_too_long_to_read_is_dropped_rather_than_repeated() -> None:
    """The same *idea* as the cap ``scatter._size_clause`` applies to the ``<desc>``, for a
    sharper reason: this name is repeated once *per point*, so an unreadable one would be the
    largest thing in the file. The number is not the same -- :data:`_tooltip.MAX_TOOLTIP_CHARS`
    is 120 where ``_describe``'s is 60, because that one is a share of a six-name sentence and
    this one is a string announced by itself.

    Dropped rather than truncated -- half a column name is a different column name. The value
    stays, because the value is the thing the reader came for.

    ``long_name not in svg`` is available here and not in the ``barplot`` equivalent: a column
    name appears nowhere else in the file, while a *category* is also drawn on the axis, whose
    tick keeps its own uncapped ``<title>``.
    """
    long_name = "면" * 5000
    data = {long_name: [1.0, 2.0], "매출": [3.0, 4.0]}
    svg = sp.scatterplot(data, x=long_name, y="매출", tooltip=True).to_string()

    assert "<title>1 · 매출: 3</title>" in svg
    assert long_name not in svg


_DECLINES_TOOLTIP = "There is no ``tooltip=``"
"""The sentence each of the six opens its explanation with.

One fixed phrase rather than a keyword, so that removing the position removes the match. It is
also what makes the six read alike: a reader who has met one of these paragraphs recognises the
next at a glance.
"""

_WITHOUT_TOOLTIP = ("areaplot", "ecdfplot", "kdeplot", "lineplot", "radarplot", "sparkline")
"""The six charts that take no ``tooltip=``, and are expected not to.

A list, so the split is a decision rather than an accident. Ten charts have the argument; these
six do not, and until now the source said nothing about why -- the word "tooltip" appeared zero
times in all six modules, so a reader could not tell a design decision from an oversight. The
reason lives in their docstrings now, and this is what keeps it there.
"""


@pytest.mark.parametrize("name", sorted(_charts()))
def test_the_marker_sentence_appears_exactly_where_it_belongs(name: str) -> None:
    """Not having the argument is a position; an unexplained absence is not.

    The gallery had the reasoning all along -- one ``<path>`` per series means the only thing to
    say is the series name -- but a reader working from ``help()`` never sees the gallery.

    **A biconditional over all sixteen, not an implication over six.** The first version
    parametrized only :data:`_WITHOUT_TOOLTIP` and asserted presence, which left the other half
    unwatched: pasting the marker into ``barplot`` -- a chart that *takes* ``tooltip=`` -- ran
    the whole suite green. ``test_theme_fields`` is cited as the precedent for the fixed-phrase
    device, and that file gets this right (``reaches_the_output != denies_it`` over every
    field); this had copied the phrase and dropped the shape.

    Matched on :data:`_DECLINES_TOOLTIP` rather than on the word "tooltip". The word is too
    weak: these paragraphs use it more than once, so deleting the sentence that states the
    position leaves the word behind in the explanation and the check passes.
    """
    import svgplot as sp

    prose = (getattr(sp, name).__doc__ or "").split("Raises:")[0]
    takes_one = "tooltip" in inspect.signature(getattr(sp, name)).parameters

    assert (
        _DECLINES_TOOLTIP in prose
    ) is not takes_one, f"{name} takes tooltip={takes_one} but its docstring says the opposite"


def test_the_two_lists_together_are_every_chart() -> None:
    """Every chart is on exactly one side of the split, and the split covers all sixteen.

    The check above is per-chart, so it says nothing about a chart that never reaches it -- one
    dropped from ``svgplot.charts.__all__``, or a seventeenth added there and to neither list
    here. This is the coverage half. (Two earlier versions of this docstring overclaimed: one
    said this was what caught a new chart with no ``tooltip=`` and no explanation -- the
    biconditional above catches that directly -- and one said it caught a chart "that exists but
    is not exported", which it could not while both sides derived from ``svgplot.__all__``.)
    """
    import svgplot as sp

    with_tooltip = {name for name in _charts() if "tooltip" in inspect.signature(getattr(sp, name)).parameters}

    assert with_tooltip | set(_WITHOUT_TOOLTIP) == set(_charts())
    assert not with_tooltip & set(_WITHOUT_TOOLTIP)


@pytest.mark.parametrize("name", _WITHOUT_TOOLTIP)
def test_a_chart_that_declines_a_tooltip_really_draws_one_mark_per_series(name: str) -> None:
    """The proposition all six paragraphs rest on, measured.

    Every one of them says a series is drawn as **one** mark, and therefore that a ``<title>``
    on it could only repeat the series name. Nothing in the tree checked that. The phrase guard
    above matches a sentence; ``test_theme_fields``, which those docstrings cite as the
    precedent, matches a sentence *against a render-and-compare measurement* -- so its phrase
    cannot outlive its proposition and this one could. This is the missing half.

    Counted in the plot body, excluding the legend: a swatch carries the same ``series-N`` class
    as the mark it stands for, so selecting on the class alone finds one extra element per
    series and would make every chart look like it draws two.

    The cut is at the **first swatch**, not at the first ``legend-text``. Splitting on the label
    was tried and let exactly one swatch through -- the legend emits swatch then label, so
    series 1's swatch precedes the first label and series 1 alone appeared to draw twice. That
    reads as a real defect in one chart rather than a mistake in the counting, which is the
    worst way for a measurement to be wrong.

    If a chart ever grows a second mark per series -- point markers on a line, say -- this fails,
    and it should: at that point the paragraph's reason is gone and the chart has become a
    candidate for ``tooltip=``.
    """

    chart = _WITHOUT_TOOLTIP_FIXTURES[name]()
    drawn = re.sub(r"<style>.*?</style>", "", chart.to_string(), flags=re.S)
    legend = re.search(r'<(?:line|rect)[^>]*class="series-\d+"[^>]*/>\s*<text[^>]*legend-text', drawn)
    body = drawn[: legend.start()] if legend else drawn
    per_series: dict[str, int] = {}
    for series in re.findall(r'<(?:path|polyline|line|rect|circle|ellipse)[^>]*class="(series-\d+)[^"]*"', body):
        per_series[series] = per_series.get(series, 0) + 1

    assert per_series, f"{name}: no series marks found — the pattern is not matching"
    assert set(per_series.values()) == {1}, f"{name} draws {per_series}, not one mark per series"


_SPREAD = {
    "v": [float(index % 9 + 1) for index in range(40)],
    "x": [float(index) for index in range(40)],
    "g": ["a", "b"] * 20,
}
_SPOKES = {"cat": ["a", "b", "c"] * 2, "v": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0], "g": ["x"] * 3 + ["y"] * 3}

_WITHOUT_TOOLTIP_FIXTURES = {
    "areaplot": lambda: __import__("svgplot").areaplot(_SPREAD, x="x", y="v", hue="g"),
    "ecdfplot": lambda: __import__("svgplot").ecdfplot(_SPREAD, x="v", hue="g"),
    "kdeplot": lambda: __import__("svgplot").kdeplot(_SPREAD, x="v", hue="g"),
    "lineplot": lambda: __import__("svgplot").lineplot(_SPREAD, x="x", y="v", hue="g"),
    "radarplot": lambda: __import__("svgplot").radarplot(_SPOKES, x="cat", y="v", hue="g"),
    "sparkline": lambda: __import__("svgplot").sparkline(_SPREAD, y="v"),
}
"""One call per chart, with ``hue=`` wherever the chart takes it, so more than one series is
drawn and "one *per series*" is a real claim rather than a count of one."""
