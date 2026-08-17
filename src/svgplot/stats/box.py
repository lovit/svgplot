"""Box-plot statistics: quartiles, whiskers, outliers (pygal's 5 box_mode precedent, docs/research/01-pygal.md A7)."""

from __future__ import annotations

MODES = ("extremes", "1.5IQR", "tukey", "stdev", "pstdev")


def box_stats(values: list[float], mode: str = "1.5IQR") -> object:
    """Compute median/quartiles/whiskers/outliers for a box plot."""
    raise NotImplementedError
