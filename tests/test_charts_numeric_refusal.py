"""A non-numeric value in a numeric column is refused **by name**, in every chart.

``scales.py`` states the package's one stance on bad input -- it "refuses by name rather than
masking or clipping" -- and nine charts broke it in the least helpful way available. A bare
``float()`` raises ``ValueError: could not convert string to float: 'a'``, which says what the
value was and nothing about where it came from; a caller with a forty-column frame has to find
the column themselves, and the same sentence came out of nine different charts (#256).

The split was inside single functions, not just across them: ``lineplot`` guarded its ``x``
(``column 'x' holds str, which has no position on an x axis``) and let ``y`` fall through to
``float()``, so the same chart answered the same mistake two ways depending on which channel
held it.

This file is the family-crossing assertion. Every chart, every numeric channel it takes: the
message must name the column. It is built from ``sp.charts.__all__`` so a seventeenth chart is
covered from its first commit -- the same source ``test_charts_tooltip_contract`` and
``test_data_missing_numpy_parity`` derive their registries from.
"""

from __future__ import annotations

import pytest

import svgplot as sp
from svgplot.data._missing import numeric_or_none, require_number

_BAD = "정수아님"
"""The offending value. Non-ASCII on purpose: the message interpolates a *type name*, never the
value, so a fixture whose value could be confused with a column name would let a message that
echoes the value pass for one that names the column."""


_CASES: dict[str, list[tuple[str, dict, dict]]] = {
    # chart -> [(which channel is spoiled, data, kwargs)]
    "areaplot": [
        ("x", {"x": [1.0, 2.0, _BAD], "y": [1.0, 2.0, 3.0]}, {"x": "x", "y": "y"}),
        ("y", {"x": [1.0, 2.0, 3.0], "y": [1.0, 2.0, _BAD]}, {"x": "x", "y": "y"}),
    ],
    "barplot": [("y", {"x": ["가", "나", "다"], "y": [1.0, 2.0, _BAD]}, {"x": "x", "y": "y"})],
    "boxplot": [("y", {"x": ["가", "가", "나", "나"], "y": [1.0, 2.0, 3.0, _BAD]}, {"x": "x", "y": "y"})],
    "ecdfplot": [("x", {"x": [1.0, 2.0, _BAD]}, {"x": "x"})],
    "gaugeplot": [("values", {"l": ["가", "나"], "v": [1.0, _BAD]}, {"labels": "l", "values": "v"})],
    "heatmap": [("values", {"x": ["가", "나"], "y": ["아", "자"], "v": [1.0, _BAD]}, {"x": "x", "y": "y", "values": "v"})],
    "histplot": [("x", {"x": [1.0, 2.0, _BAD]}, {"x": "x"})],
    "kdeplot": [("x", {"x": [1.0, 2.0, _BAD]}, {"x": "x"})],
    "lineplot": [
        ("x", {"x": [1.0, 2.0, _BAD], "y": [1.0, 2.0, 3.0]}, {"x": "x", "y": "y"}),
        ("y", {"x": [1.0, 2.0, 3.0], "y": [1.0, 2.0, _BAD]}, {"x": "x", "y": "y"}),
    ],
    "pieplot": [("values", {"l": ["가", "나", "다"], "v": [1.0, 2.0, _BAD]}, {"labels": "l", "values": "v"})],
    "radarplot": [("y", {"x": ["가", "나", "다"], "y": [1.0, 2.0, _BAD]}, {"x": "x", "y": "y"})],
    "regplot": [
        ("x", {"x": [1.0, 2.0, _BAD], "y": [1.0, 2.0, 3.0]}, {"x": "x", "y": "y"}),
        ("y", {"x": [1.0, 2.0, 3.0], "y": [1.0, 2.0, _BAD]}, {"x": "x", "y": "y"}),
    ],
    "scatterplot": [
        ("x", {"x": [1.0, 2.0, _BAD], "y": [1.0, 2.0, 3.0]}, {"x": "x", "y": "y"}),
        ("y", {"x": [1.0, 2.0, 3.0], "y": [1.0, 2.0, _BAD]}, {"x": "x", "y": "y"}),
        ("size", {"x": [1.0, 2.0, 3.0], "y": [1.0, 2.0, 3.0], "s": [1.0, 2.0, _BAD]}, {"x": "x", "y": "y", "size": "s"}),
    ],
    "sparkline": [("y", {"v": [1.0, 2.0, _BAD]}, {"y": "v"})],
    "treemap": [("values", {"l": ["가", "나", "다"], "v": [1.0, 2.0, _BAD]}, {"labels": "l", "values": "v"})],
    "violinplot": [("y", {"x": ["가", "가", "나", "나"], "y": [1.0, 2.0, 3.0, _BAD]}, {"x": "x", "y": "y"})],
}

