"""How wide a string will be, estimated without measuring a glyph.

This package has no font renderer (docs-research/12-aesthetics.md §3), so it cannot ask how
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

The glyphs whose real advance exceeds their class charge are listed individually in
:data:`_MEASURED`; see there for why a class-wide margin would be worse.

What the model is bounded on
============================

"No ASCII character exceeds its charge" is a claim about ASCII, and it does not extend past
it. Measured across Arial's whole BMP below U+3000, **558 characters still exceed their
charge**, the worst by a factor of 2.2031 (``\u0601``); in Tahoma 519 characters and 2.6268.
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
"""Charge for uppercase letters and digits. Above the measured worst case of the class once
:data:`_MEASURED` takes the outliers out -- ``Ŋ`` at 0.7231, then ``Ŗ Ĉ Ć`` and the ASCII
``C D H N R U`` at 0.7222. 0.72 sat under all of them."""

_NARROW_RATIO = 0.59
"""Charge for everything else. Above the measured worst case once :data:`_MEASURED` takes the
outliers out: ``+ < = > ~``, U+00AC and U+00D7, all at 0.584. 0.55 sat under those *and* under a digit's 0.556,
which is how a label of digits ran past the canvas edge."""

_MEASURED = {
    "@": 1.02,
    "Æ": 1.00,
    "Œ": 1.00,
    "W": 0.95,
    "œ": 0.95,
    "Ŵ": 0.95,
    "%": 0.89,
    "æ": 0.89,
    "¼": 0.84,
    "½": 0.84,
    "¾": 0.84,
    "M": 0.84,
    "m": 0.84,
    "G": 0.78,
    "O": 0.78,
    "Q": 0.78,
    "Ò": 0.78,
    "Ó": 0.78,
    "Ô": 0.78,
    "Õ": 0.78,
    "Ö": 0.78,
    "Ø": 0.78,
    "Ĝ": 0.78,
    "Ğ": 0.78,
    "Ġ": 0.78,
    "Ģ": 0.78,
    "Ĳ": 0.78,
    "Ō": 0.78,
    "Ŏ": 0.78,
    "Ő": 0.78,
    "©": 0.74,
    "®": 0.74,
    "w": 0.73,
    "ŵ": 0.73,
    "&": 0.67,
    "ď": 0.67,
    "¿": 0.62,
    "ß": 0.62,
    "ø": 0.62,
    "ŉ": 0.61,
}
"""Every character in :data:`_BOUNDED` whose real advance exceeds what its class is charged.

Adding a class-wide margin big enough to cover ``Œ`` (1.000) would charge every capital 1.0
against a mean of 0.677, and "Seoul Metropolitan" would truncate to a third. Forty literals
cover the whole tail instead: with them and the class charges above, **no character in ASCII,
Latin-1 Supplement or Latin Extended-A exceeds its charge in Arial or Helvetica** -- verified
against both fonts' ``hmtx`` tables, all 319 code points, zero remaining. Without ``W``'s
entry, ``W`` x40 runs 28px past the canvas edge (measured).

Rounded up to the nearest hundredth from the larger of the two fonts' advances, so each is
charged at least what it costs -- 0.95 against a measured 0.9438, 0.84 against 0.8330."""

_EM_WIDE_PUNCTUATION = frozenset("…—―─‥")
"""Punctuation charged a full em despite not being East Asian.

``…`` and ``—`` measure exactly 1.000 in Arial, Helvetica and Times Roman. The other three do
not, and the exceptions are worth stating rather than rounding off: ``―`` is 1.000 in Arial
and Helvetica and **absent from Times**; ``─`` is 0.7085 in Arial, 1.000 in Helvetica, absent
from Times; ``‥`` is absent from Arial and 0.667 in Helvetica. They are charged a full em
anyway -- they are box-drawing and CJK punctuation, they run to a full em in the fonts that
carry them, and over-charging truncates early rather than overflowing.

The ellipsis is the one that matters, because this module inserts it: charging it 0.55 made
every truncated label 0.45 em too long, which is 5px at the default legend size."""

_ELLIPSIS = "…"
"""One character rather than three dots, so the marker costs one slot rather than three --
though that one slot is a full em wide (see :data:`_EM_WIDE_PUNCTUATION`), not a narrow one."""

_BOUNDED = frozenset(chr(code) for code in list(range(0x20, 0x7F)) + list(range(0xA0, 0x180))) | _EM_WIDE_PUNCTUATION
"""The characters whose charge is known to be an upper bound on what they cost **in Arial or
Helvetica**.

Printable ASCII, Latin-1 Supplement and Latin Extended-A -- verified glyph by glyph against
both fonts' ``hmtx`` tables, all 319 of them -- plus the five punctuation marks charged a
full em, for 324. Latin-1 and Extended-A are in the set because European labels
(``São Paulo``, ``Bénéfice``, ``İstanbul``) are ordinary, and leaving them out would put a
``<title>`` on every one of them.

East Asian wide and fullwidth forms belong here too but are not listed: they are square by
the definition of fullwidth rather than by a measurement, so :func:`_is_bounded` tests them
by property.

