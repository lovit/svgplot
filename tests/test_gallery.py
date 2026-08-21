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

    CSS is not markup: a rule holding ``>`` or ``&`` is valid CSS and invalid XML, so the
    bodies come out before parsing.
    """
    without_doctype = re.sub(r"^<!doctype html>\n", "", markup, flags=re.I)
    return re.sub(r"(<style[^>]*>).*?(</style>)", r"\1\2", without_doctype, flags=re.S)


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
