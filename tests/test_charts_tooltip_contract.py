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
