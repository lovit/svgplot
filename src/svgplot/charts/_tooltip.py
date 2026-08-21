"""A ``<title>`` child on a mark: the browser's own tooltip, and that mark's accessible name.

Five places already emit one -- three in ``_axes.py``, one in ``_legend.py``, one in
``treemap.py`` -- all under the same intent: *the visible text had to be shortened to fit, so
the full text is kept where it can still be read.* Each wrote the same call and each carried
its own version of the reasoning. This module owns the emission so the reasoning is in one
place and so the three rules below cannot be observed by four call sites and forgotten by the
fifth.

**A mark's ``<title>``, not the document's.** ``accessibility.py`` emits the chart's own
``<title>``/``<desc>`` -- the whole picture's accessible name and description -- and owns its
own rules for them, including refusing an empty one. Those two remaining ``tag="title"`` calls
in ``src/`` are deliberate, not stragglers.

**It is not only a tooltip.** A ``<title>`` is what SVG uses for an element's accessible name,
so a mark that has one becomes a named node in the accessibility tree. That is why a mark
whose text would draw nothing gets no ``<title>`` at all: an element with an *empty* accessible
name is worse off than one with no name, because assistive technology stops falling back. And
it is why a second one is refused rather than appended: only the first ``<title>`` of an
element is used, so a second is markup that renders, validates, and says nothing.

**Text that draws nothing is skipped, not refused.** Everything reaching here is a label out of
somebody's file, so a category named with a single tab is data, not a mistake -- raising would
turn that row into a chart that will not render.

**It has to be the first child.** Both the tooltip behaviour and the accessible name are
defined in terms of the element's *first* ``<title>`` child, so this inserts at the front
rather than appending. Every call site today adds it to a node with no other children, where
the two are the same thing -- which is exactly why nobody would notice the day one of them
stopped being true.

Charts that grow a value tooltip (#191's dependents) come through here too, and by convention
take a keyword-only ``tooltip: bool = False``. **False is the default and that is not a style
choice**: a ``<title>`` per mark is an element per mark, so a 60-cell heatmap would gain 60
elements and every existing user's output would change bytes for a feature they did not ask
for.

Private/internal -- not re-exported from ``svgplot.charts``.
"""

from __future__ import annotations

import unicodedata
import xml.etree.ElementTree as ET

from svgplot._svg import SvgDocument
from svgplot.charts._describe import fits
from svgplot.charts._layout import format_value_label

_TITLE_TAG = "title"

_BLANK_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Zs", "Zl", "Zp"})
"""Unicode categories a character can be in and still draw nothing.

``Cc`` control, ``Cf`` format (U+200B, U+2060, the direction marks), ``Cs`` surrogate,
``Zs``/``Zl``/``Zp`` the spaces. Named one by one rather than taken by ``C*``/``Z*`` prefix,
which would be shorter and wrong: ``Co`` is the private use area, where an icon font puts real
glyphs and legacy Korean encodings put real syllables, and ``Cn`` is unassigned, which a font
may still map. Both draw.

Three of the six cannot arrive through any caller and are here so the set is the whole idea
rather than the reachable part of it. ``Cs``: ``_svg.py`` refuses a lone surrogate at node
construction. ``Zl``/``Zp``: ``_fold_newlines`` collapses U+2028 and U+2029 to a plain space
before serialization, so they are read back as ``Zs``. No test pins those three and none can.

**And ``Cf`` over-refuses.** It holds characters Unicode says *must* be rendered -- the Arabic
prepended concatenation marks (U+0600-0605, U+06DD, U+070F), the interlinear annotation anchors
(U+FFF9-FFFB), the Egyptian format controls (U+13430-1343F) -- and a label made only of those
loses its full text here. ``Cf`` is not ``Default_Ignorable``; it is the nearest thing the
standard library exposes, which is the whole reason this is a list rather than that property.
"""


