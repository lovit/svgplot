"""How wide a string will be, estimated without measuring a glyph.

This package has no font renderer (docs/research/12-aesthetics.md §3), so it cannot ask how
wide "매우 긴 카테고리 이름입니다" is at 11px. Every layout decision here is therefore made
from the string itself. That is an approximation, and the honest way to use one is to say
which way it errs and what it costs when it is wrong.

The model
=========

Each character is charged a fraction of the font size, from its Unicode properties. The
numbers are measured advances from Arial (``unitsPerEm=2048``), which is what ``sans-serif``
resolves to on the platforms this package is read on, and Helvetica agrees to three places:

============================  =======  =========================================
class                          charge   measured
============================  =======  =========================================
East Asian ``W``/``F``           1.00   square by construction
punctuation and dashes           1.00   ``…`` 1.000, ``—`` 1.000, ``―`` 1.000
uppercase and digits             0.73   ``A``-``Z`` mean 0.677, worst unlisted 0.722
                                        digits 0.556 (all ten identical)
everything else                  0.59   ``a``-``z`` mean 0.490, worst unlisted 0.584
============================  =======  =========================================

Both charges are the measured worst case of the class, not a round number near it. 0.55 sat
**below** a digit's 0.556 and below ``+ < = > ~`` at 0.584; 0.72 sat below ``C D H N R U`` at
0.722. Twenty-six ASCII characters were therefore charged less than they cost, which is the
one direction that overflows. At 0.59 and 0.73 **no ASCII character in Arial exceeds its
charge** -- verified against the font's own ``hmtx`` table, not asserted from memory.

``A`` (ambiguous) -- Greek, Cyrillic, box drawing, and the CJK punctuation that also appears
in Western text -- follows the same case rule. It renders wide only in a terminal font chosen
for CJK, which is not where an SVG lands.

Ten glyphs whose real advance exceeds their class charge are listed individually in
:data:`_MEASURED`; see there for why a class-wide margin would be worse.

What the model is bounded on
============================

"No ASCII character exceeds its charge" is a claim about ASCII, and it does not extend past
it. Measured across Arial's whole BMP below U+3000, **588 characters still exceed their
charge**, the worst by a factor of 2.20 (``\u0601``); in Tahoma 525 characters and 2.63.
Cyrillic ``Љ`` is charged 0.73 against 1.057, Arabic ``ص`` 0.59 against 1.098. No class-wide
number fixes that -- charging every unlisted character 2.2x would truncate Latin prose to a
third of its length for a script that is not on the page.

So the repertoire the estimate is *trusted* on is named explicitly, in :data:`_BOUNDED`, and
everything outside it keeps its full text far sooner -- see :func:`needs_full_text`. A label
in an unmeasured script may still be visually cut off by the ``viewBox``; what it may not be
is cut off with the text nowhere in the file.

**It will still be wrong in the harmless direction too** -- a label of nothing but ``i`` is
charged 0.59 against a real 0.222 and truncates sooner than it needed to, which costs room
and nothing else.
"""

from __future__ import annotations

import unicodedata

_WIDE_RATIO = 1.0
"""Charge for an East Asian wide/fullwidth form, and for the punctuation that is em-width."""

_CAPITAL_RATIO = 0.73
"""Charge for uppercase letters and digits. The measured worst case of the class once
:data:`_MEASURED` takes the outliers out: ``C D H N R U`` at 0.722, rounded up. 0.72 sat
just under them."""

_NARROW_RATIO = 0.59
"""Charge for everything else. The measured worst case once :data:`_MEASURED` takes the
outliers out: ``+ < = > ~`` at 0.584, rounded up. 0.55 sat under those *and* under a digit's
0.556, which is how a label of digits ran past the canvas edge."""

_MEASURED = {
    "@": 1.02,
    "W": 0.95,
    "%": 0.89,
    "m": 0.84,
    "M": 0.84,
    "G": 0.78,
    "O": 0.78,
    "Q": 0.78,
    "w": 0.73,
    "&": 0.67,
}
"""The handful of glyphs whose real advance exceeds what their class is charged.

Adding a class-wide margin big enough to cover ``W`` (0.944) would charge every capital
0.95 against a mean of 0.677, and "Seoul Metropolitan" would truncate a third early. Ten
literals cover the whole tail instead: with them and the class charges above, **no ASCII
character in Arial exceeds its charge**; without ``W``'s entry, ``W``x40 runs 28px past the
canvas edge (measured).

Rounded up from Arial's advances so each is charged at least what it costs -- 0.95 against a
measured 0.9438, 0.84 against 0.8330, and so on."""

_EM_WIDE_PUNCTUATION = frozenset("…—―─‥")
"""Punctuation measured at a full em in Arial/Helvetica/Times despite not being East Asian.
The ellipsis is here because this module inserts it: charging it 0.55 made every truncated
label 0.45 em too long, which is 5px at the default legend size."""

