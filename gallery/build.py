"""Generate ``docs/gallery/`` from ``gallery/examples/``.

Run with ``uv run python -m gallery.build``. Output is committed, because GitHub Pages serves
the ``main`` branch's ``/docs`` directly rather than an Actions artifact -- there is no build
step between the repository and the site. ``tests/test_gallery.py`` therefore asserts that
regenerating produces no diff, which is what keeps the committed pages from drifting away
from the code that made them.

The output directory is **rebuilt from empty** each run. Writing over the top would leave the
files of a deleted example behind, and a stale page is worse than a missing one: it renders,
so nobody notices.
"""

from __future__ import annotations

import argparse
import importlib
import pkgutil
import shutil
import sys
from pathlib import Path

from gallery import examples
from gallery.example import Page, load
from gallery.page import chart_page, index_page

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs" / "gallery"


def discover() -> list[Page]:
    """Every example module, loaded and run, ordered by chart name.

    Discovery rather than a registry: adding a chart's page is adding one file, so the sixteen
    chart PRs never touch a shared list and never queue behind each other.

    Sorted so the index order does not depend on the filesystem's -- an unordered walk would
    reshuffle the index whenever a page was added and make the no-diff check meaningless.
    """
    pages = []
    for module in sorted(pkgutil.iter_modules(examples.__path__), key=lambda found: found.name):
        pages.append(load(importlib.import_module(f"gallery.examples.{module.name}"), module.name))
    return pages


def write(pages: list[Page], output: Path) -> list[Path]:
    """Write the index, one page per chart, and one SVG per example. Returns what was written."""
    if output.exists():
        shutil.rmtree(output)
    (output / "svg").mkdir(parents=True)

    written = []
    for page in pages:
        for index, example in enumerate(page.examples, start=1):
            path = output / "svg" / f"{page.name}-{index}.svg"
            path.write_text(example.svg, encoding="utf-8")
            written.append(path)
        path = output / f"{page.name}.html"
        path.write_text(chart_page(page), encoding="utf-8")
        written.append(path)

    path = output / "index.html"
    path.write_text(index_page(pages), encoding="utf-8")
    written.append(path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT, help="where to write (default: docs/gallery)")
    arguments = parser.parse_args()

    pages = discover()
    if not pages:
        print("no examples found under gallery/examples/", file=sys.stderr)
        return 1
    written = write(pages, arguments.output)
    print(f"{len(pages)} charts, {len(written)} files -> {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
