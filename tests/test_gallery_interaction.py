"""The gallery's no-JavaScript controls: what they are wired to, and what they must not do.

Every check here was watched failing before it was kept -- 29 mutations, one at a time. Four
are shaped specifically against ways this file could pass while asserting nothing:

* The page-level checks run over pages **rendered here**, never over the committed files. A
  disk-reading version stayed green when the note was made unconditional, because the files on
  disk had not changed -- it was measuring staleness, which ``test_gallery.py`` already does.
* Several of the pages here are built by :func:`_stub`. ``ecdfplot`` became the first real
  page to declare ``INTERACTIONS`` (#207), so the "a page with controls must ..." checks are no
  longer vacuous on their own -- but one page cannot cover the shapes that matter. What the
  stubs add is **controls on figures no committed page puts them on**: the *first* figure of a
  page (the sixteen chart pages leave example 1 alone so the index thumbnails stay put), and a
  chart whose series is two classes -- ``boxplot`` draws that shape on every one of its four
  committed figures, but none of them carries a control. A third shape, a label with characters
  that have to be escaped, comes from :func:`_one_example` rather than from a stub.
* ``test_a_rule_names_every_class_its_series_actually_has`` uses ``boxplot``, the one chart
  whose series is two classes. Against any other chart a rule that dropped ``-marker`` would
  look correct.
* The fixtures at the bottom use labels with characters in them -- ``R&D``, ``S<M``, the empty
  string. Everything above uses ``온라인``/``오프라인``, on which the correct implementation
  and a double-escaping one produce the same page. A review found the bug; 187 checks did not.
"""

from __future__ import annotations

import re
import sys
import types
import xml.etree.ElementTree as ET
from html import escape
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# ``gallery`` is repo-root source, not part of the installed package.
sys.path.insert(0, str(ROOT))

from gallery import interaction  # noqa: E402
from gallery.example import Page, load  # noqa: E402
from gallery.page import chart_page, index_page  # noqa: E402

from _svg_probe import blank_style_bodies  # noqa: E402

_SETUP = """
import svgplot as sp

SERIES = {
    "주": [1, 2, 3, 4] * 2,
    "매출": [120.0, 145.0, 98.0, 176.0, 84.0, 92.0, 110.0, 131.0],
    "채널": ["온라인"] * 4 + ["오프라인"] * 4,
}

QUARTERS = {
    "분기": ["1분기", "2분기", "3분기", "4분기"] * 2,
    "매출": [120.0, 145.0, 98.0, 176.0, 84.0, 92.0, 110.0, 131.0],
    "채널": ["온라인"] * 4 + ["오프라인"] * 4,
}
"""

_BAR = 'sp.barplot(QUARTERS, x="분기", y="매출", hue="채널")'
_BOX = 'sp.boxplot(QUARTERS, x="분기", y="매출", hue="채널")'

_TARGETABLE = "|".join([r"series-\d+(?:-[\w-]+)?", *(re.escape(name) for name in interaction.MARK_CLASSES)])
_CLASS_IN_SELECTOR = re.compile(rf"\.({_TARGETABLE})\b")
"""Every class the emitter is allowed to point at: a series, one of its marker twins, or a
chart's own mark hook. Built from :data:`interaction.MARK_CLASSES` rather than listing them
again -- a hook this pattern does not know about makes ``_page_rules`` return nothing for that
page, and the guard below then *fails* rather than skipping, because it cross-checks the empty
extraction against the page's own controls. Reverting this to the series-only pattern turns
``test_every_rule_reaches_the_figure_it_was_written_for[heatmap]`` red with "the page has hover
rules but none was extracted"."""


def _selected_classes(rules: str) -> set[str]:
    """Every ``series-*`` class the selectors in ``rules`` actually name.

    A set of whole tokens, because ``f".{name}" in rules`` -- the shape this replaced -- is a
    prefix match: ``".series-1"`` is inside ``".series-1-marker"``. Both directions of the
    boxplot check passed on the exact bug they were written against, one naming only
    ``.series-1-marker`` and one naming ``.series-1-nope``, a class no figure has.
    """
    return {match.group(1) for line in rules.splitlines() for match in _CLASS_IN_SELECTOR.finditer(line.split("{")[0])}


_BLOCK_HEADER = re.compile("/\\* (svgplot-[\\w-]+) \u00b7 (\\w+) \\*/")
_ONE_RULE = re.compile(r"([^{}]+)\{[^{}]*\}")


def _page_rules(html: str) -> list[tuple[str, str, str]]:
    """``(figure, kind, selector)`` for every series rule in the page's own stylesheet.

    Matched over the whole stylesheet rather than line by line, so the same CSS wrapped
    differently still parses -- the line-based version went to zero rules on every page, and
    silently, because the guard using it skips when it finds none.

    The page's ``<style>`` sits in ``<head>``; each chart's own is inside its ``<svg>`` and
    scopes itself with ``:where()``, and those rules are not what this is about. The chrome
    comes before the first ``/* figure \u00b7 kind */`` comment, so it is skipped by having no
    figure to belong to yet.
    """
    # Split on the block headers first rather than alternating comment-or-rule in one pattern:
    # a selector pattern permissive enough to match ``#id:not(:checked) ~ svg :is(.series-1)``
    # also matches the comment above it, and swallows it.
    parts = _BLOCK_HEADER.split(html.split("<figure>", 1)[0])
    rules = []
    for index in range(1, len(parts), 3):
        figure, kind, body = parts[index], parts[index + 1], parts[index + 2]
        rules += [
            (figure, kind, " ".join(match.group(1).split()))
            for match in _ONE_RULE.finditer(body)
            if _CLASS_IN_SELECTOR.search(match.group(1))
        ]
    return rules


def _stub(examples: list[tuple[str, str]], interactions: dict[int, str] | None = None, name: str = "stub") -> Page:
    """A gallery page built here rather than committed.

    Real pages declare ``INTERACTIONS`` now (``ecdfplot`` was the first, in #207), but only on
    the figures those pages happen to want. Building one here is how a check reaches a
    *controlled* figure that no committed page provides -- the first figure of a page, or a
    chart whose series is two classes -- without waiting for a chart PR that wants exactly
    that. Every call below passes ``_BAR`` or ``_BOX``, whose labels are ``온라인``/``오프라인``;
    the cases that need a label with something to escape build their own module through
    :func:`_one_example`.
    """
    module = types.ModuleType(name)
    module.TITLE = name
    module.SUMMARY = "a page built by the tests"
    module.REQUIRES = "x · y · hue"
    module.SETUP = _SETUP
    module.EXAMPLES = examples
    if interactions is not None:
        module.INTERACTIONS = interactions
    return load(module, name)


