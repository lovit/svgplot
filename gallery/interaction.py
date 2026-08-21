"""Controls a gallery page puts *around* an inlined chart, and the CSS that wires them up.

Nothing here changes a chart. The charts are svgplot's ordinary output, unmodified; what this
module adds is markup in the host page and rules in the host page's ``<style>``. That is the
whole point of #185 having inlined the SVG: an ``<img>`` is a separate document and a page's
rules stop at its boundary, so none of this was possible against a referenced file. There is
still no JavaScript anywhere in the gallery.

The one thing it borrows from the package is ``scope.validate_css_class_name`` -- an internal
module, reached for deliberately. This file writes a caller-supplied name into a CSS selector,
which is the same question ``Chart.set_scope`` already answers, and a second pattern here
would be a second answer to it.

**Read the picture, do not describe it.** The series a chart drew, the classes each one
carries and the label the legend gave it are all *extracted from the rendered SVG*. An example
module says only *which* figures get controls. A hand-written list of series would be a second
copy of something the chart already decided, and the copy is the one that goes stale.

The mechanism is one selector shape -- ``#<figure>-toggle-1:not(:checked) ~ svg :is(.series-1,
.series-1-marker) { opacity: 0.15; }`` -- written inline rather than as an indented block
because ``ruff format`` reads an indented block after ``::`` as Python and turns the leading
``#`` of the id selector into a comment marker with a space after it.

It needs the ``<input>`` to be a *sibling before* the ``<svg>``, both direct children of
the ``<figure>``. Sibling rather than :has() on a wrapper, and that is not a style preference:
``~`` has no browser floor, while ``:has()`` does. Wrapping the controls in a ``<div>`` or a
``<fieldset>`` would break the sibling relation and force :has() back.

Specificity: the rule above is ``(1, 2, 1)`` -- one id, ``:not()`` contributing its argument's
one class plus ``:is()`` contributing its widest argument's one class, and one element name.
The chart's own rule for the same elements is ``:where(.scope) .series-1``, which is
``(0, 1, 0)`` because ``:where()`` contributes nothing. The page wins without ``!important``.

Both numbers were read off ``cssselect2`` rather than counted by hand, but **nothing in this
repository re-derives them yet**: the check that does needs ``cssselect2`` installed in CI,
which means a dependency change, which is a gate file. It is #214, and until it lands this
paragraph is a measurement someone took once rather than a property under test.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from html import escape
from xml.sax.saxutils import unescape

from svgplot.scope import validate_css_class_name

TOGGLE = "toggle"
"""One checkbox per series, all on to begin with. Needs a name per series, so it needs a legend."""

HOVER = "hover"
"""Emphasise the mark under the pointer. No markup at all -- rules only, nothing to operate.

One rule per series -- a toggle emits two, one to dim the marks and one to strike through the
label, and this has no label to strike. It needs no name either, so unlike :data:`TOGGLE` it
works on a chart with no legend: ``boxplot`` without ``hue=`` draws one series per category
(four categories, four series) and emits no legend for any of them, and that is a chart whose
marks can still be pointed at.

What it does *not* do is say anything: it is an affordance telling the reader "this one", and
the value it points at has to come from the mark's own ``<title>``.
"""

CELL = "cell"
"""Emphasise the mark under the pointer, on a chart whose marks are not series.

Same rule shape as :data:`HOVER` and a separate kind because the classes it points at come
from somewhere else. ``heatmap`` draws one class per *colour level*, so ``series_classes``
finds nothing and :func:`resolve` would refuse the figure -- and a per-level rule would be
wrong anyway: pointing at one cell would light every cell of the same shade, which is the
opposite of "this one" in a chart whose whole problem is that nine shades are hard to tell
apart.

So this points at the chart's own mark hook -- one class every mark carries and nothing else
does -- and emits **one** rule for the figure rather than one per series. :data:`MARK_CLASSES`
is the list of hooks it knows.
"""

FOCUS = "focus"
"""Pick **one** series to keep lit; the rest dim. A radio group, plus a way back.

