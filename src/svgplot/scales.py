"""Data-domain to pixel-space scales.

Linear, categorical, and time scales plus "nice" tick generation. Datetime
x-values are handled here as a scale option rather than a separate chart
type (see docs/research/10-feature-matrix.md, "시간축 선"). Kept as a single
file until a concrete need for additional scale types (e.g. log) appears.

Tick generation deliberately avoids any text-width measurement (no font
renderer in pure SVG, see docs/research/12-aesthetics.md §3) — "nice" here
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
        residual = rough_step / magnitude
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


Scale = LinearScale | CategoricalScale | TimeScale


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
    604800,
    1209600,  # days and weeks
)
"""Tick intervals in seconds that a reader recognises, coarsest last.

Nice *numbers* are not nice *times*. Treating a timestamp as a plain number gives steps like
50,000 seconds, which lands ticks at 04:13 and 18:06 and forces every label to spell out a
time nobody chose. These are the intervals a clock and a calendar actually have -- and the
reason they stop at two weeks is that longer ones are not fixed durations: a month is 28 to
31 days and a year 365 or 366, so :func:`_calendar_ticks` steps those by field instead.
"""

_MONTH_STEPS = (1, 2, 3, 6)
_YEAR_STEPS = (1, 2, 5, 10, 25, 50, 100, 250, 500, 1000)


def _aligned_ticks(low: datetime, high: datetime, count: int) -> list[datetime] | None:
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
    step = next((candidate for candidate in _SUB_MONTH_STEPS if span / candidate <= count), None)
    if step is None:
        return None
    # Aligned against local midnight of the first day rather than the Unix epoch, so a
    # 6-hour step lands on 00:00/06:00/12:00/18:00 wherever this runs.
    origin = low.replace(hour=0, minute=0, second=0, microsecond=0)
    if step >= 86400:
        origin = origin.replace(day=1)
    offset = (low - origin).total_seconds()
    first = origin + timedelta(seconds=step * math.ceil(offset / step))
    ticks, current = [], first
    limit = datetime.max - timedelta(seconds=step)
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

    Stepping by field rather than by duration is the whole point: 30-day steps drift a day
    per month and turn a year of monthly ticks into twelve different days of the month.
    """
    months = (high.year - low.year) * 12 + high.month - low.month
    step = next((candidate for candidate in _MONTH_STEPS if months / candidate <= count), None)
    if step is not None:
        first = low.year * 12 + (low.month - 1)
        first += -first % step
        ticks = []
        while first // 12 <= MAXYEAR:
            moment = datetime(first // 12, first % 12 + 1, 1)
            if moment > high:
                return ticks
            if moment >= low:
                ticks.append(moment)
            first += step
        return ticks
    years = high.year - low.year
    step = next((candidate for candidate in _YEAR_STEPS if years / candidate <= count), _YEAR_STEPS[-1])
    # ``year <= MAXYEAR`` first, because the loop's own test builds a ``datetime`` and
    # ``datetime(10000, 1, 1)`` is a ``ValueError`` rather than a value past ``high``. A
    # domain reaching 9999 rendered on ``main`` and has to keep rendering.
    ticks, year = [], low.year + -low.year % step
    while year <= MAXYEAR and datetime(year, 1, 1) <= high:
        if datetime(year, 1, 1) >= low:
            ticks.append(datetime(year, 1, 1))
        year += step
    return ticks


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
        # Time is not a number line with prettier labels. See ``_SUB_MONTH_STEPS``.
        ticks = _aligned_ticks(domain_min, domain_max, count)
        if ticks is None:
            ticks = _calendar_ticks(domain_min, domain_max, count)
        # A span shorter than the finest step (one second) leaves nothing aligned inside it,
        # so the endpoints stand in. ``dict.fromkeys`` because they are the *same* endpoint
        # when the domain is a single instant -- one row, or several rows sharing a timestamp,
        # which ``datetime.now()`` makes the commonest case there is. Two ticks carrying the
        # same label is the defect this whole change exists to remove.
        return ticks or list(dict.fromkeys([domain_min, domain_max]))
    if isinstance(scale, LinearScale):
        domain_min, domain_max = scale.domain
        return _nice_linear_ticks(domain_min, domain_max, count)
    raise TypeError(f"unsupported scale type for make_ticks: {type(scale).__name__}")
