"""Automatic histogram binning, delegated to numpy (docs/research/10-feature-matrix.md A7)."""

from __future__ import annotations

import math

import numpy as np

MAX_BINS = 10_000
"""Sane upper bound on an explicit int ``bins`` count — without this, e.g.
``bins=10**8`` returns ~800MB of edges from a single call, matching the spirit
of ``_MAX_PRECISION`` in ``stats.interpolate``."""


def histogram_bins(
    values: list[float], bins: str | int = "auto", *, bin_range: tuple[float, float] | None = None
) -> list[float]:
    """Compute histogram bin edges for the given values, delegating to
    :func:`numpy.histogram_bin_edges`.

    ``bin_range`` bins over a stated range instead of over ``values``' own extremes. Two charts
    binned separately land their boundaries in different places, so their bars come out
    different widths and a "count of 3" means a different amount of data in each -- which
    is exactly the comparison a shared axis promises and would otherwise not deliver. It is
    the same rule ``histplot`` already applies to ``hue=`` groups, extended to callers that
    know a wider range than the values in hand.

    Raises:
        ValueError: if ``values`` is empty or contains a non-numeric/non-finite value,
            if ``values``' span (``max(values) - min(values)``) isn't finite (individually
            finite values, e.g. ``-1e308`` and ``1e308``, can still overflow when numpy
            computes the range internally — surfacing as a confusing internal numpy error
            if not caught here first), if ``bins`` isn't a ``str``/``int`` or an int
            ``bins`` exceeds :data:`MAX_BINS`, or if ``bins`` isn't a value numpy accepts
            (surfaces numpy's own error message in that case).
    """
    if not values:
        raise ValueError("values must not be empty")
    if not isinstance(bins, str | int) or isinstance(bins, bool):
        raise ValueError(f"bins must be a string or int, got {bins!r}")
    if isinstance(bins, int) and bins > MAX_BINS:
        raise ValueError(f"bins must be at most {MAX_BINS}, got {bins}")
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
    if bin_range is not None:
        low, high = bin_range
        if not (math.isfinite(low) and math.isfinite(high)) or low >= high:
            raise ValueError(f"bin_range must be an increasing pair of finite numbers, got {bin_range!r}")
    edges = np.histogram_bin_edges(values, bins=bins, range=bin_range)
    return edges.tolist()
