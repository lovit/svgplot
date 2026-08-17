"""Automatic histogram binning, delegated to numpy (docs/research/10-feature-matrix.md A7)."""

from __future__ import annotations

import math

import numpy as np


def histogram_bins(values: list[float], bins: str | int = "auto") -> list[float]:
    """Compute histogram bin edges for the given values, delegating to
    :func:`numpy.histogram_bin_edges`.

    Raises:
        ValueError: if ``values`` is empty or contains a non-finite value, or if ``bins``
            isn't a type numpy accepts (surfaces numpy's own error message in that case).
    """
    if not values:
        raise ValueError("values must not be empty")
    for value in values:
        if not math.isfinite(value):
            raise ValueError(f"cannot bin a non-finite value: {value!r}")
    edges = np.histogram_bin_edges(values, bins=bins)
    return edges.tolist()
