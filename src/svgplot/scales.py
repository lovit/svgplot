"""Data-domain to pixel-space scales.

Linear, categorical, and time scales plus "nice" tick generation. Datetime
x-values are handled here as a scale option rather than a separate chart
type (see docs-research/10-feature-matrix.md, "시간축 선"). Kept as a single
file until a concrete need for additional scale types (e.g. log) appears.

Tick generation deliberately avoids any text-width measurement (no font
renderer in pure SVG, see docs-research/12-aesthetics.md §3) — "nice" here
means round numbers/round time steps, not "however many fit visually".
"""

from __future__ import annotations

import math
from datetime import MAXYEAR, datetime, timedelta

_MAX_TICK_COUNT = 1000


def _require_finite(value: float, label: str) -> float:
    """Reject NaN/inf so it can never silently become a pixel coordinate or a
    raw OverflowError/ValueError deep inside tick generation.
    """
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite, got {value!r}")
    return value


class LinearScale:
    """Maps a numeric data domain to a pixel range."""

    def __init__(self, domain: tuple[float, float], range_: tuple[float, float]) -> None:
        for value in (*domain, *range_):
            _require_finite(value, "domain/range value")
        self.domain = domain
        self.range = range_

    def __call__(self, value: float) -> float:
        """Map a data value to a pixel position."""
        _require_finite(value, "value")
        domain_min, domain_max = self.domain
        range_min, range_max = self.range
        if domain_max == domain_min:
            return (range_min + range_max) / 2
        ratio = (value - domain_min) / (domain_max - domain_min)
        return range_min + ratio * (range_max - range_min)


class LogScale:
    """Maps a positive numeric domain to a pixel range on a base-10 logarithm.

    The scale three of the four libraries this package is measured against offer
    (``pygal``'s ``logarithmic=True``, matplotlib's ``set_yscale("log")``, Bokeh's
    ``y_axis_type="log"``) and the one ``docs-research/10-feature-matrix.md`` never got a row
    for. It matters for the data this package is aimed at -- response times, file sizes,
    populations, benchmark ratios -- where a linear axis crushes the small values into one
    pixel and the chart stops answering the question it was drawn for.

    **Non-positive values are refused, not clipped or masked.** matplotlib offers
    ``nonpositive="mask"|"clip"``; this package's rule everywhere else is to name the problem
    rather than quietly redraw a different chart, and both alternatives do the latter --
    masking drops rows the caller still counted, clipping invents a value they never had.

    Raises:
        ValueError: if either end of ``domain`` is not finite and strictly positive, or if
            ``domain`` is a single point (there is no span to take a ratio across).
    """

    def __init__(self, domain: tuple[float, float], range_: tuple[float, float]) -> None:
        for value in range_:
            _require_finite(value, "range value")
        for value in domain:
            _require_finite(value, "domain value")
            if value <= 0.0:
                raise ValueError(f"a log scale needs strictly positive values, got {value!r}")
        self.domain = domain
        self.range = range_

    def __call__(self, value: float) -> float:
        """Map a data value to a pixel position."""
        _require_finite(value, "value")
        if value <= 0.0:
            raise ValueError(f"a log scale needs strictly positive values, got {value!r}")
        domain_min, domain_max = self.domain
        range_min, range_max = self.range
        if domain_max == domain_min:
            return (range_min + range_max) / 2
        ratio = math.log10(value / domain_min) / math.log10(domain_max / domain_min)
        return range_min + ratio * (range_max - range_min)


