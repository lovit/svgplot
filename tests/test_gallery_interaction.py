"""The gallery's no-JavaScript controls: what they are wired to, and what they must not do.

Every check here was watched failing before it was kept -- 29 mutations, one at a time. Four
are shaped specifically against ways this file could pass while asserting nothing:

* The page-level checks run over pages **rendered here**, never over the committed files. A
  disk-reading version stayed green when the note was made unconditional, because the files on
  disk had not changed -- it was measuring staleness, which ``test_gallery.py`` already does.
* Two of those pages are built by :func:`_stub` and always carry controls. No example module
  declares ``INTERACTIONS`` yet, so over the real gallery alone every "a page with controls
  must ..." check would hold over an empty set -- the shape of the ``<img src>`` check that
  survived the gallery losing every ``<img>`` (#185).
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

QUARTERS = {
    "분기": ["1분기", "2분기", "3분기", "4분기"] * 2,
    "매출": [120.0, 145.0, 98.0, 176.0, 84.0, 92.0, 110.0, 131.0],
    "채널": ["온라인"] * 4 + ["오프라인"] * 4,
}
"""

_BAR = 'sp.barplot(QUARTERS, x="분기", y="매출", hue="채널")'
_BOX = 'sp.boxplot(QUARTERS, x="분기", y="매출", hue="채널")'


def _stub(examples: list[tuple[str, str]], interactions: dict[int, str] | None = None, name: str = "stub") -> Page:
    """A gallery page built here rather than committed.

    The controls have to be exercised somewhere, and they cannot be exercised against the
    committed gallery: this PR's completion condition is that rebuilding ``docs/`` produces no
    diff, so nothing under ``gallery/examples/`` declares ``INTERACTIONS``. Building a page
    means these checks measure the emitter itself instead of waiting for a chart PR to make
    them meaningful.
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

    The two built pages are what stops the whole file being vacuous. No example module
    declares ``INTERACTIONS`` yet, so every real page has zero controls and every "a page with
    controls must ..." check would hold over an empty set -- the shape of the ``<img src>``
    check that survived the gallery losing every ``<img>`` (#185).
    """
    from gallery.build import discover  # imported here so a collection error names this file

    pages = [(page.name, chart_page(page)) for page in discover()]
    pages.append(("built-with-controls", chart_page(_stub([("bars", _BAR)], {1: "toggle"}))))
    pages.append(("built-with-two", chart_page(_stub([("bars", _BAR), ("boxes", _BOX)], {1: "toggle", 2: "toggle"}))))
    return pages


_PAGES = _rendered()


# ------------------------------------------------------------------ reading the picture


def test_the_series_a_control_gets_are_the_series_the_chart_drew() -> None:
    """The list of series is extracted, never declared. An example module says only *which*
    figure gets controls; a hand-written list would be a second copy of what the chart already
    decided, and the copy is the one that goes stale."""
    page = _stub([("bars", _BAR)], {1: "toggle"})
    controls = page.examples[0].controls

    assert controls is not None
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
    rules = interaction.css(example.controls)

    assert drawn[1] == ("series-1", "series-1-marker"), "the fixture stopped being the two-class case"
    for classes in drawn.values():
        for name in classes:
            assert f".{name}" in rules, f"{name} is drawn but no rule dims it"


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

    labels = {series.label for series in page.examples[0].controls.series}

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

    controls = load(module, "pie").examples[0].controls

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
    stylesheet = interaction.stylesheet([example.controls for example in _stub([("b", _BAR)], {1: "toggle"}).examples])

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
    """``for=`` pointing at nothing gives a label that does not toggle anything, and a rule
    keyed on an id that is not there simply never fires. Both fail silently in a browser."""
    present = set(re.findall(r'\bid="([^"]*)"', html))
    labelled = set(re.findall(r'<label for="([^"]*)"', html))
    keyed = set(re.findall(r"#([\w-]+):not\(:checked\)", html))

    assert labelled <= present, f"label for= names {sorted(labelled - present)}, which is not on the page"
    assert keyed <= present, f"a rule is keyed on {sorted(keyed - present)}, which is not on the page"
    assert keyed == labelled, "every control must have both a rule and a label"


def test_the_index_carries_no_controls() -> None:
    """The index inlines each page's first figure as a thumbnail inside a link. A checkbox in
    there would be a control with no explanation beside it, inside something the reader clicks
    to go elsewhere -- and it is ``aria-hidden``, so it would be a focusable stop announcing
    nothing.

    Built with a page that *does* have controls on its first figure, because otherwise this
    passes on a gallery where no page has any -- which is today's gallery. Watched: moving the
    control emission into the index left the version without this stub green.
    """
    from gallery.build import discover

    pages = [*discover(), _stub([("bars", _BAR)], {1: "toggle"})]

    assert pages[-1].examples[0].controls is not None, "the fixture stopped having controls to leak"
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

    assert {series.label for series in page.examples[0].controls.series} == {"R&D", "S<M"}
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

    assert {series.label for series in page.examples[0].controls.series} == {label, "zzz"}


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

    assert {series.label for series in page.examples[0].controls.series} == {label, "zzz"}


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

    assert [series.label for series in page.examples[0].controls.series] == ["a", "b"]
