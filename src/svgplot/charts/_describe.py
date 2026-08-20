"""The sentence a chart puts in its ``<desc>``.

Each chart knows what it drew; none of them should have to know how to phrase it. So
every chart calls :func:`describe` with its own kind and a handful of clauses built from
the helpers here, and the grammar — comma-separated clauses, one full stop, no line
breaks — lives in one place. That split is what the issue asked for: a short descriptor
per chart, one shared assembler.

Grammar
=======

``"<Kind>, <clause>, <clause>."`` — for example::

    Bar chart, 3 categories (Mon, Tue, Wed), values 0 to 9.
    Line chart, 2 series (north, south) over 10 points, x 1 to 5, y 3 to 20.

The kind comes first and is never omitted; the clauses are ordered size-before-range, so
a listener hears how much data there is before hearing what it spans.

Language
========

The sentence is **English**, matching the rest of this package's accessible text
(``accessibility.add_accessibility``'s fallback, ``Composition``'s figure description).
No ``lang``/``xml:lang`` is emitted with it, and that is deliberate rather than an
oversight: the sentence is genuinely mixed-language — its frame is English but the
category and series names inside it are the caller's own data, in whatever language they
wrote it — so stamping one language on the whole string would tell a screen reader to
pronounce the other half wrongly. Leaving it unstamped lets the host document's language
apply, which is the closest available truth.

Escaping
========

Nothing here escapes anything. The finished sentence is handed to
``accessibility.add_accessibility``, which passes it to ``_svg.add_text`` — the one
chokepoint that validates XML-forbidden characters and folds line breaks. A category name
containing a newline therefore reaches the ``<desc>`` folded to a space, exactly as the
same name reaches its tick label.

Bidirectional and zero-width control characters (U+202E, U+200B and friends) pass through,
because XML 1.0 permits them and the chokepoint's job is well-formedness, not typography.
That is the same policy the package already applies to ``<title>``, ``aria-label`` and every
tick label, so a name that reorders visually here reorders identically on the axis. Noted
so a later review does not re-derive it as a finding.

Private/internal — not re-exported from ``svgplot.charts``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from svgplot.charts._layout import format_coord

MAX_NAMES = 6
MAX_NAME_CHARS = 60
"""The two caps on a name list, applied together: at most six names, taking at most 60
characters between them (separators counted).

Why two. A count cap alone is not a bound — six names of 200 characters each is still six
names, and these names are the caller's own data, about which this package assumes
nothing. A character cap alone would list a dozen two-letter names, which is an inventory,
not a sentence a listener can hold. Each cap is the one that binds in the case the other
misses.

Where the numbers come from. A screen reader announces a description as one uninterrupted
utterance, with no way to skim it, so the limit is about what a listener can hold rather
than about file size — which puts the target near the 125-character guideline in common
use for alternative text. Measured over the 16 sentences pinned in
``tests/test_charts_describe.py``'s ``EVERY_CHART`` table, one chart of each type on
ordinary data: **35-102 characters, median 61.5**. A test recomputes those three figures
from that table, so they cannot drift out of date the way a number copied into prose does.

What the caps actually bound is the *names*, at :data:`MAX_NAME_CHARS` per list — one list
for fifteen chart types, two for ``heatmap``, which names columns and rows. Everything else
in the sentence is counts and value ranges, which grow only with their own **digits**, so a
chart with a thousand times more data gets a sentence a few characters longer, never a
thousand times longer. An adversarial search over name lengths 1-100 and category counts
7-12,345 put the longest ``heatmap`` sentence at **264 characters**; a test pins that
ceiling. Earlier drafts of this docstring quoted 222 as if it were the maximum, which it
was not — it was one sample.

