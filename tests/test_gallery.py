"""The gallery under ``docs/gallery/`` is generated but committed, so it can rot (#145).

GitHub Pages serves the ``main`` branch's ``/docs`` directly rather than an Actions artifact,
which means there is no build step between the repository and the published site: whatever is
committed is what readers see. A generated page that is committed can therefore fall behind
the code that generated it and still render perfectly, which is the worst kind of wrong -- it
looks authoritative and nobody notices.

Three checks stand against that: the committed output matches a fresh build, every chart has
an example file, and every page is well-formed with its figures present.
"""

from __future__ import annotations

import ast
import importlib
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import svgplot as sp

ROOT = Path(__file__).resolve().parent.parent
GALLERY = ROOT / "docs" / "gallery"
_SVG_NS = "http://www.w3.org/2000/svg"

# ``gallery`` is repo-root source, not part of the installed package.
sys.path.insert(0, str(ROOT))

from gallery.build import discover, write  # noqa: E402
from gallery.example import REQUIRED  # noqa: E402

from _svg_probe import blank_style_bodies  # noqa: E402


def _chart_names() -> set[str]:
    """Every public chart function, taken from the package rather than from a list here."""
    not_a_chart = {"facet", "row", "column", "grid", "apply_size", "apply_context", "add_caption", "parametric_theme"}
    return {name for name in sp.__all__ if name[0].islower() and callable(getattr(sp, name)) and name not in not_a_chart}


def _pages() -> list[Path]:
    return sorted(GALLERY.glob("*.html"))


def test_the_committed_gallery_is_what_a_fresh_build_produces() -> None:
    """The check the whole file exists for. Output is committed because Pages serves the
    branch directly, so nothing regenerates it on the way to the reader -- only this notices.

    Byte comparison rather than "it still parses": a chart whose colours or geometry changed
    still parses. Safe to compare bytes because the output is deterministic -- five separate
    processes with a randomized ``PYTHONHASHSEED`` produced identical SVG, the only randomness
    in the package being ``stats/regression.py``'s local ``random.Random(seed)`` with ``seed``
    defaulting to 0.
    """
    with tempfile.TemporaryDirectory() as scratch:
        fresh = Path(scratch) / "gallery"
        write(discover(), fresh)

        committed = {path.relative_to(GALLERY): path.read_bytes() for path in GALLERY.rglob("*") if path.is_file()}
        rebuilt = {path.relative_to(fresh): path.read_bytes() for path in fresh.rglob("*") if path.is_file()}

    assert sorted(committed) == sorted(rebuilt), "the set of generated files differs -- run `uv run python -m gallery.build`"
    stale = sorted(str(name) for name, content in rebuilt.items() if committed[name] != content)
    assert not stale, f"committed gallery is stale -- run `uv run python -m gallery.build`: {stale}"


def test_every_chart_has_a_gallery_page() -> None:
    """A chart that ships without a page is simply absent from the gallery, and absence is
    invisible -- nobody notices a chart that was never shown.

    Absolute now that all sixteen are documented. While the pages were landing one at a time
    this allowed an explicit waiting list, and that list is gone rather than left empty: an
    empty escape hatch is one somebody widens later without anyone deciding to."""
    documented = {path.stem for path in _pages() if path.stem != "index"}

    assert _chart_names() == documented, (
        f"charts with no gallery page: {sorted(_chart_names() - documented)}; "
        f"pages for things that are not charts: {sorted(documented - _chart_names())}"
    )


@pytest.mark.parametrize("page", _pages(), ids=lambda path: path.name)
def test_every_page_is_well_formed(page: Path) -> None:
    """Parsed rather than eyeballed. An unclosed tag renders anyway in a browser -- it just
    renders wrong, somewhere below the mistake.

    ``<style>`` bodies are removed first because CSS is not markup: a CSS comment mentioning
    an element name is valid CSS and would otherwise fail this for no reason.
    """
    html = page.read_text()
    markup = re.sub(r"^<!doctype html>\s*", "", html, flags=re.I)
    # ``<style[^>]*>`` rather than ``<style>``: the bare form happens to match what this
    # package emits today, so the day a style element gains an attribute this would stop
    # matching and the test would fail on CSS content rather than on markup.
    markup = re.sub(r"(<style[^>]*>).*?(</style>)", r"\1\2", markup, flags=re.S)

    ET.fromstring(markup)  # raises ParseError with a line number if a tag is unclosed


