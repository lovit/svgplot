"""Automatic histogram binning (docs/research/10-feature-matrix.md A7).

The strategies are numpy's, reimplemented here rather than delegated. Delegating was one
import in one line, and it made ``numpy`` a required dependency of a package whose job is to
put an SVG in a markdown file -- every other statistics module here is pure stdlib, and
``stats/kde.py`` records the measurement behind that choice.

Reimplementing also settles something delegating could not. numpy's ``auto`` changed between
versions: up to 2.2 it was ``min(fd, sturges)`` and from **2.3.0** it is
``min(max(fd, sqrt/2), sturges)``, a heuristic added to stop a spike in the data producing
thousands of bins. A package whose identity is "same input, same SVG" cannot have its bin
count depend on which numpy the reader happens to have installed.

The edges these produce are **bit-identical to numpy** over ordinary data: the parity grid is
nine shapes (gaussian, constant, spike, integral, bimodal, skewed, tiny, huge, negative) x
nine sizes x twelve bin specs (the seven strategies plus five explicit counts) = 972 calls,
comparing 52,000-odd individual edges, with zero mismatches.

Three deliberate divergences:

- A strategy that asks for more than :data:`_MAX_BINS` is refused. numpy builds the array;
  building the same list in Python is eight times the memory and slow enough to look like a
  hang, and no chart can show a million bars either way.
- ``stone`` is not implemented. numpy accepts it; a call that used it now gets a ``ValueError``
  naming the seven that remain.
- A column whose **magnitude dwarfs its spread** can come back with a bin or two more or
  fewer, and only through ``scott`` and ``doane``. Both go through a standard deviation, and
  at those magnitudes ``value - mean`` cancels away all but the last few digits: what is left
  is summed exactly here and pairwise by numpy, and the two round differently. Measured as the
  share of (shape, size, strategy) comparisons whose bin count differs, over uniform, spiked
  and gaussian columns: **0.00% at 1e12 and below, under 0.05% through 1e14, 0.3% at 1e15 and
  1.8% at 1e16**, worst difference two bins.

  Rely on those bounds rather than on more digits. Two independent samplings of ~4,400
  comparisons per magnitude put the first mismatch at different places -- one at 1e13, one at
  1e14 -- and read 0.24% against 0.27% at 1e15. The rate is a property of which columns were
  drawn; what is stable across both is the ceiling, the two strategies, and the two-bin worst
  case.

  Two earlier drafts of this paragraph were wrong in the other direction. The first blamed
  subnormals and near-float-maximum values, which measure 0.00%. The second blamed
  ``math.fsum`` against numpy's pairwise summation -- but CPython's own ``sum`` is compensated
  too, and no input was found where the two disagree. The real cause of that draft's numbers
  was the **quantile interpolation**: the weighted form lost everything two large neighbouring
  values had in common, so a spiked column at 1e15 measured an inter-quartile range of zero
  where numpy measured 0.25, and ``fd`` drew one bar where numpy drew 431. That is fixed in
  ``stats/quantile.py`` rather than documented, which is why the numbers above are so much
  smaller than the ones they replace.

``tests/test_stats_binning_numpy_parity.py`` covers the ordinary range and is skipped when
numpy is absent.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from itertools import pairwise

from svgplot.stats.quantile import quantile

_MAX_BINS = 10_000
"""Sane upper bound on an explicit int ``bins`` count -- without this, e.g.
``bins=10**8`` returns ~800MB of edges from a single call, matching the spirit
of ``_MAX_PRECISION`` in ``stats.interpolate``."""

_STRATEGIES = ("auto", "fd", "doane", "scott", "rice", "sturges", "sqrt")


def _saturating(compute: Callable[[], float]) -> float:
    """``compute()``, giving ``inf`` where the float range runs out.

    Python raises ``OverflowError`` from ``fsum`` and from ``**``; float64 arithmetic
    saturates to infinity instead. A column around 1e308 therefore turned a working
    ``scott``/``doane`` call into an exception the documented contract does not mention.
    Saturating keeps the two agreeing: an infinite width means one bin, which is the honest
    answer for data that wide.
    """
    try:
        return compute()
    except OverflowError:
        return math.inf


def _mean(values: list[float]) -> float:
    """The arithmetic mean, saturating to infinity rather than raising.

    One function because there was one place that did not use it: ``doane`` recomputed the
    mean with a bare ``math.fsum``, so a column around ``1e307`` came back as an
    ``OverflowError`` from a function whose ``Raises:`` documents only ``ValueError`` --
    exactly the contract :func:`_saturating` exists to keep, applied everywhere except the
    one caller that needed it.
    """
    total = _saturating(lambda: math.fsum(values))
    return total / len(values) if math.isfinite(total) else math.inf


def _population_stdev(values: list[float]) -> float:
    """Standard deviation with ``ddof=0``, which is what ``numpy.std`` defaults to."""
    mean = _mean(values)
    if not math.isfinite(mean):
        return math.inf
    total = _saturating(lambda: math.fsum(_saturating(lambda v=value: (v - mean) ** 2) for value in values))
    return math.sqrt(total / len(values)) if math.isfinite(total) else math.inf


def _bin_width(strategy: str, values: list[float], span: float) -> float:
    """The bin width a strategy asks for, or ``0.0`` for "one bin is enough".

    ``span`` is the data's own peak-to-peak, not the widened outer edges. The distinction only
    shows on constant data, where numpy widens the edges to +/-0.5 for the *linspace* but
    still hands the selectors a span of zero -- so they return zero and the chart gets one bin
    rather than five.
    """
    count = len(values)
    sturges = span / (math.log2(count) + 1.0)
    if strategy == "sturges":
        return sturges
    root = span / math.sqrt(count)
    if strategy == "sqrt":
        return root
    if strategy == "rice":
        return span / (2.0 * count ** (1 / 3))
    if strategy == "scott":
        return (24.0 * math.sqrt(math.pi) / count) ** (1 / 3) * _population_stdev(values)
    if strategy in ("fd", "auto"):
        ordered = sorted(values)
        spread = quantile(ordered, 0.75) - quantile(ordered, 0.25)
        freedman = 2.0 * spread * count ** (-1 / 3)
        if strategy == "fd":
            return freedman
        # Freedman-Diaconis is the most robust of these until the data has a spike, where its
        # inter-quartile spread collapses and the bin count runs to thousands. Half the sqrt
        # estimate is the floor numpy 2.3.0 added to stop that.
        return min(max(freedman, root / 2.0), sturges)
    # doane, the only one that looks at shape rather than spread.
    if count <= 2:
        return 0.0
    deviation = _population_stdev(values)
    if deviation == 0.0:
        return 0.0
    mean = _mean(values)
    if not math.isfinite(mean):
        return 0.0
    skew = (
        _saturating(lambda: math.fsum(_saturating(lambda v=value: ((v - mean) / deviation) ** 3) for value in values)) / count
    )
    correction = math.sqrt(6.0 * (count - 2) / ((count + 1.0) * (count + 3)))
    return span / (1.0 + math.log2(count) + math.log2(1.0 + abs(skew) / correction))


def _even_edges(low: float, high: float, count: int) -> list[float]:
    """``count + 1`` edges from ``low`` to ``high``, the way ``numpy.linspace`` lays them out.

    Accumulating ``low + index * step`` rather than adding ``step`` repeatedly, because the
    repeated addition drifts; and forcing the last edge to ``high`` rather than computing it,
    because ``low + count * step`` is not exactly ``high`` in binary floating point and a
    histogram whose last edge falls short of its own maximum drops that value.
    """
    if count < 1:
        # An infinite bin width -- a strategy handed data wide enough to saturate the float
        # range -- divides the span into nothing. ``linspace(low, high, 0 + 1)`` is one edge,
        # which is what numpy returns and is as much as such data supports.
        return [low]
    if count > _MAX_BINS:
        # The cap belongs here and not only on an explicit ``bins=``, because a *strategy* can
        # ask for billions on spiked data and numpy does not stop it either -- it just fails
        # inside C. Building the same list in Python is eight times the memory and slow enough
        # to look like a hang, so this is a deliberate divergence: numpy would eventually
        # produce (or die making) the array, and this says which number was too large.
        raise ValueError(f"bins must be at most {_MAX_BINS}, got {count} from the chosen strategy")
    step = (high - low) / count
    edges = [low + index * step for index in range(count + 1)]
    edges[-1] = high
    if any(earlier >= later for earlier, later in pairwise(edges)):
        # The divisions asked for are finer than the float grid between ``low`` and ``high``,
        # so two edges land on the same number and the bin between them can hold nothing. It
        # happens at ordinary magnitudes, not only contrived ones: past 2**53 the half-unit
        # widening a single distinct value gets is a no-op, so one row of an epoch-nanosecond
        # or ID column produces a chart with no bars at all rather than an error.
        raise ValueError(f"too many bins for the data range: cannot make {count} bins between {low!r} and {high!r}")
    return edges


def histogram_bins(values: list[float], bins: str | int = "auto") -> list[float]:
    """Histogram bin edges for ``values``.

    ``bins`` is a count or one of :data:`_STRATEGIES`.

    Raises:
        ValueError: if ``values`` is empty or holds a non-numeric or non-finite value, if the
            span isn't finite (individually finite values, e.g. ``-1e308`` and ``1e308``, can
            still overflow), if ``bins`` isn't a ``str``/``int``, if an int ``bins`` exceeds
            :data:`_MAX_BINS` or is below 1, if a str ``bins`` chooses more than
            :data:`_MAX_BINS` (numpy has no such limit -- see :func:`_even_edges`), if a str
            ``bins`` isn't a known strategy, or if the requested division is finer than the
            float grid between the edges allows.
    """
    if not values:
        raise ValueError("values must not be empty")
    if not isinstance(bins, str | int) or isinstance(bins, bool):
        raise ValueError(f"bins must be a string or int, got {bins!r}")
    if isinstance(bins, int) and not 1 <= bins <= _MAX_BINS:
        # Both ends. The upper one keeps ``bins=10**8`` from returning ~800MB of edges; the
        # lower one keeps ``bins=0`` from being read as "one bin", which is a different chart
        # from the one the caller asked for and no error at all.
        raise ValueError(f"bins must be between 1 and {_MAX_BINS}, got {bins}")
    if isinstance(bins, str) and bins not in _STRATEGIES:
        raise ValueError(f"bins must be an int or one of {', '.join(sorted(_STRATEGIES))}, got {bins!r}")
    for value in values:
        try:
            finite = math.isfinite(value)
        except TypeError as error:
            raise ValueError(f"values must be numbers, got {value!r}") from error
        except OverflowError as error:
            # An int past the float range. ``isfinite`` refuses to convert it, and this
            # function documents ``ValueError`` and nothing else -- the same contract
            # ``_saturating`` keeps for the arithmetic further down.
            raise ValueError(f"cannot bin a value too large to be a float: {value!r}") from error
        if not finite:
            raise ValueError(f"cannot bin a non-finite value: {value!r}")
    low, high = float(min(values)), float(max(values))
    # The span is measured on the *same floats* the edges are built from. Measured on the raw
    # values it can disagree with them: two Python ints either side of ``2**53`` differ by
    # exactly 1 as integers and collapse to one float, which left the selectors a real span
    # to divide and the edges nothing to divide it into -- ``ceil(0 / width)`` bins, and
    # ``_even_edges`` answering with a single edge. That is a chart with **no bars**, which
    # this module's own degenerate-edge check exists to refuse rather than draw; numpy raises
    # there and so, now, does this.
    span = high - low
    if not math.isfinite(span):
        raise ValueError(f"values span (max - min = {span!r}) must be finite")
    if low == high:
        # A single distinct value has no width to divide. numpy widens by half a unit either
        # side so the bar has somewhere to be drawn.
        low, high = low - 0.5, high + 0.5
    if isinstance(bins, int):
        return _even_edges(low, high, bins)
    width = _bin_width(bins, values, span)
    if width and _all_integers(values):
        # numpy infers a dtype, and for an integer one it raises a sub-unit width to 1 --
        # a histogram of counts has nothing to say between 0 and 1. A list of Python ints is
        # exactly what ``np.histogram_bin_edges`` sees as ``int64``, so a caller who passed
        # one and now passes it here has to get the same edges: without this, ``[0,0,1,0,2,
        # 0,1,0,0,1]`` with ``fd`` came back with three bins where numpy gives two, and 18%
        # of integer-list inputs differed.
        width = max(width, 1.0)
    return _even_edges(low, high, int(math.ceil((high - low) / width)) if width else 1)


def _all_integers(values: list[float]) -> bool:
    """Whether every value is a Python ``int`` -- the shape numpy reads as an integer dtype.

    The *type*, not the value: ``[1.0, 2.0]`` is a float array to numpy and gets no width
    floor, so testing ``value == int(value)`` here would apply the floor where numpy does not.

    ``bool`` counts, which is the one place this package's usual "a bool is not a number"
    rule does not apply — numpy casts a boolean array to ``uint8``, which
    ``np.issubdtype(..., np.integer)`` calls an integer, so the floor is applied there.
    Excluding it here made 71% of boolean columns disagree.
    """
    return all(isinstance(value, int) for value in values)
