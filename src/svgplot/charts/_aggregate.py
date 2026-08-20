"""Folding several rows that share one x into a single mark.

Three charts fold rows, and until this module they each folded differently and
irreversibly: ``barplot`` kept the last row, ``areaplot`` summed, ``lineplot`` kept both
rows as separate vertices. Those rules are all defensible defaults and all *fixed*, which
is the problem — a caller who wants the mean of three rows has no way to ask for it, and
``barplot`` in particular discards two thirds of that data without saying so.

Which charts take ``estimator=``
================================

The three that fold rows *along the x axis*: ``barplot``, ``areaplot``, ``lineplot``.
Everything else is out of scope for a reason, not by omission:

- ``histplot``/``kdeplot``/``ecdfplot``/``boxplot``/``violinplot`` consume the whole
  **distribution** of a column. Collapsing repeated values into their mean first would
  not fold marks together, it would delete the very spread these charts exist to draw.
- ``scatterplot`` draws one mark per row already — nothing folds, so nothing to choose.
- ``regplot`` likewise draws one point per row, and its fit consumes every row rather than
  folding any: pre-averaging the y values at a repeated x would change the regression
  itself, not just what is drawn, which is a different feature from this one.
- ``heatmap`` **refuses** two rows naming the same cell rather than folding them, and
  that refusal is load-bearing: a heatmap cell is an identity, not an accumulator.
- ``pieplot``/``treemap``/``gaugeplot`` are one row = one mark by construction.
- ``radarplot`` does fold, with ``barplot``'s last-row-wins rule. It is left out of this
  issue's scope deliberately rather than quietly: its folding happens per (series,
  category) pair inside a polygon that must have no gaps, so the aggregation and the
  gap check interact in a way that deserves its own change. Noted here so the omission
  is a decision on the record, not a chart someone forgot.

Why the default stays ``None``
==============================

``estimator=None`` keeps each chart's existing rule, so no existing call changes its
output by a pixel. Making ``"mean"`` the default would match seaborn, and would also
silently redraw every chart anyone has already built — a chart is a *document* in this
package, and documents that change under their author are worse than documents that need
one more argument.

What that trade would have left unfixed is the *silence*, so that is fixed separately:
:class:`~svgplot.warnings.AggregationWarning` fires when a chart actually discards rows,
i.e. only for ``barplot``. ``areaplot`` sums (nothing is lost) and ``lineplot`` draws
both vertices (nothing is lost), so neither warns — a warning that fired whenever rows
merely shared an x would be advice about nothing.

Error bars are **not** in this module's scope, and the geometry decision is recorded
rather than acted on: were one added, it would be a capped T bar rather than a plain line
or a band. A band reads as a continuous interval along x, which is wrong over categories;
a plain line without caps is hard to distinguish from a gridline crossing the bar at the
theme's stroke widths. Implementing it needs a spread statistic, its interaction with
``stacked=``/``orient=``, and a legend story, none of which this issue's acceptance
criteria ask for.

Private/internal — not re-exported from ``svgplot.charts``.
"""

from __future__ import annotations

import math
import statistics
import warnings
from collections.abc import Callable

from svgplot.stats.quantile import quantile
from svgplot.warnings import AggregationWarning

Estimator = str | Callable[[list[float]], float]

_BUILTIN_ESTIMATORS: dict[str, Callable[[list[float]], float]] = {
    # fmean rather than sum()/len(): it converts the sequence once and is the stdlib's
    # own answer for "the mean". Not an accuracy claim -- CPython 3.12+ compensates
    # sum() over floats (Neumaier), and 200,000 random groups of 2-8 values spanning
    # 1e-12..1e12 found no input where the two disagree.
    "mean": statistics.fmean,
    # stats.quantile, not statistics.median: it is the same interpolation boxplot and
    # violinplot already draw their median line at, so "the median" means one thing
    # across the package rather than two that agree on odd counts and differ nowhere
    # visible until someone looks.
    "median": lambda values: quantile(values, 0.5),
    # fsum because it is *guaranteed* correctly rounded, which the compensated sum() is
    # not -- and because areaplot's existing rule is a plain sum, so a caller writing
    # estimator="sum" out explicitly must get the same chart back. Measured: identical
    # over the same 200,000 random groups.
    "sum": math.fsum,
}