@pytest.mark.parametrize("page", _pages(), ids=lambda path: path.name)
def test_every_page_shows_the_figures_it_should(page: Path) -> None:
    """The inline replacement for "the file it points at exists": there is no file to point
    at, so what can go wrong is a figure silently not being emitted.

    A chart page carries one chart per example; the index carries one thumbnail per page.
    """
    inlined = len(re.findall(r"<svg\b", page.read_text(encoding="utf-8")))
    pages = {found.name: found for found in discover()}

    expected = len(pages) if page.stem == "index" else len(pages[page.stem].examples)

    assert inlined == expected, f"{page.name} inlines {inlined} charts, expected {expected}"


@pytest.mark.parametrize("page", _pages(), ids=lambda path: path.stem)
def test_every_inlined_chart_is_really_an_svg(page: Path) -> None:
    """Counting ``<svg`` lexically says a string is there, not that a browser sees a chart.

    Parsed, every one has to land in the SVG namespace -- an ``<svg>`` written without its
    ``xmlns`` is markup a browser reads as an unknown HTML element and draws as nothing.

    This replaces the check that every ``<img src>`` resolved. Kept in reduced form it would
    have been worse than nothing: no page has an ``<img>`` any more, so it passed on an empty
    file. The tutorial page will need that check and can carry its own.
    """
    markup = page.read_text(encoding="utf-8")
    charts = [node for node in ET.fromstring(_parseable(markup)).iter() if node.tag == f"{{{_SVG_NS}}}svg"]

    assert markup.count("<svg"), f"{page.name} inlines no chart"
    assert len(charts) == markup.count("<svg"), f"{page.name}: some <svg> is not in the SVG namespace"


def test_every_example_module_declares_what_the_builder_needs() -> None:
    """The contract, asserted where a page author will see it rather than as a build crash."""
    for page in discover():
        assert page.title and page.summary and page.requires, f"{page.name}: empty {REQUIRED}"
        assert page.examples, f"{page.name}: no examples"
        for example in page.examples:
            assert example.caption.strip(), f"{page.name}: an example has no caption"
            assert example.svg.startswith("<svg"), f"{page.name}: {example.caption!r} produced no SVG"
            # The regression that matters: a prolog is legal only at the start of an entity,
            # so one returning here would break every page it is inlined into.
            assert "<?xml" not in example.svg, f"{page.name}: {example.caption!r} still carries an XML prolog"


def test_the_index_links_every_page_it_should() -> None:
    """The index is generated from discovery, so this is really asking whether discovery and
    rendering agree -- a page written to disk but missing from the index is unreachable."""
    index = (GALLERY / "index.html").read_text()
    linked = set(re.findall(r'<a href="(\w+)\.html"', index))

    assert linked == {path.stem for path in _pages() if path.stem != "index"}


# --------------------------------------------------------------------- the inline model
#
# Inlining the SVG rather than referencing it opens failures the ``<img>`` model could not
# have: a referenced SVG is its own document, so its CSS, its ids and its accessible name
# were all somebody else's problem. Written before the conversion so each one could be seen
# failing against the ``<img>`` gallery -- a guard nobody has watched fail is a guess.


def _parseable(markup: str) -> str:
    """The page with its doctype dropped and its ``<style>`` bodies blanked.

    The blanking is ``_svg_probe.blank_style_bodies``; only the doctype step is local, because
    only a whole page has one.
    """
    return blank_style_bodies(re.sub(r"^<!doctype html>\n", "", markup, flags=re.I))


def _chart_style_bodies(markup: str) -> list[str]:
    """The ``<style>`` bodies belonging to inlined charts, not the page's own stylesheet.

    The page has a ``<style>`` of its own in ``<head>`` -- ordinary multi-line CSS with
    ``:root { … }`` and closing braces on their own lines. Reading every ``<style>`` in the
    file and splitting each line at ``{`` turns that into selectors named ``:root`` and ``}``,
    which then look like duplicates on every page. Scoped to the charts, which is what these
    checks are about.
    """
    return [
        body
        for figure in re.findall(r"<svg\b.*?</svg>", markup, re.S)
        for body in re.findall(r"<style>(.*?)</style>", figure, re.S)
    ]