def _rendered() -> list[tuple[str, str]]:
    """Every gallery page as the generator would write it *now*, plus two built here.

    Generated rather than read off disk. Reading the committed files would make these checks
    measure whether ``docs/`` is stale -- which ``test_gallery.py`` already does, byte for
    byte -- instead of measuring the generator. Watched: making the note unconditional left
    the disk-reading version green, because the committed pages on disk had not changed.

    The built pages are what keeps the coverage from depending on which figures the real pages
    happen to want. Before ``ecdfplot`` declared ``INTERACTIONS`` (#207) they were the *only*
    thing standing between this file and passing over an empty set -- the shape of the
    ``<img src>`` check that survived the gallery losing every ``<img>`` (#185).
    """
    from gallery.build import discover  # imported here so a collection error names this file

    pages = [(page.name, chart_page(page)) for page in discover()]
    pages.append(("built-with-controls", chart_page(_stub([("bars", _BAR)], {1: "toggle"}))))
    # A page whose only interaction is hover. Without it, nothing separates "this page has
    # controls" from "this page has a toggle": every real page and every other stub has a
    # toggle, so emitting the dim note unconditionally reads as correct.
    pages.append(("built-with-hover-only", chart_page(_stub([("bars", _BAR)], {1: "hover"}))))
    pages.append(("built-with-two", chart_page(_stub([("bars", _BAR), ("boxes", _BOX)], {1: "toggle", 2: "toggle"}))))
    return pages


_PAGES = _rendered()


# ------------------------------------------------------------------ reading the picture


def test_the_series_a_control_gets_are_the_series_the_chart_drew() -> None:
    """The list of series is extracted, never declared. An example module says only *which*
    figure gets controls; a hand-written list would be a second copy of what the chart already
    decided, and the copy is the one that goes stale."""
    page = _stub([("bars", _BAR)], {1: "toggle"})
    (controls,) = page.examples[0].controls

    assert [series.index for series in controls.series] == [1, 2]
    assert {series.label for series in controls.series} == {"온라인", "오프라인"}


def test_a_rule_names_every_class_its_series_actually_has() -> None:
    """``boxplot`` draws one series as two classes: the whisker is ``series-N`` and the box and
    outliers are ``series-N-marker`` -- the documented ``mark_style`` pairing in
    ``theme/css.py``, not a defect. A rule written against ``.series-N`` alone dims the whisker
    and leaves the box lit, which looks like a rendering bug rather than a selector that was
    told half the truth.

    Asserted against the chart's own output rather than against the number two, so it stays
    true if a chart ever draws a series as three.
    """
    page = _stub([("boxes", _BOX)], {1: "toggle"})
    example = page.examples[0]
    drawn = interaction.series_classes(example.svg)
    rules = interaction.css(example.controls[0])

    assert drawn[1] == ("series-1", "series-1-marker"), "the fixture stopped being the two-class case"
    named = _selected_classes(rules)
    for classes in drawn.values():
        for name in classes:
            assert name in named, f"{name} is drawn but no rule dims it"
    assert named <= {name for classes in drawn.values() for name in classes}, "a rule names a class no figure has"


def test_a_control_is_named_by_the_legend_even_when_the_legend_shortened_it() -> None:
    """A label too long for the gutter is drawn with an ellipsis and keeps its full text in a
    ``<title>`` (``charts/_legend.py``). Taking the drawn text would put the ellipsis on the
    checkbox, where there is no width problem to solve and nothing to recover the rest from."""
    long_name = "온라인 채널 " * 6
    setup = f'import svgplot as sp\nD = {{"x": ["a", "b"], "y": [1.0, 2.0], "g": ["{long_name}", "오프라인"]}}\n'
    module = types.ModuleType("long")
    module.TITLE, module.SUMMARY, module.REQUIRES = "long", "s", "r"
    module.SETUP = setup
    module.EXAMPLES = [("long labels", 'sp.barplot(D, x="x", y="y", hue="g")')]
    module.INTERACTIONS = {1: "toggle"}
    page = load(module, "long")

    labels = {series.label for series in page.examples[0].controls[0].series}

    assert "…" in page.examples[0].svg, "the fixture stopped being the truncated case"
    assert long_name in labels, f"the control was named by the shortened text: {labels}"


def test_a_chart_with_no_legend_is_refused() -> None:
    """A control needs a name, and the legend is the only place one comes from.

    ``boxplot`` without ``hue=`` is the case worth naming: it rotates the palette per category,
    so it really does draw ``series-1``..``series-3`` -- but those are categories, and it emits
    no legend for them. Left unrefused, the page would get three checkboxes labelled nothing.
    """
    module = types.ModuleType("nolegend")
    module.TITLE, module.SUMMARY, module.REQUIRES = "nolegend", "s", "r"
    module.SETUP = _SETUP
    module.EXAMPLES = [("no hue", 'sp.boxplot(QUARTERS, x="분기", y="매출")')]
    module.INTERACTIONS = {1: "toggle"}

    with pytest.raises(ValueError, match="no legend entry"):
        load(module, "nolegend")


def test_one_figure_can_carry_a_toggle_and_hover_at_once() -> None:
    """They are different mechanisms, not alternatives: an ``<input>`` the reader operates, and
    a rule that answers the pointer. A figure wanting both should not have to pick.

    The single-kind spelling stays legal because most figures want one thing --
    :func:`test_a_single_kind_is_still_a_kind` holds that half.
    """
    page = _stub([("bars", _BAR)], {1: ("toggle", "hover")})
    controls = page.examples[0].controls
    rules = "".join(interaction.css(control) for control in controls)

    assert [control.kind for control in controls] == ["toggle", "hover"]
    assert ":not(:checked)" in rules and ":hover" in rules
    assert interaction.markup(controls[0]) and not interaction.markup(controls[1])


def test_the_markup_of_every_kind_reaches_the_page_not_just_the_first() -> None:
    """``markup`` returns ``""`` for hover, and every page written so far lists ``toggle``
    first, so the loop over ``example.controls`` could be a loop over ``controls[:1]`` and
    nothing would notice -- three spellings of that mutation, including reverting the change
    outright, left this file green. Declaring the kinds the other way round is what makes the
    second iteration the one that emits anything."""
    page = _stub([("bars", _BAR)], {1: ("hover", "toggle")})
    figure = chart_page(page)

    assert [control.kind for control in page.examples[0].controls] == ["hover", "toggle"]
    assert figure.count('type="checkbox"') == 2, "the toggle came second and its markup was dropped"


def test_a_switched_off_series_does_not_answer_the_pointer() -> None:
    """The two kinds on one figure would otherwise contradict each other. The dim rule carries
    an id so it wins ``opacity``, but it sets no ``stroke`` -- and the chart's own
    ``:where(.scope) .series-1`` is (0,1,0) against the hover rule's (0,3,0) -- so pointing at
    a series the reader switched off drew a dark outline round a ghost.

    Keyed on ``:checked``, the two selectors cannot both match, which is a stronger statement
    than winning the cascade: there is no state in which a rule for a hidden series applies.
    """
    page = chart_page(_stub([("bars", _BAR)], {1: ("toggle", "hover")}))
    hover = [selector for _figure, kind, selector in _page_rules(page) if kind == "hover"]

    assert hover, "the fixture stopped emitting hover rules"
    for selector in hover:
        assert ":hover" in selector, selector
        assert ":checked ~ svg" in selector and ":not(:checked)" not in selector, selector


