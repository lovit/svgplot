"""Every numeric *argument* answers the same question about what counts as a number.

A caller's data comes from an array library, and so do the numbers they hand to arguments
alongside it. ``charts/_layout._finite`` -- which every chart's ``width=``/``height=`` goes
through -- says so out loud: ``numbers.Real`` rather than ``int | float``, because
``numpy.float32``/``numpy.int64`` are neither of those two while being perfectly good numbers.

Three other validators were written with the narrower test and drifted from it. The split was
visible **inside a single call**: ``heatmap(..., width=np.float32(400), center=np.float32(1.5))``
accepted the first argument and refused the second. ``numpy.float64`` slipped through both --
it subclasses ``float`` -- so only the narrower dtypes ever showed it (#256, #274).

This file is the family-crossing assertion for argument types, and it is deliberately *not* an
import-sharing arrangement. ``palette`` and ``chart`` sit below ``charts`` and must not depend
on it, so the three validators stay separate expressions of one rule and this is what keeps
them in step -- the same shape as ``test_charts_numeric_refusal.py``, one layer up.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

import svgplot as sp
from svgplot.theme.base import Theme

numpy = pytest.importorskip("numpy", reason="install the numpy-parity extra to check this")

_HEAT = {"구간": ["가", "나"], "행": ["위", "아래"], "값": [1.0, 2.0]}
_XY = {"가로": [1.0, 2.0, 3.0], "세로": [1.0, 2.0, 3.0]}
_DIVERGING = "coolwarm"
"""A registered diverging palette. ``center=`` needs one -- passing it beside a sequential cmap
raises before the type check is reached, which is how a first draft of this file "passed"."""


def _accepts(argument: str, value: object) -> None:
    """Draw a chart passing ``value`` to ``argument``. Raises if it is refused."""
    if argument == "width":
        sp.heatmap(_HEAT, x="구간", y="행", values="값", width=value)  # type: ignore[arg-type]
    elif argument == "center":
        sp.heatmap(_HEAT, x="구간", y="행", values="값", cmap=_DIVERGING, center=value)  # type: ignore[arg-type]
    elif argument == "xlim":
        # ``(0.0, value)``, not ``(value, value)``: a window of zero width is refused for its own
        # reasons, so a pair of equal bounds made every outcome an exception and the comparison
        # below degenerated into matching two error *messages* -- which differ because each
        # quotes the value it was given. One good bound keeps an accepted value at "ok".
        sp.lineplot(_XY, x="가로", y="세로", xlim=(0.0, value))  # type: ignore[arg-type]
    elif argument == "ylim":
        sp.lineplot(_XY, x="가로", y="세로", ylim=(0.0, value))  # type: ignore[arg-type]
    elif argument == "vmax":
        sp.gaugeplot({"이름": ["가"], "값": [1.0]}, values="값", labels="이름", vmax=value)  # type: ignore[arg-type]
    elif argument in ("opacity", "fill_opacity", "corner_radius"):
        Theme(**{argument: value})  # type: ignore[arg-type]
    else:  # pragma: no cover - the table below is the only caller
        raise AssertionError(argument)


_VALID: dict[str, float] = {
    "width": 400.0,
    "center": 2.0,
    "xlim": 2.0,
    "ylim": 2.0,
    "vmax": 2.0,
    "opacity": 0.5,
    "fill_opacity": 0.5,
    "corner_radius": 2.0,
}
"""A value each argument accepts outright, used as the reference in every comparison below.

Per argument because "an ordinary number" is not the same number everywhere: ``width=2`` is
refused by a minimum-canvas rule that has nothing to do with types (``canvas must be at least
240.0x180.0``), and comparing against a value that fails for an unrelated reason would make the
comparison vacuous.
"""

_ARGUMENTS = list(_VALID)
"""One per validator that answers this question, plus ``width`` as the reference.

