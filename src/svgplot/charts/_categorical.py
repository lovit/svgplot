"""Bucketing rows into (category, hue) groups — shared by ``boxplot`` and ``violinplot``.

``violinplot``'s docstring promises that it and ``boxplot`` take the same positional arguments.
That promise is about more than the call: it says a category means the same thing in both, and
a hue group means the same thing in both. One function is how that stays true.

It used to live in ``charts/box.py`` and ``violinplot`` imported it from there -- the only
chart-to-chart import in the package -- with a do-nothing alias on the violin side to soften
the borrow. The dependency was real; the place was wrong. Moving it does not hide the names:
``box.py`` still imports both, so ``svgplot.charts.box.NO_HUE`` still resolves. What changes is
that neither chart owns them, so neither can drift them for its own convenience.
"""

from __future__ import annotations

from svgplot.data._missing import is_missing, require_number

NO_HUE = ""
"""The single hue slot a chart drawn without ``hue=`` has.

A sentinel rather than a branch: one code path that draws N boxes per band, where N is 1
unless a hue says otherwise, is what keeps the no-hue geometry exactly what it was.
"""


def group_by_category(columns: dict[str, list], x: str, y: str, hue: str | None = None) -> dict[tuple[str, str], list[float]]:
    """Drop rows with a missing x or y value, then bucket y values by (category, hue).

    Preserves first-seen order on both axes, so categories render left-to-right and hue
    groups slot within a band in the order they first appear in the data rather than an
    arbitrary sort -- the rule every other chart here already follows.
    """
    groups: dict[tuple[str, str], list[float]] = {}
    # ``columns[hue]`` rather than a guarded lookup: a hue naming no column is a ``KeyError``,
    # which is what this function's callers document and what every other chart raises.
    hues = columns[hue] if hue is not None else None
    for index, (xv, yv) in enumerate(zip(columns[x], columns[y], strict=True)):
        # ``is_missing`` rather than ``is None``: a NaN category label is not a category, and
        # letting it through buckets those rows under the string "nan". ``violinplot`` already
        # filtered this way and ``boxplot`` did not, which is exactly the kind of disagreement
        # sharing this function is meant to end.
        if is_missing(xv) or is_missing(yv):
            continue
        hue_value = NO_HUE if hues is None else hues[index]
        if is_missing(hue_value):
            continue
        groups.setdefault((str(xv), str(hue_value)), []).append(require_number(yv, y))
    return groups