What happens at the cap. Overflow is reported, never silently dropped: the listed names
are followed by ``and N more``. A name is never shortened — a half-name is a different
name — and the list is always a *prefix*, never a subset chosen by what happens to fit,
so what a listener hears first is what a reader sees first. If even the first name does
not fit, the parenthetical is dropped entirely and the clause is left as a bare count:
``"2 categories"`` says less than ``"2 categories (b)"`` but nothing misleading, whereas
listing the second name while dropping the first would."""

_IRREGULAR_PLURALS = {"category": "categories", "series": "series"}
"""Nouns this module uses whose plural isn't ``+s``. Small and closed on purpose: a
general pluralizer would be a lot of machinery for a fixed vocabulary of about a dozen
words, all of them chosen here rather than by a caller."""


def plural(count: int, noun: str) -> str:
    """``"1 category"`` / ``"3 categories"`` — a count and its noun, agreeing."""
    if count == 1:
        return f"1 {noun}"
    return f"{count} {_IRREGULAR_PLURALS.get(noun, noun + 's')}"


def _fitting(names: Sequence[str]) -> list[str]:
    """The prefix of ``names`` that fits inside both caps — see :data:`MAX_NAME_CHARS`."""
    listed: list[str] = []
    used = 0
    for name in names[:MAX_NAMES]:
        cost = len(name) + (2 if listed else 0)  # 2 for the ", " separator
        if used + cost > MAX_NAME_CHARS:
            break
        listed.append(name)
        used += cost
    return listed


def group(names: Sequence[str], noun: str) -> str:
    """``"3 categories (a, b, c)"``, capped — ``"9 categories (a, b, c, d, e, f and 3 more)"``.

    ``names`` is taken in the order the chart draws them, so what a listener hears first is
    what a reader sees first.
    """
    counted = plural(len(names), noun)
    listed = _fitting(names)
    if not listed:
        return counted
    remaining = len(names) - len(listed)
    inside = ", ".join(listed) + (f" and {remaining} more" if remaining else "")
    return f"{counted} ({inside})"


def fits(name: str) -> bool:
    """Whether a single caller-supplied string is short enough to read out.

    The same budget the name lists use, applied to the one clause that names something
    other than a category: ``scatterplot``'s ``size=`` column. Without it that clause was
    the only place a caller string reached the ``<desc>`` uncapped — measured, a
    500,000-character column name produced a 500,064-character description while every
    capped path stayed under 250.
    """
    return bool(_fitting([name]))


def over(series_names: Sequence[str] | None, count_clause: str) -> str:
    """``"2 series (north, south) over 10 points"``, or just ``"10 points"`` without ``hue=``.

    Six charts build this same clause. It lives here so the wording is decided once: a
    change of preposition should not be a change to six files.
    """
    if series_names is None:
        return count_clause
    return f"{group(series_names, 'series')} over {count_clause}"


def number(value: float) -> str:
    """A value as it reads aloud, using the same rounding the chart's own coordinates use.

    Falls back for anything ``format_coord`` refuses (a non-finite bound). A description
    is not worth failing a render over: by the time this is called the chart has already
    drawn, so raising here would turn a chart that renders into a chart that doesn't.

    Which is why the fallback is a fixed word rather than ``repr(value)``. ``repr`` of a
    large enough ``int`` raises on CPython's 4300-digit conversion limit, and ``repr`` of a
    caller's own object can raise or be arbitrarily long — either would break the promise
    this function exists to keep. No public path reaches it today (every chart forces its
    values through ``float()`` first), which is exactly why it must not be able to.
    """
    try:
        return format_coord(value)
    except ValueError:
        return "an unreportable value"


def moment(value: datetime) -> str:
    """A datetime as it reads aloud, dropping a midnight time-of-day that says nothing."""
    text = value.isoformat(sep=" ")
    return text.removesuffix(" 00:00:00")


def span(label: str, low: object, high: object) -> str:
    """``"x 1 to 5"`` / ``"x 2024-01-01 to 2024-03-01"`` — one axis's extent."""
    render = moment if isinstance(low, datetime) else number
    return f"{label} {render(low)} to {render(high)}"  # type: ignore[operator]


def describe(kind: str, *clauses: str | None) -> str:
    """Assemble the finished sentence. ``None``/empty clauses are dropped, not rendered
    as gaps, so a chart can pass an optional clause inline without branching around it.
    """
    parts = [kind, *(clause for clause in clauses if clause)]
    return ", ".join(parts) + "."
