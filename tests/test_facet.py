from __future__ import annotations

import re

import pytest

from svgplot.chart.composition import Composition
from svgplot.charts.bar import barplot
from svgplot.charts.line import lineplot
from svgplot.layout.facet import facet

# Two col groups x two row groups, with the (bot, R) combination deliberately absent
# so the blank-cell path is exercised by the shared fixture.
GRID_DATA = {
    "x": [1, 2, 1, 2, 1, 2],
    "y": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
    "c": ["L", "L", "R", "R", "R", "R"],
    "r": ["top", "top", "top", "top", "bot", "bot"],
}
"""Three of four (row, col) combinations, with the hole at ``(bot, L)`` — the
*leading* column of its row, deliberately.

A hole in the trailing column is useless for pinning blank-cell behavior: drop
the blank and the resulting ragged row lays out pixel-identically to the correct
one, so the test passes either way. Only a leading-column hole shifts its row's
surviving panel left when the blank is dropped, which is what makes this fixture
actually detect the regression (found in review of PR #47).
"""
COL_DATA = {
    "x": [1, 2, 3, 1, 2, 3],
    "y": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
    "c": ["a", "a", "a", "b", "b", "b"],
}
CAT_DATA = {
    "cat": ["p", "q", "p", "q"],
    "y": [1.0, 2.0, 3.0, 4.0],
    "c": ["a", "a", "b", "b"],
}


def panels(svg: str) -> list[tuple[float, float]]:
    """(x, y) of every placed child panel, in document order."""
    return [(float(x), float(y)) for x, y in re.findall(r'<svg x="([\d.-]+)" y="([\d.-]+)"', svg)]


def titles(svg: str) -> list[str]:
    return re.findall(r'class="composition-title"[^>]*>([^<]*)<', svg)


# ---------------------------------------------------------------------------
# col= / row= / both — the three arrangement modes
# ---------------------------------------------------------------------------


def test_facet_col_only_lays_panels_out_horizontally() -> None:
    svg = facet(lineplot, COL_DATA, col="c", x="x", y="y").to_string()
    placed = panels(svg)
    assert len(placed) == 2
    # Same row (equal y), advancing x — a horizontal strip, not a column.
    assert placed[0][1] == placed[1][1]
    assert placed[0][0] < placed[1][0]


def test_facet_row_only_lays_panels_out_vertically() -> None:
    svg = facet(lineplot, COL_DATA, row="c", x="x", y="y").to_string()
    placed = panels(svg)
    assert len(placed) == 2
    assert placed[0][0] == placed[1][0]
    assert placed[0][1] < placed[1][1]


def test_facet_col_and_row_together_form_a_2d_grid() -> None:
    """Rows come from ``row=``'s values and columns from ``col=``'s, so the three
    present combinations occupy two distinct x positions and two distinct y ones.
    """
    svg = facet(lineplot, GRID_DATA, col="c", row="r", x="x", y="y").to_string()
    placed = panels(svg)
    assert len(placed) == 3  # (bot, L) is absent from the data
    assert len({x for x, _ in placed}) == 2
    assert len({y for _, y in placed}) == 2


def test_facet_leaves_a_missing_combination_blank_without_shifting_neighbours() -> None:
    """The absent (bot, L) panel must leave a hole. If the blank were dropped
    instead, (bot, R) would slide left into the vacated first column and the two
    rows would no longer share a column lattice. The hole sits in the *leading*
    column on purpose — see GRID_DATA's docstring for why a trailing-column hole
    cannot detect this.
    """
    svg = facet(lineplot, GRID_DATA, col="c", row="r", x="x", y="y").to_string()
    placed = panels(svg)
    by_row: dict[float, list[float]] = {}
    for x, y in placed:
        by_row.setdefault(y, []).append(x)
    rows = [sorted(xs) for _, xs in sorted(by_row.items())]
    assert [len(xs) for xs in rows] == [1, 2]  # bot has one panel, top has two
    # The single "bot" panel stays in the *second* column, aligned with "top"'s
    # second — not slid left into the blank first column.
    assert rows[0][0] == rows[1][1]
    assert rows[0][0] != rows[1][0]


# ---------------------------------------------------------------------------
# titles, ordering
# ---------------------------------------------------------------------------


def test_facet_titles_name_the_facet_column_and_value() -> None:
    assert titles(facet(lineplot, COL_DATA, col="c", x="x", y="y").to_string()) == ["c = a", "c = b"]


def test_facet_2d_titles_name_both_facet_values() -> None:
    rendered = titles(facet(lineplot, GRID_DATA, col="c", row="r", x="x", y="y").to_string())
    assert rendered == ["r = bot, c = R", "r = top, c = L", "r = top, c = R"]


def test_facet_orders_panels_deterministically_regardless_of_row_order() -> None:
    """Group order must come from the sorted facet values, not from whichever row
    happened to appear first in the input.
    """
    reversed_rows = {key: list(reversed(values)) for key, values in COL_DATA.items()}
    assert titles(facet(lineplot, reversed_rows, col="c", x="x", y="y").to_string()) == ["c = a", "c = b"]


# ---------------------------------------------------------------------------
# arbitrary chart functions
# ---------------------------------------------------------------------------


def test_facet_works_with_a_different_chart_function_and_its_own_keywords() -> None:
    """``barplot`` takes a categorical x plus keywords ``lineplot`` doesn't have
    (``orient``), so this pins that **kwargs pass-through isn't shaped around any
    one chart type's signature.
    """
    composition = facet(barplot, CAT_DATA, col="c", x="cat", y="y", orient="h")
    assert isinstance(composition, Composition)
    assert len(panels(composition.to_string())) == 2


def test_facet_returns_a_composition_that_serializes_like_a_chart() -> None:
    svg = facet(lineplot, COL_DATA, col="c", x="x", y="y").to_string()
    assert svg.startswith("<?xml")
    assert svg.rstrip().endswith("</svg>")


# ---------------------------------------------------------------------------
# edge cases and validation
# ---------------------------------------------------------------------------


def test_facet_single_group_still_produces_one_panel() -> None:
    single = {"x": [1, 2, 3], "y": [1.0, 2.0, 3.0], "c": ["only", "only", "only"]}
    svg = facet(lineplot, single, col="c", x="x", y="y").to_string()
    assert len(panels(svg)) == 1
    assert titles(svg) == ["c = only"]


def test_facet_requires_col_or_row() -> None:
    with pytest.raises(ValueError, match="col= or row="):
        facet(lineplot, COL_DATA, x="x", y="y")


def test_facet_rejects_unknown_facet_column() -> None:
    with pytest.raises(KeyError, match="nope"):
        facet(lineplot, COL_DATA, col="nope", x="x", y="y")


def test_facet_propagates_the_plot_function_error_for_an_unusable_group() -> None:
    """A group whose rows the chart function rejects surfaces that function's own
    error rather than silently losing a panel.
    """
    with pytest.raises(KeyError, match="missing"):
        facet(lineplot, COL_DATA, col="c", x="missing", y="y")
