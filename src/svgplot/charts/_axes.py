"""Axis rendering shared by every chart type: spine line, grid lines, tick marks,
and tick label text for a linear/categorical/time scale.

Static axis elements (spine/grid-line/tick-line/tick-label) all share one CSS
class per element *type*, not a ``document.semantic_class``-per-instance name
— ``theme.css``'s ``<style>`` block targets ``.spine``/``.grid-line``/etc. once
and every matching element picks it up uniformly. Only per-series/per-legend
elements (see ``charts/line.py``, ``charts/_legend.py``) need unique classes.

Private/internal — not re-exported from ``svgplot.charts``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime
from itertools import pairwise

from svgplot._svg import SvgDocument
from svgplot.charts._layout import Margin, PlotArea, format_coord, resolve_margin
from svgplot.charts._textwidth import needs_full_text, text_width, truncate_to_width
from svgplot.scales import CategoricalScale, LinearScale, Scale, make_ticks

_DEFAULT_TICK_LENGTH = 6.0
_TICK_LABEL_OFFSET = 18.0
_Y_TICK_LABEL_OFFSET = 8.0


def _tick_position(scale: Scale, tick: object) -> float:
    """A ``CategoricalScale`` tick should sit at its band's center, not its band's
    start — every other scale type's ``__call__`` already returns the position a
    tick belongs at.
    """
    if isinstance(scale, CategoricalScale):
        return scale.center(str(tick))
    return scale(tick)


_DEFAULT_LABEL_FONT_SIZE = 10.0
"""Fallback for a caller with no ``Theme`` in scope, matching ``Theme.tick_label_font_size``.

It is a fallback and not the answer. An earlier version hardcoded 11.0 -- which is
``legend_font_size``, not this one -- and asserted in its own docstring that no theme exposed
the value separately. ``Theme.tick_label_font_size`` is a public field, and ``apply_context``
scales it: 8px on ``paper``, 13 on ``talk``, 16 on ``poster``. Measuring a 16px label as 11px
under-counts it by a third, which is how every defect this module fixes stayed alive on
``poster`` while the tests -- which shared the same wrong constant -- passed."""


_Y_LABEL_GUTTER = 14.0
"""Pixels reserved to the left of a y tick label's own width.

It stands in for two things — the tick mark's offset (``tick_length + 2``, chosen inside
``render_y_axis``) and a little air so the label does not touch the edge it was moved inside
of. A constant rather than a sum, because :func:`fit_left_margin` settles the margin before
any theme-dependent geometry exists and so has no ``tick_length`` to add.

That makes it a **bound, not a composition**, and the bound holds while ``tick_size <= 12``:
past that the offset alone is 14 and a numeric label — which cannot be shortened — starts
``tick_size + 2 - 14`` px off the canvas. No shipped preset comes close (``paper`` 3.2,
``notebook`` 4.0, ``talk`` 5.2, ``poster`` 6.4, ``minimal`` 0.0), and the previous behaviour
was worse at every size — the same label began 62.8 px off the canvas before this margin
existed. Threading ``tick_length`` through eleven call sites is the fix if a theme ever wants
a larger tick."""

_MAX_LEFT_MARGIN_FRACTION = 0.30
"""How much of the canvas the left margin may take to fit its labels.

