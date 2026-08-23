"""Missing-value detection shared by data ingestion and every chart type.

Lives in ``data`` rather than ``charts`` because "is this data point missing?"
is a property of the data, not of any rendering decision — ``data.semantic``
needs it to drop rows with no well-defined group, and each chart needs the
same rule to drop unplottable points. Housing it under either one alone would
misrepresent which module owns it (same reasoning as ``data/_columns.py``).

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
    if isinstance(value, float):  # the common case, and a subclass check is enough for it
        return value != value
    if value is None:
        return True
    # ``bool(...)``: a numpy scalar comparison returns ``numpy.bool_``, not ``bool``.
    return isinstance(value, numbers.Number) and bool(value != value)


def numeric_or_none(value: object) -> float | None:
    """Coerce to ``float``, or ``None`` if the value is missing.

    Lets a caller drop missing points and convert survivors in one pass, instead of
    testing and converting separately.
    """
    return None if is_missing(value) else float(value)