_FLAT = [(name, channel, data, kwargs) for name, cases in _CASES.items() for channel, data, kwargs in cases]


def test_the_case_table_covers_every_chart() -> None:
    """A seventeenth chart has to be added here rather than quietly skipping the rule.

    ``sp.charts.__all__`` is the package's own answer to "which sixteen".
    """
    assert set(_CASES) == set(sp.charts.__all__), set(_CASES) ^ set(sp.charts.__all__)


@pytest.mark.parametrize(("name", "channel", "data", "kwargs"), _FLAT, ids=[f"{n}-{c}" for n, c, _, _ in _FLAT])
def test_a_non_numeric_value_is_refused_by_column_name(name: str, channel: str, data: dict, kwargs: dict) -> None:
    """The message names the column the caller passed, not just the value that broke.

    Asserted as "the column name appears" rather than against a fixed sentence: ``lineplot``'s
    ``x`` says "has no position on an x axis" and ``radarplot`` names the category as well, and
    both are *more* specific than the shared message. Requiring one wording would force those
    two to become less helpful to satisfy a test.
    """
    column = kwargs[channel]

    with pytest.raises(ValueError) as caught:
        getattr(sp, name)(data, **kwargs)

    message = str(caught.value)
    assert repr(column) in message, f"{name} refused {channel}= without naming the column {column!r}: {message}"
    assert "could not convert string to float" not in message, f"{name} let float()'s own message out: {message}"


@pytest.mark.parametrize(("name", "channel", "data", "kwargs"), _FLAT, ids=[f"{n}-{c}" for n, c, _, _ in _FLAT])
def test_the_same_chart_draws_the_fixture_once_the_value_is_a_number(
    name: str, channel: str, data: dict, kwargs: dict
) -> None:
    """Non-vacuity, and it is doing real work: without it a chart that refused *every* call --
    or one whose fixture was malformed in some second way -- would satisfy the check above by
    raising for the wrong reason entirely."""
    repaired = {key: [9.0 if value is _BAD else value for value in column] for key, column in data.items()}

    assert getattr(sp, name)(repaired, **kwargs).to_string()


def test_the_shared_helper_names_the_column() -> None:
    """The helper's own contract, so the rule is one readable expression rather than something
    inferred from sixteen error messages."""
    with pytest.raises(ValueError, match=r"column '매출' holds str, which is not a number"):
        require_number("nope", "매출")

    with pytest.raises(ValueError, match=r"column '매출' holds NoneType, which is not a number"):
        require_number(None, "매출")


def test_the_helper_reports_the_type_not_the_value() -> None:
    """A column of long strings would otherwise put an arbitrary amount of the caller's data
    into the exception, and the *kind* is what says what went wrong. The value is still on the
    chained cause for anyone reading the traceback."""
    secret = "x" * 500

    with pytest.raises(ValueError) as caught:
        require_number(secret, "값")

    assert secret not in str(caught.value)
    assert secret in str(caught.value.__cause__)