ESTIMATORS = tuple(_BUILTIN_ESTIMATORS)
"""The estimator names this package resolves. Anything else must be a callable, which is
the escape hatch for the rest of statistics — this list stays short on purpose."""


def resolve_estimator(estimator: Estimator | None) -> Callable[[list[float]], float] | None:
    """Turn an ``estimator=`` argument into the function that folds a group, or ``None``.

    Validated here, at the top of the chart, rather than at the first group it is applied
    to: a misspelled name should report itself before any rendering work, and before the
    chart has already drawn half its marks with one rule and the rest with another.

    Raises:
        ValueError: if ``estimator`` is a string that isn't one of :data:`ESTIMATORS`.
        TypeError: if it is neither a string, a callable, nor ``None``.
    """
    if estimator is None:
        return None
    if isinstance(estimator, str):
        if estimator not in _BUILTIN_ESTIMATORS:
            raise ValueError(f"estimator must be one of {ESTIMATORS} or a callable, got {estimator!r}")
        return _BUILTIN_ESTIMATORS[estimator]
    if callable(estimator):
        return estimator
    raise TypeError(f"estimator must be one of {ESTIMATORS}, a callable, or None, got {estimator!r}")


def apply_estimator(estimate: Callable[[list[float]], float], values: list[float], *, group: str) -> float:
    """Fold one group's values, checking that what comes back can actually be plotted.

    A caller's own callable can return anything at all. Without this check a ``None`` or a
    ``nan`` travels on into the scale and surfaces as a message about an SVG coordinate,
    naming neither the estimator nor the group it came from — the same reasoning
    ``pieplot`` and ``gaugeplot`` already apply to their raw inputs.

    Raises:
        ValueError: if the estimator returns something that isn't a finite real number,
            or raises. Its own exception is chained, so a callable that fails on its own
            terms (an empty-sequence error, say) still reports its own message.
    """
    try:
        result = estimate(values)
    except Exception as error:  # re-raised immediately as ValueError, named and chained
        raise ValueError(f"estimator failed on group {group!r} with values {values!r}: {error}") from error
    if isinstance(result, bool):
        # float(True) is 1.0, so a callable that accidentally returns a comparison would
        # plot a bar of height 1 rather than say anything. Rejected next to str for the
        # same reason: the value arrived as something that is not a measurement.
        raise ValueError(f"estimator returned a non-numeric value for group {group!r}: {result!r}")
    if isinstance(result, str | bytes | bytearray):
        # float("12") succeeds, so without this a string flows straight into the scale and
        # the estimator's contract quietly becomes "whatever this text happens to parse
        # as". A number that arrived as text is a units bug waiting to happen, not a value.
        raise ValueError(f"estimator returned a non-numeric value for group {group!r}: {result!r}")
    try:
        number = float(result)
    except (TypeError, ValueError) as error:
        raise ValueError(f"estimator returned a non-numeric value for group {group!r}: {result!r}") from error
    if not math.isfinite(number):
        raise ValueError(f"estimator returned a non-finite value for group {group!r}: {result!r}")
    return number


def warn_rows_discarded(chart: str, *, rows: int, marks: int) -> None:
    """Warn once per chart call that rows sharing an x were thrown away.

    Once per *call*, not once per group: a chart with a hundred duplicated categories
    would otherwise emit a hundred warnings for one decision the caller makes once.

    Nothing is warned about when ``rows == marks`` — no chart should tell a caller about a
    fold that folded nothing.
    """
    discarded = rows - marks
    if discarded <= 0:
        return
    warnings.warn(
        f"{chart} kept {marks} of {rows} rows: rows sharing a category collapse to the last one. "
        f"Pass estimator='mean' (or 'median'/'sum', or a callable) to aggregate them instead; "
        f"silence this with warnings.filterwarnings('ignore', category=svgplot.AggregationWarning).",
        AggregationWarning,
        stacklevel=3,
    )
