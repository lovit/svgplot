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

Row *order* is input order, not plot order, and with ``hue=`` the two differ -- the marks are
grouped into series and the table is not. Reordering the table to match was rejected rather
than deferred: a table is a lookup structure keyed by value, and group-ordering it reads worse
than the input order the caller wrote. What a mark needs is not the same order but the same
*row*, and it gets it by number: :attr:`LabelData.row_indices` records which input rows
survived, ``data.semantic.channel_row_indices`` records which rows each series holds, and
:meth:`LabelData.row` is asked by index rather than by position.

A column named in the spec but *not* used as a chart channel may still be missing in a
surviving row. Those cells render as :data:`MISSING_TEXT` and the row is kept -- dropping
it would silently shrink the table for a column the chart never consulted.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import cached_property

from svgplot.data._columns import column_length, extract_columns
from svgplot.data._missing import is_missing
from svgplot.labels.spec import LabelSpec


@dataclass(frozen=True)
class LabelData:
    """A ``LabelSpec`` plus the rows that survived channel filtering.

    ``columns`` holds only the fields the spec names -- a chart keeps this for the
    lifetime of the ``Chart``, and holding the caller's whole DataFrame would both waste
    memory and let a post-plot mutation of *the caller's data* make the table disagree
    with the SVG. The snapshot is shallowly frozen: the lists inside are fresh copies, so
    they are not aliases of the caller's, but nothing stops a holder of this object from
    mutating them.
    """

    spec: LabelSpec
    columns: dict[str, list]
    row_indices: tuple[int, ...] = ()
    """Which original rows survived, in the order ``columns`` holds them.

    The table does not need this -- it reads its rows in order. A *tooltip* does: a mark knows
    the row it was drawn from, and the only way to ask this snapshot about that row is by
    index. Every other way of pairing them is a second filter, and two filters over the same
    data is exactly the thing that can silently disagree.

    Defaults to empty so the dataclass can be built without it in a test; every path through
    :func:`collect_label_data` fills it.
    """

    def __len__(self) -> int:
        return column_length(self.columns)

    def row(self, index: int) -> dict[str, object] | None:
        """The snapshot's row for original row ``index``, or ``None`` if it did not survive.

        ``None`` rather than a raise. Today no chart can ask about a row this snapshot dropped:
        the filter here is ``is_missing`` over the required channels and a chart's is
        ``numeric_or_none`` over the same ones, and those agree exactly -- ``numeric_or_none``
        returns ``None`` precisely when ``is_missing`` is true, and raises rather than dropping
        for a value it cannot read at all. So this is the answer *if the two ever drift apart*,
        and the caller falls back to naming its own channels. The alternative, answering with
        whichever row is at that position, keeps working and starts lying.
        """
        position = self._positions.get(index)
        return None if position is None else {name: values[position] for name, values in self.columns.items()}

    @cached_property
    def _positions(self) -> dict[int, int]:
        """``row_indices`` inverted, built once.

        A plain property rebuilt it on every call, and :meth:`row` is called once per mark:
        an 8,000-point scatter with ``info=`` and ``tooltip=True`` spent 1.38s against 0.05s
        without, and 64,000 points took 85s where the same lookups against a dict built once
        take 7ms. Quadratic in the number of marks is the wrong shape for a lookup that exists
        so a tooltip can be filled.

        ``cached_property`` on a frozen dataclass writes through ``__dict__`` directly, which
        ``frozen=True`` does not block -- it intercepts ``__setattr__``, and this never calls
        it. Sound because the value is derived from ``row_indices``, which is a tuple and
        cannot change underneath it.
        """
        return {row_index: position for position, row_index in enumerate(self.row_indices)}


def collect_label_data(
    data: object, info: LabelSpec | list[tuple[str, str]] | None, *, required: Sequence[str | None]
) -> LabelData | None:
    """Snapshot the ``info`` fields of ``data``, keeping rows whose channels are present.

    Args:
        data: the same shapes ``data.ingest_longform`` accepts.
        info: the spec to snapshot for, or ``None`` to skip label collection entirely. The
            raw ``[(label, "@field{format}"), ...]`` form is accepted and parsed here, so
            each chart takes both shapes without repeating the conversion.
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
        ValueError: if ``info`` is a list that doesn't parse as a spec.
    """
    if info is None:
        return None
    spec = info if isinstance(info, LabelSpec) else LabelSpec.parse(info)

    columns = extract_columns(data)

    for field in spec:
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
        spec=spec,
        columns={field.field: [columns[field.field][row_index] for row_index in kept] for field in spec},
        row_indices=tuple(kept),
    )
