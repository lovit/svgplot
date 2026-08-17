"""Semantic channel extraction: hue=/col=/row= column-to-visual-channel mapping.

size=/style= are 2차 additions planned for this same file
(docs/research/10-feature-matrix.md A2).
"""

from __future__ import annotations


def extract_channels(
    data: object,
    hue: str | None = None,
    col: str | None = None,
    row: str | None = None,
) -> object:
    """Split a long-form DataFrame into groups keyed by the given semantic channels."""
    raise NotImplementedError
