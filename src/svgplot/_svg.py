"""SVG document builder.

Low-level XML tree construction used internally by ``chart.base.Chart`` and
``chart.composition.Composition``. Responsible for node creation, pretty-print
serialization, and assigning semantic (non-random) ``class``/``id`` values so
the generated SVG stays hand-editable (see docs/research/14-scope-recommendation.md,
핵심 원칙 1). Not part of the public API — always accessed through Chart/Composition.

Security note (PR #23 security review): this is the package's single escape
chokepoint. Every user-supplied string (labels, titles, data values) must be
inserted through this module's node/text-creation API (``add_node``/``add_text``)
— never via raw string concatenation elsewhere. ``xml.etree.ElementTree``
escapes text/attribute values automatically at serialization time, so as long
as callers never build markup by concatenating strings themselves, escaping
is handled in exactly this one place.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"


def _format_number(value: float) -> str:
    """Format a number as a clean literal (``120.5``, not ``120.50000000000001``)."""
    rounded = round(float(value), 6)
    if rounded == int(rounded):
        return str(int(rounded))
    text = f"{rounded:.6f}".rstrip("0").rstrip(".")
    return text


class SvgDocument:
    """A single SVG document being built up as a tree of nodes.

    Coordinates and other computed values are written as literals (not
    formulas) so the resulting markup can be read and hand-edited directly.
    """

    def __init__(self, width: float = 800, height: float = 600) -> None:
        self.width = width
        self.height = height
        self._class_counters: dict[str, int] = {}
        self.root = ET.Element(
            "svg",
            {
                "xmlns": SVG_NS,
                "width": _format_number(width),
                "height": _format_number(height),
                "viewBox": f"0 0 {_format_number(width)} {_format_number(height)}",
            },
        )

    def add_node(
        self,
        parent: ET.Element | None,
        tag: str,
        attrib: dict[str, str] | None = None,
        classes: list[str] | None = None,
    ) -> ET.Element:
        """Create a child element under ``parent`` (or the document root if ``None``).

        ``attrib`` values are coerced to strings; numeric values should already
        be formatted via :func:`_format_number` by the caller so coordinates
        stay literal. Styling is expressed via ``classes`` (CSS classes), not
        an inline ``style=`` attribute — see docs/research/12-aesthetics.md §4.
        """
        target = parent if parent is not None else self.root
        node = ET.SubElement(target, tag)
        if attrib:
            for key, value in attrib.items():
                node.set(key, str(value))
        if classes:
            node.set("class", " ".join(classes))
        return node

    def add_text(
        self,
        parent: ET.Element | None,
        text: str,
        attrib: dict[str, str] | None = None,
        classes: list[str] | None = None,
    ) -> ET.Element:
        """Create a ``<text>`` node whose content is ``text`` (escaped at serialization time)."""
        node = self.add_node(parent, "text", attrib=attrib, classes=classes)
        node.text = text
        return node

    def semantic_class(self, prefix: str) -> str:
        """Return a semantic, incrementing class name like ``series-1`` — never a random hash."""
        count = self._class_counters.get(prefix, 0) + 1
        self._class_counters[prefix] = count
        return f"{prefix}-{count}"

    def to_string(self, *, pretty: bool = True) -> str:
        """Serialize the document to an SVG string.

        With ``pretty=True`` (the default) the output is indented so it stays
        readable/hand-editable in a text editor.
        """
        if pretty:
            ET.indent(self.root, space="  ")
        body = ET.tostring(self.root, encoding="unicode")
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{body}\n' if pretty else body
