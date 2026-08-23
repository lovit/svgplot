"""Missing-value detection, and the coercion that follows it, shared by data ingestion and
every chart type.

Lives in ``data`` rather than ``charts`` because "is this data point missing?"
is a property of the data, not of any rendering decision — ``data.semantic``
needs it to drop rows with no well-defined group, and each chart needs the
same rule to drop unplottable points. Housing it under either one alone would
misrepresent which module owns it (same reasoning as ``data/_columns.py``).

The coercion belongs with the test for the same reason: "drop it or convert it" is one
decision per value, and :func:`numeric_or_none` was already both halves of it. What is new
is that the conversion says *which column* it failed on — see :func:`require_number`.

Private/internal — not re-exported from ``svgplot.data``.
"""

from __future__ import annotations

import numbers


def is_missing(value: object) -> bool:
    """``None`` or NaN.

    NaN is detected via ``value != value`` rather than ``math.isnan`` so this works
    for any float-like that follows IEEE reflexivity without importing numpy — this
    package's optional-dependency stance (see ``data/_columns.py``'s duck-typed
    DataFrame handling).

    The type test is ``numbers.Number``, not ``float``, because ``float`` is exactly
    the wrong width for that stance: ``numpy.float64`` subclasses ``float`` but
    ``numpy.float32``, ``float16`` and ``longdouble`` do not, so a ``float`` test made
    NaN-detection depend on a column's dtype. A ``float32`` column of the same numbers
    silently kept its NaN rows — as a fourth hue group labelled ``nan`` in the legend,
    or as ``ValueError: value must be finite`` from a scale that got handed one (#257).
    Every numpy scalar registers as ``numbers.Number``, as do ``Decimal`` and
    ``Fraction``; ``str`` and ``numpy.str_`` do not, so a text column still answers
    ``False`` without a comparison.

    ``numpy.datetime64("NaT")`` is *not* covered: it is not a ``Number``, and a missing
    timestamp needs a decision about the time axis rather than this predicate's answer.
    """
    # ``bool(...)`` on both comparisons: a numpy scalar's ``!=`` answers ``numpy.bool_``, not
    # ``bool``, and ``numpy.float64`` *is* a ``float`` subclass -- so the fast path needs the
    # conversion just as much as the general one. Without it a ``data`` module in a package with
    # no runtime dependency on numpy returns a numpy type, which stays invisible (``numpy.bool_``
    # is truthy and compares equal to ``True``) until something far from here asks ``is True``.
    if isinstance(value, float):  # the common case, and a subclass check is enough for it
        return bool(value != value)
    if value is None:
        return True
    return isinstance(value, numbers.Number) and bool(value != value)


def require_number(value: object, column: str, *, context: str = "") -> float:
    """``float(value)``, naming the column when the value is not a number.

    ``scales.py`` states this package's one stance on bad input -- it "refuses **by name**
    rather than masking or clipping" -- and a bare ``float()`` breaks it in the least helpful
    way available: ``ValueError: could not convert string to float: 'a'`` says what the value
    was and nothing about where it came from. A caller with a forty-column frame has to find
    the column themselves, and the same message came out of nine different charts (#256).

    ``TypeError`` and ``ValueError`` are both caught and both re-raised as ``ValueError``:
    ``float(None)`` raises the first and ``float("a")`` the second, and to a caller they are
    one mistake -- a column that is not numbers. The original is chained, so the value is still
    visible to anyone who reads the traceback.

    The type name rather than the value: a column of long strings would otherwise put an
    arbitrary amount of the caller's data into the exception, and the *kind* is what tells them
    what went wrong. The value survives on the chained cause.

    ``context`` appends a caller-supplied phrase naming *which row* -- ``radarplot`` passes the
    category, because on a chart with one mark per spoke that is what the reader is looking at.
    It is additive on purpose: the column name is the part every chart owes the caller, and a
    chart that can say more should not have to give that up to say it (#256).
    """
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        where = f" ({context})" if context else ""
        raise ValueError(f"column {column!r} holds {type(value).__name__}, which is not a number{where}") from error


def numeric_or_none(value: object, column: str) -> float | None:
    """Coerce to ``float``, or ``None`` if the value is missing.

    Lets a caller drop missing points and convert survivors in one pass, instead of
    testing and converting separately. Survivors go through :func:`require_number`, so a
    column that is not missing and not numeric is refused by name rather than by
    ``float()``'s own message.
    """
    return None if is_missing(value) else require_number(value, column)