The answer for a chart whose marks are strokes. ``lineplot`` draws ``fill: none``, so the whole
hit region of a series is its stroke -- two pixels of it under the presets the gallery uses, 2.5
under ``print`` and 3.2 under the ``poster`` context, none of which is a target. :data:`HOVER`
can be written there and will not be caught, and a tooltip has one element per series to hang on and the same problem reaching it. A
control the reader *operates* sidesteps the geometry entirely.

Radios rather than checkboxes because "focus one" is a single choice, and a radio group gives
that for free -- including the arrow-key behaviour, which a group of checkboxes does not have.
The cost is that a radio cannot be un-picked by clicking it again, so the group carries an
extra "all" option at index 0. Without it the reader can leave the default state and never get
back to it, which is a worse trap than the one this solves.

Dims rather than hides, for :data:`NOTE`'s reason -- and the same rules, so a page can say the
one thing about both kinds.
"""

KINDS = (TOGGLE, HOVER, CELL, FOCUS)

FOCUS_ALL = 0
"""The index of the "show everything" radio. Series are numbered from 1, so 0 is free."""

FOCUS_ALL_LABEL = "전체"
"""What the "show everything" radio is called.

The one control label this module writes rather than reads off the chart. Every other name
comes from the legend, because a name written here would be a second copy of something the
picture already decided; this one names a *state* the picture has no entry for.
"""

MARK_CLASSES = ("heatmap-cell",)
"""The mark hooks :data:`CELL` can point at, in the order it prefers them.

One entry today, and the reason is narrower than "heatmap is the only chart with a mark hook":
``scatterplot`` marks its points ``scatter-point``, ``violinplot`` its bodies ``violin-body``,
and several more do the same. ``heatmap`` is the one chart with a mark hook and **no series
classes**, so it is the one that :data:`HOVER` cannot serve. The hook carries no colour either
-- hand-recolouring a heatmap goes through the nine ``level-N`` rules, which is what that
module's docstring is about.

A chart with no hook this list knows cannot take this kind, and :func:`resolve` says so rather
than emitting a rule that matches nothing.
"""

DIM_OPACITY = "0.15"
"""What a switched-off series fades to. Not ``display: none`` -- see :data:`NOTE`."""

NOTE = (
    "체크를 끄면 시리즈가 사라지지 않고 흐려진다. 축·눈금·카테고리 밴드는 그릴 때 한 번 정해지고 "
    "다시 계산되지 않으므로, 감추면 남은 그림이 자기보다 넓은 축 위에 서게 된다. 흐리게 하는 것은 "
    '"이건 지금 보지 말라"는 말이고, 감추는 것은 "이 값은 없다"는 말이다 — 뒤쪽은 사실이 아니다.'
)
"""Why the controls dim rather than hide, in one place so sixteen pages cannot disagree.

The reasoning behind it, which the pages do not repeat: no chart in this package recomputes
its ticks, its category bands or its domain when a series is switched off, because nothing is
switched off at render time -- the geometry was decided once, when the file was written. So
``display: none`` would leave the survivors standing on an axis scaled for data that is no
longer drawn, which is a claim about a re-layout that did not happen. The ``<desc>`` is baked
at the same moment ("2 series (…)"), and hiding an element removes it from the accessibility
tree, so the description and the tree would disagree structurally. ``opacity: 0`` is worse
than either: invisible, still hit-testable, still read aloud.
"""

_BLANK_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Zs", "Zl", "Zp"})
"""Unicode categories a character can be in and still draw nothing.

``Cc`` control, ``Cf`` format (U+200B, U+2060, the direction marks), ``Zs``/``Zl``/``Zp`` the
spaces. Deliberately **not** ``Co`` (private use, where an icon font puts real glyphs and legacy
Korean encodings put real syllables) or ``Cn`` (unassigned, which a font may still map) -- both
draw, and a ``C*`` prefix would have swallowed them.

