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


def test_set_title_and_palette_return_self_for_chaining() -> None:
    chart = _sample_chart()

    result = chart.set_title("My Chart").palette(["#e69f00", "#56b4e9"])

    assert result is chart
    assert chart._title == "My Chart"
    assert chart._palette == ["#e69f00", "#56b4e9"]


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


def test_save_rejects_unsupported_extension(tmp_path: Path) -> None:
    chart = _sample_chart()

    with pytest.raises(ValueError, match="unsupported file extension"):
        chart.save(str(tmp_path / "chart.pdf"))


def test_save_png_without_cairosvg_installed_raises_import_error(tmp_path: Path) -> None:
    try:
        import cairosvg  # noqa: F401
    except ImportError:
        pass
    else:
        pytest.skip("cairosvg is installed in this environment; the missing-dependency path isn't exercised")

    chart = _sample_chart()

    with pytest.raises(ImportError, match="png"):
        chart.save(str(tmp_path / "chart.png"))