@pytest.mark.parametrize("page", _pages(), ids=lambda path: path.stem)
def test_no_two_figures_on_a_page_define_the_same_selector(page: Path) -> None:
    """The reason the gallery used ``<img>`` at all, now that it does not.

    An inline SVG's ``<style>`` is document-global, so two charts on one page both defining
    ``.series-1`` means the later one repaints the earlier. Duplicates are refused outright
    rather than only when the declarations differ: every chart defines ``.tick-line``,
    ``.spine`` and four others identically, so a "same selector, different body" check would
    pass on a page with no scoping at all.
    """
    selectors = [
        selector.strip()
        for body in _chart_style_bodies(page.read_text(encoding="utf-8"))
        for rule in body.splitlines()
        if rule.strip()
        for selector in rule.split("{")[0].split(",")
    ]
    duplicates = sorted({name for name in selectors if selectors.count(name) > 1})

    assert selectors, f"{page.name} defines no CSS at all"
    assert not duplicates, f"{page.name}: two figures define {duplicates}"


@pytest.mark.parametrize("page", _pages(), ids=lambda path: path.stem)
def test_no_page_repeats_an_element_id(page: Path) -> None:
    """``Chart.set_table_id`` exists for exactly this, and inlining is what makes it real:
    duplicate ids make ``aria-describedby`` resolve to whichever came first, so the second
    chart would be described by the first chart's data."""
    ids = re.findall(r'\bid="([^"]*)"', page.read_text(encoding="utf-8"))

    assert len(ids) == len(set(ids)), f"{page.name} repeats {sorted({i for i in ids if ids.count(i) > 1})}"


@pytest.mark.parametrize("page", _pages(), ids=lambda path: path.stem)
def test_every_aria_describedby_points_at_something_on_the_page(page: Path) -> None:
    """In the ``<img>`` model this reference dangled harmlessly -- it named an id in a document
    the SVG could not see. Inlined, a dangling IDREF is a real one, and the fix is to render
    the table it names rather than to drop the attribute."""
    markup = page.read_text(encoding="utf-8")
    referenced = set(re.findall(r'aria-describedby="([^"]*)"', markup))
    present = set(re.findall(r'\bid="([^"]*)"', markup))

    assert referenced <= present, f"{page.name}: {sorted(referenced - present)} is referenced but not on the page"


@pytest.mark.parametrize("page", _pages(), ids=lambda path: path.stem)
def test_no_inlined_chart_is_left_named_Chart(page: Path) -> None:  # noqa: N802 - the literal name is the point
    """Inlined, each chart is a ``role="img"`` node in the page's accessibility tree, so its
    ``aria-label`` is what a screen reader announces. The default is ``"Chart"`` for all of
    them, which on the index would be sixteen nodes announcing the same word."""
    labels = re.findall(r'<svg[^>]*\baria-label="([^"]*)"', page.read_text(encoding="utf-8"))

    assert labels, f"{page.name} inlines no chart"
    assert sp.Chart.DEFAULT_TITLE not in labels, f"{page.name} leaves a chart named {sp.Chart.DEFAULT_TITLE!r}"


@pytest.mark.parametrize("page", _pages(), ids=lambda path: path.stem)
def test_no_page_carries_an_xml_declaration(page: Path) -> None:
    """A prolog is legal only at the very start of an entity. One arriving mid-document with
    an inlined chart renders as text and stops the page parsing."""
    assert "<?xml" not in page.read_text(encoding="utf-8")


def test_the_gallery_figure_shows_the_two_orders_disagreeing() -> None:
    """The page says the table's order and the marks' order differ; on the first draft's data
    they did not.

    The regions were five 수도권 then five 지방, which sort in that same order and sit in
    contiguous blocks -- so a purely positional implementation would have produced a
    byte-identical page, and the one published figure demonstrating the pairing rule did not
    exercise it. Interleaving the regions fixed the data; this keeps it fixed, because the
    NOTE beside the figure is a claim about that data and nothing else reads it.
    """
    from gallery.examples import scatterplot as page

    namespace: dict[str, object] = {}
    exec(page.SETUP, namespace)
    stores = namespace["STORES"]

    chart = sp.scatterplot(stores, x="면적", y="매출", hue="지역", info=[("점포", "@점포")], tooltip=True)
    from_marks = [title.removeprefix("점포: ") for title in re.findall(r"<title>([^<]*)</title>", chart.to_string())[:-1]]

    assert from_marks != list(stores["점포"]), "the figure's data no longer shows the two orders differing"
    assert sorted(from_marks) == sorted(stores["점포"]), "the marks and the table hold the same rows"