def test_a_switched_off_series_is_out_of_the_pointer_s_way_entirely() -> None:
    """``opacity`` does not take an element out of hit testing. Without ``pointer-events: none``
    a dimmed series keeps swallowing the pointer for everything drawn under it, and on an
    overlaid ``areaplot`` figure that is not hypothetical: series-2's fill lies entirely inside
    series-1's, so switching series-2 off left series-1 -- still switched *on* -- unable to
    respond to the pointer anywhere below series-2's top edge, and its own ``<title>`` tooltip
    unreachable there.

    Read off the committed page rather than a stub, because the geometry is the reason.
    """
    areaplot = next(html for name, html in _PAGES if name == "areaplot")
    rules = [line for line in areaplot.split("<figure>", 1)[0].splitlines() if f"opacity: {interaction.DIM_OPACITY}" in line]

    assert rules, "the fixture stopped emitting dim rules"
    for line in rules:
        assert "pointer-events: none" in line, line


def test_hover_alone_is_not_keyed_on_a_checkbox_that_does_not_exist() -> None:
    """The other half: a hover-only figure has no ``<input>``, so a ``#id:checked`` prefix would
    be a selector that never matches and a figure that never responds."""
    page = chart_page(_stub([("bars", _BAR)], {1: "hover"}))
    hover = [selector for _figure, kind, selector in _page_rules(page) if kind == "hover"]

    assert hover, "the fixture stopped emitting hover rules"
    assert all(":checked" not in selector and ":hover" in selector for selector in hover), hover


def test_a_single_kind_is_still_a_kind() -> None:
    """A bare string is what fifteen of the sixteen pages will write, so it stays legal."""
    page = _stub([("bars", _BAR)], {1: "toggle"})

    assert [control.kind for control in page.examples[0].controls] == ["toggle"]


def test_a_list_of_kinds_is_a_sequence_of_kinds_too() -> None:
    """The declared contract is "a string or a sequence"; narrowing the check to ``tuple`` alone
    left every test green, because nothing passed a list with a valid kind in it."""
    page = _stub([("bars", _BAR)], {1: ["toggle", "hover"]})

    assert [control.kind for control in page.examples[0].controls] == ["toggle", "hover"]


@pytest.mark.parametrize(
    ("declared", "message"),
    [
        pytest.param((), "write no entry at all", id="empty-tuple"),
        pytest.param([], "write no entry at all", id="empty-list"),
        pytest.param(("toggle", "toggle"), "names a kind twice", id="repeated"),
    ],
)
def test_an_entry_that_asks_for_nothing_or_for_the_same_thing_twice_is_refused(declared: object, message: str) -> None:
    """A figure *listed* in ``INTERACTIONS`` asked for something. An empty sequence read as
    "nothing" is the silence the ``TypeError`` beside it exists to prevent, and a repeated kind
    builds a page with two ``<input>`` elements sharing one id -- which
    :func:`test_every_control_reference_resolves_on_its_own_page` cannot see, because it
    compares sets."""
    with pytest.raises(ValueError, match=message):
        _stub([("bars", _BAR)], {1: declared})  # type: ignore[dict-item]


@pytest.mark.parametrize(
    "declared", [pytest.param(True, id="bool"), pytest.param(3, id="int"), pytest.param(["toggle", 1], id="mixed")]
)
def test_an_interactions_value_that_is_not_a_kind_is_refused(declared: object) -> None:
    """``{2: True}`` is a plausible typo, and left alone it would emit nothing at all -- a
    figure quietly losing its controls looks exactly like a figure that never asked."""
    with pytest.raises(TypeError, match="a kind or a sequence of kinds"):
        _stub([("bars", _BAR)], {1: declared})


@pytest.mark.parametrize(
    ("kind", "refused"),
    [pytest.param("toggle", True, id="toggle"), pytest.param("hover", False, id="hover")],
)
def test_only_a_toggle_needs_the_chart_to_have_a_legend(kind: str, refused: bool) -> None:
    """The headline difference between the two kinds, and until this existed nothing checked it.

    A toggle needs a name per series and the legend is where names come from. Hover needs none
    -- there is nothing to label -- so it works on a chart that draws series without naming
    them. ``boxplot`` without ``hue=`` is exactly that: one series per category from the
    per-category palette -- four here, because the fixture has four -- and no legend for any
    of them.

    Written as one parametrized pair rather than two tests, because the claim is the
    *difference*: removing the ``kind == TOGGLE`` condition left the whole suite green, since
    the existing refusal test only used ``toggle`` and the hover page used a chart that has a
    legend anyway.
    """
    module = types.ModuleType(f"nolegend-{kind}")
    module.TITLE, module.SUMMARY, module.REQUIRES = "nolegend", "s", "r"
    module.SETUP = _SETUP
    module.EXAMPLES = [("no hue", 'sp.boxplot(QUARTERS, x="분기", y="매출")')]
    module.INTERACTIONS = {1: kind}

    if refused:
        with pytest.raises(ValueError, match="no legend entry"):
            load(module, "nolegend")
        return

    (controls,) = load(module, "nolegend").examples[0].controls

    # Four categories in the fixture, so four series from the per-category palette -- and no
    # legend for any of them, which is the state a toggle cannot use and hover can.
    assert [series.index for series in controls.series] == [1, 2, 3, 4]
    assert all(series.label == "" for series in controls.series), "hover names nothing, so it needs no name"


def test_a_hover_rule_names_every_class_its_series_actually_has() -> None:
    """The same reason the toggle rule does. ``boxplot`` draws a series as ``series-N`` plus
    ``series-N-marker``, so a rule against the first class alone emphasises the whisker and
    leaves the box flat -- which reads as a rendering bug rather than a selector that was told
    half the truth."""
    module = types.ModuleType("boxhover")
    module.TITLE, module.SUMMARY, module.REQUIRES = "boxhover", "s", "r"
    module.SETUP = _SETUP
    module.EXAMPLES = [("boxes", _BOX)]
    module.INTERACTIONS = {1: "hover"}
    example = load(module, "boxhover").examples[0]
    drawn = interaction.series_classes(example.svg)
    rules = interaction.css(example.controls[0])

    assert drawn[1] == ("series-1", "series-1-marker"), "the fixture stopped being the two-class case"
    named = _selected_classes(rules)
    for classes in drawn.values():
        for name in classes:
            assert name in named, f"{name} is drawn but nothing emphasises it"
    assert named <= {name for classes in drawn.values() for name in classes}, "a rule names a class no figure has"


_HEATMAP = 'sp.heatmap({"c": ["a", "b"], "r": ["p", "p"], "v": [1.0, 2.0]}, x="c", y="r", values="v")'


def test_a_cell_kind_points_at_the_chart_s_mark_hook() -> None:
    """``heatmap`` draws one class per colour *level*, so it has no series to point at -- and a
    per-level rule would be the wrong thing anyway: pointing at one cell would light every cell
    of the same shade, in a chart whose whole problem is that nine shades are hard to tell
    apart. One rule for the figure, keyed on the hook every cell carries."""
    page = _stub([("cells", _HEATMAP)], {1: "cell"})
    (controls,) = page.examples[0].controls
    rules = [selector for _f, kind, selector in _page_rules(chart_page(page)) if kind == "cell"]

    assert [series.classes for series in controls.series] == [("heatmap-cell",)]
    assert len(rules) == 1, rules
    assert ".heatmap-cell:hover" in rules[0]
    assert not interaction.markup(controls), "a cell rule has nothing to operate"


