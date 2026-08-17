"""Automatic histogram binning, delegated to numpy (docs/research/10-feature-matrix.md A7)."""

from __future__ import annotations


def histogram_bins(values: list[float], bins: str | int = "auto") -> object:
    """Compute histogram bin edges and counts for the given values."""
    raise NotImplementedError