``width`` is ``charts/_layout._finite``; ``center`` is ``palette/normalize._require_finite_number``;
``xlim``/``ylim`` are ``chart/_domain._require_finite_pair``; ``vmax`` is ``gauge``'s use of
``_finite`` after #256 removed its own copy. The last three are ``Theme.__post_init__``, which a
review found still narrow after this file's first draft claimed the count was complete -- the
third time that count has been wrong (#256 fixed two, #271's review found two more, #276's found
these). Hence a table built to be added to rather than a number written in prose.
"""


def _outcome(argument: str, value: object) -> str:
    """What the call did: ``"ok"``, or the exception's type and message.

    Compared against the *same number as a plain float* rather than matched against a phrase.
    Three mutations survived a phrase-matching version of this file -- ``_finite`` narrowing to
    ``int | float`` says "width must be a finite number", which matches neither of the two
    phrases that draft looked for, and a ``bool`` accepted by the type check still raised later
    for being a zero-width window, so "it raised" was satisfied for the wrong reason. Comparing
    outcomes asks the question directly and cannot be defeated by rewording.
    """
    try:
        _accepts(argument, value)
    except Exception as error:
        return f"{type(error).__name__}: {error}"
    return "ok"


@pytest.mark.parametrize("argument", _ARGUMENTS)
@pytest.mark.parametrize("dtype", ["float32", "float64", "int32", "int64"])
def test_a_numpy_scalar_lands_exactly_where_the_same_python_number_does(argument: str, dtype: str) -> None:
    """The rule, across every argument that asks it, without reading a single message.

    ``2`` and ``numpy.<dtype>(2)`` are the same number, so every one of these arguments has to
    treat them identically. No message is read: the comparison is against what the same value
    as a plain float does, which is a question no rewording can dodge.
    """
    reference = _VALID[argument]
    assert _outcome(argument, numpy.dtype(dtype).type(reference)) == _outcome(
        argument, reference
    ), f"{argument}= treats {dtype} differently from the same value as a float"


@pytest.mark.parametrize("argument", _ARGUMENTS)
def test_the_ordinary_python_number_is_not_itself_refused(argument: str) -> None:
    """Non-vacuity for the comparison above, which an argument that refused *everything* would
    satisfy trivially: a plain ``2.0`` has to get past the type rule.

    Every argument here accepts ``2.0`` outright, so the assertion is simply that it did.
    """
    assert (
        _outcome(argument, _VALID[argument]) == "ok"
    ), f"{argument}= refused a plain float: {_outcome(argument, _VALID[argument])}"


@pytest.mark.parametrize("argument", _ARGUMENTS)
@pytest.mark.parametrize(
    ("bad", "would_become"),
    [(True, 1.0), (float("nan"), None), (float("inf"), None), ("2", None)],
    ids=["bool", "nan", "inf", "str"],
)
def test_what_was_refused_before_is_still_refused(argument: str, bad: object, would_become: float | None) -> None:
    """Widened, not opened -- and asserted as a *difference* rather than as "it raised".

    ``bool`` is the one that has to be named: it **is** ``numbers.Real``, so admitting every
    ``Real`` without excluding it makes ``center=True`` a request for 1 -- the argument
    ``_finite``'s own docstring makes about ``width``. Requiring only that ``True`` raises is
    not enough, because ``xlim=(True, True)`` becomes ``(1.0, 1.0)`` and raises anyway as a
    zero-width window, so a version of this check that asked for a raise passed while the
    guard was gone.

    The comparison is against the value each bad one would silently *become* if the guard were
    dropped. ``nan``/``inf``/``"2"`` cannot become a number at all, so ``2.0`` stands in as an
    ordinary value the argument accepts -- the assertion there is that the bad value does not
    reach the same outcome an acceptable one does.
    """
    # ``None`` means "there is no number this could silently become" -- then the reference is
    # the argument's own accepted value, and the assertion is that the bad one does not reach
    # the same outcome an acceptable one does.
    reference = _VALID[argument] if would_become is None else would_become

    assert _outcome(argument, bad) != _outcome(argument, reference), f"{argument}= treats {bad!r} the same as {reference!r}"


def test_the_argument_table_names_a_validator_that_still_exists() -> None:
    """The registry check. Each entry above stands for one validator; if a validator is merged
    away or renamed, the entry should be reconsidered rather than left pointing at nothing.

    Asserted by calling each one and requiring it to *do* something -- refuse a string -- so an
    argument that silently stopped validating cannot sit here unnoticed.
    """
    for argument in _ARGUMENTS:
        with pytest.raises((ValueError, TypeError)):
            _accepts(argument, "not a number")


def test_float64_alone_would_not_have_shown_the_split() -> None:
    """Why the dtype list above is not just ``float64``, stated as an executable fact.

    ``numpy.float64`` subclasses ``float``, so it satisfied the narrow ``int | float`` test as
    well as the wide one -- it is exactly the dtype that could not reveal the drift, and a
    fixture using it would have passed against the defect.
    """
    assert isinstance(numpy.float64(2.0), float)
    assert not isinstance(numpy.float32(2.0), float)
    assert not isinstance(numpy.int64(2), float)


# ---------------------------------------------------------------------------
# the three validators, called directly
# ---------------------------------------------------------------------------


def _validators() -> dict[str, object]:
    """Each validator wrapped to one signature, so the table below can ask them all one question.

    Called directly rather than through a chart because the chart route cannot see *where* a
    value was refused: dropping the finiteness test from either validator still ends in an
    exception -- a ``nan`` that gets past it dies further down in a scale -- so a check that only
    compares outcomes stays green. Measured; two mutations survived exactly that way.
    """
    from svgplot.chart._domain import _require_finite_pair
    from svgplot.charts._layout import _finite
    from svgplot.palette.normalize import _require_finite_number

    return {
        "_layout._finite": lambda value: _finite(value, "width"),
        "palette._require_finite_number": lambda value: _require_finite_number(value, field="center"),
        "_domain._require_finite_pair": lambda value: _require_finite_pair((0.0, value)),
    }


@pytest.mark.parametrize("name", sorted(_validators()))
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")], ids=["nan", "inf", "-inf"])
def test_every_validator_refuses_a_non_finite_number_itself(name: str, bad: float) -> None:
    """Not "the call eventually fails" -- *this* function raises."""
    with pytest.raises(ValueError):
        _validators()[name](bad)  # type: ignore[operator]


@pytest.mark.parametrize("name", sorted(_validators()))
@pytest.mark.parametrize("bad", [True, "2", None, [2.0]], ids=["bool", "str", "none", "list"])
def test_every_validator_refuses_a_non_number_itself(name: str, bad: object) -> None:
    """``bool`` included: it is ``numbers.Real``, so widening the type test without excluding it
    turns ``center=True`` into a request for 1."""
    with pytest.raises(ValueError):
        _validators()[name](bad)  # type: ignore[operator]


@pytest.mark.parametrize("name", sorted(_validators()))
@pytest.mark.parametrize("dtype", ["float32", "float64", "int32", "int64"])
def test_every_validator_accepts_a_numpy_scalar_itself(name: str, dtype: str) -> None:
    """The widening, at the level it was written. The chart-level comparison above says the
    three agree; this says what they agree *on*."""
    assert _validators()[name](numpy.dtype(dtype).type(2)) is not None  # type: ignore[operator]


@pytest.mark.parametrize("name", sorted(_validators()))
def test_every_validator_turns_an_unfloatable_real_into_a_value_error(name: str) -> None:
    """A ``Real`` too large to become a float raises ``OverflowError`` from ``math.isfinite``,
    and every one of these documents ``ValueError``.

    This is the hole widening the type test opened: before it, ``Fraction(10**400)`` failed the
    ``int | float`` check and was refused cleanly; after it, the value reached ``isfinite`` and
    the ``OverflowError`` came out raw. ``_layout._finite`` already had the ``try``/``except``
    and its docstring already named this exact case -- the two new sites had to copy the whole
    pattern, not half of it (#274).
    """
    with pytest.raises(ValueError):
        _validators()[name](Fraction(10**400))  # type: ignore[operator]


@pytest.mark.parametrize("name", sorted(_validators()))
def test_every_validator_accepts_a_real_that_is_not_int_or_float(name: str) -> None:
    """Non-vacuity for the check above, and the point of widening in the first place: an
    ordinary ``Fraction`` is a perfectly good number and has to get through, so the guard cannot
    be satisfied by refusing the whole type."""
    assert _validators()[name](Fraction(3, 2)) is not None  # type: ignore[operator]