def test_a_cell_hook_is_read_from_a_tag_not_from_the_text() -> None:
    """``xml.etree`` does not escape ``"`` in text content, so a category literally named
    ``class="heatmap-cell"`` renders as those characters inside a ``<text>``. Scanning the file
    for the string accepted a ``cell`` control on that ``barplot`` and emitted a rule matching
    nothing -- the outcome the "read it from the picture" rule exists to prevent."""
    decoy = 'sp.barplot({"q": [\'class="heatmap-cell"\', "Q2"], "v": [1.0, 2.0]}, x="q", y="v")'

    with pytest.raises(ValueError, match="draws no mark hook"):
        _stub([("decoy", decoy)], {1: "cell"})


def test_a_cell_kind_on_a_chart_with_no_mark_hook_is_refused() -> None:
    """A hook the emitter *believes* is there produces a rule that matches nothing, and a rule
    that matches nothing looks exactly like a figure whose author asked for no interaction."""
    with pytest.raises(ValueError, match="draws no mark hook"):
        _stub([("bars", _BAR)], {1: "cell"})


def test_a_cell_page_gets_no_control_chrome_and_no_note() -> None:
    """Both belong to the toggle: the chrome styles ``<input>``/``<label>`` pairs a cell page
    has none of, and the note explains why a switched-off series is dimmed rather than hidden,
    which is not a thing this page does."""
    page = chart_page(_stub([("cells", _HEATMAP)], {1: "cell"}))

    assert "figure > .series-toggle" not in page
    assert "interaction-note" not in page
    assert ":hover" in page, "and the rule itself is still there"


_HOVER_PAGES = frozenset({"areaplot", "gaugeplot", "kdeplot", "radarplot", "scatterplot"})
"""The committed pages that declare ``hover``, by name rather than by count.

A count decays. The bar was ``>= 3`` while ``areaplot`` and ``scatterplot`` were the only two,
so it made ``radarplot``'s hover load-bearing -- and then ``gaugeplot`` merged and made three
without it, at which point deleting the hover this page exists to demonstrate left the whole
suite green. Named, a page cannot lose its hover behind a sibling gaining one.
"""

_TWINS = [
    pytest.param("kdeplot", 3, 5, id="kdeplot"),
    pytest.param("radarplot", 2, 3, id="radarplot"),
]
"""Pages that draw the *same* curves twice, differing only in ``fill=``: ``(page, filled,
unfilled)``, 1-based.

``kdeplot``'s pair is not adjacent -- figure 4 sits between them, differing by ``bandwidth=``
rather than by ``fill=`` -- which is why the numbers are written out rather than inferred."""


def _series_fill(markup: str, number: int) -> str | None:
    """The fill of series ``number``, read from the rules its *drawn* classes actually carry.

    Not ``.series-1`` alone. ``boxplot`` draws one series as two classes -- the whisker is
    ``series-N`` with ``fill: none`` and the box is ``series-N-marker`` with a real fill -- so
    reading the first rule calls a boxplot unhittable, when its box is the easiest mark on the
    page to land on. That is this file's own ``mark_style`` lesson, committed one test lower
    down.

    Intersected with the classes the figure *draws*, not with the rules it emits: ``kdeplot``
    and ``radarplot`` under ``fill=False`` emit a ``.series-N-marker`` rule with a fill and then
    draw no marker element at all, so "any rule with a fill" calls them filled. Both directions
    have a trap and only the intersection avoids both.
    """
    drawn = {name for name in interaction.series_classes(markup).get(number, ()) if name}
    for css_class in drawn:
        rule = re.search(rf"\.{re.escape(css_class)} \{{[^}}]*\}}", markup)
        if rule and "fill: none" not in rule.group(0):
            return rule.group(0)
    return None


@pytest.mark.parametrize("html", [pytest.param(html, id=name) for name, html in _PAGES])
def test_hover_is_only_declared_where_the_pointer_can_reach_the_mark(html: str) -> None:
    """A ``:hover`` rule on a mark the pointer cannot land on is an affordance drawn for
    something that does not respond. The chart's own CSS decides: a series whose every drawn
    class is ``fill: none`` leaves the 2px stroke as its whole hit region, while a filled one
    answers anywhere inside it.

    ``radarplot`` and ``kdeplot`` each draw the *same* curves both ways, so on those pages the
    difference is one argument. That makes "put hover on the filled figure and not the unfilled
    one" an editorial judgement no emitter can check -- ``resolve`` sees series either way --
    which is why this is asserted against the **chart's own output** rather than against the
    page's declaration.

    One direction only. The converse is not a rule: a filled figure without hover is a page that
    demonstrated the contrast once instead of everywhere it could.

    ``cell`` is deliberately out of scope. Its target is a chart's mark hook rather than a
    series, and a hook carries no fill of its own -- ``heatmap-cell``'s colour comes from the
    nine ``level-N`` rules -- so there is no rule here to read. The hook exists on filled rects
    by construction.
    """
    hovered = {figure for figure, kind, _selector in _page_rules(html) if kind == "hover"}
    if not hovered:
        pytest.skip("this page declares no hover")

    for markup in re.findall(r"<figure>.*?</figure>", html, re.S):
        scope = re.search(r'class="(?:[^"]* )?(svgplot-[\w-]+)(?: [^"]*)?"', markup)
        assert scope, f"a figure carries no readable scope class:\n{markup[:200]}"
        if scope.group(1) not in hovered:
            continue
        for number in interaction.series_classes(markup):
            fill = _series_fill(markup, number)
            assert fill, f"{scope.group(1)}: hover on series {number}, whose every drawn class is fill: none"


@pytest.mark.parametrize(("page", "filled", "unfilled"), _TWINS)
def test_the_fill_twins_differ_in_hover_and_not_in_toggle(page: str, filled: int, unfilled: int) -> None:
    """The claim these pages exist to make, pinned per page rather than counted.

    Both twins carry a toggle -- that is the contrast; without it the pair degrades to "one has
    controls and one does not", which is a weaker statement that looks the same in a screenshot.
    Only the filled one carries hover.

    Named here rather than left to the parametrized guard above, which checks one direction on
    every page and structurally cannot say "this page still declares hover at all".
    """
    html = next(markup for name, markup in _PAGES if name == page)
    rules = _page_rules(html)
    hovered = {figure for figure, kind, _selector in rules if kind == "hover"}
    toggled = {figure for figure, kind, _selector in rules if kind == "toggle"}

    assert hovered == {f"svgplot-{page}-{filled}"}, hovered
    assert {f"svgplot-{page}-{filled}", f"svgplot-{page}-{unfilled}"} <= toggled, toggled


