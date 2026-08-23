"""``is_missing`` against every float width numpy has.

The predicate's type test used to be ``isinstance(value, float)``, which is exactly the wrong
width for a package that reads DataFrames by duck-typing: ``numpy.float64`` subclasses ``float``
and ``numpy.float32`` does not, so whether a NaN was seen depended on a column's dtype. The same
nine numbers as ``float32`` rather than ``float64`` produced a fourth hue group labelled ``nan``,
a bar chart that counted a dropped row, and -- in ``radarplot`` -- a *different exception*:
``radar values must be finite, got nan`` where the ``float64`` column said ``the series has no
value for '남'``. Nothing in 4,007 tests compared the two (#257).

So the assertion here is parity, across the whole chart family rather than one chart: rendering
with a ``float`` NaN and rendering with each numpy NaN must produce the same result, where
"result" is the SVG, or the exception, or the warning -- all three, because each of the three is
where a width difference actually surfaced.

Skipped without numpy, which is the ordinary case: it is in the ``numpy-parity`` extra and
nothing in ``src/`` imports it. ``test_data.py`` carries the stdlib half of the same rule
(``Decimal("nan")``), so reverting the predicate to ``float`` is caught with or without numpy.
"""

from __future__ import annotations

import warnings

import pytest

import svgplot as sp
from svgplot.data._missing import is_missing

numpy = pytest.importorskip("numpy", reason="install the numpy-parity extra to check this")

_NAN_WIDTHS = {
    "float16": numpy.float16("nan"),
    "float32": numpy.float32("nan"),
    "float64": numpy.float64("nan"),
    "longdouble": numpy.longdouble("nan"),
}
"""Every float numpy offers. ``float64`` is the one that *did* work -- it subclasses ``float`` --
and it stays in the table so a fix that special-cases the three by name still fails."""

_MISSING_AT = 2
"""Which row of :func:`_frame` is replaced by the missing value."""

_COLUMNS: dict[str, list] = {
    "값": [12.0, 8.0, 20.0, 16.0, 5.0, 24.0, 9.0, 14.0, 6.0],
    "보조": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0],
    "구간": ["가", "가", "가", "나", "나", "나", "다", "다", "다"],
    "축": ["동", "서", "남", "동", "서", "남", "동", "서", "남"],
}
"""Whole numbers, and small ones: every value here is exact in ``float16``, so a column
converted to a narrow dtype formats to the same text and the parity check measures the
missing-value rule rather than rounding."""

_ROWS = 9
_CATEGORY_SIZE = 3
"""Three rows per category in ``구간`` -- ``violinplot`` needs two values left in a category
after one is dropped, and a two-row category would make it raise instead of render."""


def _frame(missing: object, column: str, rows: int = _ROWS) -> dict[str, list]:
    """The fixture with ``missing`` standing in for one value of ``column``."""
    frame = {name: list(values[:rows]) for name, values in _COLUMNS.items()}
    frame[column] = [missing if index == _MISSING_AT else value for index, value in enumerate(frame[column])]
    return frame


