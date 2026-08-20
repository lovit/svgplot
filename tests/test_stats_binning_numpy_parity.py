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
    a spike is where Freedman-Diaconis collapses and numpy 2.3.0's sqrt floor takes over.
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


def test_the_auto_strategy_uses_the_floor_numpy_2_3_added_not_the_older_formula() -> None:
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


# ---------------------------------------------------------------------------
# where the two are documented to differ, and by how much
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "offset", "spread"),
    [("ordinary", 0.0, 100.0), ("thousands", 1e3, 100.0), ("1e12", 1e12, 100.0)],
)
def test_a_magnitude_the_module_calls_ordinary_still_matches_edge_for_edge(name: str, offset: float, spread: float) -> None:
    """The module docstring puts the divergence past a magnitude/spread ratio of 1e12. Below
    it, "bit-identical" has to keep meaning bit-identical."""
    rng = random.Random(f"ordinary-{name}")
    for size in (20, 100, 500):
        values = [offset + rng.uniform(0.0, spread) for _ in range(size)]
        for strategy in _STRATEGIES:
            assert histogram_bins(values, strategy) == numpy.histogram_bin_edges(values, bins=strategy).tolist()


def test_a_column_whose_magnitude_dwarfs_its_spread_differs_by_at_most_one_bin() -> None:
    """The one place the two disagree, bounded rather than merely admitted. An epoch-nanosecond
    timestamp and an ID column near ``2**53`` are the real shapes this describes, and the cause
    is arithmetic, not the float grid: ``math.fsum`` is correctly rounded and ``numpy.std``'s
    pairwise summation is not. A regression that widened this would show up as a bin count off
    by more than one, or as a divergence appearing on ordinary data (the test above).
    """
    rng = random.Random("dwarfed")
    worst = 0
    for offset in (1e16, float(2**53)):
        for size in (20, 100, 500):
            values = [offset + rng.uniform(0.0, 100.0) for _ in range(size)]
            for strategy in _STRATEGIES:
                mine = histogram_bins(values, strategy)
                theirs = numpy.histogram_bin_edges(values, bins=strategy).tolist()
                worst = max(worst, abs(len(mine) - len(theirs)))

    assert worst <= 1


def test_an_integer_column_matches_including_numpy_s_width_floor() -> None:
    """numpy reads a list of Python ints as an integer dtype and raises a sub-unit bin width
    to 1. The parity grid above passes ``float(rng.randint(...))``, which is a float array to
    numpy, so it went straight past this -- and 18% of genuine integer lists differed."""
    rng = random.Random("integers")
    for size in (2, 10, 60):
        values = [rng.randint(-20, 20) for _ in range(size)]
        for strategy in _STRATEGIES:
            assert histogram_bins(values, strategy) == numpy.histogram_bin_edges(values, bins=strategy).tolist()
