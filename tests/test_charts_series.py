"""Tests for the series split seven charts share.

It was seven copies of eight lines, and what makes it worth a module is not the eight lines
but the three policies inside them -- ordering, refusal, and how "no hue" is spelled. Each one
is asserted here, because until now every one of them was only ever checked through a chart,
and a chart's assertions are about the chart.
"""

from __future__ import annotations

import pytest

from svgplot.charts._series import series_items, series_rows

_ROWS = {"x": [1, 2, 3, 4], "y": [1.0, 2.0, 3.0, 4.0], "g": ["b", "a", "b", "a"]}


def test_no_hue_is_one_series_keyed_none() -> None:
    """The spelling every caller unpacks. ``None`` rather than a made-up label, because a
    chart uses it to decide whether to draw a legend at all -- an invented name would put one
    entry in the legend of a chart with nothing to distinguish."""
    columns = {"x": [1, 2], "y": [1.0, 2.0]}

    assert series_items(_ROWS, columns, None) == [(None, columns)]


def test_series_come_back_in_order_of_their_label_as_text() -> None:
    """The order is the palette assignment and the legend order, so it is a visible decision
    and not an implementation detail. Reordering here recolours every chart."""
    assert [label for label, _ in series_items(_ROWS, _ROWS, "g")] == ["a", "b"]


def test_labels_that_cannot_be_compared_are_still_ordered() -> None:
    """``sorted`` on the values raises ``TypeError`` for ``[1, "a"]`` -- one column of
    real-world data holding a number and a string is enough. Sorting by ``str`` is total, and
    a lexical order beats refusing to draw data the chart could otherwise render."""
    mixed = {"x": [1, 2, 3], "y": [1.0, 2.0, 3.0], "g": [10, "a", 2]}

    assert [str(label) for label, _ in series_items(mixed, mixed, "g")] == ["10", "2", "a"]


def test_a_hue_column_with_no_usable_rows_names_itself() -> None:
    """Drawing nothing is the alternative, and a blank chart does not say which column
    emptied it. The caller has the column name; the error has to as well."""
    empty = {"x": [1, 2], "y": [1.0, 2.0], "g": [None, None]}

    with pytest.raises(ValueError, match="no rows with a non-missing 'g' value"):
        series_items(empty, empty, "g")


def test_each_series_carries_only_its_own_rows() -> None:
    """The split has to be a split. A helper that handed every series the whole frame would
    satisfy the count and the ordering and draw every line on top of itself."""
    grouped = dict(series_items(_ROWS, _ROWS, "g"))

    assert grouped["a"]["x"] == [2, 4]
    assert grouped["b"]["x"] == [1, 3]


def test_every_column_survives_the_split_not_just_the_plotted_ones() -> None:
    """Charts index columns the helper never hears about -- ``size=``, ``labels=``, the hue
    column itself for its own legend. Narrowing to the plotted ones here would break them
    silently, since the failure is a ``KeyError`` far from this function."""
    wide = {"x": [1, 2], "y": [1.0, 2.0], "size": [3.0, 4.0], "g": ["a", "b"]}
    first = series_items(wide, wide, "g")[0][1]

    assert set(first) == set(wide)


# ---------------------------------------------------------------------------
# series_rows — the same split, carrying the rows it was built from
# ---------------------------------------------------------------------------


def test_series_items_is_a_view_of_series_rows_not_a_second_split() -> None:
    """Both functions answer with the labels and columns an independent split would give.

    Written against a stated expectation rather than against ``series_rows`` itself. The first
    draft compared ``series_items(...)`` with the same comprehension ``series_items`` is
    *defined* as, which is ``f(x) == f(x)``: reversing the series order, reversing every
    column and returning row 99 for every row all left it passing. What is worth pinning is
    not that the projection exists -- the source shows that -- but that the pair really is the
    split seven charts expect, ordered the way the palette is assigned.
    """
    expected = [("a", {"x": [2, 4], "y": [2.0, 4.0], "g": ["a", "a"]}), ("b", {"x": [1, 3], "y": [1.0, 3.0], "g": ["b", "b"]})]

    assert series_items(_ROWS, _ROWS, "g") == expected
    assert [(label, columns) for label, columns, _ in series_rows(_ROWS, _ROWS, "g")] == expected


def test_each_series_knows_which_input_rows_it_holds() -> None:
    labelled = {label: rows for label, _, rows in series_rows(_ROWS, _ROWS, "g")}

    assert labelled == {"a": [1, 3], "b": [0, 2]}


def test_without_hue_the_rows_are_the_whole_input_in_order() -> None:
    """``ingest_longform`` drops nothing, so there is nothing for the indices to skip -- and
    saying that here means the no-hue caller gets a real answer rather than an empty list that
    would silently disable every tooltip on a chart without a ``hue=``."""
    [(label, columns, rows)] = series_rows(_ROWS, _ROWS, None)

    assert (label, rows) == (None, [0, 1, 2, 3])
    assert columns is _ROWS


def test_a_series_holding_no_rows_cannot_appear() -> None:
    """Only rows with a non-missing hue value are grouped, so every series has at least one."""
    holed = {"x": [1, 2, 3], "y": [1.0, 2.0, 3.0], "g": ["a", None, "a"]}

    assert [(label, rows) for label, _, rows in series_rows(holed, holed, "g")] == [("a", [0, 2])]
