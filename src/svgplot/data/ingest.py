"""Long-form DataFrame ingestion — the seaborn-style ``data=, x=, y=`` entry point.

Accepts a pandas DataFrame (duck-typed — pandas is never imported, so it stays
out of this package's dependencies), a dict of column name -> sequence, or a
list of dict records, and normalizes all three into the same column-dict shape
(see ``data._columns`` for the shared normalization this and ``semantic.py``
both build on).

Wide-form auto-detection is a 2차 addition planned for this same file
(docs-research/10-feature-matrix.md A2, docs-research/14-scope-recommendation.md).
"""

from __future__ import annotations

from dataclasses import dataclass

from svgplot.data._columns import column_length, extract_columns


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
        return column_length(self.columns)


def ingest_longform(data: object, x: str, y: str | None = None) -> LongFormData:
    """Validate and normalize a long-form DataFrame (or array-like) input.

    Raises:
        TypeError: if ``data`` isn't a DataFrame-like object, dict of columns,
            or list of dict records.
        KeyError: if ``x`` (or ``y``, when given) isn't a column in ``data``.
        ValueError: if the columns don't all share the same length.
    """
    columns = extract_columns(data)
    if x not in columns:
        raise KeyError(f"x column not found in data: {x!r}")
    if y is not None and y not in columns:
        raise KeyError(f"y column not found in data: {y!r}")
    column_length(columns)
    return LongFormData(columns=columns, x=x, y=y)