_CALLS: dict[str, tuple[dict[str, str], str, int]] = {
    "areaplot": ({"x": "보조", "y": "값"}, "값", _ROWS),
    "barplot": ({"x": "구간", "y": "값"}, "값", _ROWS),
    "boxplot": ({"x": "구간", "y": "값"}, "값", _ROWS),
    "ecdfplot": ({"x": "값"}, "값", _ROWS),
    "gaugeplot": ({"values": "값", "labels": "축"}, "값", _ROWS),
    "heatmap": ({"x": "구간", "y": "축", "values": "값"}, "값", _ROWS),
    "histplot": ({"x": "값"}, "값", _ROWS),
    "kdeplot": ({"x": "값"}, "값", _ROWS),
    "lineplot": ({"x": "보조", "y": "값"}, "값", _ROWS),
    "pieplot": ({"values": "값", "labels": "축"}, "값", _ROWS),
    # Three rows, so ``축`` names each spoke once. On all nine, a dropped row leaves the spoke
    # filled by a later row and the chart renders identically with and without the NaN -- the
    # shape :func:`test_the_fixture_puts_the_missing_value_where_the_chart_can_see_it` rejects.
    # At three it is the chart that refuses a gap, and *which* refusal is what differed by width.
    "radarplot": ({"x": "축", "y": "값"}, "값", _CATEGORY_SIZE),
    "regplot": ({"x": "보조", "y": "값"}, "값", _ROWS),
    "scatterplot": ({"x": "보조", "y": "값"}, "값", _ROWS),
    "sparkline": ({"y": "값"}, "값", _ROWS),
    "treemap": ({"values": "값", "labels": "축"}, "값", _ROWS),
    "violinplot": ({"x": "구간", "y": "값"}, "값", _ROWS),
}
"""How to draw each chart, and which of its columns takes the missing value.

Always a numeric channel: that is the one a narrow dtype reaches, and it is the channel every
chart has. The ``hue`` route -- where the defect was first seen, as a ``nan`` legend entry --
gets its own test below rather than a column here, because only some of the sixteen take one.
"""

_CHARTS = sorted(_CALLS)


def _render(name: str, missing: object) -> tuple[str, tuple[str, ...]]:
    """Draw one chart with ``missing`` in its numeric column; return what came back.

    An exception is a result like any other here, and a legitimate one -- ``radarplot`` refuses a
    gap. What must not depend on the width of the NaN is *which* result: the same SVG, or the
    same exception, or the same warning. Warnings are captured rather than let through because
    ``barplot``'s aggregation warning counts the surviving rows out loud ("kept 3 of 8 rows"),
    which makes it a direct reading of how many values the predicate dropped.
    """
    kwargs, column, rows = _CALLS[name]
    frame = _frame(missing, column, rows)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            result = getattr(sp, name)(frame, **kwargs).to_string()
        except Exception as error:
            result = f"{type(error).__name__}: {error}"
    return result, tuple(f"{w.category.__name__}: {w.message}" for w in caught)


@pytest.mark.parametrize("width", sorted(_NAN_WIDTHS))
@pytest.mark.parametrize("name", _CHARTS)
def test_a_chart_reads_a_numpy_nan_the_same_as_a_python_one(name: str, width: str) -> None:
    """The whole point of the file. Parity, per chart, per float width."""
    assert _render(name, _NAN_WIDTHS[width]) == _render(
        name, float("nan")
    ), f"{name} draws a {width} NaN differently from a python float NaN"


@pytest.mark.parametrize("width", sorted(_NAN_WIDTHS))
@pytest.mark.parametrize("name", _CHARTS)
def test_a_chart_reads_a_whole_numpy_column_the_same_as_a_python_one(name: str, width: str) -> None:
    """The realistic shape of the bug: not a lone numpy scalar, but a whole column of them.

    A DataFrame hands over every value in the column as a numpy scalar, not just the NaN, so the
    non-missing values take the same trip through the predicate -- and a fix that reached only
    the NaN would pass the test above and fail here. The values in :data:`_COLUMNS` are exact in
    ``float16``, so any difference is the missing-value rule and not rounding.
    """
    kwargs, column, rows = _CALLS[name]
    dtype = numpy.dtype(width)

    def as_column(missing: object) -> tuple[str, tuple[str, ...]]:
        frame = _frame(missing, column, rows)
        frame[column] = list(numpy.array(frame[column], dtype=dtype))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                result = getattr(sp, name)(frame, **kwargs).to_string()
            except Exception as error:
                result = f"{type(error).__name__}: {error}"
        return result, tuple(f"{w.category.__name__}: {w.message}" for w in caught)

    assert as_column(float("nan")) == _render(
        name, float("nan")
    ), f"{name} draws a {width} column differently from a python float one"


