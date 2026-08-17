"""Composition — the object every ``svgplot.layout`` function (row/column/grid) returns.

Holds multiple Chart objects arranged spatially but exposes the same
``.save()``/``.to_string()`` interface as a single Chart, so a composed
"도판" can be saved exactly like any other chart. See
docs/research/16-layout-vocabulary.md.
"""

from __future__ import annotations

from svgplot.chart.base import Chart


class Composition:
    """A spatial arrangement of one or more Chart objects."""

    def __init__(self, charts: list[Chart]) -> None:
        raise NotImplementedError

    def to_string(self, *, pretty: bool = True) -> str:
        raise NotImplementedError

    def save(self, path: str) -> None:
        raise NotImplementedError

    def _repr_svg_(self) -> str:
        raise NotImplementedError