def has_visible_text(text: str) -> bool:
    """Whether ``text`` would put anything on screen.

    Not ``str.strip()``: that covers the separators and the ASCII controls, so it catches
    ``""``, ``"\\t"`` and even U+00A0 -- but it passes U+200B ZERO WIDTH SPACE and U+2060 WORD
    JOINER, which draw exactly as much as a space does, which is nothing. There is no principle
    under which a no-break space is not text and a zero-width space is.

    **It leans toward keeping the text, and does not manage it everywhere.** Getting this wrong
    loses information: the callers only reach here because a label was too long to show, so a
    string wrongly called invisible is one whose full text disappears from the file entirely.
    That is why :data:`_BLANK_CATEGORIES` is a list rather than a ``C*``/``Z*`` prefix -- the
    prefix form also swallows ``Co`` and ``Cn``, which draw. It is *not* leak-free: some ``Cf``
    characters draw too, and are refused where they should not be. :data:`_BLANK_CATEGORIES`
    names them.

    It cannot catch every invisible string, and the ones it misses are named rather than left
    to be rediscovered: U+3164 HANGUL FILLER and the jamo fillers U+115F/U+1160 are ``Lo``,
    letters alongside every Korean and CJK character; the variation selectors U+FE00-FE0F are
    ``Mn``, the category of a combining accent, which does draw; U+2800 BRAILLE PATTERN BLANK
    is ``So``, a symbol. Telling any of them from what shares their category needs the
    ``Default_Ignorable_Code_Point`` property, which the standard library does not expose, and
    a hand-kept list would be wrong the first time somebody found a character not on it.

    ``gallery/interaction.py`` asks the same question about a control's name and carries its own
    copy while these land as separate changes; whichever merges second should take this one.
    """
    return any(unicodedata.category(character) not in _BLANK_CATEGORIES for character in text)


def format_number(value: float) -> str:
    """A number as a tooltip should spell it: the shorter of two spellings, both exact.

    ``format_value_label`` is the first choice because it is how this package writes a value
    label -- ``30.0`` reads ``30`` rather than ``30.0``. It is a plain decimal literal, though,
    and ``1e308`` is 309 digits of one. That matters more here than anywhere else: a mark's
    ``<title>`` is its *accessible name*, so those digits are read out one at a time, and there
    is one ``<title>`` per mark rather than one per chart.

    So when the literal is longer than Python's own shortest round-trip ``repr``, the ``repr``
    wins -- which is only ever the case when the literal is expanding scientific notation back
    into digits. **Neither branch rounds.** An earlier version capped the length and fell back
    to ``%g``, which is six significant figures: measured over 10,000 uniform samples, 91% of
    ordinary values came out rewritten -- ``13.436424411240122`` became ``13.4364``. A tooltip
    that quietly rewrites the value it names is worse than a long one.
    """
    literal = format_value_label(value)
    exact = repr(float(value))
    return literal if len(literal) <= len(exact) else exact


def format_label(value: object) -> str | None:
    """A group label as a tooltip should spell it, or ``None`` if it should be left out.

    Numbers go through :func:`format_number` so one tooltip does not spell the same kind of
    value two ways -- a numeric ``hue=`` column would otherwise read ``x: 1 · group: 1.0``.

    ``None`` for a label that is unreadably long or draws nothing, and that bound is the point:
    a label reaches here once *per mark*, where the legend says it once.

    Measured before it existed, on 1,000 points whose ``x`` and ``y`` are ``0.0``..``999.0``
    and whose single hue group is named with 100,000 Hangul characters: **185,050 bytes with
    the tooltip off, 100,235,830 with it on** -- 542 times larger. The fixture is written out
    because a ratio without one is not a measurement.

    Left out rather than truncated, for the reason a column name is: half a label is a
    different label, and the mark still says its x and y.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        text = str(value)
        return text if fits(text) and has_visible_text(text) else None
    return format_number(float(value))


def add_tooltip(document: SvgDocument, node: ET.Element, text: str) -> ET.Element | None:
    """Give ``node`` a ``<title>`` child holding ``text``, and return it.

    ``None``, and no ``<title>``, when ``text`` would draw nothing. Not refused -- **the text
    here is data, not a caller's argument.** Every caller passes a label that came out of
    somebody's file, and a category whose name is a single tab is an ordinary thing to find in
    a CSV. Raising would turn that row into a chart that will not render at all.

    Emitting nothing is also the *stronger* reading of the rule this module exists for. A
    ``<title>`` is the mark's accessible name, and one containing only a tab is an empty
    accessible name -- worse than no name, because assistive technology stops falling back.
    Before this module, all five call sites emitted exactly that.

    Raises:
        ValueError: if ``node`` already has a ``<title>``. That one *is* a caller's mistake:
            only the first is used, so a second is markup that renders, validates and says
            nothing.
    """
    if not has_visible_text(text):
        return None
    if any(child.tag == _TITLE_TAG for child in node):
        raise ValueError(f"<{node.tag}> already has a <title>; only the first is used, so a second says nothing")
    title = document.add_text(node, text, tag=_TITLE_TAG)
    if node[0] is not title:
        # Appending is right only while the mark has no other children. Moved rather than
        # asserted, because a mark that grows a second child later would otherwise lose its
        # tooltip silently -- the markup stays valid and the browser simply shows nothing.
        node.remove(title)
        node.insert(0, title)
    return title
