"""Shared column-shape normalization used by both ``ingest.py`` and ``semantic.py``.

Private/internal — not re-exported from ``svgplot.data``. Lives in its own file
(rather than inside ``ingest.py``) because both modules depend on it equally;
housing it under either one's name would misrepresent which module actually
owns it.
"""

from __future__ import annotations


def extract_columns(data: object) -> dict[str, list]:
    """Normalize DataFrame-like / dict-of-columns / list-of-records input into ``{column: [values]}``.

    DataFrame support is duck-typed (``.columns`` + ``__getitem__``) rather than
    ``isinstance``-checked against pandas, so this package never needs pandas as
    a dependency while still accepting real DataFrames at runtime.

    For a list of dict records, the **first record's keys** define the column
    set: a key present only in a later record is silently dropped, and a key
    missing from a later record becomes ``None`` for that row. Records are
    expected to share one schema, as is typical for long-form data; this
    still degrades predictably (no crash, no silently-wrong lengths) if they don't.
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


def column_length(columns: dict[str, list]) -> int:
    """Validate that all columns share one length and return it (0 for no columns)."""
    lengths = {len(values) for values in columns.values()}
    if len(lengths) > 1:
        raise ValueError(f"columns have mismatched lengths: {lengths}")
    return lengths.pop() if lengths else 0