class CategoricalScale:
    """Maps discrete category values to evenly spaced pixel bands (d3's ``scaleBand``).

    ``scale(category)`` gives a band's start position; ``scale.center(category)``
    gives its midpoint (what most callers actually want, e.g. for tick labels);
    ``scale.bandwidth`` gives each band's width (e.g. for bar width); ``scale.step``
    gives the spacing between consecutive band starts.

    ``padding`` is d3's ``scaleBand().padding()``: the fraction of each step left as
    gutter, split evenly on both sides so the band stays centred in its step. It exists
    because ``charts/bar.py`` and ``charts/box.py`` each carry a hand-rolled copy of this
    idea (``_BAND_PADDING_FRACTION``/``_BOX_WIDTH_FRACTION``) and a violin plot would have
    been the third. **Migrating those two onto this is deliberately a separate change** —
    it is a behaviour-preserving refactor, and folding it in here would mix two intents.
    """

    def __init__(self, categories: list[str], range_: tuple[float, float], *, padding: float = 0.0) -> None:
        self.categories = list(categories)
        if len(set(self.categories)) != len(self.categories):
            raise ValueError(f"categories must be unique, got duplicates in: {self.categories!r}")
        if not isinstance(padding, int | float) or isinstance(padding, bool) or not 0.0 <= float(padding) < 1.0:
            raise ValueError(f"padding must be a number in [0, 1), got {padding!r}")
        self.range = range_
        self.padding = float(padding)
        self._index_by_category = {category: index for index, category in enumerate(self.categories)}

    @property
    def step(self) -> float:
        """Distance between consecutive band starts, gutter included."""
        if not self.categories:
            return 0.0
        range_min, range_max = self.range
        return (range_max - range_min) / len(self.categories)

    @property
    def bandwidth(self) -> float:
        """Drawn width of one band. Equals :attr:`step` at the default ``padding=0.0``."""
        return self.step * (1.0 - self.padding)

    def __call__(self, category: str) -> float:
        """Map a category to its band's start position."""
        if category not in self._index_by_category:
            raise KeyError(f"category not found in scale: {category!r}")
        range_min, _ = self.range
        step = self.step
        # Half the gutter sits on each side, which is what keeps center() independent of
        # padding -- tick labels must not shift when a chart changes its bar width.
        return range_min + self._index_by_category[category] * step + (step - self.bandwidth) / 2

    def center(self, category: str) -> float:
        """Map a category to its band's midpoint.

        Unaffected by ``padding`` -- exactly so at ``padding=0.0``, and to within float
        rounding otherwise (measured worst case ~1.4e-15 relative, far below the six
        decimal places ``format_coord`` emits).
        """
        return self(category) + self.bandwidth / 2


class TimeScale:
    """Maps a datetime domain to a pixel range (a ``LinearScale`` over Unix timestamps).

    ``datetime.timestamp()``/``fromtimestamp()`` interpret naive ``datetime``
    values (no ``tzinfo``) in the local system timezone — pass timezone-aware
    values if you need a result independent of where this code runs.
    """

    def __init__(self, domain: tuple[datetime, datetime], range_: tuple[float, float]) -> None:
        self.domain = domain
        self.range = range_
        self._linear = LinearScale((domain[0].timestamp(), domain[1].timestamp()), range_)

    def __call__(self, value: datetime) -> float:
        """Map a datetime value to a pixel position."""
        return self._linear(value.timestamp())