def test_the_pages_that_declare_hover_are_the_ones_that_should() -> None:
    """The set, not a count. ``>= 3`` was true of ``areaplot``/``gaugeplot``/``scatterplot``
    alone, so it stopped protecting the page it was written for the moment a sibling PR added a
    hover page -- and one did, between this being written and being reviewed.

    Committed pages only: ``_PAGES`` also holds the stubs this file builds, one of which is
    hover-only, so a bar counted over all of them is met by fixtures the test made itself.
    """
    with_hover = {
        name
        for name, html in _PAGES
        if not name.startswith("built-") and any(kind == "hover" for _f, kind, _s in _page_rules(html))
    }

    assert with_hover == _HOVER_PAGES, f"{sorted(with_hover ^ _HOVER_PAGES)} changed"


_LINES = 'sp.lineplot(SERIES, x="주", y="매출", hue="채널")'


def test_a_focus_group_dims_the_others_rather_than_lighting_the_one() -> None:
    """Picking a line emits *one* rule naming the series it did not pick. Dimming everything and
    lighting one back up would need two rules at the same weight and would read as an
    instruction to undo itself.

    Same ``opacity`` and the same ``pointer-events`` as a toggle, so the page's one note about
    dimming covers both kinds."""
    page = _stub([("lines", _LINES)], {1: "focus"})
    (controls,) = page.examples[0].controls
    # Straight from the emitter: ``_page_rules`` keeps only rules that name a series class, and
    # the label half deliberately names none.
    selectors = [line.split("{")[0].strip() for line in interaction.css(controls).splitlines() if "{" in line]

    dim = [selector for selector in selectors if "~ svg" in selector]
    marked = [selector for selector in selectors if "+ label" in selector]

    assert dim == [
        "#svgplot-stub-1-focus-1:checked ~ svg :is(.series-2)",
        "#svgplot-stub-1-focus-2:checked ~ svg :is(.series-1)",
    ]
    # ``+``, not ``~``: a radio's own label is the element directly after it, and ``~`` would
    # reach every later label in the group -- so picking the first would mark all of them.
    assert marked == ["#svgplot-stub-1-focus-1:checked + label", "#svgplot-stub-1-focus-2:checked + label"]


def test_the_all_radio_is_checked_and_has_no_rule() -> None:
    """A radio cannot be un-picked by clicking it again, so without this the reader leaves the
    default state and never gets back. It carries no rule *because* nothing matching is what
    returns the figure to undimmed -- an "all" that had its own rule would be a third state."""
    html = chart_page(_stub([("lines", _LINES)], {1: "focus"}))
    radios = re.findall(r"<input[^>]*type=\"radio\"[^>]*>", html)
    keyed = set(re.findall(r"#([\w-]+):checked", html))

    assert len(radios) == 3, "one per series plus all"
    assert 'id="svgplot-stub-1-focus-0"' in radios[0] and 'checked="checked"' in radios[0]
    assert all('checked="checked"' not in radio for radio in radios[1:]), "only all starts checked"
    assert "svgplot-stub-1-focus-0" not in keyed


def test_two_focus_figures_on_one_page_are_separate_groups() -> None:
    """Radios are exclusive within a ``name``. Sharing one across figures would make picking a
    line in the second silently release the first, which looks like the page losing its state
    for no reason a reader can see."""
    html = chart_page(_stub([("first", _LINES), ("second", _LINES)], {1: "focus", 2: "focus"}))
    groups = set(re.findall(r'<input[^>]*type="radio"[^>]*name="([^"]*)"', html))

    assert groups == {"svgplot-stub-1-focus", "svgplot-stub-2-focus"}


def test_a_focus_control_is_named_by_the_legend_like_a_toggle() -> None:
    """The same refusal a toggle gets: a chart with no legend entry for a series it drew would
    give that radio an empty accessible name.

    Two series, one of them named with a tab -- a single-series chart is refused a step earlier
    for a different reason, so it cannot reach this check."""
    blank = 'sp.lineplot({"주": [1, 2, 1, 2], "매출": [1.0, 2.0, 3.0, 4.0], "채널": ["\t", "\t", "b", "b"]},'
    with pytest.raises(ValueError, match="no legend entry"):
        _stub([("blank", blank + ' x="주", y="매출", hue="채널")')], {1: "focus"})


def test_a_focus_group_needs_two_series_to_choose_between() -> None:
    """One series makes two radios that do the same thing: picking the line dims nothing, and
    the page still gets the note about dimming. An earlier version emitted that and called it
    the page's business -- but ``test_every_control_reference_resolves_on_its_own_page`` refuses
    it, because the series radio ends up labelled and unruled. The module was documenting as
    allowed what the suite rejects."""
    one = 'sp.lineplot({"주": [1, 2, 3], "매출": [1.0, 2.0, 3.0], "채널": ["a", "a", "a"]}, x="주", y="매출", hue="채널")'

    with pytest.raises(ValueError, match="needs two series to choose between"):
        _stub([("one", one)], {1: "focus"})


def test_a_focus_page_gets_the_radio_chrome_and_not_the_checkbox_chrome() -> None:
    """The per-kind halves are emitted for the kinds a page uses. Keeping them in one block put
    two ``.series-focus`` rules on every page that has a checkbox -- eight files rewritten so
    that seven of them could style an element they do not contain."""
    focus_only = chart_page(_stub([("lines", _LINES)], {1: "focus"}))
    toggle_only = chart_page(_stub([("bars", _BAR)], {1: "toggle"}))

    assert "figure > .series-focus {" in focus_only and "figure > .series-toggle {" not in focus_only
    assert "figure > .series-toggle {" in toggle_only and "figure > .series-focus {" not in toggle_only
    assert "interaction-note" in focus_only, "a focus figure dims, so it carries the note too"


def test_a_page_with_only_hover_gets_no_control_chrome() -> None:
    """The chrome styles ``<input>``/``<label>`` pairs, and a hover page has none. Its own half
    of the same claim -- the note -- is checked by
    :func:`test_a_page_with_controls_carries_the_note`; this is the half that emitting the
    chrome unconditionally left green."""
    hover_only = chart_page(_stub([("bars", _BAR)], {1: "hover"}))
    with_toggle = chart_page(_stub([("bars", _BAR)], {1: "toggle"}))

    assert "figure > .series-toggle" in with_toggle, "the fixture stopped emitting chrome at all"
    assert "figure > .series-toggle" not in hover_only
    assert ":hover" in hover_only, "and the hover rule itself is still there"


def test_a_legend_over_rows_is_not_refused_and_that_is_a_judgement_not_a_check() -> None:
    """``pieplot`` emits a swatch and a label per *slice*, which in the rendered file is
    indistinguishable from a ``hue=`` chart's swatch and label per group. So the rule "a toggle
    belongs only where ``hue=`` produced the series" cannot be enforced here, and pretending it
    could would be worse than saying so: a check that cannot fire reads as protection.

    Written down as a test rather than only as a comment because it is a limit somebody will
    otherwise rediscover by adding controls to a pie chart and finding nothing stopped them.
    """
    module = types.ModuleType("pie")
    module.TITLE, module.SUMMARY, module.REQUIRES = "pie", "s", "r"
    module.SETUP = 'import svgplot as sp\nD = {"이름": ["가", "나", "다"], "값": [3.0, 4.0, 5.0]}\n'
    module.EXAMPLES = [("slices", 'sp.pieplot(D, values="값", labels="이름")')]
    module.INTERACTIONS = {1: "toggle"}

    (controls,) = load(module, "pie").examples[0].controls

    assert [series.label for series in controls.series] == ["가", "나", "다"]


