"""The x span a set of density curves share — used by ``kdeplot`` and ``violinplot``.

Both charts evaluate several groups on **one grid**, and both settle that grid the same way:
take the span each group would have chosen alone, and union them. Pooling the values first and
computing one bandwidth from the pool would be the obvious alternative and it clips a narrow
group's tail, because the bandwidth that suits the pool is too wide for the narrow group.

What the two charts do *not* share, and why this takes a callback rather than the values:

* ``kdeplot`` groups by hue label and names the hue in a bandwidth failure; ``violinplot``
  groups by ``(category, hue)`` and names the *category*, because a bandwidth error is about
  the values in one violin and pointing at the hue would name the wrong half.
* ``violinplot`` probes the bandwidth on a two-point grid first (it needs the width, not the
  curve), and ``kdeplot`` asks ``stats.kde`` directly.

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