Room for a label is worth taking from the plot area right up to the point where the plot is
no longer the thing on the page. Past this the labels are shortened instead, which is a loss
for a category name and not allowed for a value -- a value label wider than 30% of the canvas
is asking for a different chart, or a caller-set size (#120)."""

_MIN_LABEL_WIDTH_EMS = 2.4
"""Room below which shortening stops helping and thinning takes over, in **ems**.

In ems rather than pixels because the point is how much *label* fits, and that scales with the
font: 24px is two CJK characters at the default 10px and barely one on ``poster``. 2.4 em
leaves one CJK character plus the ellipsis, or two Latin ones -- little enough that anything
narrower is not a shortened label at all. A band below this leaves nothing but an ellipsis, and a hundred of those is not a
shortened axis, it is a row of dots. Measured: a 100x100 heatmap gives each category 5.80px,
which is 0.58 em at the default size."""


_LINE_HEIGHT = 1.2
"""Vertical room one label needs, in ems. Stacked labels collide at the line box, not at the
glyph, so this is the pitch below which a left axis has to thin."""


ROTATION_DEGREES = 45.0
"""How far a category label turns when it will not fit its band lying flat.

Forty-five, not ninety. The research this package is built from names rotation as the way to
avoid overlap *without measuring text* (``docs-research/12-aesthetics.md`` §3), and 45 is what
pygal's ``x_label_rotation`` and matplotlib's ``rotation=`` are reached for in practice. At 90
a label is read sideways and costs its full width in vertical margin; at 45 it costs
``width x sin(45)`` = 71% of that and stays readable at a glance. The tradeoff only gets worse
past 45, because the vertical cost rises while legibility falls.
"""

_MAX_BOTTOM_MARGIN_FRACTION = 0.35
"""How much of the canvas height rotated labels may take, mirroring the left-margin cap.

Slightly more than :data:`_MAX_LEFT_MARGIN_FRACTION` (0.30) because the bottom margin starts
smaller: the presets give the left 60px of 800 and the bottom 50px of 600, so the same
fraction would buy the bottom less room than the labels there actually need. Past the cap the
label is shortened as before -- the chart is still worth more than its axis.
"""


def rotated_label_extent(labels: Sequence[str], font_size: float) -> float:
    """How far below the axis a rotated label reaches, for the widest of ``labels``.

    A label turned by :data:`ROTATION_DEGREES` projects ``width x sin(theta)`` onto the
    vertical. That projection is the whole reason rotation solves this: flat, a label's budget
    is the band it sits in, which shrinks as categories are added; rotated, its budget is the
    bottom margin, which does not depend on how many categories there are.
    """
    if not labels:
        return 0.0
    widest = max(text_width(label, font_size) for label in labels)
    return widest * math.sin(math.radians(ROTATION_DEGREES))


def wants_rotation(categories: Sequence[str], *, bandwidth: float, font_size: float) -> bool:
    """Whether the widest category label needs turning to stay distinguishable.

    The test is the same budget :func:`render_x_axis` gives a flat label, so this answers
    "would the label be shortened?" -- and shortening is what rotation exists to avoid. It is
    not "would it be shortened *to nothing*": by the time a label is cut to a few characters,
    every label on the axis has been cut to the **same** prefix and the axis has stopped
    naming anything. Measured on eight ``2024년 N분기 실적`` categories, a 500px canvas drew
    ``2024…`` eight times and a 360px one drew ``20…`` eight times.
    """
    if not categories or bandwidth <= 0.0:
        return False
    room = max(bandwidth - font_size / 2, 0.0)
    return any(text_width(str(category), font_size) > room for category in categories)


def _label_stride(positions: list[float], needed: float) -> int:
    """Draw every n-th label, so that each has ``needed`` pixels of the axis to itself.

    Grid lines and tick marks still go on every tick -- the axis keeps showing where the data
    is. It is only the *text* that thins, because text is the only part that needs room. Which
    ticks keep their label is left to position rather than to content: any rule that picked
    "important" ones would be inventing a judgement the caller did not make.

    The geometry this promises is only as good as ``charts/_textwidth`` estimate it rests on,
    which is a bound for Latin-1, Latin Extended-A and fullwidth text and an approximation
    outside them. Measured against real font advances, a twelve-category Cyrillic axis still
    overlaps by up to 0.54 px and an Arabic one by more, because per-character advances do not
    model shaping. Those labels always keep their full text in a ``<title>``, so nothing is
    lost — but the *overlap* remedy is scoped to the scripts the estimator bounds.

    Thinning is the only remedy available on an axis of **values**, where shortening would
    make the axis false, and it is the right one on a crowded axis of names too -- shortening
    a label to the 5.8px a 100x100 heatmap gives it leaves an ellipsis and nothing else.

    Positions rather than a scale, so the same rule serves a categorical band, a numeric tick
    spacing and a vertical pitch. The three used to be one rule for the first and nothing at
    all for the other two.
    """
    if len(positions) < 2 or needed <= 0:
        return 1
    pitch = min(abs(later - earlier) for earlier, later in pairwise(sorted(positions)))
    if pitch <= 0 or pitch >= needed:
        return 1
    return max(1, math.ceil(needed / pitch))


def _bottom_anchor(text: str, x: float, font_size: float, width: float) -> str:
    """Which way a bottom label should grow so that it stays on the canvas.

    Centred is right for every label with room either side, and wrong for the two at the ends
    of the axis, which have room on one side only. Thinning cannot help there -- the extreme
    tick sits at the extreme value however few of them there are -- and neither can the left
    margin. Measured, ``scatterplot({'x': [0, 1.2e15]})`` put ``1200000000000000`` 18.4px past
    the right edge of a default canvas.

    Anchoring rather than shortening, because a bottom tick label on a numeric or time axis is
    the value. Anchoring costs the reader nothing: the label still touches its tick, it simply
    extends the way there is room to extend.

    A **category** label never needs it and must not get it. It has already been cut to fit
    its own band, so it cannot reach the canvas edge — while shifting it inward *would* push
    it a half-width into its neighbour's band, which is how two long Korean labels came to
    overlap at the ``poster`` label size even though each one fitted.
    """
    half = text_width(text, font_size) / 2
    if x - half < 0:
        return "start"
    if x + half > width:
        return "end"
    return "middle"


def _shown_label(scale: Scale, tick: object, available: float, font_size: float, time_format: str) -> tuple[str, bool]:
    """The label to draw and whether the full text has to be kept beside it.

    A **category** label is a name, so it is cut to the room it has. A tick label on a numeric
    or time axis *is* the value it names: cutting ``1234567`` to ``1234…`` makes the axis say
    something false, and no ``<title>`` repairs a reader who believed the axis. Those are left
    whole and given room instead -- see :func:`fit_left_margin`.
    """
    text = _tick_label_text(scale, tick, time_format=time_format)
    if not isinstance(scale, CategoricalScale):
        return text, False
    shown = truncate_to_width(text, font_size, available)
    return shown, shown != text or needs_full_text(text, font_size, available)


_DATE_FORMATS = ("%Y", "%Y-%m", "%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S")
"""Time-axis label formats for a domain spanning a day or more, coarsest first."""

_CLOCK_FORMATS = ("%H:%M", "%H:%M:%S", "%H:%M:%S.%f")
"""The same for ticks that all fall on one calendar date, where repeating that date on every
tick would spend the axis' width on a date the reader can only read once.

One date, not one day's worth of hours: ticks running 12:00, 18:00, 00:00, 06:00 span
eighteen hours but two dates, and dropping the date there leaves a reader to guess which
midnight ``00:00`` is."""


_MUST_BE_ZERO = {
    "%Y": ("month", "day", "hour", "minute", "second", "microsecond"),
    "%Y-%m": ("day", "hour", "minute", "second", "microsecond"),
    "%Y-%m-%d": ("hour", "minute", "second", "microsecond"),
    "%Y-%m-%d %H:%M": ("second", "microsecond"),
    "%Y-%m-%d %H:%M:%S": ("microsecond",),
    "%H:%M": ("second", "microsecond"),
    "%H:%M:%S": ("microsecond",),
    "%H:%M:%S.%f": (),
}
"""The fields each format hides, and therefore the fields a tick must not carry to use it.

``month``/``day`` count from 1, so "zero" means 1 for those two -- a year label is honest only
about 1 January."""


def _keeps_every_field(tick: datetime, fmt: str) -> bool:
    """Whether ``fmt`` hides nothing ``tick`` actually carries.

    ``%Y`` on a tick at 29 December reads "2025", which is a fact about the year and a lie
    about the tick -- and the reader has no way to tell, because the axis looks tidy. Round-
    tripping through ``strptime`` cannot express this, since a clock format carries no date at
    all and would never round-trip; what matters is only that the hidden fields are empty.
    """
    return all(getattr(tick, field) == (1 if field in ("month", "day") else 0) for field in _MUST_BE_ZERO[fmt])


def _time_format(ticks: list[datetime], domain: tuple[datetime, datetime]) -> str:
    """The coarsest format that still tells the ticks apart.

    A fixed ``"%Y-%m-%d"`` is right for a domain of months and wrong either way outside it.
    Measured on a three-hour domain it labelled all five ticks ``2024-01-01``; on a three-year
    domain it spent eleven characters on a day nobody asked about. Both are the same bug --
    the resolution has to come from the domain, which is what matplotlib's locator/formatter
    pair does and what this is the small version of.

    Choosing by *distinctness* rather than by a span-to-format table is what makes the "no
    duplicate labels" property hold rather than be approximated: a table has to guess how many
    ticks will land in a span, and the ticks are right there.
    """
    # The *domain*, not the ticks. A domain spanning two weeks that happens to receive one
    # tick has one tick date, and choosing by the ticks then dropped the date from a label
    # standing for thirteen days -- ``00:00``, with the year nowhere in the file.
    ladder = _CLOCK_FORMATS if domain[0].date() == domain[1].date() else _DATE_FORMATS
    for candidate in ladder:
        # Three conditions, and the third is the one that keeps a label honest.
        #
        # Telling the *ticks* apart is not enough: a single tick is distinguished by every
        # format including ``%Y``, so an eleven-day axis came out labelled "2024". Telling the
        # *domain's ends* apart is not enough either: both ends of a thirty-six-day span
        # across New Year differ under ``%Y``, and the axis came out ``["2025", "2026"]`` with
        # its first tick standing at 29 December. A label has to be a truthful truncation of
        # the tick it names -- ``%Y`` only where every tick really is 1 January at midnight.
        if (
            len({tick.strftime(candidate) for tick in ticks}) == len(ticks)
            and (domain[0].strftime(candidate) != domain[1].strftime(candidate) or domain[0] == domain[1])
            and all(_keeps_every_field(tick, candidate) for tick in ticks)
        ):
            return candidate
    # Reaching here means no format in the ladder both separates the ticks and resolves the
    # domain. The date ladder stops at seconds, so two ticks less than a second apart on a
    # multi-date domain would land here -- ``make_ticks`` does not produce that, but the
    # finest format showing the most it can beats raising.
    return ladder[-1]


def _tick_label_text(scale: Scale, tick: object, *, time_format: str) -> str:
    if isinstance(scale, CategoricalScale):
        return str(tick)
    if isinstance(tick, datetime):
        return tick.strftime(time_format)
    return format_coord(float(tick))


def render_x_axis(
    document: SvgDocument,
    scale: Scale,
    area: PlotArea,
    *,
    tick_count: int = 5,
    tick_length: float = _DEFAULT_TICK_LENGTH,
    font_size: float = _DEFAULT_LABEL_FONT_SIZE,
    rotate: bool = False,
) -> None:
    """Draw the bottom spine, vertical grid lines, tick marks, and tick labels for ``scale``.

    ``tick_length`` should come from the ``Theme`` being rendered with
    (``theme.tick_size``) so a theme's tick length actually takes visual effect —
    it defaults to a sane constant only for direct/standalone callers that don't
    have a ``Theme`` in scope.

    ``rotate`` turns category labels by :data:`ROTATION_DEGREES` instead of shortening them,
    and is decided by the caller because the bottom margin has to be widened to match *before*
    the plot area exists — see :func:`fit_bottom_margin`. It is ignored on a numeric or time
    axis: those labels are values, they are never shortened in the first place, and turning
    them only makes them harder to read.
    """
    document.add_node(
        None,
        "line",
        attrib={
            "x1": format_coord(area.left),
            "y1": format_coord(area.bottom),
            "x2": format_coord(area.right),
            "y2": format_coord(area.bottom),
        },
        classes=["spine"],
    )
    label_offset = tick_length + _TICK_LABEL_OFFSET
    ticks = make_ticks(scale, count=tick_count)
    time_format = _time_format(ticks, scale.domain) if ticks and isinstance(ticks[0], datetime) else ""
    # A bottom label spreads sideways from its tick, so what it needs is its own width -- the
    # band on a categorical axis, and on an axis of values the widest label, which cannot be
    # shortened and so has nothing else to give.
    #
    # One and a half widths, not one. The labels at the ends of a numeric axis are anchored
    # inward (see ``_bottom_anchor``), which moves them half a width toward their neighbour --
    # so the gap that matters is between a centred label's right edge and an ``end``-anchored
    # one's left edge, and requiring only one width let them overlap by 31.6px on a plain
    # ``scatterplot({'x': [0, 1e15]})``. Trading a canvas overrun for two illegible labels is
    # a worse deal than the overrun.
    needed = (
        _MIN_LABEL_WIDTH_EMS * font_size
        if isinstance(scale, CategoricalScale)
        else 1.5
        * max((text_width(_tick_label_text(scale, tick, time_format=time_format), font_size) for tick in ticks), default=0.0)
        + font_size / 2
    )
    # Turning is for names, not values -- see the ``rotate`` note in this function's docstring.
    turning = rotate and isinstance(scale, CategoricalScale)
    positions = [_tick_position(scale, tick) for tick in ticks]
    if turning:
        # Turned labels are parallel strips, so what separates them is the distance *across*
        # the strips, not along the axis: two of them collide when the band pitch projected
        # perpendicular to the text -- ``pitch x sin(theta)`` -- falls under a line height.
        # Their lengths never enter it, which is why turning buys so much: 60 short categories
        # still need thinning at an 11.7px pitch, while 8 long ones at 87.5px do not, and
        # measuring the *horizontal* footprint instead dropped half of those eight for a
        # collision that does not happen.
        needed = _LINE_HEIGHT * font_size / math.sin(math.radians(ROTATION_DEGREES))
    stride = _label_stride(positions, needed)
    for index, tick in enumerate(ticks):
        x = _tick_position(scale, tick)
        document.add_node(
            None,
            "line",
            attrib={
                "x1": format_coord(x),
                "y1": format_coord(area.top),
                "x2": format_coord(x),
                "y2": format_coord(area.bottom),
            },
            classes=["grid-line"],
        )
        document.add_node(
            None,
            "line",
            attrib={
                "x1": format_coord(x),
                "y1": format_coord(area.bottom),
                "x2": format_coord(x),
                "y2": format_coord(area.bottom + tick_length),
            },
            classes=["tick-line"],
        )
        # A band is all the room a category label has, less the same half-em of breathing room
        # the numeric branch above reserves. Without that subtraction the budget equals the
        # pitch exactly on an axis with no padding, and two full-width labels come out
        # touching -- measured at 0.006px apart on a 13-category bar chart, and actually
        # overlapping once the label font grows to the ``talk`` and ``poster`` sizes. Running
        # into a neighbour is the same defect as running off the canvas and harder to spot,
        # because both labels are still there and both are legible.
        if index % stride:
            continue
        if turning:
            # ``end`` anchoring puts the label's *last* character at the tick, which is what
            # makes a column of turned labels line up along the axis instead of drifting away
            # from their own ticks.
            label = _tick_label_text(scale, tick, time_format=time_format)
            baseline = area.bottom + label_offset
            # Turning buys a much larger budget than the band, but not an unlimited one: on a
            # small canvas the margin caps in ``fit_rotated_labels`` bind before the label
            # ends. What is left is measured here, from this label's own anchor, because the
            # room differs per tick -- the leftmost label runs out of canvas sideways long
            # before the rightmost one does. Letting it run over instead was measured at 110px
            # outside a 240x180 poster chart, and "outside the canvas" is not a lesser defect
            # than "shortened": it is the one this package refuses everywhere else.
            turn = math.radians(ROTATION_DEGREES)
            budget = min(x / math.cos(turn), (document.height - baseline) / math.sin(turn))
            shown = truncate_to_width(label, font_size, budget)
            node = document.add_text(
                None,
                shown,
                tag="text",
                attrib={
                    "x": format_coord(x),
                    "y": format_coord(baseline),
                    "text-anchor": "end",
                    "transform": f"rotate({format_coord(-ROTATION_DEGREES)} {format_coord(x)} {format_coord(baseline)})",
                },
                classes=["tick-label"],
            )
            if shown != label or needs_full_text(label, font_size, budget):
                document.add_text(node, label, tag="title")
            continue
        room = max(getattr(scale, "bandwidth", 0.0) * stride - font_size / 2, 0.0)
        shown, keep_full = _shown_label(scale, tick, room, font_size, time_format)
        node = document.add_text(
            None,
            shown,
            tag="text",
            attrib={
                "x": format_coord(x),
                "y": format_coord(area.bottom + label_offset),
                "text-anchor": "middle"
                if isinstance(scale, CategoricalScale)
                else _bottom_anchor(shown, x, font_size, document.width),
            },
            classes=["tick-label"],
        )
        if keep_full:
            document.add_text(node, _tick_label_text(scale, tick, time_format=time_format), tag="title")


def render_y_axis(
    document: SvgDocument,
    scale: Scale,
    area: PlotArea,
    *,
    tick_count: int = 5,
    tick_length: float = _DEFAULT_TICK_LENGTH,
    font_size: float = _DEFAULT_LABEL_FONT_SIZE,
) -> None:
    """Draw the left spine, horizontal grid lines, tick marks, and tick labels for ``scale``.

    ``tick_length`` should come from the ``Theme`` being rendered with
    (``theme.tick_size``) so a theme's tick length actually takes visual effect —
    it defaults to a sane constant only for direct/standalone callers that don't
    have a ``Theme`` in scope.
    """
    document.add_node(
        None,
        "line",
        attrib={
            "x1": format_coord(area.left),
            "y1": format_coord(area.top),
            "x2": format_coord(area.left),
            "y2": format_coord(area.bottom),
        },
        classes=["spine"],
    )
    label_x_offset = tick_length + 2
    ticks = make_ticks(scale, count=tick_count)
    time_format = _time_format(ticks, scale.domain) if ticks and isinstance(ticks[0], datetime) else ""
    # A left label stacks, so what it needs is a line box rather than its own width. Nothing
    # thinned this axis at all: a horizontal bar chart of 53 categories put its labels 9.81px
    # apart at a 10px font, and every one of them overlapped its neighbour.
    stride = _label_stride([_tick_position(scale, tick) for tick in ticks], _LINE_HEIGHT * font_size)
    for index, tick in enumerate(ticks):
        y = _tick_position(scale, tick)
        document.add_node(
            None,
            "line",
            attrib={
                "x1": format_coord(area.left),
                "y1": format_coord(y),
                "x2": format_coord(area.right),
                "y2": format_coord(y),
            },
            classes=["grid-line"],
        )
        document.add_node(
            None,
            "line",
            attrib={
                "x1": format_coord(area.left - tick_length),
                "y1": format_coord(y),
                "x2": format_coord(area.left),
                "y2": format_coord(y),
            },
            classes=["tick-line"],
        )
        # After the grid line and the tick mark, not before them. Skipping the whole iteration
        # thinned those away too, so a 100x100 heatmap drew all 100 column boundaries and only
        # 34 row boundaries -- a reader could no longer line a cell up with its row, which is
        # the thing thinning was supposed to preserve.
        if index % stride:
            continue
        # Right-aligned at the axis, so a label grows leftwards into the margin and then off
        # the canvas into negative coordinates. Measured on ``main``, a horizontal bar chart's
        # longest category label started at x=-83.7.
        shown, keep_full = _shown_label(scale, tick, area.left - label_x_offset, font_size, time_format)
        node = document.add_text(
            None,
            shown,
            tag="text",
            attrib={
                "x": format_coord(area.left - label_x_offset),
                "y": format_coord(y + _Y_TICK_LABEL_OFFSET / 2),
                "text-anchor": "end",
            },
            classes=["tick-label"],
        )
        if keep_full:
            document.add_text(node, _tick_label_text(scale, tick, time_format=time_format), tag="title")


def fit_left_margin(
    margin: Margin,
    domain: tuple[float, float] | Sequence[str],
    *,
    width: float,
    tick_count: int = 5,
    font_size: float = _DEFAULT_LABEL_FONT_SIZE,
) -> Margin:
    """``margin`` widened, if it needs to be, to fit ``scale``'s tick labels.

    This is the other half of the rule in :func:`_shown_label`. A category label is a name and
    can be shortened; a numeric or time label **is** the value, so the only honest way to keep
    it inside the canvas is to make room. Measured on ``main``, ``1200000000000000`` on a y
    axis started at x=-62.8 and a horizontal bar chart's longest category at x=-83.7 -- both
    outside the ``viewBox``, where nothing renders them.

    Widening is capped at :data:`_MAX_LEFT_MARGIN_FRACTION`; past that a name is shortened and
    a value is left to overflow, because shrinking the plot further would hide the chart to
    show its axis. A **bottom** axis of values gets neither: it is thinned instead (see
    :func:`_label_stride`), which costs resolution and never truth. The estimate is the same approximation :mod:`svgplot.charts._textwidth`
    documents, so this fits labels to within the error described there -- generously in the
    fonts it was measured against, and not at all in a font nobody measured.
    """
    # A provisional scale, because which ticks a scale produces depends on its domain and not
    # on the pixels it maps to -- which is what lets the margin be settled before the plot
    # area that the real scale needs exists.
    scale: Scale = (
        CategoricalScale(list(domain), (0.0, 1.0)) if not isinstance(domain, tuple) else LinearScale(domain, (0.0, 1.0))
    )
    top, right, bottom, left = resolve_margin(margin)
    ticks = make_ticks(scale, count=tick_count)
    if not ticks:
        return top, right, bottom, left
    # ``fit_left_margin`` builds its own scale from a domain, never a time one, so there is
    # no format to choose here -- the ticks are categories or numbers.
    widest = max(text_width(_tick_label_text(scale, tick, time_format=""), font_size) for tick in ticks)
    needed = widest + _Y_LABEL_GUTTER
    # ``max(left, ...)`` outermost: the cap applies to the *candidate*, not to the result, so
    # this function widens and never narrows. Clamping the result instead let a small canvas
    # shrink a caller's own margin -- 60px became 30 at ``width=100`` -- which is the opposite
    # of what the name says and what #120 will hit.
    return top, right, bottom, max(left, min(needed, width * _MAX_LEFT_MARGIN_FRACTION))


def fit_rotated_labels(
    margin: Margin,
    categories: Sequence[str],
    *,
    height: float,
    plot_width: float,
    font_size: float = _DEFAULT_LABEL_FONT_SIZE,
    tick_length: float = _DEFAULT_TICK_LENGTH,
    padding: float = 0.0,
) -> tuple[Margin, bool]:
    """``margin`` opened up for turned category labels, and whether they are turned at all.

    Returns the pair rather than just the margin because the caller needs both and they have
    to agree: the decision to rotate and the room rotation needs are the same decision, and
    computing them in two places is how they drift apart. :func:`render_x_axis` takes the
    boolean, :func:`~svgplot.charts._layout.new_canvas` takes the margin.

    **Two** sides, not one, which is why this is not called ``fit_bottom_margin``. A turned
    label reaches down *and* to the left of its tick, and the leftmost category's tick is only
    half a band inside the plot -- measured at the ``poster`` label size, that label started
    25.8px outside the canvas while the bottom margin was comfortably deep enough. Fitting the
    depth and forgetting the reach is the same bug as not fitting at all, just harder to see.

    ``plot_width`` is the width the *plot area* will have, not the canvas: the band a label
    has to fit inside is a share of the plot, so passing the canvas width would find the
    labels roomier than they are and leave them flat when they needed turning.

    Both sides are capped (:data:`_MAX_BOTTOM_MARGIN_FRACTION`, :data:`_MAX_LEFT_MARGIN_FRACTION`).
    Past a cap the labels are still turned and the longest is clipped at its far end, which
    keeps their beginnings distinct -- where a flat label shortened past its common prefix
    leaves every label on the axis reading the same thing.
    """
    top, right, bottom, left = resolve_margin(margin)
    names = [str(category) for category in categories]
    if not names:
        return (top, right, bottom, left), False
    # ``padding`` because a padded ``CategoricalScale`` gives a label *less* room than the
    # pitch suggests -- ``violinplot`` insets its bands by 20%, so an 87.5px pitch is a 70px
    # budget. Deciding on the pitch while ``render_x_axis`` measures against the real band made
    # the two disagree exactly where it matters: a 73.2px label came out whole on ``boxplot``
    # and shortened to "카테고리…" on ``violinplot``, which is the defect rotation exists to fix.
    pitch = plot_width / len(names)
    bandwidth = pitch * (1.0 - padding)
    if not wants_rotation(names, bandwidth=bandwidth, font_size=font_size):
        return (top, right, bottom, left), False
    widest = max(text_width(name, font_size) for name in names)
    turn = math.radians(ROTATION_DEGREES)
    # Everything between the plot's bottom edge and the label's far corner, in the order the
    # renderer stacks it: the tick mark, the gap under it, the label's own vertical projection,
    # and finally the label's *height* turned sideways -- at 45 degrees a line of text is a
    # parallelogram, not a segment, so its far corner sits one rotated line-height further down
    # than its baseline does.
    depth = tick_length + _TICK_LABEL_OFFSET + widest * math.sin(turn) + font_size * math.cos(turn)
    # The leftmost tick stands half a band inside the plot area, and the label reaches back from
    # it by its turned horizontal footprint. Whatever that reach exceeds is what the left margin
    # still owes -- but widening the left margin narrows the plot, which narrows the band, which
    # moves that tick further left and lengthens the debt. Solved rather than approximated:
    # with ``extra`` added to the left, the band becomes ``(plot_width - extra) / n``, so
    #
    #     left + extra >= widest*cos - (plot_width - extra) / 2n
    #
    # and rearranging gives the line below. Ignoring the feedback and adding the first-pass
    # figure left the ``poster`` label 2.6px outside the canvas; ignoring the half-band credit
    # instead would over-reserve 70px of left margin on a five-category chart.
    owed = widest * math.cos(turn) - pitch / 2 - left
    # Minus, not plus. Widening the left *narrows* the band, so the half-band credit shrinks as
    # the margin grows and the debt is larger than the first pass says -- the sign that makes
    # the difference between closing the overflow and making it worse.
    extra = max(0.0, owed / (1.0 - 1.0 / (2 * len(names)))) if len(names) > 1 else max(0.0, owed) * 2.0
    return (
        top,
        right,
        max(bottom, min(depth, height * _MAX_BOTTOM_MARGIN_FRACTION)),
        left + min(extra, plot_width * _MAX_LEFT_MARGIN_FRACTION),
    ), True
