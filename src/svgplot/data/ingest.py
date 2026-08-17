"""Long-form DataFrame ingestion — the seaborn-style ``data=, x=, y=`` entry point.

Accepts a pandas DataFrame (duck-typed — pandas is never imported, so it stays
out of this package's dependencies), a dict of column name -> sequence, or a
list of dict records, and normalizes all three into the same column-dict shape.

Wide-form auto-detection is a 2차 addition planned for this same file
(docs/research/10-feature-matrix.md A2, docs/research/14-scope-recommendation.md).
"""

from __future__ import annotations

from dataclasses import dataclass


def _extract_columns(data: object) -> dict[str, list]:
    """Normalize DataFrame-like / dict-of-columns / list-of-records input into ``{column: [values]}``.

    DataFrame support is duck-typed (``.columns`` + ``__getitem__``) rather than
    ``isinstance``-checked against pandas, so this package never needs pandas as
    a dependency while still accepting real DataFrames at runtime.
    """
    if hasattr(data, "columns") and hasattr(data, "__getitem__"):
        return {str(column): list(data[column]) for column in data.columns}
    if isinstance(data, dict):
        return {str(key): list(value) for key, value in data.items()}
    if isinstance(data, list | tuple):
        if not data:
            return {}
        if not all(isinstance(row, dict) for row in data):
            raise TypeError("list/tuple input must be a list of dict records")
        keys = list(data[0].keys())
        return {str(key): [row.get(key) for row in data] for key in keys}
    raise TypeError(
        f"unsupported data type: {type(data).__name__} (expected a pandas DataFrame, "
        "a dict of column name -> sequence, or a list of dict records)"
    )


def _column_length(columns: dict[str, list]) -> int:
    """Validate that all columns share one length and return it (0 for no columns)."""
    lengths = {len(values) for values in columns.values()}
    if len(lengths) > 1:
        raise ValueError(f"columns have mismatched lengths: {lengths}")
    return lengths.pop() if lengths else 0


@dataclass(frozen=True)
class LongFormData:
    """Normalized long-form data: equal-length columns, plus which ones are ``x``/``y``.

    Missing values (``None``/``NaN``) are preserved exactly as given — ingestion
    never drops rows. Whether/how to handle a missing point (skip it, show a
    gap, ...) is a chart-type-specific decision made later, not an ingestion one.
    """

    columns: dict[str, list]
    x: str
    y: str | None

    def __len__(self) -> int:
        return _column_length(self.columns)


def ingest_longform(data: object, x: str, y: str | None = None) -> LongFormData:
    """Validate and normalize a long-form DataFrame (or array-like) input.

    Raises:
        TypeError: if ``data`` isn't a DataFrame-like object, dict of columns,
            or list of dict records.
        KeyError: if ``x`` (or ``y``, when given) isn't a column in ``data``.
        ValueError: if the columns don't all share the same length.
    """
    columns = _extract_columns(data)
    if x not in columns:
        raise KeyError(f"x column not found in data: {x!r}")
    if y is not None and y not in columns:
        raise KeyError(f"y column not found in data: {y!r}")
    _column_length(columns)
    return LongFormData(columns=columns, x=x, y=y)