# ------------------------------------------------------- captions against the code they caption
#
# The caption becomes the figure's ``aria-label``, so it is the only description a screen
# reader gets. Written after an audit claimed in a PR body did not reproduce. Measured against
# this branch's own tip before the fix: seven of the 76 figures passed an argument no caption
# named -- ``barplot`` one, ``gaugeplot`` three, ``kdeplot``, ``scatterplot`` and ``violinplot``
# one each -- and two more captions described a figure that was not the one under them. That
# second pair is the argument for a test rather than a sentence: one of the two was a caption
# this branch had written itself, in the commit before the one measured, while rewriting the
# page it sat on.

_SUBJECT = ("data", "x", "y", "hue", "size", "values", "labels")
"""The channels. A page's ``REQUIRES`` already declares these, and every figure on the page
passes them -- naming them again in each caption would say nothing. What a caption has to
account for is what makes *this* figure different from the one above it: the options."""


def _keywords(code: str) -> set[str]:
    return {
        keyword.arg
        for node in ast.walk(ast.parse(code))
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg
    }


def test_every_option_a_figure_passes_is_named_in_its_caption() -> None:
    """A figure that quietly passes ``stacked=True`` under a caption about tooltips teaches the
    reader that the caption is the whole call, and it is not."""
    unnamed = []
    for page in discover():
        for example in page.examples:
            options = _keywords(example.code) - set(_SUBJECT)
            # ``opt=`` at an identifier boundary, not ``opt in caption``: ``width`` is a
            # substring of ``bandwidth``, both are parameters of the same chart, and two live
            # captions say "bandwidth=" -- so a bare containment check passes a figure that
            # quietly adds ``width=`` under a caption that never mentions it. Measured: all 76
            # figures already satisfy the anchored form, so this costs nothing today.
            missing = sorted(option for option in options if not re.search(rf"(?<![A-Za-z0-9_]){option}=", example.caption))
            if missing:
                unnamed.append((page.name, example.caption, missing))

    assert not unnamed, f"captions that do not name an option their code passes: {unnamed}"


def test_the_audit_would_notice_a_channel_going_missing() -> None:
    """The exemption above is a list of names, and a list can be edited until it exempts
    everything -- adding ``tooltip`` to it would drop every ``tooltip=True`` figure out of the
    audit. Two assertions, because the first alone does not close that: agreeing with
    ``_CHANNELS`` only makes the edit take two lines instead of one, since nothing in
    ``test_api_shape`` requires a ``_CHANNELS`` entry to be a real parameter -- its own use of
    the tuple is ``assert set(positional) <= set(_CHANNELS)``, an upper bound, which widening
    can never fail. Measured: widening both tuples with ``tooltip`` left all 3,899 tests green,
    and a live caption could then stop naming ``tooltip=`` with nothing complaining. The second
    assertion says every exempt name is one some chart really takes positionally, which is what
    makes ``tooltip`` unaddable. One direction, not equality: the converse -- that no chart takes
    anything positionally the audit does not exempt -- is what ``test_api_shape``'s own per-chart
    check is for, and asserting it here again would fail this test, with this test's message,
    for a chart signature that changed."""
    import inspect

    from test_api_shape import _CHANNELS

    positional = {
        name
        for chart in sp.charts.__all__
        for name, spec in inspect.signature(getattr(sp, chart)).parameters.items()
        if spec.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    }

    assert set(_SUBJECT) == set(_CHANNELS), "the caption audit and the signature guard disagree about what a channel is"
    assert (
        set(_SUBJECT) <= positional
    ), f"{sorted(set(_SUBJECT) - positional)} is exempt from the caption audit but no chart takes it positionally"


# --------------------------------------------------------------- prose against the page it sits on
#
# The conventions in ``gallery/examples/__init__.py`` are mostly a matter of taste and stay
# unenforced. Two of them are not: a figure ordinal in a NOTE is a reference that goes wrong the
# moment a figure is inserted above it, and the interaction note names the figures that carry a
# control. Both were wrong at some point on a page that rendered perfectly.

_ORDINALS = {"첫": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10}

_ORDINAL = re.compile(rf"(?<![가-힣])({'|'.join(_ORDINALS)})\s*번째")

