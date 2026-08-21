"""Controls a gallery page puts *around* an inlined chart, and the CSS that wires them up.

Nothing here reaches into the package. The charts are svgplot's ordinary output, unchanged;
what this module adds is markup in the host page and rules in the host page's ``<style>``.
That is the whole point of #185 having inlined the SVG: an ``<img>`` is a separate document
and a page's rules stop at its boundary, so none of this was possible against a referenced
file. There is still no JavaScript anywhere in the gallery.

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

Specificity, counted rather than assumed: the rule above is ``(1, 2, 1)`` -- one id, ``:not()``
contributing its argument's one class plus ``:is()`` contributing its widest argument's one
class, and one element name. The chart's own rule for the same elements is ``:where(.scope)
.series-1``, which is ``(0, 1, 0)`` because ``:where()`` contributes nothing. The page wins
without ``!important``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from xml.sax.saxutils import unescape

from svgplot.scope import validate_css_class_name

TOGGLE = "toggle"
"""The only control kind so far: one checkbox per series, all on to begin with."""

KINDS = (TOGGLE,)

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

_CLASS_ATTRIBUTE = re.compile(r'\bclass="([^"]*)"')
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


def resolve(figure: str, kind: str, svg: str) -> Controls:
    """Work out the controls ``figure`` should carry, from the chart it holds.

    What this refuses is a figure with no names to put on its controls -- a chart with no
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

    classes = series_classes(svg)
    labels = legend_labels(svg)
    # A blank label counts as missing, not as a name. An empty <label> gives the checkbox an
    # empty accessible name, which is worse than an unlabelled one: assistive technology stops
    # looking for a fallback. An empty hue value is an ordinary thing to find in real data.
    if not classes:
        raise ValueError(f"{figure}: the chart drew no series, so there is nothing to control")
    named = {index for index, label in labels.items() if label.strip()}
    missing = sorted(set(classes) - named)
    if missing:
        raise ValueError(
            f"{figure}: the chart has no legend entry for series {missing}, " f"so a control for it would have no name"
        )
    return Controls(
        figure=figure,
        kind=kind,
        series=tuple(Series(index=index, label=labels[index], classes=classes[index]) for index in sorted(classes)),
    )


def markup(controls: Controls) -> str:
    """The ``<input>``/``<label>`` pairs, as direct children of the figure and before its SVG.

    Real form controls rather than anything styled to look like one: a checkbox is reachable
    with Tab and operated with Space for free, and an element pretending to be one is not.
    """
    lines = []
    for series in controls.series:
        identifier = escape(controls.input_id(series), quote=True)
        lines += [
            f'      <input type="checkbox" class="series-toggle" id="{identifier}" checked="checked" />\n',
            f'      <label for="{identifier}">{escape(series.label)}</label>\n',
        ]
    return "".join(lines)


def css(controls: Controls) -> str:
    """The rules those controls drive: one per series, plus the matching label state."""
    rules = [f"      /* {controls.figure} */\n"]
    for series in controls.series:
        selector = f"#{controls.input_id(series)}:not(:checked)"
        targets = ", ".join(f".{name}" for name in series.classes)
        rules += [
            f"      {selector} ~ svg :is({targets}) {{ opacity: {DIM_OPACITY}; }}\n",
            f"      {selector} + label {{ opacity: 0.5; text-decoration: line-through; }}\n",
        ]
    return "".join(rules)


CHROME = """\
      /* Controls sit inside the figure element, before the chart, as its direct children:
         the sibling combinator in the generated rules depends on that, and a wrapper would
         quietly break every one of them. Left as native checkboxes -- a real control is
         reachable with Tab and operated with Space without anything here arranging it. */
      figure > .series-toggle { margin: 0 0.3rem 0.75rem 0; vertical-align: -0.1em; }
      figure > .series-toggle + label { margin-right: 1.1rem; font-size: 0.9rem; color: var(--muted); }
      .interaction-note { margin: 0 0 1.75rem; color: var(--muted); font-size: 0.9rem; }
"""
"""The part of the control CSS that does not vary, emitted only on pages that have controls.

Kept out of ``page.STYLE`` deliberately. ``STYLE`` is shared by all seventeen files, so a rule
added there rewrites every one of them -- which would put sixteen independent chart PRs into a
queue behind each other for no reason.
"""


def stylesheet(controls: list[Controls]) -> str:
    """The whole per-page addition: the chrome once, then one block per figure.

    Empty when the page has no controls, and that matters more than it looks: ``page.STYLE``
    ends in a newline, so appending nothing to it is byte-identical to what the gallery
    already commits.
    """
    if not controls:
        return ""
    return CHROME + "".join(css(control) for control in controls)
