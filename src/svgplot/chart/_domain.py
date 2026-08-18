"""What a chart's axes actually spanned, so several charts can be made to agree.

``layout`` places charts; making their axes line up is a *data*-level question
(docs/research/16-layout-vocabulary.md, 설계 원칙 3, which names a ``shared_x=``-style
parameter as the intended mechanism). This module is that mechanism's data half: a chart
records what it used, callers union those records, and the charts are asked to redraw
against the union.

Recorded rather than predicted
==============================

A caller could try to compute the union straight from the data -- ``min``/``max`` of the
plotted columns -- and for ``lineplot`` or ``scatterplot`` that would work. It does not
generalise: ``histplot``'s y domain is a bin **count**, ``kdeplot``'s is a **density**, and
``ecdfplot``'s depends on ``stat=``. None of those exist in the input columns, so nothing
outside the chart can derive them. Asking the chart what it used is the only answer that
covers every chart with one rule.

The consequence is that sharing costs a second render. That is the price of the general
answer, and it is paid only when a caller asks for shared axes.

Categorical axes union differently
==================================

Two panels showing categories ``[a, b]`` and ``[b, c]`` share ``[a, b, c]`` -- a union, not
a min/max. Order is first-seen across panels in panel order, which keeps a reader's own
ordering rather than imposing alphabetical.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Domains:
    """The domains one chart drew against.

    ``None`` on a field means "this chart has no such axis" -- a pie has neither, a
    ``barplot`` has ``categories`` and ``y`` but no numeric ``x``. It does not mean
    "unknown": a chart that draws an axis always records it.
    """

    x: tuple[float, float] | None = None
    y: tuple[float, float] | None = None
    categories: tuple[str, ...] | None = None

    def is_empty(self) -> bool:
        return self.x is None and self.y is None and self.categories is None


def union(domains: list[Domains]) -> Domains:
    """The smallest domains containing all of ``domains``.

    Panels that record nothing on an axis are skipped rather than treated as ``(0, 0)`` --
    an empty panel must not drag a shared axis down to zero.

    Raises:
        ValueError: if ``domains`` is empty. A union of nothing has no defensible answer,
            and returning an all-``None`` ``Domains`` would look like "no axes" to the
            caller, which is a different thing.
    """
    if not domains:
        raise ValueError("cannot take the union of no domains")

    xs = [domain.x for domain in domains if domain.x is not None]
    ys = [domain.y for domain in domains if domain.y is not None]
    categories: list[str] = []
    for domain in domains:
        for category in domain.categories or ():
            if category not in categories:
                categories.append(category)

    return Domains(
        x=(min(low for low, _ in xs), max(high for _, high in xs)) if xs else None,
        y=(min(low for low, _ in ys), max(high for _, high in ys)) if ys else None,
        categories=tuple(categories) or None,
    )


def apply_limit(computed: tuple[float, float], override: tuple[float, float] | None) -> tuple[float, float]:
    """The domain a chart should draw against, given its own and a caller's override.

    The override **replaces** rather than widens. Widening would make a shared axis
    impossible to narrow, and a caller who asks for ``(0, 100)`` on data spanning 0..300
    means to clip the view, not to be told 300.

    Raises:
        ValueError: if ``override`` isn't an increasing pair of finite numbers. A reversed
            or degenerate pair maps every value to one pixel, which draws a chart that
            looks rendered and shows nothing.
    """
    if override is None:
        return computed
    low, high = _require_finite_pair(override)
    if low >= high:
        raise ValueError(f"axis limits must be increasing, got {override!r}")
    return (low, high)


def _require_finite_pair(value: object) -> tuple[float, float]:
    import math

    if not isinstance(value, tuple | list) or len(value) != 2:
        raise ValueError(f"axis limits must be a (low, high) pair, got {value!r}")
    low, high = value
    for bound in (low, high):
        if isinstance(bound, bool) or not isinstance(bound, int | float) or not math.isfinite(bound):
            raise ValueError(f"axis limits must be finite numbers, got {value!r}")
    return (float(low), float(high))