def _nice_step(rough_step: float) -> float:
    """Round a step size up to a "nice" 1/2/5 * 10^n value (classic nice-number tick algorithm).

    Raises:
        ValueError: if ``rough_step``'s magnitude is so extreme (near float's
            min/max representable range) that computing a step would overflow,
            underflow to zero, or otherwise fail — this normalizes what would
            otherwise be a raw ``OverflowError``/``ZeroDivisionError``.
    """
    if rough_step <= 0:
        return 1.0
    try:
        # 10.0 (float), not 10 (int): `10 ** non_negative_int` is a Python int, and an
        # int this large can later overflow converting *back* to float with a confusing
        # "int too large to convert to float" instead of a clean, expected ValueError.
        magnitude = 10.0 ** math.floor(math.log10(rough_step))
        # Rounded before it reaches the ladder below, so that the ladder answers the same way
        # for the same data at any unit. Without it ``(0, 3.5)`` drew 8 ticks and ``(0, 35)``
        # drew 4: ``3.5 / 5`` gives ``0.7``, whose residual ``0.7 / 0.1`` is
        # ``6.999999999999999`` and takes the ``< 7`` branch, while ``35 / 5`` gives ``7.0``
        # with an exact residual that does not (#273).
        #
        # **Not** because "the arithmetic says 7" -- it does not, and an earlier version of this
        # comment claimed it did. The double written ``0.7`` is *below* decimal 0.7, so the exact
        # quotient is ``6.99999999999999916...`` however it is computed; ``Decimal``, ``Fraction``
        # and multiplying by ``10 ** -exponent`` all agree it is under 7. There is no arithmetic
        # that recovers "the user meant 0.7" from a value that arrived as ``span / count``.
        #
        # The requirement is unit-invariance, and this is the trade it costs. A residual within
        # ``1e-10`` of a branch point now takes the upper branch whether it got there by division
        # error or by being that value -- ``_nice_step(6.999999999999999)`` answers 10 where it
        # used to answer 5. That direction is the coherent one: to a caller, a domain topping out
        # at ``6.999999999999999`` is a domain topping out at 7, and it now gets 7's axis. Before,
        # ``0.7``, ``6.999999999999999``, ``7.0`` and ``70.0`` split two ways; they no longer do.
        #
        # Ten digits: ``residual`` lies in ``[1, 10)`` for every reachable input, where a double's
        # ULP runs from ``2.2e-16`` to ``1.8e-15``. Rounding at the tenth significant digit
        # therefore sits 4.75 to 5.05 orders of magnitude above the error it absorbs -- narrowest
        # at the top of the range, which is where the ``< 7`` branch lives. Differences larger
        # than ``1e-10`` are preserved; the trade above is what happens to smaller ones.
        residual = round(rough_step / magnitude, 10)
    except (OverflowError, ZeroDivisionError, ValueError) as error:
        raise ValueError(f"cannot compute a tick step for rough_step={rough_step!r}") from error
    if residual < 1.5:
        nice = 1
    elif residual < 3:
        nice = 2
    elif residual < 7:
        nice = 5
    else:
        nice = 10
    step = nice * magnitude
    return _require_finite(step, "tick step")


def _round_tick(value: float, step: float) -> float:
    """Clean up float noise from ``index * step`` without collapsing genuinely distinct
    ticks to the same value when ``step`` itself has a tiny magnitude (a fixed
    ``round(value, 10)`` would do exactly that for e.g. a ``1e-300``-scale domain).
    """
    if value == 0:
        return 0.0
    decimals = max(10, -math.floor(math.log10(abs(step))) + 4)
    return round(value, decimals)


def _nice_linear_ticks(domain_min: float, domain_max: float, count: int) -> list[float]:
    """Generate round tick values spanning ``[domain_min, domain_max]`` (order-independent).

    Ticks are built by integer tick-index multiplication, not by repeatedly
    adding ``step`` to a running value. Cumulative addition can silently stop
    advancing once the running value is large enough that ``step`` is smaller
    than its float precision (ULP) — that would hang this function forever on
    perfectly ordinary data (e.g. a domain of microsecond-resolution
    timestamps, or large integer IDs), not just adversarial input. Index
    multiplication has no such failure mode and keeps the tick count
    structurally bounded to ~``count`` regardless of the domain's magnitude.
    """
    low, high = sorted((domain_min, domain_max))
    if low == high:
        return [low]
    span = _require_finite(high - low, "domain span")
    step = _nice_step(span / max(count, 1))
    start_index = math.ceil(low / step)
    # Algebraically (high + step*1e-9) / step, but computed this way so the
    # intermediate high + step*1e-9 never overflows for a high near float's max
    # (step*1e-9 would push it to inf even though high/step itself is fine).
    end_index = math.floor(high / step + 1e-9)
    end_index = max(end_index, start_index)
    ticks = [_round_tick((start_index + offset) * step, step) for offset in range(end_index - start_index + 1)]
    # At extreme domain magnitudes, step can be smaller than that magnitude's float
    # precision (ULP), making distinct tick indices round to the same float — dedup
    # while preserving order rather than showing repeated tick labels.
    return list(dict.fromkeys(ticks))


