"""Missing-value detection shared by data ingestion and every chart type.

Lives in ``data`` rather than ``charts`` because "is this data point missing?"
is a property of the data, not of any rendering decision — ``data.semantic``
needs it to drop rows with no well-defined group, and each chart needs the
same rule to drop unplottable points. Housing it under either one alone would
misrepresent which module owns it (same reasoning as ``data/_columns.py``).

Private/internal — not re-exported from ``svgplot.data``.
"""

from __future__ import annotations


def is_missing(value: object) -> bool:
    """``None`` or NaN.

    NaN is detected via ``value != value`` rather than ``math.isnan`` so this works
    for numpy's NaN (and any other float-like that follows IEEE reflexivity) without
    importing numpy — this package's optional-dependency stance (see
    ``data/_columns.py``'s duck-typed DataFrame handling).
    """
    return value is None or (isinstance(value, float) and value != value)


def numeric_or_none(value: object) -> float | None:
    """Coerce to ``float``, or ``None`` if the value is missing.

    Lets a caller drop missing points and convert survivors in one pass, instead of
    testing and converting separately.
    """
    return None if is_missing(value) else float(value)