Three of the six cannot arrive through any caller and are here so the set is the whole idea
rather than the reachable part of it. ``Cs``: ``_svg.py`` refuses a lone surrogate at node
construction ("characters not allowed in XML 1.0"). ``Zl``/``Zp``: ``_fold_newlines`` collapses
U+2028 and U+2029 to a plain space before serialization, so they are read back as ``Zs``. No
test pins those three and none can -- said here rather than left as unexercised entries that
somebody later mistakes for measured ones.

**And one direction is not covered at all.** ``Cf`` holds characters Unicode says *must* be
rendered -- the Arabic prepended concatenation marks (U+0600-0605, U+06DD, U+070F), the
interlinear annotation anchors (U+FFF9-FFFB), the Egyptian format controls (U+13430-1343F) --
and this refuses a label made only of them. ``Cf`` is not ``Default_Ignorable``; it is the
closest category to it that the standard library exposes, which is the whole reason this list
exists rather than that property.
"""

_CLASS_ATTRIBUTE = re.compile(r'<[a-zA-Z][^>]*?\bclass="([^"]*)"')
"""Every ``class`` attribute in the picture -- anchored on a tag so *text* cannot supply one.

``xml.etree`` does not escape ``"`` in text content, so a category literally named
``class="heatmap-cell"`` renders as those characters inside a ``<text>`` element. Without the
``<tag`` anchor, :func:`resolve` accepted a ``cell`` control on a ``barplot`` carrying that
label and emitted a rule matching nothing -- which is the outcome the whole "read it from the
picture" rule exists to prevent. The anchor is not a parser: an attribute value containing
``>`` would still cut the match short. It is the cheap half of the fix, and the expensive half
(parsing) buys nothing here, because every generator of these files is this package.
"""
_SERIES_CLASS = re.compile(r"^series-(\d+)(?:-marker)?$")
# A legend row is a swatch element immediately followed by its label, and ``_legend.py``
# emits nothing between them. Anchoring on the label and looking *back* one element is what
# keeps a bar from being mistaken for a swatch: a mark is never the element directly before a
# legend label, but every swatch is. The optional <title> holds the untruncated text, which
# ``_legend.py`` adds whenever the label was shortened to fit the gutter -- so a long label
# reads here as what the author wrote, not as what fitted.
_LEGEND_ROW = re.compile(
    r'<(?:line|rect)\b[^>]*\bclass="([^"]*)"[^>]*/>\s*'
    r'<text\b[^>]*\bclass="[^"]*\blegend-text\b[^"]*"[^>]*>([^<]*)(?:<title>([^<]*)</title>)?'
)


@dataclass(frozen=True)
class Series:
    """One series of a rendered chart, as the chart itself drew it."""

    index: int
    label: str
    classes: tuple[str, ...]


@dataclass(frozen=True)
class Controls:
    """The controls one figure carries, resolved against the SVG that figure holds."""

    figure: str
    kind: str
    series: tuple[Series, ...]

    def input_id(self, series: Series) -> str:
        return f"{self.figure}-{self.kind}-{series.index}"


def series_classes(svg: str) -> dict[int, tuple[str, ...]]:
    """Every ``series-N`` class the chart actually emitted, grouped by series number.

    Read rather than assumed because one series is not always one class. ``boxplot`` draws its
    whisker with ``series-1`` and its box and outliers with ``series-1-marker`` -- the
    documented ``mark_style`` pairing in ``theme/css.py``, not a defect -- so a rule written
    against ``.series-1`` alone would dim half a box and leave the other half lit. Reading the
    picture means the rule cannot be told a series has fewer classes than it does.
    """
    found: dict[int, set[str]] = {}
    for attribute in _CLASS_ATTRIBUTE.findall(svg):
        for name in attribute.split():
            if match := _SERIES_CLASS.match(name):
                found.setdefault(int(match.group(1)), set()).add(name)
    return {index: tuple(sorted(names)) for index, names in sorted(found.items())}


def legend_labels(svg: str) -> dict[int, str]:
    """What the chart's own legend calls each series, in the legend's own order.

    A control labelled differently from the swatch beside it would be two names for one thing
    with nothing keeping them in step, so there is only one name and this is where it comes
    from.

    The text is **un-escaped on the way out**, because what is read here is markup: a series
    called ``R&D`` is in the file as ``R&amp;D``. Returned raw it would be escaped a second
    time when the label is written, and the page would show ``R&amp;D`` beside a swatch
    labelled ``R&D`` -- the two names this function exists to prevent. ``saxutils.unescape``
    rather than ``html.unescape``: it inverts exactly the three entities the serializer
    produces, where the HTML one also decodes references the serializer never writes and would
    turn a literal ``&notit;`` in someone's data into ``¬it;``.

    Whitespace is **kept**, not trimmed. Trimming looks harmless and is not: a legend label of
    ``"온라인 채널 "`` would come back a different string from the one the author wrote, and
    silently rewriting somebody's text is not this function's job. The one case where trimming
    would have helped -- an empty label, whose capture runs past ``</text>``'s pretty-printed
    newline and picks up the next line's indentation -- is handled where it belongs, in
    :func:`resolve`, which refuses a series whose name is blank.
    """
    labels = {}
    for classes, shown, full in _LEGEND_ROW.findall(svg):
        for name in classes.split():
            if match := _SERIES_CLASS.match(name):
                labels[int(match.group(1))] = unescape(full or shown)
    return labels


def _has_visible_text(label: str) -> bool:
    """Whether ``label`` puts anything on screen for a reader to read.

    Not ``str.strip()``. That covers the separators and the ASCII controls, so it refuses
    ``""``, ``"   "`` and even U+00A0 -- but it passes U+200B ZERO WIDTH SPACE and U+2060 WORD
    JOINER, which render as nothing and leave exactly the empty accessible name this check
    exists to refuse. There is no principle under which a no-break space is not a name and a
    zero-width space is.

    The categories are named one by one rather than taken by prefix. ``C*`` would have been
    shorter and is wrong: it also covers ``Co``, the private use area, where an icon font puts
    real glyphs -- measured, U+E000 was refused by the prefix form.

    **It does not catch every invisible label, and cannot.** Three kinds get through, recorded
    here rather than left to be rediscovered:

    * U+3164 HANGUL FILLER and the jamo fillers U+115F/U+1160, which Unicode classifies ``Lo``
      -- letters, alongside every Korean and CJK character.
    * The variation selectors, U+FE00-FE0F and U+E0100-E01EF, which are ``Mn`` -- the same
      category as a combining accent, which *does* draw.
    * U+2800 BRAILLE PATTERN BLANK, which is ``So``, a symbol.

    Telling any of them from what shares their category needs the
    ``Default_Ignorable_Code_Point`` property, which the standard library does not expose. A hand-kept list would be wrong the
    first time somebody found a character not on it. So what is refused here is a label made
    only of characters that are *by category* not part of a word; a label made of something
    that is a word by category and invisible in practice is somebody deliberately writing an
    invisible label, and this is not the place that catches it.
    """
    return any(unicodedata.category(character) not in _BLANK_CATEGORIES for character in label)


def resolve(figure: str, kind: str, svg: str) -> Controls:
    """Work out the controls ``figure`` should carry, from the chart it holds.

    The kinds that emit a named control -- ``toggle`` and ``focus`` -- are checked against the
    legend. ``hover`` and ``cell`` need no names, only rules.

    What a toggle refuses is a figure with no names to put on its controls -- a chart with no
    legend at all (a single series, or ``boxplot``'s per-category palette, which is not a
    legend). What it deliberately does **not** refuse is a chart whose legend names rows
    rather than groups: ``pieplot`` emits a swatch and a label per slice, exactly as a
    ``hue=`` chart does per group, so nothing in the rendered file distinguishes them. That
    "a toggle belongs only where ``hue=`` produced the series" is therefore an editorial
    judgement each page makes, not something this function can check -- and the reason it
    matters is that a toggle over rows reads as data editing rather than as a legend.

    ``figure`` is validated here even though every caller today gets it from
    ``Chart.set_scope``, which already refuses anything CSS-unsafe. That protection is real but
    accidental: it holds because ``example.load`` happens to call ``set_scope`` before this,
    and moving or dropping that line would silently leave ``css()`` interpolating an arbitrary
    string into a selector and a comment -- ``x{} body{background:red}`` breaks out of both.
    The package's own validator is reused rather than a second pattern written here, because a
    second pattern is a second answer to the same question.

    Raises:
        ValueError: if ``figure`` is not a usable CSS class name, if ``kind`` is not a known
            control kind, or if the chart has no usable legend entry for a series it drew.
    """
    validate_css_class_name(figure, kind="figure")
    if kind not in KINDS:
        raise ValueError(f"{figure}: unknown control kind {kind!r}, expected one of {KINDS}")

    if kind == CELL:
        # Read from the picture, like everything else here: a hook the emitter *believes* is
        # there produces a rule that matches nothing, and a rule that matches nothing looks
        # exactly like a figure whose author asked for no interaction.
        painted = {name for attribute in _CLASS_ATTRIBUTE.findall(svg) for name in attribute.split()}
        drawn = [name for name in MARK_CLASSES if name in painted]
        if not drawn:
            raise ValueError(f"{figure}: the chart draws no mark hook, so there is nothing to point at; tried {MARK_CLASSES}")
        return Controls(figure=figure, kind=kind, series=(Series(index=0, label="", classes=(drawn[0],)),))

    classes = series_classes(svg)
    labels = legend_labels(svg)
    if not classes:
        raise ValueError(f"{figure}: the chart drew no series, so there is nothing to control")
    # A label with nothing visible in it counts as missing, not as a name. An empty <label>
    # gives the checkbox an empty accessible name, which is worse than an unlabelled one:
    # assistive technology stops looking for a fallback. An empty hue value is an ordinary
    # thing to find in real data.
    if kind == FOCUS and len(classes) < 2:
        # Two radios that do the same thing: picking the one line dims nothing, and the page
        # still gets the note about dimming. An earlier version emitted that and called it the
        # page's business -- but the page guard refuses it (a labelled control with no rule),
        # so the module was documenting as allowed what the suite rejects. One of the two had
        # to move, and refusing is the half that cannot be wrong by accident.
        raise ValueError(f"{figure}: a focus group needs two series to choose between, and the chart drew {len(classes)}")
    if kind in (TOGGLE, FOCUS):
        named = {index for index, label in labels.items() if _has_visible_text(label)}
        missing = sorted(set(classes) - named)
        if missing:
            raise ValueError(
                f"{figure}: the chart has no legend entry for series {missing}, so a control for it would have no name"
            )
    return Controls(
        figure=figure,
        kind=kind,
        series=tuple(Series(index=index, label=labels.get(index, ""), classes=classes[index]) for index in sorted(classes)),
    )


def markup(controls: Controls) -> str:
    """The ``<input>``/``<label>`` pairs, as direct children of the figure and before its SVG.

    Real form controls rather than anything styled to look like one: a checkbox is reachable
    with Tab and operated with Space for free, a radio group adds arrow-key movement within it,
    and an element pretending to be either is not.

    **The group has no accessible name of its own.** A ``<fieldset>``/``<legend>`` or a
    ``role="radiogroup"`` wrapper would give one, and a wrapper is exactly what the sibling
    combinator in every generated rule cannot survive -- so a screen reader announces
    "전체, radio button, 1 of 3" without saying what is being chosen. Named here rather than
    left to be found: the per-control names are checked hard (see :func:`resolve`), and this is
    the one accessible name in the module that nothing checks because nothing can.

    Empty for a ``hover`` or ``cell`` figure: there is nothing to operate, only a rule.

    A ``focus`` figure emits radios sharing one ``name``, which is what makes them exclusive,
    plus the "all" radio that starts checked. ``name`` is the figure id rather than anything
    shorter because two focus figures on one page would otherwise be one group, and picking a
    line in the second would silently release the first.
    """
    if controls.kind == FOCUS:
        group = escape(f"{controls.figure}-focus", quote=True)
        first = escape(controls.input_id(Series(index=FOCUS_ALL, label="", classes=())), quote=True)
        lines = [
            f'      <input type="radio" class="series-focus" name="{group}" id="{first}" checked="checked" />\n',
            f'      <label for="{first}">{escape(FOCUS_ALL_LABEL)}</label>\n',
        ]
        for series in controls.series:
            identifier = escape(controls.input_id(series), quote=True)
            lines += [
                f'      <input type="radio" class="series-focus" name="{group}" id="{identifier}" />\n',
                f'      <label for="{identifier}">{escape(series.label)}</label>\n',
            ]
        return "".join(lines)
    if controls.kind != TOGGLE:
        return ""
    lines = []
    for series in controls.series:
        identifier = escape(controls.input_id(series), quote=True)
        lines += [
            f'      <input type="checkbox" class="series-toggle" id="{identifier}" checked="checked" />\n',
            f'      <label for="{identifier}">{escape(series.label)}</label>\n',
        ]
    return "".join(lines)


def css(controls: Controls, *, toggled_by: Mapping[int, str] | None = None) -> str:
    """The rules those controls drive: one per series, plus the matching label state.

    ``toggled_by`` maps a series number to the id of the checkbox that switches it, for the
    figures that carry a toggle *and* hover. **Without it the two kinds contradict each
    other**: the dim rule wins the ``opacity`` on its id, but nothing else sets a ``stroke`` at
    that weight, so pointing at a series the reader has switched off still draws a dark outline
    round it. Keying the hover rule on ``:checked`` makes the two mutually exclusive rather
    than merely ordered -- a switched-off series does not answer the pointer at all.
    """
    rules = [f"      /* {controls.figure} · {controls.kind} */\n"]
    if controls.kind in (HOVER, CELL):
        for series in controls.series:
            targets = ", ".join(f".{name}:hover" for name in series.classes)
            if toggled_by and (input_id := toggled_by.get(series.index)):
                rules.append(
                    f"      #{input_id}:checked ~ svg :is({targets})" " { opacity: 1; stroke: #16181d; stroke-width: 1.5; }\n"
                )
                continue
            # Keyed on the chart's scope class, which ``apply_scope`` puts on the root <svg>,
            # so this reaches one figure and not the next one down the page.
            #
            # ``opacity`` because the theme draws these marks at 0.75 and full opacity is a
            # change the reader sees without this file having to know a colour.
            #
            # The stroke is a fixed near-black rather than ``var(--fg)``, and what it has to
            # read against is the chart's own ``.plot-background`` -- an opaque rect the chart
            # paints over the whole canvas, so the page's ``--figure-bg`` never shows through.
            # That fill is ``#ffffff`` under every preset the gallery uses (none of the
            # examples pass ``theme=``). Under ``theme="dark"`` it is ``#1e1e1e`` and this
            # stroke would be invisible; a page wanting hover on a dark-preset chart needs its
            # own colour, and this rule does not try to guess one.
            rules.append(f"      .{controls.figure} :is({targets}) {{ opacity: 1; stroke: #16181d; stroke-width: 1.5; }}\n")
        return "".join(rules)
    if controls.kind == FOCUS:
        # One rule per radio, naming the *other* series -- so picking a line dims its
        # neighbours rather than dimming everything and lighting one back up. Two rules at the
        # same weight would work too and would read as an instruction to undo itself.
        #
        # The "all" radio gets no rule at all, which is what makes it the way back: nothing
        # matches, so nothing dims.
        for series in controls.series:
            others = [name for other in controls.series if other is not series for name in other.classes]
            targets = ", ".join(f".{name}" for name in others)
            rules += [
                f"      #{controls.input_id(series)}:checked ~ svg :is({targets})"
                f" {{ opacity: {DIM_OPACITY}; pointer-events: none; }}\n",
                # ``+``, not ``~``: a radio's own label is the element directly after it, while
                # ``~`` would reach every later label in the group. The toggle strikes through
                # the label of the series it switched off; this marks the one that is on,
                # because that is the smaller set and the one the reader is looking for.
                f"      #{controls.input_id(series)}:checked + label {{ font-weight: 600; color: var(--fg); }}\n",
            ]
        return "".join(rules)
    for series in controls.series:
        selector = f"#{controls.input_id(series)}:not(:checked)"
        targets = ", ".join(f".{name}" for name in series.classes)
        rules += [
            # ``pointer-events: none`` because ``opacity`` does not take an element out of hit
            # testing. Without it a switched-off series keeps swallowing the pointer for
            # everything drawn under it -- on the overlaid ``areaplot`` figure, series-2's fill
            # lies entirely inside series-1's, so switching series-2 off left series-1
            # unhighlightable everywhere below series-2's top edge, and its own ``<title>``
            # tooltip unreachable. A series the reader has switched off should not be in the
            # pointer's way at all.
            f"      {selector} ~ svg :is({targets}) {{ opacity: {DIM_OPACITY}; pointer-events: none; }}\n",
            f"      {selector} + label {{ opacity: 0.5; text-decoration: line-through; }}\n",
        ]
    return "".join(rules)


CHROME = """\
      /* Controls sit inside the figure element, before the chart, as its direct children:
         the sibling combinator in the generated rules depends on that, and a wrapper would
         quietly break every one of them. Left as native inputs -- a real control is reachable
         with Tab and operated with Space or the arrow keys without anything here arranging it. */
      .interaction-note { margin: 0 0 1.75rem; color: var(--muted); font-size: 0.9rem; }
