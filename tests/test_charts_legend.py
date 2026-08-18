from __future__ import annotations

import pytest

from svgplot._svg import SvgDocument
from svgplot.charts._legend import render_legend


def test_render_legend_stroke_mark_style_draws_line_swatches() -> None:
    document = SvgDocument()
    render_legend(document, [("A", "series-1"), ("B", "series-2")], x=10.0, y=20.0)

    swatches = document.root.findall(".//line[@class='series-1']") + document.root.findall(".//line[@class='series-2']")
    assert len(swatches) == 2
    assert not document.root.findall(".//rect[@class='series-1']")


def test_render_legend_fill_mark_style_draws_rect_swatches() -> None:
    document = SvgDocument()
    render_legend(document, [("A", "series-1")], x=10.0, y=20.0, mark_style="fill")

    assert document.root.findall(".//rect[@class='series-1']")
    assert not document.root.findall(".//line[@class='series-1']")


def test_render_legend_rejects_unknown_mark_style() -> None:
    document = SvgDocument()
    with pytest.raises(ValueError, match="mark_style"):
        render_legend(document, [("A", "series-1")], x=0.0, y=0.0, mark_style="bogus")


def test_render_legend_labels_each_entry() -> None:
    document = SvgDocument()
    render_legend(document, [("A", "series-1"), ("B", "series-2")], x=10.0, y=20.0)

    labels = [node.text for node in document.root.findall(".//text[@class='legend-text']")]
    assert labels == ["A", "B"]


def test_render_legend_rows_do_not_overlap() -> None:
    document = SvgDocument()
    render_legend(document, [("A", "series-1"), ("B", "series-2"), ("C", "series-3")], x=10.0, y=20.0)

    labels = document.root.findall(".//text[@class='legend-text']")
    y_positions = [float(label.get("y")) for label in labels]
    assert y_positions == sorted(y_positions)
    assert len(set(y_positions)) == len(y_positions)