Scale = LinearScale | LogScale | CategoricalScale | TimeScale


_SUB_MONTH_STEPS = (
    1,
    2,
    5,
    10,
    15,
    30,  # seconds
    60,
    120,
    300,
    600,
    900,
    1800,  # minutes
    3600,
    7200,
    10800,
    21600,
    43200,  # hours
    86400,
    172800,
    259200,
    345600,
    604800,
    1209600,
    1814400,  # days and weeks
)
"""Tick intervals in seconds that a reader recognises, coarsest last.

Nice *numbers* are not nice *times*. Treating a timestamp as a plain number gives steps like
50,000 seconds, which lands ticks at 04:13 and 18:06 and forces every label to spell out a
time nobody chose. These are the intervals a clock and a calendar actually have -- and the
reason they stop at two weeks is that longer ones are not fixed durations: a month is 28 to
31 days and a year 365 or 366, so :func:`_calendar_ticks` steps those by field instead.

Three and four days are here because the ladder used to jump from two days to a week, and an
eleven-to-thirteen-day domain -- twelve daily rows, an ordinary shape -- fell into the gap:
the two-day step no longer fit inside ``count`` and the week step fit only once, so the axis
drew a **single** tick labelled ``00:00``, with the date nowhere in the file.

Three weeks is here for the same reason one rung up: 1 week to 2 weeks left 36 to 40 days with
only two ticks, because the two-week step fits twice and the month field has not taken over
yet. The gap moved rather than closed the first time it was patched.
"""

_LONGEST_FIXED_SPAN = 75 * 86400
"""Longest span still measured in fixed durations, in seconds -- about eleven weeks.

Eleven and not six: the month field needs three month boundaries inside the span before it
yields three ticks, and below that a 46-day chart came back with a single label. Beyond it the
calendar takes over. A month is not a fixed duration, so a span of several
months stepped by weeks drifts off the month boundaries and its labels have to spell out the
day; stepped by the month field it reads ``2024-02``, ``2024-03``."""

_MONTH_STEPS = (1, 2, 3, 6)
_YEAR_STEPS = (1, 2, 5, 10, 25, 50, 100, 250, 500, 1000)


_LOG_MANTISSAS = ((1,), (1, 3), (1, 2, 5), (1, 2, 3, 5, 7), tuple(range(1, 10)))
"""Ladders of leading digits, coarsest first, for a log axis too narrow for its decades alone.

Powers of ten are the ticks a reader expects on a log axis, and across several decades they
are all it needs. Inside one decade there is exactly one of them, which is not an axis -- so
the ladder subdivides, taking the first rung that clears :data:`_MIN_TICKS`. The rungs are
the round leading digits in the order a reader tolerates them: halves and fifths before
thirds and sevenths, and every digit only as a last resort.
"""


