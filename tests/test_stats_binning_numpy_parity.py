"""``stats.binning`` against the numpy it replaced.

The strategies here are numpy's, reimplemented so that ``svgplot`` has no runtime dependency.
That only holds while the two agree, and "agree" has to mean edge for edge -- a bin boundary
that differs in the last place moves a value from one bar to the next.

Skipped when numpy is absent, which is the ordinary case now: it is in the ``numpy-parity``
extra and nothing in ``src/`` imports it. That the *implementation* runs without numpy is
checked by running it without numpy, not from here -- see the PR for #116.
"""

from __future__ import annotations

import math
import random

import pytest

from svgplot.stats.binning import _MAX_BINS as MAX_BINS, histogram_bins

numpy = pytest.importorskip("numpy", reason="install the numpy-parity extra to check this")

_STRATEGIES = ["auto", "fd", "doane", "scott", "rice", "sturges", "sqrt"]
_COUNTS = [1, 2, 3, 17, 257]


def _dataset(kind: str, size: int, rng: random.Random) -> list[float]:
    """One of the shapes the strategies actually disagree on.

    Constant and spiked are the two that matter most: a constant column is where the selectors
    are handed a zero span and numpy widens the *edges* without widening what it measures, and
    a spike is where Freedman-Diaconis collapses and numpy 2.5's sqrt floor takes over.
    """
    if kind == "constant":
        return [3.5] * size
    if kind == "spike":
        return [rng.uniform(0.0, 1.0) for _ in range(size - 1)] + [1000.0] if size > 1 else [1.0]
    if kind == "integral":
        return [float(rng.randint(0, 20)) for _ in range(size)]
    if kind == "bimodal":
        return [rng.gauss(0.0, 1.0) if index % 2 else rng.gauss(50.0, 1.0) for index in range(size)]
    if kind == "skewed":
        return [rng.expovariate(1.0) for _ in range(size)]
    if kind == "tiny":
        return [rng.uniform(0.0, 1e-12) for _ in range(size)]
    if kind == "huge":
        return [rng.uniform(0.0, 1e12) for _ in range(size)]
    if kind == "negative":
        return [rng.uniform(-50.0, 50.0) for _ in range(size)]
    return [rng.gauss(0.0, 1.0) for _ in range(size)]


_SHAPES = ["gaussian", "constant", "spike", "integral", "bimodal", "skewed", "tiny", "huge", "negative"]
_SIZES = [1, 2, 3, 5, 10, 37, 100, 499, 1000]


@pytest.mark.parametrize("bins", _STRATEGIES + _COUNTS, ids=[str(b) for b in _STRATEGIES + _COUNTS])
@pytest.mark.parametrize("shape", _SHAPES)
def test_the_edges_are_the_ones_numpy_would_have_returned(shape: str, bins: object) -> None:
    """Every edge, not the count and not an approximation. A boundary off by one float moves
    a value between bars, and that is the whole content of a histogram."""
    rng = random.Random(f"{shape}-{bins}")
    for size in _SIZES:
        values = _dataset(shape, size, rng)
        try:
            expected = numpy.histogram_bin_edges(values, bins=bins).tolist()  # type: ignore[arg-type]
        except ValueError:
            # numpy refuses degenerate edges ("Too many bins for data range"); so do we, and
            # matching the refusal matters as much as matching the numbers.
            with pytest.raises(ValueError):
                histogram_bins(values, bins)  # type: ignore[arg-type]
            continue
        if len(expected) - 1 > MAX_BINS:
            # The one deliberate divergence: a strategy that asks for more bins than a chart
            # can show is refused here and built by numpy. See ``_even_edges``.
            with pytest.raises(ValueError, match="at most"):
                histogram_bins(values, bins)  # type: ignore[arg-type]
            continue

        assert histogram_bins(values, bins) == expected, f"{shape} n={size} bins={bins}"  # type: ignore[arg-type]


def test_the_auto_strategy_uses_the_floor_numpy_2_5_added_not_the_older_formula() -> None:
    """``auto`` was ``min(fd, sturges)`` and became ``min(max(fd, sqrt/2), sturges)``. The
    difference only shows on a spike, where the older formula follows the collapsed
    inter-quartile spread into thousands of bins -- which is why pinning the behaviour here
    rather than delegating is what makes the bin count independent of the installed numpy."""
    values = [index / 500.0 for index in range(500)] + [1000.0]
    older = 2.0 * (numpy.percentile(values, 75) - numpy.percentile(values, 25)) * len(values) ** (-1 / 3)
    span = max(values) - min(values)

    assert older > 0.0
    assert math.ceil(span / older) > 5000, "this fixture must be one where the old formula explodes"
    assert len(histogram_bins(values, "auto")) - 1 < 100
    assert histogram_bins(values, "auto") == numpy.histogram_bin_edges(values, bins="auto").tolist()