_ELLIPSIS = "…"
"""One character rather than three dots, so the marker costs one slot rather than three --
though that one slot is a full em wide (see :data:`_EM_WIDE_PUNCTUATION`), not a narrow one."""

_BOUNDED = frozenset(chr(code) for code in range(0x20, 0x7F)) | _EM_WIDE_PUNCTUATION
"""The characters whose charge is known to be an upper bound on what they cost.

Printable ASCII, verified glyph by glyph against Arial's ``hmtx``, plus the punctuation
measured at a full em. East Asian wide and fullwidth forms belong here too but are not
listed -- they are square by the definition of fullwidth rather than by a measurement, so
:func:`_is_bounded` tests them by property.

Everything else -- Cyrillic, Greek, Arabic, Hebrew, accented Latin -- is charged by a class
rule nobody measured it against, and is treated accordingly."""

_TITLE_THRESHOLD = 0.80
"""How close to the budget a **bounded** label may be estimated at before its full text is
preserved anyway, as a fraction of the budget.

Even inside the measured repertoire the estimate is not the render: it is an upper bound per
character, so a label near the budget can still land over it once the font's real advances
add up differently than assumed. Preserving the text above this fraction means the only
bounded labels with no fallback are the ones with room to spare."""

_UNMEASURED_THRESHOLD = 0.35
"""The same fraction for a label containing anything outside :data:`_BOUNDED`.

Derived rather than chosen. The worst measured underestimate outside ASCII is 2.20x in Arial
and 2.63x in Tahoma, so a label estimated at a fraction *f* of the budget can render at up to
2.63 *f* of it -- and stays inside only while *f* is under 1/2.63 = 0.38. 0.35 sits under
that with room for a font nobody measured.

This is what closes the hole 0.80 alone left open: ``ص`` x14 estimates 90.8px against a
118px budget, which 0.80 calls comfortable, and renders at 169.1px -- 51px past the canvas
edge, untruncated, with the text in no ``<title>`` either. Under 0.35 the same label keeps
its text. The cost is a ``<title>`` on non-Latin labels around a third of the budget, which
is invisible markup rather than a visible change."""


def _charge(char: str) -> float:
    if unicodedata.east_asian_width(char) in ("W", "F") or char in _EM_WIDE_PUNCTUATION:
        return _WIDE_RATIO
    if char in _MEASURED:
        return _MEASURED[char]
    if char.isupper() or char.isdigit():
        return _CAPITAL_RATIO
    return _NARROW_RATIO


def text_width(text: str, font_size: float) -> float:
    """Estimated rendered width of ``text`` in pixels."""
    return font_size * sum(_charge(char) for char in text)


def _is_bounded(text: str) -> bool:
    """Whether every character in ``text`` is charged at least what it really costs.

    Fullwidth forms are tested by property rather than membership: being one em wide is what
    ``east_asian_width`` reporting ``W``/``F`` means, so no per-font measurement applies.
    """
    return all(char in _BOUNDED or unicodedata.east_asian_width(char) in ("W", "F") for char in text)


def needs_full_text(text: str, font_size: float, available: float) -> bool:
    """Whether ``text``'s full form should be kept somewhere even if it was not truncated.

    True once the estimate is close enough to the budget that being wrong about it would put
    the label past the edge. Without this the bound the model relies on -- "shortening costs
    presentation, not information" -- holds only when the estimate errs *long*, which is the
    direction that already truncates. The dangerous direction is the other one, and it is the
    only one that loses the text rather than the look.

    How close counts depends on how far the estimate can be wrong, which is not one number:
    inside :data:`_BOUNDED` the charge is a measured ceiling, outside it the charge is a
    guess that measured 2.63x low at worst. Hence two thresholds.
    """
    threshold = _TITLE_THRESHOLD if _is_bounded(text) else _UNMEASURED_THRESHOLD
    return available > 0 and text_width(text, font_size) > available * threshold


def truncate_to_width(text: str, font_size: float, available: float) -> str:
    """``text`` shortened with an ellipsis until it is estimated to fit ``available``.

    Returns ``text`` unchanged when it already fits, so a chart whose labels are short --
    which is most of them -- emits exactly what it emitted before.

    An ``available`` too small for even the ellipsis returns the ellipsis anyway. Returning
    ``""`` would leave a swatch with nothing beside it, which reads as a rendering bug
    rather than as "there was more text here"; the ellipsis at least says something was cut.
    An *empty* label is the exception: nothing was cut, so saying so would be a lie.
    """
    if not text:
        return text
    if available <= 0:
        return _ELLIPSIS
    if text_width(text, font_size) <= available:
        return text
    budget = available - text_width(_ELLIPSIS, font_size)
    if budget <= 0:
        return _ELLIPSIS
    kept: list[str] = []
    used = 0.0
    for char in text:
        width = text_width(char, font_size)
        if used + width > budget:
            break
        kept.append(char)
        used += width
    return "".join(kept).rstrip() + _ELLIPSIS
