"""Semantic channel extraction: hue=/col=/row= column-to-visual-channel mapping.

size=/style= are 2차 additions planned for this same file
(docs-research/10-feature-matrix.md A2).
"""

from __future__ import annotations

from svgplot.data._columns import column_length, extract_columns
from svgplot.data._missing import is_missing


def extract_channels(
    data: object,
    hue: str | None = None,
    col: str | None = None,
    row: str | None = None,
) -> dict[object, dict[str, list]]:
    """Split long-form data into groups keyed by the given semantic channel(s).

    Each group's value is a column-dict subset (same shape as
    ``ingest.LongFormData.columns``) containing only the rows in that group,
    across *all* of ``data``'s columns — not just the channel columns — so
    downstream code can still read ``x``/``y`` per group.

    With exactly one channel given, group keys are that channel's raw values
    (e.g. ``{"a": ..., "b": ...}``). With more than one, keys are a tuple in
    ``(hue, col, row)`` order, omitting any channel that wasn't requested.

    A row whose value is missing (``None``/NaN) for *any* requested channel has
    no well-defined group and is dropped from the result entirely — it is not
    given a group of its own.

    Raises:
        ValueError: if none of ``hue``/``col``/``row`` is given.
        KeyError: if a given channel isn't a column in ``data``.
    """
    channels = [(name, column) for name, column in (("hue", hue), ("col", col), ("row", row)) if column is not None]
    if not channels:
        raise ValueError("at least one of hue/col/row must be given")

    columns = extract_columns(data)
    for channel_name, column_name in channels:
        if column_name not in columns:
            raise KeyError(f"{channel_name} column not found in data: {column_name!r}")
    length = column_length(columns)

    groups: dict[object, dict[str, list]] = {}
    for index in range(length):
        key_parts = [columns[column_name][index] for _, column_name in channels]
        if any(is_missing(value) for value in key_parts):
            continue  # missing channel value -> no well-defined group, drop the row
        key = key_parts[0] if len(key_parts) == 1 else tuple(key_parts)
        group = groups.setdefault(key, {name: [] for name in columns})
        for name, values in columns.items():
            group[name].append(values[index])
    return groups
