"""Sequential colormaps (needed for heatmap-family charts, docs/research/10-feature-matrix.md A5)."""

from __future__ import annotations


def sequential(name: str, n: int) -> list[str]:
    """Return n colors sampled from the named sequential colormap."""
    raise NotImplementedError
