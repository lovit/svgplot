"""Narrow a caller's data down to the rows a chart actually drew, for label rendering.

Why this lives in ``labels`` rather than beside it:

- Not ``spec.py``: that module owns the ``@field{format}`` mini-language -- parsing and
  formatting single values. Choosing *which rows* survive is a data question that never
  touches a format spec.
- Not ``data/``: the selection is driven entirely by a ``LabelSpec``, and ``data/`` has no
  business importing from ``labels``. The dependency runs one way, so the shared piece it
  does need (``is_missing``) is imported *from* ``data`` instead. Same argument
  ``data/_columns.py`` makes for its own placement.

Private/internal -- not re-exported from ``svgplot.labels``.

Row selection
=============

``render_table`` reads the *original* columns, but charts drop rows and ``lineplot`` even
sorts them. Three alignments were possible and two are wrong:

- **Every original row** would make the table assert data the chart never drew.
- **"The rows actually drawn"** is undefinable for half the chart types: ``bar`` lets the
  last row of a category win, ``area`` sums, ``box`` buckets, ``hist`` bins. There is no
  row-to-mark correspondence to report.
- **Rows whose required channels are all present** -- what this module does. It reuses
  ``data._missing.is_missing``, so the rule is *identical* to the one each chart applies
  when dropping unplottable points, and it stays well-defined for every chart type.

Row *order* is input order, not plot order. Plot order differs only for ``lineplot``, and
restoring it would mean threading the indices ``extract_channels`` discards through seven
chart modules; with ``hue=`` it would also group-order the table, which reads worse. A
table is a lookup structure keyed by value, not a positional companion to the marks.

A column named in the spec but *not* used as a chart channel may still be missing in a
surviving row. Those cells render as :data:`MISSING_TEXT` and the row is kept -- dropping
it would silently shrink the table for a column the chart never consulted.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from svgplot.data._columns import column_length, extract_columns
from svgplot.data._missing import is_missing
from svgplot.labels.spec import LabelSpec


@dataclass(frozen=True)
class LabelData:
    """A ``LabelSpec`` plus the rows that survived channel filtering.

    ``columns`` holds only the fields the spec names -- a chart keeps this for the
    lifetime of the ``Chart``, and holding the caller's whole DataFrame would both waste
    memory and let a post-plot mutation make the table disagree with the SVG.
    """

    spec: LabelSpec
    columns: dict[str, list]

    def __len__(self) -> int:
        return column_length(self.columns) if self.columns else 0


def collect_label_data(data: object, info: LabelSpec | None, *, required: Sequence[str | None]) -> LabelData | None:
    """Snapshot the ``info`` fields of ``data``, keeping rows whose channels are present.

    Args:
        data: the same shapes ``data.ingest_longform`` accepts.
        info: the spec to snapshot for, or ``None`` to skip label collection entirely.
        required: the channel column names the calling chart consumes -- ``x``/``y``/
            ``hue``/``size``/``values``/``labels`` as applicable. ``None`` entries are
            ignored so a caller can pass optional channels straight through.

    Returns:
        ``None`` if ``info`` is ``None``, otherwise a :class:`LabelData` whose columns are
        restricted to the spec's fields and whose rows are those with every required
        channel present, in input order.

    Raises:
        KeyError: if a field named in ``info``, or a name in ``required``, isn't a column
            in ``data``. Raised here at plot time rather than deferred to ``save()``, so a
            typo surfaces where the spec was passed.
    """
    if info is None:
        return None

    columns = extract_columns(data)

    for field in info:
        if field.field not in columns:
            raise KeyError(f"field not found in data: {field.field!r}")

    channels = [name for name in required if name is not None]
    for name in channels:
        if name not in columns:
            raise KeyError(f"channel column not found in data: {name!r}")

    kept = [
        row_index
        for row_index in range(column_length(columns))
        if all(not is_missing(columns[name][row_index]) for name in channels)
    ]

    return LabelData(
        spec=info,
        columns={field.field: [columns[field.field][row_index] for row_index in kept] for field in info},
    )