def test_the_helper_passes_numbers_through_unchanged() -> None:
    """The other half of the range. A helper that raised for everything would satisfy every
    refusal check above and no chart would draw at all."""
    assert require_number(3, "값") == 3.0
    assert require_number(2.5, "값") == 2.5
    assert isinstance(require_number(3, "값"), float)


def test_numeric_or_none_still_drops_missing_before_it_refuses() -> None:
    """Order matters: a missing value is dropped, not refused. Reversing the two would make
    every ``None`` in every optional channel an error instead of a gap."""
    assert numeric_or_none(None, "값") is None
    assert numeric_or_none(float("nan"), "값") is None
    assert numeric_or_none(2.0, "값") == 2.0

    with pytest.raises(ValueError, match=r"column '값'"):
        numeric_or_none("nope", "값")


def test_sparkline_names_the_argument_it_actually_takes() -> None:
    """``sparkline`` has no ``x=`` -- its docstring says so out loud -- but it passed ``y`` into
    ``ingest_longform``'s first required channel, which is spelled ``x``. A caller who mistyped
    ``y=`` was told to check an argument they could not have passed, and had nothing to search
    their own code for."""
    with pytest.raises(KeyError, match=r"y column not found in data: 'nope'"):
        sp.sparkline({"v": [1.0, 2.0]}, y="nope")


def test_sparkline_still_reports_a_missing_column_at_all() -> None:
    """Non-vacuity for the translation: a version that swallowed the KeyError entirely would
    satisfy a check that only asked for the word ``y``."""
    with pytest.raises(KeyError):
        sp.sparkline({"v": [1.0, 2.0]}, y="없는컬럼")

    assert sp.sparkline({"v": [1.0, 2.0]}, y="v").to_string()


_NUMPY_SCALARS = pytest.importorskip("numpy", reason="install the numpy-parity extra to check this")


@pytest.mark.parametrize(
    ("call", "label"),
    [
        (lambda np, d: sp.gaugeplot(d, values="v", labels="l", vmin=np.float32(0.0)), "gaugeplot vmin"),
        (lambda np, d: sp.gaugeplot(d, values="v", labels="l", vmax=np.float32(100.0)), "gaugeplot vmax"),
        (lambda np, d: sp.gaugeplot(d, values="v", labels="l", vmax=np.int64(100)), "gaugeplot vmax int64"),
        (lambda np, d: sp.pieplot(d, values="v", labels="l", inner_radius=np.float32(0.4)), "pieplot inner_radius"),
    ],
)
def test_a_numpy_scalar_is_accepted_where_width_accepts_one(call, label: str) -> None:
    """One caller, one array library, two answers: ``width=np.float32(400)`` was accepted and
    ``vmax=np.float32(100)`` refused, because ``_layout._finite`` tests ``numbers.Real`` while
    ``gauge`` and ``pie`` each kept a copy testing ``int | float``. ``numpy.float64`` slipped
    through both -- it subclasses ``float`` -- so only the narrower dtypes showed the split.
    """
    numpy = _NUMPY_SCALARS
    data = {"l": ["가", "나"], "v": [1.0, 2.0]}

    assert call(numpy, data).to_string(), label

    # The parameter these were measured against, on the same call, for the same reason.
    assert sp.pieplot(data, values="v", labels="l", width=numpy.float32(400.0)).to_string()


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True, "0.4"])
def test_the_widened_check_still_refuses_what_it_refused_before(bad: object) -> None:
    """Widened, not opened. ``bool`` is the one that has to be named: it is ``numbers.Real``,
    so admitting every ``Real`` without excluding it would make ``vmax=True`` a request for
    one -- which is the argument ``_layout._finite``'s own docstring makes about ``width``."""
    data = {"l": ["가", "나"], "v": [1.0, 2.0]}

    with pytest.raises(ValueError, match="vmax"):
        sp.gaugeplot(data, values="v", labels="l", vmax=bad)  # type: ignore[arg-type]
