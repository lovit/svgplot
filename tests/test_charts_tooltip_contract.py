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

_NOT_A_CHART = {
    "facet",
    "row",
    "column",
    "grid",
    "apply_size",
    "apply_context",
    "add_caption",
    "parametric_theme",
}


def _charts() -> list[str]:
    """Every public chart function, taken from the package rather than from a list here."""
    return sorted(
        name for name in sp.__all__ if name[0].islower() and callable(getattr(sp, name)) and name not in _NOT_A_CHART
    )


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
        pytest.skip(f"{name} has no tooltip= yet")

    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, f"{name}: tooltip must be keyword-only"
    positional = [
        other
        for other, spec in inspect.signature(getattr(sp, name)).parameters.items()
        if spec.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    ]
    assert "tooltip" not in positional, f"{name}: tooltip drifted in front of the * that keeps it keyword-only"
    assert parameter.default is False, f"{name}: tooltip must default to False, got {parameter.default!r}"


def test_tooltip_off_is_byte_for_byte_what_it_was() -> None:
    """The promise to everyone who never asks for this. Checked against a rendering with the
    argument omitted *and* one passing ``False`` explicitly, so the default and the value
    cannot drift apart."""
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
    ``y`` ``0.0``..``999.0``, one hue group named with 100,000 Hangul characters. Output went from 185,050 characters to 100,235,830 -- 542 times -- and
    from 385,070 bytes to 300,437,850, which is 780, because UTF-8 spends three bytes on each
    of those characters. With the label on half the points instead of all of them it is half
    of that: the multiplier is the mark count, not the label.

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
    """The same cap ``_size_clause`` applies to the ``<desc>``, for a sharper reason: this name
    is repeated once *per point*, so an unreadable one would be the largest thing in the file.

    Dropped rather than truncated -- half a column name is a different column name. The value
    stays, because the value is the thing the reader came for.
    """
    long_name = "면" * 5000
    data = {long_name: [1.0, 2.0], "매출": [3.0, 4.0]}
    svg = sp.scatterplot(data, x=long_name, y="매출", tooltip=True).to_string()

    assert "<title>1 · 매출: 3</title>" in svg
    assert long_name not in svg
