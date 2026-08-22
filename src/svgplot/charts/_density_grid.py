"""The x span a set of density curves share — used by ``kdeplot`` and ``violinplot``.

Both charts evaluate several groups on **one grid**, and both settle that grid the same way:
take the span each group would have chosen alone, and union them. Pooling the values first and
computing one bandwidth from the pool is the obvious alternative, and it is rejected because it
makes a group's margin depend on **which other groups it was drawn beside**. Scott's rule is
``sd(values) * n**-0.2``, and pooling moves both factors at once, so the direction is not fixed
-- run these three and the same six values get a bandwidth 0.84x or 243x their own:

    >>> from svgplot.stats.kde import kde
    >>> bw = lambda v: kde(v, bandwidth="scott", grid=2).bandwidth
    >>> a = [10.0, 10.1, 10.2, 10.3, 10.4, 10.5]
    >>> round(bw(a), 4)
    0.1307
    >>> round(bw(a + [10.05, 10.15, 10.25, 10.35, 10.45, 10.55]), 4)  # a neighbour on top of it
    0.1097
    >>> round(bw(a + [110.0, 110.1, 110.2, 110.3, 110.4, 110.5]), 4)  # one a hundred units away
    31.771

Two earlier drafts of this paragraph each asserted a direction -- first that pooling is "too
wide" for a narrow group, then that it "shrinks" -- and both were measurable and wrong, because
the direction is a property of the fixture rather than of the rule. The union has no direction
to get wrong: every group keeps the span it would have chosen alone.

What the two charts do *not* share, and why this takes a callback rather than the values:

``kdeplot`` groups by hue label and names the hue in a bandwidth failure -- or names nothing,
when there is no ``hue=`` and the one group has no label to give. ``violinplot`` groups by
``(category, hue)`` and always names the *category*, because a bandwidth error is about the
values in one violin and pointing at the hue would name the wrong half. That is the whole of the
difference -- both probe the width on a two-point grid, and an earlier draft of this paragraph
claimed otherwise -- but it is enough that the bandwidth function has to stay with its caller.

So the callers keep their own bandwidth function and this owns only the rule they agree on.

**The shared cost, recorded once.** If two groups differ in scale by orders of magnitude the
grid step can exceed the narrow group's bandwidth entirely, and that group evaluates to zero
everywhere -- drawn flat on the baseline. That is inherent to sharing a grid rather than a
defect in this function, and seaborn behaves the same way for the same reason.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable


def union_grid_range(
    items: Iterable[tuple[object, list[float]]],
    bandwidth_of: Callable[[list[float], object], float],
    cut: float,
) -> tuple[float, float]:
    """``(low, high)``: the union of each group's own span, ``cut`` bandwidths past its extremes.

    ``bandwidth_of(values, label)`` is the caller's, so a failure names whatever that caller
    calls a group -- see this module's docstring for why the two callers disagree about that.
    """
    lows: list[float] = []
    highs: list[float] = []
    for label, values in items:
        width = bandwidth_of(values, label)
        lows.append(min(values) - cut * width)
        highs.append(max(values) + cut * width)
    return min(lows), max(highs)