_NOT_A_FIGURE = {("histplot", "다섯 번째 슬롯"), ("regplot", "그 두 번째다")}
"""Ordinals in NOTES that count something other than figures.

An exclusion list rather than a pattern for what a reference *looks* like, because the first
attempt at the latter went the wrong way: it matched ``번째 그림``, five particles and three punctuation marks, and
quietly dropped five real references written some other way -- ``다섯 번째가``, ``세 번째가``,
``(네 번째)은``, ``(다섯 번째)는``, ``네 번째와 다섯 번째 모두``. One of them was the only
pointer to ``lineplot``'s fifth figure, and losing it turned the guard below off for that page
with nothing to show for it.

Matching every ordinal and naming the exceptions fails in the safe direction: a reference
written a new way is audited by default, and an ordinal that counts something else fails loudly
until someone decides which it is. The two here count x slots and the things this chart adds to
another; both sit in range today only because their pages happen to be long enough.
"""


def _without_exceptions(note: str, page: str) -> str:
    for owner, phrase in _NOT_A_FIGURE:
        if owner == page:
            note = note.replace(phrase, "")
    return note


def _cited_figures(notes: list[str], page: str) -> set[int]:
    return {_ORDINALS[match[1]] for note in notes for match in _ORDINAL.finditer(_without_exceptions(note, page))}


def test_no_note_points_past_the_last_figure() -> None:
    """``다섯 번째`` on a four-figure page is a reference to nothing, and the build does not care.

    Range only. A reference that points at the *wrong* figure while staying in range is not
    covered here and cannot be, in general -- nothing mechanical knows that ``세 번째(누적)``
    means the stacked one. The one place it is covered is the interaction note below, where the
    page declares the answer in ``INTERACTIONS`` and the sentence can be checked against it.
    """
    overflowing = [
        (page.name, sorted(number for number in _cited_figures(page.notes, page.name) if number > len(page.examples)))
        for page in discover()
    ]

    assert not [row for row in overflowing if row[1]], f"notes citing figures that do not exist: {overflowing}"


def test_every_exception_to_the_ordinal_audit_is_still_in_use() -> None:
    """An exclusion list is only safe while every entry earns its place. One left behind after
    its sentence is rewritten silently exempts whatever text drifts into the same shape."""
    by_page = {page.name: " ".join(page.notes) for page in discover()}
    unused = [(owner, phrase) for owner, phrase in _NOT_A_FIGURE if phrase not in by_page.get(owner, "")]

    assert not unused, f"exceptions no longer on the page that justifies them: {unused}"

    # And each must be the *whole* phrase that makes it a non-reference: an ordinal followed by
    # the noun it counts (``다섯 번째 슬롯``) or closed off as a predicate (``그 두 번째다``).
    # An entry ending at a particle -- ``다섯 번째가`` -- is a real reference, and adding one
    # would re-create the regression this list exists to avoid, from the other direction.
    #
    # ``그림`` disqualifies an entry outright, whichever shape it otherwise fits. Requiring
    # "some noun after the ordinal" was not enough: ``세 번째 그림`` satisfies it and is the most
    # ordinary reference there is, so three such entries each switched the audit off for a page
    # with the whole suite green. ``다섯 번째 그림이다`` slips past the predicate clause the same way.
    unjustified = [
        (owner, phrase)
        for owner, phrase in _NOT_A_FIGURE
        if "그림" in phrase or not (phrase.endswith("다") or re.search(r"번째\s+\S", phrase))
    ]

    assert not unjustified, f"exceptions that are ordinary figure references: {unjustified}"


def test_every_ordinal_in_the_gallery_is_classified() -> None:
    """The audit above is worth only as much as the set of ordinals it sees. Every ``N 번째`` on
    every page is either a figure reference it counts or a listed exception -- there is no third
    category that quietly leaves. This is what the previous, pattern-based version could not
    say: it silently ignored anything it did not recognise."""
    for page in discover():
        for note in page.notes:
            seen = len(_ORDINAL.findall(_without_exceptions(note, page.name)))
            # Bare ``번째``, not ``_ORDINAL`` again: counting both sides with the same pattern
            # makes this vacuous -- anything the pattern does not recognise is missing from
            # *both* and the equality holds. ``열두 번째``, ``12번째`` and an ordinal glued to a
            # preceding syllable all slipped through that way.
            total = len(re.findall("번째", note))
            excepted = sum(note.count(phrase) for owner, phrase in _NOT_A_FIGURE if owner == page.name)

            assert seen + excepted == total, f"{page.name}: {total - seen - excepted} ordinals fell through: {note[:70]}"


