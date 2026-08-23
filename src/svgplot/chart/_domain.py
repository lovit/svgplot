"""What a chart's axes actually spanned, so several charts can be made to agree.

``layout`` places charts; making their axes line up is a *data*-level question
(docs-research/16-layout-vocabulary.md, 설계 원칙 3, which names a ``shared_x=``-style
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

import numbers
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
    x_step: float | None = None
    """How wide each division of the x axis is, for a chart whose x axis is binned.

    A shared *range* is not enough. ``bins="auto"`` derives its bin width from each panel's
    own values, so two panels covering one range still land their boundaries in different
    places -- measured, two panels of the same fixture choose 0.650000 against 0.216667 for the
    same shared span, a three-to-one difference in what one bar means. Pinning the edges needs
    the
    division shared too, because ``histogram_bins`` with an integer count and a range returns
    exactly ``linspace(low, high, count + 1)``.

    The width rather than the count, because the count is only meaningful against the range
    it was chosen for. Sharing a *count* re-spreads it over the wider union: two panels of
    three bars each, one at 1..3 and one at 100..102, both chose 3 -- and 3 bins across
    1..102 puts every value of each panel in one bar. Measured, that turned 3 bars per panel
    on ``main`` into 1. A width survives the change of range unharmed.

    ``None`` for a continuous axis, which is most of them."""

    categories_axis: str = "x"
    """Which **screen** axis the categories occupy. ``barplot(orient="h")`` draws them up
    the left edge, and a caller sharing "the x axis" means the one it can see -- so the
    field has to record where they landed, not which data role they play."""


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

    axes = {domain.categories_axis for domain in domains if domain.categories is not None}
    if len(axes) > 1:
        raise ValueError(f"charts disagree about which axis holds their categories: {sorted(axes)}")

    steps = [domain.x_step for domain in domains if domain.x_step is not None]

    return Domains(
        x=(min(low for low, _ in xs), max(high for _, high in xs)) if xs else None,
        y=(min(low for low, _ in ys), max(high for _, high in ys)) if ys else None,
        # The finest division any panel asked for, so sharing never coarsens a panel that
        # had more to show -- the narrowest width, not the largest count.
        x_step=min(steps) if steps else None,
        categories=tuple(categories) or None,
        categories_axis=axes.pop() if axes else "x",
    )


def narrows(computed: tuple[float, float], override: tuple[float, float] | None) -> bool:
    """Whether ``override`` makes the domain smaller than the chart computed for itself.

    Only a narrowing override can put a mark outside the plot area *because of the override*.
    Marks overhang the edge anyway -- a marker at the domain's maximum always spills its outer
    radius past the spine, with or without a limit -- and that is not something to cut; a clip
    exists for the values a narrowed window pushed out of view, not for the geometry of a mark
    sitting on the boundary. The distinction is not pedantry: ``facet`` shares an axis by handing every
    panel the *union* of the panels' domains, which by construction covers each panel's data,
    and treating that as a reason to clip cut the extreme markers of an unfaceted-looking chart
    in half -- a caller who passed no limit at all seeing marks lose their outer radius.

    Equal bounds are not narrowing. Widening on one side and narrowing on the other is.

    Validates through :func:`_require_finite_pair` rather than unpacking. Of the eighteen
    chart-and-axis pairs, sixteen reach this function before :func:`apply_limit`, so a bare
    ``low, high = override`` here would answer a malformed argument with ``too many values to
    unpack`` instead of the message that names the parameter. The two that do not: ``histplot``'s
    ``xlim=``, which settles the bin range first and so meets ``apply_limit`` there, and
    ``barplot``'s discarded axis -- ``xlim=`` under ``orient="v"`` and ``ylim=`` under ``"h"`` --
    which reaches neither, because the chart drops it at the call site. A malformed value in that
    slot is refused by nothing and always has been; it is the price of an argument the chart
    ignores.

    Raises:
        ValueError: if ``override`` isn't a pair of finite numbers -- the same refusal
            :func:`apply_limit` makes, raised at whichever of the two the chart reaches first.
    """
    if override is None:
        return False
    low, high = _require_finite_pair(override)
    return low > computed[0] or high < computed[1]


def apply_limit(computed: tuple[float, float], override: tuple[float, float] | None) -> tuple[float, float]:
    """The domain a chart should draw against, given its own and a caller's override.

    The override **replaces** rather than widens. Widening would make a shared axis
    impossible to narrow, and a caller who asks for ``(0, 100)`` on data spanning 0..300
    means to clip the view, not to be told 300. *Clip* is meant literally: the marks that
    fall outside the window are cut at the plot area rather than drawn past it, which is
    ``charts/_layout.marks_viewport``'s job and happens only when :func:`narrows` says this
    override actually made the domain smaller.

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
        # ``numbers.Real``, for the reason ``charts/_layout._finite`` gives and this shared the
        # gap with: a limit comes from the same array library the data did, so
        # ``xlim=(np.float32(0), np.float32(3))`` was refused on a call whose ``width=`` accepted
        # the same dtype (#274). ``numpy.float64`` slipped through both -- it subclasses
        # ``float`` -- so only the narrower dtypes showed the split.
        if isinstance(bound, bool) or not isinstance(bound, numbers.Real) or not math.isfinite(bound):
            raise ValueError(f"axis limits must be finite numbers, got {value!r}")
    return (float(low), float(high))


def require_categories(value: object) -> tuple[str, ...]:
    """A caller's ``categories=`` as a tuple, or a ``ValueError`` naming what they passed.

    The same reasoning as :func:`_require_finite_pair`, which refuses a zero-width window
    because a chart that renders but shows nothing is worse than one that says why. An empty
    sequence, or one naming categories none of the rows carry, produces exactly that: axes,
    a legend, and no marks. A bare string is worse than useless -- ``categories="ab"`` reads
    as one name and unpacks into two.

    Non-string members are rejected here rather than at the scale, which raises
    ``KeyError: "category not found in scale: '1'"`` -- a message about an internal lookup that
    has already turned the caller's ``1`` into a string,
    quoting a value the caller wrote as ``1``.
    """
    if isinstance(value, str):
        raise ValueError(f"categories must be a sequence of names, not a single string, got {value!r}")
    try:
        names = tuple(value)  # type: ignore[call-overload]
    except TypeError:
        raise ValueError(f"categories must be a sequence of names, got {value!r}") from None
    if not names:
        raise ValueError("categories must name at least one category, got an empty sequence")
    if not all(isinstance(name, str) for name in names):
        raise ValueError(f"categories must be a sequence of names, got {names!r}")
    return names
