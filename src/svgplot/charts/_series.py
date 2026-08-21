"""How a chart splits its rows into series (docs-research/10-feature-matrix.md A2).

Seven charts held this character for character, and it is not a formatting decision -- the
eight lines carry three policies:

- **the order series appear in**, which is the order the palette assigns colours and the
  legend lists names, so changing it recolours every chart;
- **that an empty ``hue=`` is refused**, naming the column, rather than drawn as nothing;
- **how "no ``hue=``" is spelled**, as one series keyed ``None``.

Change any of the three and seven files have to agree, and one left behind means two charts
answer the same question differently. That has already happened once: ``radarplot`` handled
the category set derived from here differently and left spokes no series could fill (#104).

Private/internal -- not re-exported from ``svgplot.charts``.
"""

from __future__ import annotations

from svgplot.data._columns import column_length, extract_columns
from svgplot.data.semantic import channel_row_indices

SeriesItems = list[tuple[object | None, dict[str, list]]]
SeriesRows = list[tuple[object | None, dict[str, list], list[int]]]


def series_items(data: object, columns: dict[str, list], hue: str | None) -> SeriesItems:
    """The ``(label, columns)`` pairs a chart should draw, one per series.

    ``columns`` is the chart's already-ingested long-form data and is returned as the single
    series when there is no ``hue=``. ``data`` is the caller's original because the ``hue=``
    branch re-ingests from it and does not consult ``columns`` at all -- see
    :func:`series_rows`, where the split and the row numbers both come from ``data``. The two
    are the same content today (``ingest_longform`` drops no rows and filters no columns), and
    every caller in this package passes ``longform.columns``; a caller that passed something
    narrower would get one answer without ``hue=`` and another with it.

    Ordered by ``str(label)`` rather than by the values themselves. The labels of one column
    can be a mix of types that do not compare -- ``sorted`` would raise ``TypeError`` on
    ``[1, "a"]`` -- and a chart that raises on data it could draw is worse than one whose
    ordering is lexical. The order matters beyond aesthetics: it is what pairs a series with
    its palette colour and its place in the legend.

    Raises:
        ValueError: if ``hue`` names a column whose every row is missing. Drawing nothing is
            the alternative, and a blank chart does not say which column emptied it.
    """
    return [(label, group) for label, group, _rows in series_rows(data, columns, hue)]


def series_rows(data: object, columns: dict[str, list], hue: str | None) -> SeriesRows:
    """:func:`series_items` plus, per series, the **original row indices** it was built from.

    ``series_items`` is defined in terms of this rather than beside it, so the two cannot
    disagree about order or about which rows a series holds. That matters more than the
    duplication it saves: the order is what pairs a series with its palette colour, and a
    second sort would be a second place for that to change.

    A chart needs the indices to trace a mark back to the row it came from -- to fill a tooltip
    from the same ``info=`` spec the footnote table uses. Without ``hue=`` the indices are just
    ``range``, because ``ingest_longform`` drops no rows; with it they come from
    :func:`~svgplot.data.semantic.channel_row_indices`, which is the same filter
    ``extract_channels`` is built from.

    Raises:
        ValueError: if ``hue`` names a column whose every row is missing.
    """
    if hue is None:
        return [(None, columns, list(range(column_length(columns))))]
    indices = channel_row_indices(data, hue=hue)
    if not indices:
        raise ValueError(f"no rows with a non-missing {hue!r} value")
    original = extract_columns(data)
    return [
        (label, {name: [values[index] for index in rows] for name, values in original.items()}, rows)
        for label, rows in sorted(indices.items(), key=lambda item: str(item[0]))
    ]
