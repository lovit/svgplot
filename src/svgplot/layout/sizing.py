"""Two-mode sizing (fixed/responsive), replacing Bokeh's 8-value sizing_mode
for a markdown-embedded static document (docs/research/16-layout-vocabulary.md).

Bokeh's six viewport-relative modes assume a viewport whose height constrains
layout; a markdown document scrolls vertically forever, so only "fixed pixel
size" and "scale to the container's width, keeping aspect ratio" survive.
"""

from __future__ import annotations

from svgplot.chart.base import Chart
from svgplot.chart.composition import chart_document
from svgplot.charts._layout import format_coord

SIZE_MODES = ("fixed", "responsive")

_RESPONSIVE_CLASS = "svgplot-responsive"
# No caller input reaches this CSS — it is a literal constant, the safest case of
# the "CSS-semantic safety is the caller's job" contract in _svg.py's security note.
_RESPONSIVE_CSS = f".{_RESPONSIVE_CLASS} {{ max-width: 100%; height: auto; }}"


def apply_size(chart: Chart, mode: str = "fixed") -> Chart:
    """Set the chart's sizing mode: 'fixed' (explicit width/height) or
    'responsive' (viewBox + CSS max-width:100%).

    ``"fixed"`` writes explicit pixel ``width``/``height`` and drops ``viewBox``,
    so the SVG renders at exactly its authored size. ``"responsive"`` keeps
    ``viewBox`` (which is what preserves the aspect ratio) and attaches a CSS
    class capping the rendered width at the container's — the ``max-width:100%;
    height:auto`` idiom the research doc specifies. The class is used rather than
    an inline ``style=`` attribute because ``_svg.py`` blocks that attribute
    outright, matching this package's CSS-class-only styling contract.

    Mutates ``chart``'s document in place and returns the same chart, matching
    :meth:`svgplot.chart.base.Chart.set_title`'s chaining convention.

    Raises:
        ValueError: if ``mode`` isn't one of :data:`SIZE_MODES`.
    """
    if mode not in SIZE_MODES:
        raise ValueError(f"mode must be one of {SIZE_MODES}, got {mode!r}")

    document = chart_document(chart)
    root = document.root
    width, height = format_coord(document.width), format_coord(document.height)

    if mode == "fixed":
        document.set_attribute(root, "width", width)
        document.set_attribute(root, "height", height)
        root.attrib.pop("viewBox", None)
        existing = root.get("class", "").split()
        remaining = [name for name in existing if name != _RESPONSIVE_CLASS]
        if remaining:
            document.set_attribute(root, "class", " ".join(remaining))
        else:
            root.attrib.pop("class", None)
        return chart

    document.set_attribute(root, "viewBox", f"0 0 {width} {height}")
    existing = root.get("class", "").split()
    if _RESPONSIVE_CLASS not in existing:
        document.set_attribute(root, "class", " ".join([*existing, _RESPONSIVE_CLASS]))
    if not any(element.tag == "style" and element.text == _RESPONSIVE_CSS for element in root):
        document.add_text(None, _RESPONSIVE_CSS, tag="style")
    return chart
