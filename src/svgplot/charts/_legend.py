"""Legend rendering shared by every chart type whose hue=/grouping produces
multiple series: one color swatch + label per entry.

Private/internal — not re-exported from ``svgplot.charts``.
"""

from __future__ import annotations

from svgplot._svg import SvgDocument
from svgplot.charts._layout import format_coord

_SWATCH_WIDTH = 16.0
_LABEL_GAP = 6.0
_ROW_HEIGHT = 20.0
_TEXT_BASELINE_OFFSET = 4.0


def render_legend(document: SvgDocument, entries: list[tuple[str, str]], *, x: float, y: float) -> None:
    """Draw a vertical legend starting at ``(x, y)``, one row per ``entries`` item.

    Each entry is ``(label, css_class)`` — ``css_class`` is reused as-is (e.g. the
    same class a series' ``<path>`` already carries), so this function only
    positions a swatch + text per entry; it never chooses or emits any color
    itself — that's ``theme.css.render_theme_style``'s job, which already styles
    ``css_class`` via its ``<style>`` block.
    """
    for index, (label, css_class) in enumerate(entries):
        row_y = y + index * _ROW_HEIGHT
        document.add_node(
            None,
            "line",
            attrib={
                "x1": format_coord(x),
                "y1": format_coord(row_y),
                "x2": format_coord(x + _SWATCH_WIDTH),
                "y2": format_coord(row_y),
            },
            classes=[css_class],
        )
        document.add_text(
            None,
            label,
            tag="text",
            attrib={"x": format_coord(x + _SWATCH_WIDTH + _LABEL_GAP), "y": format_coord(row_y + _TEXT_BASELINE_OFFSET)},
            classes=["legend-text"],
        )
