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
    indices = channel_row_indices(data, hue, col, row)
    return {
        key: {name: [values[index] for index in rows] for name, values in columns.items()} for key, rows in indices.items()
    }


def channel_row_indices(
    data: object,
    hue: str | None = None,
    col: str | None = None,
    row: str | None = None,
) -> dict[object, list[int]]:
    """The same split as :func:`extract_channels`, as *original row indices* per group.

    The two are one filter with two views: ``extract_channels`` is defined in terms of this,
    not beside it. A chart that needs to trace a mark back to the row it came from -- to fill a
    tooltip from the same ``info=`` spec the footnote table uses -- needs the indices, and a
    second implementation of "which rows are in which group" is a second thing to go wrong.
    The risk is not hypothetical: the label snapshot in ``labels/_source.py`` applies its own
    filter over the same data, and the whole difficulty of pairing a mark with its table row is
    that two filters can silently disagree about which rows survived.

    Group keys and their order are exactly ``extract_channels``', because that function is
    built from this one.

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

    groups: dict[object, list[int]] = {}
    for index in range(column_length(columns)):
        key_parts = [columns[column_name][index] for _, column_name in channels]
        if any(is_missing(value) for value in key_parts):
            continue  # missing channel value -> no well-defined group, drop the row
        key = key_parts[0] if len(key_parts) == 1 else tuple(key_parts)
        groups.setdefault(key, []).append(index)
    return groups