def _log_ticks(domain_min: float, domain_max: float, count: int) -> list[float]:
    """Ticks at round mantissas times powers of ten, spanning ``[domain_min, domain_max]``.

    Not :func:`_nice_linear_ticks` on the exponents: that would put ticks at 10**0.5, which is
    3.1622776601683795 and reads as noise on an axis whose whole point is round magnitudes.

    The count is a request, as everywhere else here. What is guaranteed is the floor: the
    ladder keeps subdividing until at least :data:`_MIN_TICKS` land inside the domain, so a
    domain of 3 to 9 gets an axis rather than a single ``10`` that is not even in it.
    """
    low, high = sorted((domain_min, domain_max))
    if low == high:
        return [low]
    first, last = math.floor(math.log10(low)), math.ceil(math.log10(high))
    best: list[float] = []
    for mantissas in _LOG_MANTISSAS:
        ticks = [
            value
            for exponent in range(first, last + 1)
            for mantissa in mantissas
            if low <= (value := mantissa * 10.0**exponent) <= high
        ]
        # ``sorted`` because a mantissa ladder walks decades in the outer loop, and the last
        # mantissa of one decade can exceed the first of the next only if the ladder is
        # malformed -- keeping the sort makes that impossible to depend on either way.
        best = sorted(dict.fromkeys(ticks))
        if len(best) >= _MIN_TICKS:
            return best
    # Even every leading digit was not enough, which means the domain spans less than one
    # round step -- 2 to 3 offers exactly two of them. Over a ratio that small a log axis is
    # visually almost a linear one (2..3 stretches by 1.5x end to end), so the linear ladder
    # both reaches ``_MIN_TICKS`` here and reads as round numbers rather than as 2.15443469.
    # Asked for more until it is enough, the way the month and year ladders above do. The
    # count is a request everywhere in this module, so passing ``_MIN_TICKS`` does not *get*
    # ``_MIN_TICKS`` -- a request of three over 1e-10..1.5e-10 comes back with two. The floor
    # is not a request, so it is reached by stepping rather than by asking once.
    requested = max(count, _MIN_TICKS)
    while requested <= 4 * _MIN_TICKS:
        ticks = _nice_linear_ticks(low, high, requested)
        if len(ticks) >= _MIN_TICKS:
            return ticks
        requested += 1
    return _nice_linear_ticks(low, high, requested)


_MIN_TICKS = 3
"""Below this an axis stops being an axis -- two labels name the ends and describe nothing
between them."""


def _aligned_ticks(low: datetime, high: datetime, count: int, *, unbounded: bool = False) -> list[datetime] | None:
    """Ticks on a recognisable clock interval, or ``None`` if the span is past two weeks.

    Aligned to the interval rather than to the domain's start: a reader looking for "the
    Tuesday" wants midnight, not midnight-plus-however-long-the-data-happens-to-start-after.

    The origin is the first day's midnight (the first of its month, for steps of a day or
    more), so alignment is exact against that origin and only *approximately* against later
    calendar boundaries -- a two-week step runs 01-01, 01-15, 01-29, 02-12, which is not the
    first of February. That is the price of a fixed duration, and it is why anything longer
    than two weeks is handed to :func:`_calendar_ticks` instead of extended here.
    """
    span = (high - low).total_seconds()
    # The candidate landing nearest ``count``, not the finest one that fits under it. "Fits
    # under" makes the ladder's own gaps into cliffs: a 36-day span puts 5.14 ticks on a weekly
    # step and 2.57 on a fortnightly one, and taking the fortnight because 5.14 is a shade over
    # five leaves a five-week chart with two labels. Nearest keeps the week.
    if span > _LONGEST_FIXED_SPAN and not unbounded:
        # Past about six weeks a month reads better than a count of weeks, and only
        # :func:`_calendar_ticks` can step by a field. Bounding the span rather than the tick
        # count is what keeps that hand-off at a fixed place: choosing by nearest count alone
        # would let three-week steps compete with months out to fifteen weeks.
        return None
    usable = [candidate for candidate in _SUB_MONTH_STEPS if span / candidate >= 1.0]
    if not usable:
        return None
    step = min(usable, key=lambda candidate: abs(span / candidate - count))
    # Aligned against local midnight of the first day rather than the Unix epoch, so a
    # 6-hour step lands on 00:00/06:00/12:00/18:00 wherever this runs.
    origin = low.replace(hour=0, minute=0, second=0, microsecond=0)
    if step >= 86400:
        origin = origin.replace(day=1)
    offset = (low - origin).total_seconds()
    first = origin + timedelta(seconds=step * math.ceil(offset / step))
    ticks, current = [], first
    # ``datetime.max`` is naive, and an aware domain cannot be compared with a naive value
    # at all -- the guard against stepping past representable time has to live in the same
    # awareness as the ticks it guards.
    limit = datetime.max.replace(tzinfo=low.tzinfo) - timedelta(seconds=step)
    while current <= high:
        ticks.append(current)
        if current > limit:
            # One more step would leave the representable range. Stopping is the same answer
            # as running out of domain, and raising ``OverflowError`` from inside a tick loop
            # is what ``_nice_step``'s docstring already promises this module does not do.
            break
        current += timedelta(seconds=step)
    return ticks


