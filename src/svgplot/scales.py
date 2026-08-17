"""Data-domain to pixel-space scales.

Linear, categorical, and time scales plus "nice" tick generation. Datetime
x-values are handled here as a scale option rather than a separate chart
type (see docs/research/10-feature-matrix.md, "시간축 선"). Kept as a single
file until a concrete need for additional scale types (e.g. log) appears.
"""

from __future__ import annotations


class LinearScale:
    """Maps a numeric data domain to a pixel range."""

    def __init__(self, domain: tuple[float, float], range_: tuple[float, float]) -> None:
        raise NotImplementedError


class CategoricalScale:
    """Maps discrete category values to evenly spaced pixel bands."""

    def __init__(self, categories: list[str], range_: tuple[float, float]) -> None:
        raise NotImplementedError


class TimeScale:
    """Maps a datetime domain to a pixel range."""

    def __init__(self, domain: tuple[object, object], range_: tuple[float, float]) -> None:
        raise NotImplementedError


def make_ticks(scale: object, count: int = 5) -> list[object]:
    """Generate "nice" tick positions for the given scale."""
    raise NotImplementedError
