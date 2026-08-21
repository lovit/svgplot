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

_TITLE_TAG = "title"


def _has_visible_text(text: str) -> bool:
    """Whether ``text`` would put anything on screen.

    Not ``str.strip()``: that covers the separators and the ASCII controls, so it catches
    ``""``, ``"\\t"`` and even U+00A0 -- but it passes U+200B ZERO WIDTH SPACE and U+2060 WORD
    JOINER, which draw exactly as much as a space does, which is nothing. There is no principle
    under which a no-break space is not text and a zero-width space is. ``C*`` is control and
    formatting characters, ``Z*`` is every kind of space.

    It cannot catch every invisible string. U+3164 HANGUL FILLER draws nothing too, but Unicode
    classifies it ``Lo`` -- a letter, alongside every Korean and CJK character -- and telling
    the letters that draw nothing from the letters that draw something needs the
    ``Default_Ignorable_Code_Point`` property, which the standard library does not expose.

    ``gallery/interaction.py`` asks the same question about a control's name and carries its own
    copy while these land as separate changes; whichever merges second should take this one.
    """
    return any(not unicodedata.category(character).startswith(("C", "Z")) for character in text)


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
    if not _has_visible_text(text):
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
