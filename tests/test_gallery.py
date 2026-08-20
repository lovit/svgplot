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

# ``gallery`` is repo-root source, not part of the installed package.
sys.path.insert(0, str(ROOT))

from gallery.build import discover, write  # noqa: E402
from gallery.example import REQUIRED  # noqa: E402

# Charts that do not have a gallery page yet. Each of the sixteen chart issues empties one
# line of this list; when it is empty the completeness check below becomes absolute and the
# list should be deleted rather than left as an empty permanent escape hatch.
AWAITING_A_PAGE = {
    "sparkline",
}


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


def test_every_chart_has_a_gallery_page_or_is_listed_as_awaiting_one() -> None:
    """A chart that ships without a page would simply be absent from the gallery, and absence
    is invisible. The waiting list makes each gap a line someone has to delete on purpose."""
    documented = {path.stem for path in _pages() if path.stem != "index"}
    missing = _chart_names() - documented - AWAITING_A_PAGE

    assert not missing, f"charts with no gallery page and not on the waiting list: {sorted(missing)}"


def test_the_waiting_list_only_names_charts_that_exist() -> None:
    """So a chart that gets a page, or gets renamed, cannot leave a stale line behind that
    silently excuses a real gap later."""
    documented = {path.stem for path in _pages() if path.stem != "index"}

    assert not (
        AWAITING_A_PAGE & documented
    ), f"already documented but still on the waiting list: {sorted(AWAITING_A_PAGE & documented)}"
    assert _chart_names() >= AWAITING_A_PAGE, f"not a chart: {sorted(AWAITING_A_PAGE - _chart_names())}"


@pytest.mark.parametrize("page", _pages(), ids=lambda path: path.name)
def test_every_page_is_well_formed(page: Path) -> None:
    """Parsed rather than eyeballed. An unclosed tag renders anyway in a browser -- it just
    renders wrong, somewhere below the mistake.

    ``<style>`` bodies are removed first because CSS is not markup: a CSS comment mentioning
    an element name is valid CSS and would otherwise fail this for no reason.
    """
    html = page.read_text()
    markup = re.sub(r"^<!doctype html>\s*", "", html, flags=re.I)
    markup = re.sub(r"(<style>).*?(</style>)", r"\1\2", markup, flags=re.S)

    ET.fromstring(markup)  # raises ParseError with a line number if a tag is unclosed


@pytest.mark.parametrize("page", _pages(), ids=lambda path: path.name)
def test_every_figure_a_page_references_exists(page: Path) -> None:
    """A missing figure is a broken image in the reader's browser and nothing at all in CI."""
    sources = re.findall(r'<img[^>]*src="([^"]+)"', page.read_text())

    assert sources, f"{page.name} shows no figures"
    missing = [src for src in sources if not (page.parent / src).is_file()]
    assert not missing, f"{page.name} references figures that do not exist: {missing}"


def test_every_example_module_declares_what_the_builder_needs() -> None:
    """The contract, asserted where a page author will see it rather than as a build crash."""
    for page in discover():
        assert page.title and page.summary and page.requires, f"{page.name}: empty {REQUIRED}"
        assert page.examples, f"{page.name}: no examples"
        for example in page.examples:
            assert example.caption.strip(), f"{page.name}: an example has no caption"
            assert example.svg.startswith("<?xml"), f"{page.name}: {example.caption!r} produced no SVG"


def test_the_index_links_every_page_it_should() -> None:
    """The index is generated from discovery, so this is really asking whether discovery and
    rendering agree -- a page written to disk but missing from the index is unreachable."""
    index = (GALLERY / "index.html").read_text()
    linked = set(re.findall(r'<a href="(\w+)\.html"', index))

    assert linked == {path.stem for path in _pages() if path.stem != "index"}