def _calendar_ticks(low: datetime, high: datetime, count: int) -> list[datetime]:
    """Ticks on whole months or whole years, for spans where a fixed interval cannot be one.

    Stepping by field rather than by duration is the whole point: 30-day steps drift a day per
    month, so a year of them lands on seven different days of the month instead of always the
    first.
    """
    months = (high.year - low.year) * 12 + high.month - low.month
    # Nearest to ``count`` rather than the first that fits, for the same reason as
    # :func:`_aligned_ticks`: a 46-day span holds one monthly tick and taking that because it
    # "fits" leaves a seven-week chart with a single label.
    # Months while a month step still reads, years past that -- decided by what the step
    # actually produces rather than by a span threshold, because "months" and "years" overlap:
    # 23 months is six-month steps, 30 years is decades, and a rule keyed off the span alone
    # put a two-year chart on the year path with two labels.
    step = min(_MONTH_STEPS, key=lambda candidate: abs(months / candidate - count)) if months >= 1 else None
    if step is not None and _MIN_TICKS - 1 <= months / step <= 2 * count:
        first = low.year * 12 + (low.month - 1)
        first += -first % step
        ticks = []
        while first // 12 <= MAXYEAR:
            moment = datetime(first // 12, first % 12 + 1, 1, tzinfo=low.tzinfo)
            if moment > high:
                return ticks
            if moment >= low:
                ticks.append(moment)
            first += step
        return ticks
    years = high.year - low.year
    # Nearest, not first-that-fits -- the same rule the two ladders above use, and for the
    # same reason those two spell out: a ladder with gaps in it turns "the first step that
    # fits under count" into a cliff. Measured with first-that-fits, spans of 251-275,
    # 501-725 and 1251-1475 years came back with **two** ticks, which this module's own
    # ``_MIN_TICKS`` calls not an axis. A 261-year span now picks 50 years, not 100.
    #
    # And then stepped down while the answer is still too sparse, because "nearest" is chosen
    # from ``years / candidate``, an estimate taken *before* aligning to the step -- alignment
    # can cost a tick at either end, which left 72-73 and 715-748 year spans degenerate for
    # start years that are not themselves round. The month ladder has carried the same guard
    # from the start; the year ladder was the one without it.
    step = _YEAR_STEPS[0]
    if years:
        step = min(_YEAR_STEPS, key=lambda candidate: abs(years / candidate - count))
        while step != _YEAR_STEPS[0] and len(_years_between(low, high, step)) < _MIN_TICKS:
            step = _YEAR_STEPS[_YEAR_STEPS.index(step) - 1]
    return _years_between(low, high, step)


def _years_between(low: datetime, high: datetime, step: int) -> list[datetime]:
    """New-year ticks every ``step`` years inside ``[low, high]``.

    ``year <= MAXYEAR`` first, because the loop's own test builds a ``datetime`` and
    ``datetime(10000, 1, 1)`` is a ``ValueError`` rather than a value past ``high``. A domain
    reaching 9999 rendered on ``main`` and has to keep rendering.
    """
    ticks, year = [], low.year + -low.year % step
    while year <= MAXYEAR and datetime(year, 1, 1, tzinfo=low.tzinfo) <= high:
        if datetime(year, 1, 1, tzinfo=low.tzinfo) >= low:
            ticks.append(datetime(year, 1, 1, tzinfo=low.tzinfo))
        year += step
    return ticks


def _same_instant(first: datetime, second: datetime) -> bool:
    """Whether two wall-clock readings name the same moment. ``False`` if either is past what
    the platform can place, since two unplaceable values cannot be shown to coincide."""
    if first == second:
        return True
    try:
        return first.timestamp() == second.timestamp()
    except (OverflowError, OSError, ValueError):
        return False


def _exists_locally(tick: datetime) -> bool:
    """Whether ``tick`` names a local reading that actually happens.

    ``fromtimestamp(t.timestamp())`` returns the instant the platform resolves ``t`` to, so a
    tick that comes back as something else was never a real local time — a spring-forward
    deletes an hour from the clock and the ladders here, stepping in wall-clock ``timedelta``,
    will offer one from inside the hole. An *ambiguous* time (the repeated hour in autumn)
    does round-trip: it happens twice rather than never.

    Aware ticks carry their offset, so no wall-clock reading of theirs is ever missing.
    """
    if tick.tzinfo is not None:
        return True
    try:
        return datetime.fromtimestamp(tick.timestamp()) == tick
    except (OverflowError, OSError, ValueError):
        # Past what the platform's local-time conversion can represent. Treated as real:
        # a tick it cannot resolve is also a tick it cannot collide with.
        return True


def _distinct_instants(ticks: list[datetime], bounds: tuple[float, float]) -> list[datetime]:
    """Drop a tick only when another tick already stands on its instant, or when it lands
    outside the axis.

    The defect this exists for is two differently-labelled ticks at **one pixel**: a
    non-existent 02:00 folds onto the real 03:00, and ``TimeScale`` places both at the same
    coordinate. Which tick to keep is decided by :func:`_exists_locally` — the real reading
    wins, whichever came first.

    Only on collision, and that qualifier is the whole point. An earlier version dropped every
    tick that failed the round trip, wherever it came from, which deleted **real days and
    years**: in a zone that transitions at midnight (Santiago, Beirut, Havana) a day-stepped
    axis lost a whole day, and Samoa's 1950 half-hour jump erased a *year* label from a
    two-century axis. Measured, those false drops outnumbered genuine collisions by 2.4x to
    13.6x — a worse fault than the one being fixed, and invisible to a test suite whose zones
    all transition at 02:00 or 03:00.

    ``bounds`` closes the other half. A non-existent tick with nothing to collide with used to
    survive and be drawn at whatever instant the clock resolved it to, which is not the instant
    its label names -- and when the gap pushes it past the end of the domain it leaves the axis
    entirely. A Santiago axis of 22:00-01:00 put its ``00:30`` label at x=1000 of a 0-800
    range, out of order with its neighbours.

    Only the ones that resolve outside the domain, so this does not become the unconditional
    filter above. Measured over the 1940-2035 transitions of ten zones, 54,673 proposed ticks:
    250 dropped for collision, 184 for landing outside, and **zero** dropped for any other
    reason. Santiago's 2024-09-08 and Apia's 1950 both stay.
    """
    kept: dict[float, datetime] = {}
    unplaceable: list[datetime] = []
    for tick in ticks:
        try:
            instant = tick.timestamp()
        except (OverflowError, OSError, ValueError):
            # Unplaceable, so uncollidable; ``TimeScale`` will report it if it matters. Held
            # in a list rather than keyed into ``kept``: the synthetic key this used to build
            # was ``len(kept) - 1e18``, and at that magnitude adding one changes nothing, so a
            # second such tick overwrote the first -- and the key sorted them both ahead of
            # every real instant.
            unplaceable.append(tick)
            continue
        if not bounds[0] <= instant <= bounds[1]:
            # Its label says one thing and the clock puts it somewhere else, far enough away
            # to leave the axis. There is no honest place to draw it.
            continue
        previous = kept.get(instant)
        if previous is None or (not _exists_locally(previous) and _exists_locally(tick)):
            kept[instant] = tick
    return [kept[instant] for instant in sorted(kept)] + unplaceable


def make_ticks(scale: Scale, count: int = 5) -> list[float] | list[str] | list[datetime]:
    """Generate "nice" tick positions for the given scale (no text-width measurement).

    ``CategoricalScale`` returns every category, in order — categorical axes
    show all labels rather than a sampled subset. ``count`` is a request, not a
    guarantee: the actual number returned can be slightly more or fewer (nice
    round steps rarely divide a domain into exactly ``count`` pieces), and may
    be smaller still after removing duplicate ticks at extreme magnitudes.

    Raises:
        TypeError: if ``scale`` isn't a ``LinearScale``, ``CategoricalScale``, or ``TimeScale``.
        ValueError: if ``count`` exceeds a sane upper bound.
    """
    if count > _MAX_TICK_COUNT:
        raise ValueError(f"count is too large: {count} (max {_MAX_TICK_COUNT})")
    if isinstance(scale, CategoricalScale):
        return list(scale.categories)
    if isinstance(scale, TimeScale):
        domain_min, domain_max = scale.domain
        if _same_instant(domain_min, domain_max):
            # Two different wall-clock readings of **one instant**: a domain that falls
            # entirely inside a spring-forward hole, where 02:00 and 03:00 are the same
            # moment. ``TimeScale`` maps every value in such a domain to the middle of its
            # range, so any ladder run over it puts every tick on one pixel no matter how
            # distinct the ticks are. One instant, one tick.
            return [domain_min]
        # Time is not a number line with prettier labels. See ``_SUB_MONTH_STEPS``.
        ticks = _aligned_ticks(domain_min, domain_max, count)
        if ticks is None:
            ticks = _calendar_ticks(domain_min, domain_max, count)
            if len(ticks) < _MIN_TICKS:
                # The seam between fixed durations and calendar fields, closed from the far
                # side. Wherever ``_LONGEST_FIXED_SPAN`` is put, spans just past it hold only
                # one or two month boundaries -- a 46-day chart came back with a single label
                # at 45 days, and moving the boundary to 75 moved the same gap to 76. Rather
                # than chase it, a calendar answer too sparse to read hands back to the
                # durations, which always have a step fine enough.
                relaxed = _aligned_ticks(domain_min, domain_max, count, unbounded=True)
                # Only if it is actually better. A 700-day span has one usable fixed step --
                # three weeks -- and thirty-three of those is not an improvement on two years.
                if relaxed and _MIN_TICKS <= len(relaxed) <= 2 * count:
                    ticks = relaxed
        # A span shorter than the finest step (one second) leaves nothing aligned inside it,
        # so the endpoints stand in. ``dict.fromkeys`` because they are the *same* endpoint
        # when the domain is a single instant -- one row, or several rows sharing a timestamp,
        # which ``datetime.now()`` makes the commonest case there is. Two ticks carrying the
        # same label is the defect this whole change exists to remove.
        # After every ladder, not inside one: the fold that makes two ticks share a pixel is
        # a property of the local clock, not of the step that produced them.
        ticks = _distinct_instants(ticks, (domain_min.timestamp(), domain_max.timestamp()))
        return ticks or list(dict.fromkeys([domain_min, domain_max]))
    if isinstance(scale, LogScale):
        domain_min, domain_max = scale.domain
        return _log_ticks(domain_min, domain_max, count)
    if isinstance(scale, LinearScale):
        domain_min, domain_max = scale.domain
        return _nice_linear_ticks(domain_min, domain_max, count)
    raise TypeError(f"unsupported scale type for make_ticks: {type(scale).__name__}")
