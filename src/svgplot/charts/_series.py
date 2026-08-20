"""How a chart splits its rows into series (docs/research/10-feature-matrix.md A2).

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

from svgplot.data.semantic import extract_channels

SeriesItems = list[tuple[object | None, dict[str, list]]]


def series_items(data: object, columns: dict[str, list], hue: str | None) -> SeriesItems:
    """The ``(label, columns)`` pairs a chart should draw, one per series.

    ``columns`` is the chart's already-ingested long-form data, used as the single series when
    there is no ``hue=``. ``data`` is the caller's original, because ``extract_channels`` does
    its own ingestion and grouping.

    Ordered by ``str(label)`` rather than by the values themselves. The labels of one column
    can be a mix of types that do not compare -- ``sorted`` would raise ``TypeError`` on
    ``[1, "a"]`` -- and a chart that raises on data it could draw is worse than one whose
    ordering is lexical. The order matters beyond aesthetics: it is what pairs a series with
    its palette colour and its place in the legend.

    Raises:
        ValueError: if ``hue`` names a column whose every row is missing. Drawing nothing is
            the alternative, and a blank chart does not say which column emptied it.
    """
    if hue is None:
        return [(None, columns)]
    groups = extract_channels(data, hue=hue)
    if not groups:
        raise ValueError(f"no rows with a non-missing {hue!r} value")
    return sorted(groups.items(), key=lambda item: str(item[0]))