_JAVASCRIPT_CLAUSE = "JavaScript 는 0줄이다"
"""The fixed tail of the interaction note. Found by that phrase rather than by the words for a
control, because the pages do not share those: ``lineplot`` writes ``조작 장치`` where the rest
write ``체크박스``, since its controls are a checkbox *and* a radio."""


def test_the_interaction_note_names_the_figures_that_have_controls() -> None:
    """A page's controls come from ``INTERACTIONS``; the sentence describing them is written by
    hand. Reordering ``scatterplot``'s examples moved a control from figure 4 to figure 5 and
    left the sentence saying 4 -- true of nothing, and invisible to every other test here.

    Both directions: a page with controls has exactly one such note naming exactly the
    controlled figures, and a page with none does not disclaim JavaScript for a control it
    never draws.
    """
    for page in discover():
        controlled = {index for index, example in enumerate(page.examples, 1) if example.controls}
        notes = [note for note in page.notes if _JAVASCRIPT_CLAUSE in note]

        if not controlled:
            assert not notes, f"{page.name} draws no control but disclaims JavaScript for one"
            continue

        assert len(notes) == 1, f"{page.name} has controls on {sorted(controlled)} and {len(notes)} notes saying so"
        assert (
            _cited_figures(notes, page.name) == controlled
        ), f"{page.name}: the note names {sorted(_cited_figures(notes, page.name))}, the controls are on {sorted(controlled)}"


_VERB_FINAL = re.compile(r"다$")
"""A caption ends in a verb. In Korean that is the syllable ``다`` and nothing else -- an earlier
version listed ``었다``/``한다``/``된다`` beside it, every one of which already ends in ``다``."""

_NUMBER_WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}

_ENDS_IN_A_NOUN = {
    ("areaplot", 4),
    ("boxplot", 1),
    ("lineplot", 5),
    ("scatterplot", 4),
    ("sparkline", 1),
    ("sparkline", 3),
}
"""The captions the conventions let end in a noun, listed rather than described.

Two shapes qualify -- the value or size the figure was given, and the condition the figure is
for -- and no pattern tells either from an ordinary noun phrase, so the exemption is a list and
this is what keeps the list honest. It was written after the rule claimed "two captions" while
nine ended in a noun and two of the nine -- ``heatmap``'s third and ``pieplot``'s third -- fitted
neither shape it allowed.
"""


def test_only_the_listed_captions_end_in_a_noun() -> None:
    """Both directions, so the list cannot grow to cover a caption nobody reconsidered, and
    cannot keep an entry whose caption has since been rewritten."""
    ending_in_a_noun = {
        (page.name, index)
        for page in discover()
        for index, example in enumerate(page.examples, 1)
        if not _VERB_FINAL.search(example.caption)
    }

    assert ending_in_a_noun == _ENDS_IN_A_NOUN
    # The conventions state the number in prose, and a number in prose drifts -- this rule once
    # said "two" while nine captions ended in a noun. Without this, adding a caption *and*
    # listing it here is green while the sentence goes on saying six.
    conventions = importlib.import_module("gallery.examples").__doc__ or ""
    assert (
        f"and {_NUMBER_WORDS[len(_ENDS_IN_A_NOUN)]}\ncaptions use them" in conventions
    ), f"the conventions do not say {_NUMBER_WORDS[len(_ENDS_IN_A_NOUN)]} captions end in a noun"


def test_every_page_answers_the_hue_question() -> None:
    """``hue=`` decides what colour means, so a page that says nothing about it leaves a reader
    to guess from silence. Either a field describing what the channel takes, or a field saying
    the chart does not take one -- sixteen out of sixteen, matched against the signature so a
    page cannot answer wrongly either."""
    import inspect

    for page in discover():
        takes_hue = "hue" in inspect.signature(getattr(sp, page.name)).parameters
        # ``hue`` appearing somewhere is not an answer -- a field reading ``· hue`` and stopping
        # names the channel and says nothing. The two forms below are the two answers.
        declares_hue = "hue(선택):" in page.requires
        refuses_hue = "hue 는 받지 않는다" in page.requires

        assert declares_hue or refuses_hue, f"{page.name}: REQUIRES names no hue= field and no refusal"
        assert not (declares_hue and refuses_hue), f"{page.name}: REQUIRES both declares and refuses hue="
        assert (
            declares_hue is takes_hue
        ), f"{page.name}: takes hue={takes_hue} but REQUIRES says {'it does not' if refuses_hue else 'it does'}"