def test_an_interaction_for_an_example_that_does_not_exist_is_refused() -> None:
    """A typo'd index would otherwise mean a figure silently gets no controls -- and a missing
    control is invisible, because the page still renders."""
    with pytest.raises(ValueError, match="INTERACTIONS names example"):
        _stub([("bars", _BAR)], {2: "toggle"})


def test_an_unknown_control_kind_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown control kind"):
        _stub([("bars", _BAR)], {1: "raio"})


# ------------------------------------------------------------------ what the rules may do


def test_no_rule_hides_anything() -> None:
    """The decision this whole milestone rests on, kept as a rule rather than as prose.

    No chart recomputes its ticks, its category bands or its domain when a series is switched
    off -- the geometry was decided when the file was written. ``display: none`` would leave
    the survivors on an axis scaled for data that is no longer drawn, and would remove the
    element from the accessibility tree while the ``<desc>`` still says "2 series". Dimming
    claims neither.
    """
    stylesheet = interaction.stylesheet(
        [control for example in _stub([("b", _BAR)], {1: "toggle"}).examples for control in example.controls]
    )

    assert "opacity" in stylesheet
    for forbidden in ("display:", "visibility:"):
        assert forbidden not in stylesheet.replace(" ", ""), f"a rule uses {forbidden}"


def test_a_page_with_no_controls_adds_no_css_at_all() -> None:
    """Why the committed gallery is unchanged by this PR. ``page.STYLE`` ends in a newline, so
    appending the empty string to it is byte-for-byte what the pages already hold."""
    assert interaction.stylesheet([]) == ""


# ------------------------------------------------------------------ the rendered page


def test_the_controls_are_siblings_before_the_chart() -> None:
    """The load-bearing structural fact, and the reason there is no ``:has()`` anywhere here.

    The rules reach the chart with ``~``, which sees only *following siblings of the same
    parent*. An ``<input>`` after the SVG reaches nothing; an ``<input>`` inside a ``<div>`` or
    a ``<fieldset>`` reaches nothing either, and that one is the trap -- the page still looks
    right, the controls still render, and every rule silently stops matching.

    Parsed into direct children rather than scanned for tag order in the text, because a
    wrapper preserves the order. Watched: wrapping the controls in a ``<div>`` left the
    text-scanning version of this green.
    """
    html = chart_page(_stub([("bars", _BAR)], {1: "toggle"}))
    # Style bodies blanked *before* the figure is cut out: the page stylesheet is inside a
    # <style> and CSS may mention a tag name, so cutting first can cut from a comment.
    figure = ET.fromstring(re.search(r"<figure>.*?</figure>", blank_style_bodies(html), re.S).group(0))
    children = [child.tag.rsplit("}", 1)[-1] for child in figure]

    assert children == ["input", "label", "input", "label", "svg"], f"not flat siblings: {children}"


@pytest.mark.parametrize("html", [pytest.param(html, id=name) for name, html in _PAGES])
def test_a_page_with_controls_carries_the_note(html: str) -> None:
    """Stated both ways, so it catches the note going missing *and* the note appearing on a
    page with nothing to explain. Both directions were watched failing."""
    # Escaped, because the note is prose with quotation marks in it and the page escapes
    # every value it renders. Comparing against the raw constant would never match, and a
    # test that never matches is one somebody deletes the interesting half of.
    has_controls = 'class="series-toggle"' in html

    assert has_controls == (
        escape(interaction.NOTE) in html
    ), "a page with controls must explain that they dim rather than hide, and a page without them must not"


@pytest.mark.parametrize("html", [pytest.param(html, id=name) for name, html in _PAGES])
def test_every_control_reference_resolves_on_its_own_page(html: str) -> None:
    """``for=`` pointing at nothing gives a label that does not operate anything, and a rule
    keyed on an id that is not there simply never fires. Both fail silently in a browser.

    Every control needs a **label**; not every control needs a **rule**. A ``focus`` group's
    "all" radio deliberately has none -- nothing matching is exactly what makes it the way back
    to the default state -- so the equality that held while ``toggle`` was the only kind with
    markup is now an inclusion in one direction and an explicit exception in the other.
    """
    present = set(re.findall(r'\bid="([^"]*)"', html))
    labelled = set(re.findall(r'<label for="([^"]*)"', html))
    keyed = set(re.findall(r"#([\w-]+):(?:not\(:checked\)|checked)", html))
    ruleless = {name for name in labelled if name.endswith(f"-focus-{interaction.FOCUS_ALL}")}

    assert labelled <= present, f"label for= names {sorted(labelled - present)}, which is not on the page"
    assert keyed <= present, f"a rule is keyed on {sorted(keyed - present)}, which is not on the page"
    assert keyed <= labelled, f"{sorted(keyed - labelled)} is keyed on by a rule and has no label"
    assert labelled - keyed == ruleless, f"{sorted(labelled - keyed - ruleless)} has a label and no rule"


@pytest.mark.parametrize("html", [pytest.param(html, id=name) for name, html in _PAGES])
def test_every_rule_reaches_the_figure_it_was_written_for(html: str) -> None:
    """Resolving the ids is only half of it. A rule can name an id that exists, a combinator
    that reaches nothing, and a class no figure has, and stay silent in every one of those
    cases -- the browser applies nothing and the page looks like a page whose author did not
    ask for controls.

    **The figure a rule was written for is taken from its own block comment, not from its
    anchor.** An earlier version read the anchor and then checked the rule against the figure
    the anchor happened to name, which is circular: keying figure 3's hover rules on figure 2's
    checkbox produced a page where figure 3 has no hover at all, and that version passed. The
    comment is the emitter's statement of intent, so it is the thing the anchor is checked
    *against*.

    Watched failing with six mutations of the emitter, each of which the id check above and the
    whole rest of this file passed: scoping a hover rule to ``.{figure}-nope``, changing the
    toggle's ``~ svg`` to ``~ nosuchtag``, renaming every target class to one no figure draws,
    keying a figure's hover rules on another figure's checkbox, keying every series' hover rule
    on series-1's checkbox, and re-emitting the same CSS wrapped over three lines.
    """
    rules = _page_rules(html)
    if not rules:
        assert 'type="checkbox"' not in html, "the page has controls but no rule was extracted"
        assert ":hover" not in html.split("<figure>", 1)[0], "the page has hover rules but none was extracted"
        pytest.skip("this page declares no controls")

    figures = {
        element.get("class"): figure
        for figure in (ET.fromstring(markup) for markup in re.findall(r"<figure>.*?</figure>", blank_style_bodies(html), re.S))
        for element in figure.iter()
        if element.tag.endswith("}svg")
    }

    for figure_name, _kind, selector in rules:
        assert figure_name in figures, f"the block claims {figure_name}, which is not a figure on this page: {selector}"
        figure = figures[figure_name]
        wanted = {match.group(1) for match in _CLASS_IN_SELECTOR.finditer(selector)}
        drawn = {
            name
            for element in figure.iter()
            for name in (element.get("class") or "").split()
            if name.startswith("series-") or name in interaction.MARK_CLASSES
        }
        assert wanted <= drawn, f"the rule names {sorted(wanted - drawn)}, which {figure_name} does not draw: {selector}"

        keyed = re.search(r"#([\w-]+):(?:not\(:checked\)|checked)", selector)
        scoped = re.search(r"\.(svgplot-[\w-]+)(?![\w-])", selector)
        assert keyed or scoped, f"a rule is anchored on nothing: {selector}"
        if scoped and not keyed:
            assert scoped.group(1) == figure_name, f"the rule is scoped to {scoped.group(1)}, not to {figure_name}"
            continue

        assert keyed
        # A ``focus`` rule is the one shape where the id and the classes are deliberately
        # *different* series: picking line 1 dims the others, so the rule keyed on ``-focus-1``
        # names ``.series-2``. Checked as "the id belongs to this figure and to a series it
        # draws" rather than "the id matches the classes", which is true of every other kind.
        numbers = {name.split("-")[1] for name in wanted if name.startswith("series-")}
        drawn_numbers = {name.split("-")[1] for name in drawn if name.startswith("series-")}
        if "-focus-" in keyed.group(1):
            focused = keyed.group(1).rsplit("-", 1)[1]
            assert keyed.group(1) == f"{figure_name}-focus-{focused}", keyed.group(1)
            assert focused in drawn_numbers, f"{figure_name} focuses series {focused}, which it does not draw"
            assert focused not in numbers, f"{figure_name}'s focus rule dims the series it focuses"
        else:
            expected = {f"{figure_name}-toggle-{number}" for number in numbers}
            assert keyed.group(1) in expected, f"{figure_name}'s rule for {sorted(wanted)} is keyed on {keyed.group(1)}"
        _assert_the_combinator_walks(html, figure_name, keyed.group(1), selector)