"""
"""The part of the control CSS that is the same for every kind: the note's own rule.

Kept out of ``page.STYLE`` deliberately. ``STYLE`` is shared by all seventeen files, so a rule
added there rewrites every one of them -- which would put sixteen independent chart PRs into a
queue behind each other for no reason.
"""


_CONTROL_CHROME = {
    TOGGLE: """\
      figure > .series-toggle { margin: 0 0.3rem 0.75rem 0; vertical-align: -0.1em; }
      figure > .series-toggle + label { margin-right: 1.1rem; font-size: 0.9rem; color: var(--muted); }
""",
    FOCUS: """\
      figure > .series-focus { margin: 0 0.3rem 0.75rem 0; vertical-align: -0.1em; }
      figure > .series-focus + label { margin-right: 1.1rem; font-size: 0.9rem; color: var(--muted); }
""",
}
"""The per-kind half of the chrome, emitted only for the kinds a page actually uses.

Split off when ``focus`` arrived. Keeping it in :data:`CHROME` would have put two ``.series-focus``
rules on every page that has a checkbox -- eight files rewritten so that seven of them could
style an element they do not contain. The same argument that keeps :data:`CHROME` out of
``page.STYLE``, one level down.
"""


def stylesheet(controls: list[Controls]) -> str:
    """The whole per-page addition: the chrome once, then one block per figure.

    Empty when the page has no controls, and that matters more than it looks: ``page.STYLE``
    ends in a newline, so appending nothing to it is byte-identical to what the gallery
    already commits.

    The ``.interaction-note`` rule sits in :data:`CHROME` with the control chrome, so a page
    with only ``hover`` figures gets neither -- it has no note and no ``<input>`` to style.
    """
    if not controls:
        return ""

    kinds = {control.kind for control in controls}
    # The note explains dimming, which is what a toggle and a focus radio both do; a page whose
    # figures are all ``hover`` or ``cell`` has nothing to dim and gets neither.
    chrome = CHROME if kinds & {TOGGLE, FOCUS} else ""
    chrome += "".join(css for kind, css in _CONTROL_CHROME.items() if kind in kinds)
    # A figure that carries both kinds needs its hover rules keyed on its own checkboxes, so
    # they are collected here rather than inside ``css``, which sees one figure's one kind.
    toggles = {
        control.figure: {series.index: control.input_id(series) for series in control.series}
        for control in controls
        if control.kind == TOGGLE
    }
    return chrome + "".join(css(control, toggled_by=toggles.get(control.figure)) for control in controls)
