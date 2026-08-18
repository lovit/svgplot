"""Tests for svgplot.chart.base.Chart."""

from __future__ import annotations

from pathlib import Path

import pytest

from svgplot._svg import SvgDocument
from svgplot.chart.base import Chart


def _sample_chart() -> Chart:
    document = SvgDocument(width=100, height=100)
    document.add_node(None, "circle", attrib={"cx": "50", "cy": "50", "r": "10"}, classes=["series-1"])
    return Chart(document)


def test_to_string_returns_svg_string_with_expected_tag_and_class() -> None:
    chart = _sample_chart()

    output = chart.to_string()

    assert "<circle" in output
    assert 'class="series-1"' in output


def test_to_string_compact_is_single_line() -> None:
    chart = _sample_chart()

    assert "\n" not in chart.to_string(pretty=False)


def test_to_string_is_idempotent() -> None:
    chart = _sample_chart()

    assert chart.to_string() == chart.to_string()


def test_set_title_and_palette_return_self_for_chaining() -> None:
    chart = _sample_chart()

    result = chart.set_title("My Chart").palette(["#e69f00", "#56b4e9"])

    assert result is chart
    assert chart._title == "My Chart"
    assert chart._palette == ["#e69f00", "#56b4e9"]


def test_set_title_and_palette_do_not_change_rendered_output() -> None:
    """This issue only requires chaining; applying title/palette to the document is a later issue's job."""
    chart = _sample_chart()
    before = chart.to_string()

    chart.set_title("My Chart").palette(["#e69f00"])

    assert chart.to_string() == before
    assert "My Chart" not in chart.to_string()
    assert "#e69f00" not in chart.to_string()


def test_repr_svg_returns_compact_svg_string() -> None:
    chart = _sample_chart()

    output = chart._repr_svg_()

    assert "<circle" in output
    assert "\n" not in output


def test_save_writes_svg_file(tmp_path: Path) -> None:
    chart = _sample_chart()
    path = tmp_path / "chart.svg"

    chart.save(str(path))

    content = path.read_text(encoding="utf-8")
    assert "<circle" in content


@pytest.mark.parametrize("extension", [".svg", ".SVG", ".Svg"])
def test_save_svg_extension_is_case_insensitive(tmp_path: Path, extension: str) -> None:
    chart = _sample_chart()
    path = tmp_path / f"chart{extension}"

    chart.save(str(path))

    assert "<circle" in path.read_text(encoding="utf-8")


def test_save_rejects_unsupported_extension(tmp_path: Path) -> None:
    chart = _sample_chart()

    with pytest.raises(ValueError, match="unsupported file extension"):
        chart.save(str(tmp_path / "chart.pdf"))


def test_save_rejects_path_with_no_extension(tmp_path: Path) -> None:
    chart = _sample_chart()

    with pytest.raises(ValueError, match="unsupported file extension"):
        chart.save(str(tmp_path / "chart"))


def test_save_png_without_cairosvg_installed_raises_import_error(cairosvg_unavailable: None, tmp_path: Path) -> None:
    chart = _sample_chart()

    with pytest.raises(ImportError, match="png"):
        chart.save(str(tmp_path / "chart.png"))


def test_save_writes_png_file_when_cairosvg_available(require_cairosvg: None, tmp_path: Path) -> None:
    chart = _sample_chart()
    path = tmp_path / "chart.png"

    chart.save(str(path))

    assert path.exists()
    assert path.read_bytes().startswith(b"\x89PNG")