The set is about *characters*, and the guarantee is also about *fonts*. ``theme.font_family``
is a public setting, and in Verdana ``÷`` measures 0.818 against a 0.59 charge, in Comic Sans
``Ĳ`` measures 1.127 against 0.78. That is what :data:`_TITLE_THRESHOLD` absorbs, for the
faces named there and no others.

Everything outside the set -- Cyrillic, Greek, Arabic, Hebrew, Devanagari, Thai -- is charged
by a class rule nobody measured it against, and keeps its full text unconditionally."""

_TITLE_THRESHOLD = 0.60
"""How close to the budget a **bounded** label may be estimated at before its full text is
preserved anyway, as a fraction of the budget.

Derived from the fonts, not chosen -- and the fonts it is derived from are named here,
because that list *is* the guarantee's scope:

=================  ==========================================  =========
family             worst ratio across **every weight it ships**  needs
=================  ==========================================  =========
SF NS              1.2430  (``¶``, Black Italic)                 <= 0.804
Trebuchet MS       1.1198  (``ŉ``, Bold)                          <= 0.893
Tahoma             1.3870  (``>``, Negreta)                       <= 0.721
Arial              1.4408  (``¶``, Black)                         <= 0.694
Geneva             1.4536  (``ŉ``)                                <= 0.688
Verdana            1.4698  (``>``, Bold)                          <= 0.680
Comic Sans MS      1.5068  (``Ĳ``, Bold)                          <= 0.664
**Helvetica / Helvetica Neue**  **1.5560**  (``―``, HN Medium)    <= 0.643
=================  ==========================================  =========

Every weight, not the regular one -- and for SF NS the nine named weights it ships, at the
font's default optical size, instanced from the variable font rather than read off its
``hmtx`` (which describes one point in a design space, not the weights).

Two things that scope deliberately leaves out, both checked and both harmless here. At the
small optical size a legend actually selects (``opsz=17``) the worst ratio rises to 1.3246,
and sweeping every named instance of the family -- 369 of them, including widths -- reaches
1.9953 on Extra Expanded Black. Neither disturbs the threshold: both stay under the 1.5560
that Helvetica Neue Medium already sets, and an expanded width is not reachable through
``font-family`` alone (it needs ``font-stretch``/``font-variation-settings``, which this
package does not emit). An earlier version of this table listed the regular face
of each family and put Arial at 1.0000 -- Arial Black runs ``¶`` at 1.4408, and Comic Sans
Bold at 1.5068 was the second-worst face in the whole set and absent from the table entirely.
The threshold happened to survive that, because the family whose *regular* face was worst is
also the family with the worst face overall; that is luck, not method.

A label estimated at fraction *f* of the budget renders at up to 1.5560 *f*, so it stays
inside only while *f* is under 0.643. 0.60 sits under that with room.

What that ratio decides is **when to attach a ``<title>``**, and only that. Truncation is a
separate rule that fills the budget to *f* near 1.0, so a label the estimate calls a fit can
still overflow in a family whose faces run wider than the estimate charges — measured,
``">" * 18`` in Verdana Regular is estimated at 116.8 px and renders at 162.0 px, 44 px past
the canvas, with its ``<title>`` correctly attached. **Visual containment is measured only for
Arial and Helvetica Regular**, the two the per-character table below is built from; for the
rest of the list the guarantee is that the text is never *lost*, because it is always in the
file.

**Outside this list the bound does not hold**, and it is a short list on purpose -- these are
what ``font-family: sans-serif`` resolves to plus the families a caller is likely to name.
Setting ``theme.font_family`` to something else voids it: Heiti SC needs 0.590, Songti SC
0.590, Ayuthaya 0.508. (DejaVu Sans Bold's 0.621 is *above* 0.60 and so already covered — it
is listed here as a near miss, not as a family the threshold fails.) Chasing those would mean titling nearly every
label, which trades a rare overflow for markup on all of them.

Two earlier answers were wrong the same way, each by measuring too small a set: 0.80 came
from Arial alone and Verdana overflowed it by 15px; 0.65 came from the stack above minus its
bold and medium faces, and Helvetica Neue Medium -- which the *default* family reaches --
overflowed that."""


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

    How close counts depends on how far the estimate can be wrong, and outside
    :data:`_BOUNDED` there is **no answer** -- not a larger margin, an absent one. A single
    character can be arbitrarily wide: ``⸻`` (U+2E3B) measures 2.493 em in the font macOS
    falls back to, so six of them estimate 38.9px against a 118px budget -- a third of it,
    comfortable by any fraction one might pick -- and render at 164.5px, 46px past the canvas
    edge. An earlier version of this function picked 0.35 and called it derived; it was
    derived from the glyphs the measured fonts happened to *have*, and the worst cases are
    exactly the ones they do not.

    So there is no threshold for unbounded text. It keeps its full text, always.
    """
    if not _is_bounded(text):
        return True
    return available > 0 and text_width(text, font_size) > available * _TITLE_THRESHOLD


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
