"""Automatic histogram binning, delegated to numpy (docs/research/10-feature-matrix.md A7)."""

from __future__ import annotations

import math

import numpy as np

_MAX_BINS = 10_000
"""Sane upper bound on an explicit int ``bins`` count — without this, e.g.
``bins=10**8`` returns ~800MB of edges from a single call, matching the spirit
of ``_MAX_PRECISION`` in ``stats.interpolate``."""


def histogram_bins(values: list[float], bins: str | int = "auto") -> list[float]:
    """Compute histogram bin edges for the given values, delegating to
    :func:`numpy.histogram_bin_edges`.

    Raises:
        ValueError: if ``values`` is empty or contains a non-numeric/non-finite value,
            if ``values``' span (``max(values) - min(values)``) isn't finite (individually
            finite values, e.g. ``-1e308`` and ``1e308``, can still overflow when numpy
            computes the range internally — surfacing as a confusing internal numpy error
            if not caught here first), if ``bins`` isn't a ``str``/``int`` or an int
            ``bins`` exceeds :data:`_MAX_BINS`, or if ``bins`` isn't a value numpy accepts
            (surfaces numpy's own error message in that case).
    """
    if not values:
        raise ValueError("values must not be empty")
    if not isinstance(bins, str | int) or isinstance(bins, bool):
        raise ValueError(f"bins must be a string or int, got {bins!r}")
    if isinstance(bins, int) and bins > _MAX_BINS:
        raise ValueError(f"bins must be at most {_MAX_BINS}, got {bins}")
    for value in values:
        try:
            finite = math.isfinite(value)
        except TypeError as error:
            raise ValueError(f"values must be numbers, got {value!r}") from error
        if not finite:
            raise ValueError(f"cannot bin a non-finite value: {value!r}")
    span = max(values) - min(values)
    if not math.isfinite(span):
        raise ValueError(f"values span (max - min = {span!r}) must be finite")
    edges = np.histogram_bin_edges(values, bins=bins)
    return edges.tolist()