def _assert_the_combinator_walks(html: str, figure_name: str, input_id: str, selector: str) -> None:
    """The ``~`` in ``#id:checked ~ svg`` only reaches a *later sibling of that input*.

    Located by the anchor's own id rather than by "the first ``<input>`` in the figure": with a
    decoy input before the ``<svg>``, comparing the earliest input satisfies every rule on the
    page including one whose own checkbox comes after the chart.
    """
    walked = re.search(r"~\s+([\w-]+)", selector)
    if walked is None:
        return
    markup = next(m for m in re.findall(r"<figure>.*?</figure>", blank_style_bodies(html), re.S) if figure_name in m)
    children = list(ET.fromstring(markup))
    tags = [child.tag.split("}")[-1] for child in children]
    anchors = [index for index, child in enumerate(children) if child.get("id") == input_id]
    targets = [index for index, tag in enumerate(tags) if tag == walked.group(1)]

    assert anchors, f"<input id={input_id}> is not a direct child of {figure_name}: {selector}"
    assert targets, f"the rule walks to <{walked.group(1)}>, which is not a child of {figure_name}: {selector}"
    assert min(anchors) < min(targets), f"<input id={input_id}> must precede <{walked.group(1)}> for ~ to reach it"


def test_the_rule_extraction_sees_a_rule_on_every_committed_page_that_has_controls() -> None:
    """The guard above skips when it finds no rules, so the day its extraction breaks is the day
    it reports sixteen skips and no failures. Re-emitting the same CSS wrapped over three lines
    -- a formatting change nobody would think twice about -- did exactly that to the
    line-by-line version it replaced.

    Counted over the **committed** pages only. An earlier bar of "three pages carry rules" was
    met by the three stubs this file builds itself, so deleting ``INTERACTIONS`` from every real
    example module left it green.
    """
    committed = {name: html for name, html in _PAGES if not name.startswith("built-")}
    with_controls = {name for name, html in committed.items() if 'type="checkbox"' in html}
    with_rules = {name for name, html in committed.items() if _page_rules(html)}

    assert len(with_controls) >= 3, f"only {sorted(with_controls)} of the committed pages carry a control"
    assert with_controls <= with_rules, f"{sorted(with_controls - with_rules)} have controls and no extracted rule"


def test_a_control_starts_checked_so_the_page_opens_showing_everything() -> None:
    """``checked="checked"`` is load-bearing twice over. Without it every series loads dimmed --
    a page that opens looking like the reader already switched it off -- and, since the hover
    rules are keyed on ``:checked``, with no hover anywhere either. Dropping the attribute left
    the whole suite green before this."""
    html = chart_page(_stub([("bars", _BAR)], {1: ("toggle", "hover")}))
    inputs = re.findall(r"<input\b[^>]*>", html)

    assert inputs, "the fixture stopped emitting controls"
    assert all('checked="checked"' in tag for tag in inputs), inputs


def test_the_index_carries_no_controls() -> None:
    """The index inlines each page's first figure as a thumbnail inside a link. A checkbox in
    there would be a control with no explanation beside it, inside something the reader clicks
    to go elsewhere -- and it is ``aria-hidden``, so it would be a focusable stop announcing
    nothing.

    Built with a page that *does* have controls on its **first** figure, which no real page
    has: the sixteen chart pages keep example 1 untouched so the index thumbnails do not
    change, so without this stub the check would pass over a gallery whose first figures are
    all bare. Watched: moving the control emission into the index left the version without this
    stub green.
    """
    from gallery.build import discover

    pages = [*discover(), _stub([("bars", _BAR)], {1: "toggle"})]

    assert pages[-1].examples[0].controls, "the fixture stopped having controls to leak"
    assert 'class="series-toggle"' not in index_page(pages)


# ------------------------------------------------------- what a review found the fixtures hid


def _one_example(setup: str, code: str, name: str = "one") -> Page:
    module = types.ModuleType(name)
    module.TITLE, module.SUMMARY, module.REQUIRES = name, "s", "r"
    module.SETUP = setup
    module.EXAMPLES = [("only", code)]
    module.INTERACTIONS = {1: "toggle"}
    return load(module, name)


def test_a_label_holding_an_ampersand_is_not_escaped_twice() -> None:
    """``R&D`` is an ordinary hue value, and it is in the rendered SVG as ``R&amp;D`` because
    that file is markup. Read raw and then escaped again on the way into the page, the reader
    sees ``R&amp;D`` on the checkbox beside a swatch labelled ``R&D`` -- two names for one
    thing, which is the exact failure ``legend_labels`` exists to prevent.

    Every other fixture in this file uses labels with nothing to escape, so all 187 checks
    passed while this was broken. The right and the wrong implementation agree on ``온라인``.
    """
    setup = 'import svgplot as sp\nD = {"x": ["a", "b"], "y": [1.0, 2.0], "g": ["R&D", "S<M"]}\n'
    page = _one_example(setup, 'sp.barplot(D, x="x", y="y", hue="g")')
    html = chart_page(page)

    assert {series.label for series in page.examples[0].controls[0].series} == {"R&D", "S<M"}
    assert re.findall(r"<label for=\"[^\"]*\">([^<]*)</label>", html) == ["R&amp;D", "S&lt;M"]
    assert "&amp;amp;" not in html


