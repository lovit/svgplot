"""Tests for svgplot.output.{svg,png,jupyter}."""

from __future__ import annotations

from pathlib import Path

import pytest

from svgplot._svg import SvgDocument
from svgplot.output.jupyter import repr_svg
from svgplot.output.png import to_png
from svgplot.output.svg import save_svg, to_string


def _sample_document() -> SvgDocument:
    doc = SvgDocument(width=100, height=100)
    doc.add_node(None, "circle", attrib={"cx": "50", "cy": "50", "r": "10"}, classes=["series-1"])
    return doc


def test_to_string_delegates_to_document() -> None:
    document = _sample_document()

    assert to_string(document) == document.to_string(pretty=True)
    assert to_string(document, pretty=False) == document.to_string(pretty=False)


def test_save_svg_writes_readable_file(tmp_path: Path) -> None:
    document = _sample_document()
    path = tmp_path / "chart.svg"

    save_svg(document, str(path))

    content = path.read_text(encoding="utf-8")
    assert "<circle" in content
    assert 'class="series-1"' in content


def test_save_svg_compact_writes_single_line(tmp_path: Path) -> None:
    document = _sample_document()
    path = tmp_path / "chart.svg"

    save_svg(document, str(path), pretty=False)

    content = path.read_text(encoding="utf-8")
    assert "\n" not in content


def test_repr_svg_is_compact_and_matches_document_output() -> None:
    document = _sample_document()

    assert repr_svg(document) == document.to_string(pretty=False)
    assert "\n" not in repr_svg(document)


def test_to_png_without_cairosvg_installed_raises_import_error_with_install_hint(tmp_path: Path) -> None:
    try:
        import cairosvg  # noqa: F401
    except ImportError:
        pass
    else:
        pytest.skip("cairosvg is installed in this environment; the missing-dependency path isn't exercised")

    document = _sample_document()

    with pytest.raises(ImportError, match="png"):
        to_png(document, str(tmp_path / "chart.png"))


def test_to_png_writes_file_when_cairosvg_available(tmp_path: Path) -> None:
    pytest.importorskip("cairosvg")

    document = _sample_document()
    path = tmp_path / "chart.png"

    to_png(document, str(path))

    assert path.exists()
    assert path.read_bytes().startswith(b"\x89PNG")