@pytest.mark.parametrize("name", _CHARTS)
def test_the_fixture_puts_the_missing_value_where_the_chart_can_see_it(name: str) -> None:
    """Non-vacuity, and it is not decoration -- it caught a real hole while this file was written.

    Every assertion above compares two renders that both contain a NaN. If a chart ignored the
    column the NaN sits in, or filled the gap from another row, both sides would agree for the
    wrong reason and the parity check would pass over a chart it never tested. ``radarplot`` on
    the nine-row frame was exactly that: the dropped spoke was refilled by a later row and the
    two renders were byte-identical. So each chart must *notice*: replacing the missing value
    with an ordinary number has to change the result.
    """
    kwargs, column, rows = _CALLS[name]
    del kwargs, rows  # read inside _render; named here so the fixture columns stay legible
    assert _render(name, float("nan")) != _render(
        name, _COLUMNS[column][_MISSING_AT]
    ), f"{name} renders the same with and without the missing value, so nothing above tests it"


def test_the_call_table_holds_every_chart_and_nothing_else() -> None:
    """A seventeenth chart has to be added here, rather than quietly skipping the parity check.

    ``sp.charts.__all__`` is the package's own answer to "which sixteen" -- the same source
    ``test_charts_tooltip_contract`` and ``test_charts_describe`` derive from.
    """
    assert set(_CALLS) == set(sp.charts.__all__), set(_CALLS) ^ set(sp.charts.__all__)


@pytest.mark.parametrize("width", sorted(_NAN_WIDTHS))
def test_a_missing_hue_value_never_becomes_a_group_of_its_own(width: str) -> None:
    """The symptom that opened #257, stated where it was seen.

    A ``float32`` NaN in the hue column survived ``channel_row_indices``, became a dict key, and
    was drawn as a legend entry reading ``nan`` -- a fourth series in a chart with three.
    """
    rows = {"보조": [1.0, 2.0, 3.0, 4.0], "값": [12.0, 8.0, 20.0, 16.0]}
    labels = ["동", "서", _NAN_WIDTHS[width], _NAN_WIDTHS[width]]
    svg = sp.scatterplot({**rows, "구간": labels}, x="보조", y="값", hue="구간").to_string()
    assert "nan" not in svg, f"a {width} NaN reached the rendered chart as a hue group"


@pytest.mark.parametrize("width", sorted(_NAN_WIDTHS))
def test_every_numpy_nan_is_missing(width: str) -> None:
    assert is_missing(_NAN_WIDTHS[width])


@pytest.mark.parametrize("width", sorted(_NAN_WIDTHS))
def test_a_numpy_number_that_is_not_nan_is_not_missing(width: str) -> None:
    """The other half. A predicate returning ``True`` for every numpy scalar would pass every
    check above -- each chart would simply draw nothing, consistently, at every width."""
    assert not is_missing(type(_NAN_WIDTHS[width])(1.5))


def test_a_numpy_integer_is_not_missing() -> None:
    """``numpy.int64`` registers as ``numbers.Number`` too, and has no NaN to be confused with."""
    assert not is_missing(numpy.int64(0))
    assert not is_missing(numpy.uint8(0))


def test_numpy_text_is_not_missing() -> None:
    """``numpy.str_`` subclasses ``str``, not ``numbers.Number``, so it never reaches a
    comparison -- which is what keeps a category column out of the NaN test entirely."""
    assert not is_missing(numpy.str_("남"))
    assert not is_missing(numpy.str_(""))


def test_a_numpy_nat_is_not_missing() -> None:
    """Pinned because it is the one reflexivity-failing value the predicate deliberately does
    *not* claim: ``NaT != NaT`` is true, but it is not a ``Number``, and a missing timestamp
    needs a decision about the time axis rather than this predicate's answer. Stated as a test
    so that if the decision is ever made, the docstring saying otherwise fails with it.
    """
    assert not is_missing(numpy.datetime64("NaT", "s"))