def test_a_series_whose_legend_name_is_blank_is_refused() -> None:
    """An empty hue value is ordinary in real data, and it renders as a legend row with no
    text. Left through, the page gets a checkbox with an empty accessible name -- worse than an
    unlabelled one, because assistive technology stops looking for a fallback."""
    setup = 'import svgplot as sp\nD = {"x": ["a", "b"], "y": [1.0, 2.0], "g": ["", "q"]}\n'

    with pytest.raises(ValueError, match="no legend entry"):
        _one_example(setup, 'sp.barplot(D, x="x", y="y", hue="g")')


@pytest.mark.parametrize(
    "label",
    [
        pytest.param("", id="empty"),
        pytest.param("   ", id="spaces"),
        pytest.param("\u00a0", id="no-break-space"),
        pytest.param("\u200b", id="zero-width-space"),
        pytest.param("\u2060", id="word-joiner"),
        pytest.param("\u200f", id="right-to-left-mark"),
        # These two arrive as a plain space: ``_svg.py``'s ``_fold_newlines`` collapses U+2028
        # and U+2029 before serialization, so what is read back is ``Zs``, not ``Zl``/``Zp``.
        # Kept for the round trip, and named for what they actually exercise -- dropping
        # ``Zl``/``Zp`` from the set changes nothing here, and an id claiming otherwise would
        # be one more test asserting something it does not reach.
        pytest.param("\u2028", id="line-separator-folded-to-a-space"),
        pytest.param("\u2029", id="paragraph-separator-folded-to-a-space"),
        pytest.param("\u200b \u2060", id="a-mix-of-them"),
    ],
)
def test_a_name_made_only_of_invisible_characters_is_refused(label: str) -> None:
    """``str.strip()`` was the first fix and it stopped one character short. It refuses
    U+00A0 -- a *space* -- and passes U+200B, which draws exactly as much: nothing. There is no
    principle under which one of those is a name and the other is not, and the outcome for a
    reader is the same empty accessible name either way.

    Two things that render as nothing are deliberately *not* in this list, and
    :func:`test_an_invisible_character_that_is_not_blank_by_category_gets_through` names them.
    """
    setup = f'import svgplot as sp\nD = {{"x": ["a", "b"], "y": [1.0, 2.0], "g": [{label!r}, "zzz"]}}\n'

    with pytest.raises(ValueError, match="no legend entry"):
        _one_example(setup, 'sp.barplot(D, x="x", y="y", hue="g")')


@pytest.mark.parametrize(
    "label",
    [
        pytest.param("\u3164", id="hangul-filler"),
        pytest.param("\ufe0f", id="variation-selector-16"),
        pytest.param("\u2800", id="braille-pattern-blank"),
    ],
)
def test_an_invisible_character_that_is_not_blank_by_category_gets_through(label: str) -> None:
    """The recorded limit, asserted so it is a known gap rather than a surprise.

    U+3164 is ``Lo`` -- a letter, alongside every Korean and CJK character. U+FE0F is ``Mn``,
    the category of a combining accent, which does draw. U+2800 is ``So``, a symbol. Telling
    any of them from what shares their category needs the ``Default_Ignorable_Code_Point``
    property, which the standard library does not expose, and a hand-kept list would be wrong
    the first time somebody found a character not on it.

    One case is missing in the other direction and is not asserted because it is not new: the
    rule *over*-refuses U+1680 OGHAM SPACE MARK (``Zs``, but it draws a stemline) and the
    Arabic prepended-concatenation marks (``Cf``, but they draw). The prefix form did the same,
    so nothing regressed -- but the recorded limits should not read as if only one direction
    had any.

    Written as a passing case rather than a comment because a comment would not notice the day
    Python grows the property and this stops being true.
    """
    setup = f'import svgplot as sp\nD = {{"x": ["a", "b"], "y": [1.0, 2.0], "g": [{label!r}, "zzz"]}}\n'

    page = _one_example(setup, 'sp.barplot(D, x="x", y="y", hue="g")')

    assert {series.label for series in page.examples[0].controls[0].series} == {label, "zzz"}


@pytest.mark.parametrize(
    "label",
    [
        pytest.param(".", id="punctuation"),
        pytest.param("\ue000", id="private-use-area"),
    ],
)
def test_a_name_that_draws_ink_without_being_a_letter_is_still_a_name(label: str) -> None:
    """The other side of the rule. ``.`` is an ordinary category value; a private use codepoint
    is what an icon font draws its glyphs at.

    The private use case is why the categories are named one by one instead of taken by
    ``C*`` prefix -- ``Co`` is under that prefix, and the prefix form refused U+E000.
    """
    setup = f'import svgplot as sp\nD = {{"x": ["a", "b"], "y": [1.0, 2.0], "g": [{label!r}, "zzz"]}}\n'

    page = _one_example(setup, 'sp.barplot(D, x="x", y="y", hue="g")')

    assert {series.label for series in page.examples[0].controls[0].series} == {label, "zzz"}


def test_a_series_with_no_legend_row_of_its_own_is_refused() -> None:
    """The other half of the refusal, which no test reached: a chart with *some* legend rows
    and a series that has none. Removing the ``missing`` term from ``resolve`` left all 47
    checks green, because the only case exercised was "no legend at all".

    Built as markup rather than by rendering a chart, because no chart produces this today --
    it is what a change to the legend's shape would produce, and the point is to notice.
    """
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<rect class="series-1" /><rect class="series-2" />'
        '<rect x="0" class="series-1" /><text class="legend-text">A</text>'
        "</svg>"
    )

    with pytest.raises(ValueError, match=r"no legend entry for series \[2\]"):
        interaction.resolve("svgplot-x-1", "toggle", svg)


def test_a_figure_name_that_would_break_out_of_a_css_rule_is_refused() -> None:
    """``css()`` interpolates the figure name into a selector and into a comment, and neither
    is protected by ``html.escape`` -- ``x{} body{background:red}`` would add a rule to the
    page, and ``*/`` would end the comment early.

    Unreachable today, because ``example.load`` calls ``set_scope`` first and that refuses the
    same names. But that is a guard standing one line away in another file: move it and this
    one is gone with nothing saying so. The package's own validator is reused rather than a
    second pattern, so there is one answer to "what is a safe class name".
    """
    with pytest.raises(ValueError, match="figure class name"):
        interaction.resolve("x{} body{background:red}", "toggle", '<svg><rect class="series-1" /></svg>')


def test_a_size_legend_does_not_become_a_series(monkeypatch: pytest.MonkeyPatch) -> None:
    """``scatterplot(hue=, size=)`` draws two legends. The size legend's rows are ``<circle>``
    samples with a marker class, and counting them as series would give the page checkboxes
    for "3.0" and "9.0" -- numbers, not groups."""
    setup = (
        "import svgplot as sp\n"
        'D = {"x": [1.0, 2.0, 3.0, 4.0], "y": [1.0, 2.0, 3.0, 4.0],\n'
        '     "g": ["a", "a", "b", "b"], "w": [3.0, 5.0, 7.0, 9.0]}\n'
    )
    page = _one_example(setup, 'sp.scatterplot(D, x="x", y="y", hue="g", size="w")')

    assert [series.label for series in page.examples[0].controls[0].series] == ["a", "b"]
