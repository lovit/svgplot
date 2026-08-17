"""SVG document builder.

Low-level XML tree construction used internally by ``chart.base.Chart`` and
``chart.composition.Composition``. Responsible for node creation, pretty-print
serialization, and assigning semantic (non-random) ``class``/``id`` values so
the generated SVG stays hand-editable (see docs/research/14-scope-recommendation.md,
핵심 원칙 1). Not part of the public API — always accessed through Chart/Composition.

Security note (PR #23/#24 security review, 2 rounds): this is the package's
single escape chokepoint. Every user-supplied string (labels, titles, data
values) must be inserted through this module's node/text-creation API
(``add_node``/``add_text``) — never via raw string concatenation elsewhere.
``xml.etree.ElementTree`` escapes text/attribute *values* automatically at
serialization time, but it does **not** escape tag names or attribute names,
so those are fully validated (``_validate_name``, ASCII-only XML Name syntax,
``fullmatch`` so no trailing-newline bypass) before a node is ever attached to
the tree — attribute names that would enable inline event handlers or inline
styling (``style``, ``on*``) are rejected outright, matching this package's
CSS-class-only styling contract. Text, attribute values, and CSS class names
are checked for characters XML 1.0 forbids (NUL and other control characters,
lone surrogates), which would otherwise silently produce a document that
fails to parse. All validation runs before any node is created, so a rejected
call never leaves a partial/orphan node behind.

This chokepoint's guarantee covers name/value escaping and structural
validity — it does not vet attribute *values* for XSS-relevant semantics
(e.g. a ``javascript:`` URI in ``href``). No current caller in this package
emits URI-bearing attributes; a future caller that does must validate the
URI scheme itself before calling into this module.
"""

from __future__ import annotations

import copy
import math
import re
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"

_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*(:[A-Za-z_][A-Za-z0-9_.-]*)?$")
_INVALID_XML_CHAR_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")
_BLOCKED_ATTRIBUTE_LOCAL_NAMES = frozenset({"style"})


def _validate_name(name: str, kind: str) -> str:
    """Reject anything that isn't a safe, ASCII-only XML Name (tag/attribute name).

    For ``kind="attribute"``, also rejects ``style`` and any ``on*`` event-handler
    attribute name, since this package styles exclusively via CSS classes.
    """
    if not _NAME_RE.fullmatch(name):
        raise ValueError(f"invalid XML {kind} name: {name!r}")
    if kind == "attribute":
        local_name = name.rsplit(":", 1)[-1].lower()
        if local_name in _BLOCKED_ATTRIBUTE_LOCAL_NAMES or local_name.startswith("on"):
            raise ValueError(f"attribute name not allowed (inline style/event handlers are blocked): {name!r}")
    return name


def _validate_text(value: str, kind: str) -> str:
    """Reject characters XML 1.0 forbids in text/attribute values/class names."""
    if _INVALID_XML_CHAR_RE.search(value):
        raise ValueError(f"{kind} contains characters not allowed in XML 1.0: {value!r}")
    return value


def _validate_class_name(class_name: str) -> str:
    """Reject an empty class, whitespace (would smuggle extra classes via join), or invalid XML chars."""
    if not class_name or any(char.isspace() for char in class_name):
        raise ValueError(f"invalid CSS class name: {class_name!r}")
    return _validate_text(class_name, "CSS class")


def _format_number(value: float) -> str:
    """Format a number as a clean literal (``120.5``, not ``120.50000000000001``)."""
    try:
        number = float(value)
    except (TypeError, OverflowError, ValueError) as error:
        raise ValueError(f"cannot format value as an SVG literal: {value!r}") from error
    if not math.isfinite(number):
        raise ValueError(f"cannot format a non-finite number as an SVG literal: {value!r}")
    rounded = round(number, 6)
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
        formatted_width, formatted_height = _format_number(width), _format_number(height)
        self.root = ET.Element(
            "svg",
            {
                "xmlns": SVG_NS,
                "width": formatted_width,
                "height": formatted_height,
                "viewBox": f"0 0 {formatted_width} {formatted_height}",
            },
        )

    def add_node(
        self,
        parent: ET.Element | None,
        tag: str,
        attrib: dict[str, str | int | float] | None = None,
        classes: list[str] | None = None,
    ) -> ET.Element:
        """Create a child element under ``parent`` (or the document root if ``None``).

        ``tag`` and ``attrib`` keys must be safe XML Names (``ValueError`` otherwise);
        ``style``/``on*`` attribute names are rejected outright. ``attrib`` values are
        coerced to strings; numeric values should already be formatted via
        :func:`_format_number` by the caller so coordinates stay literal. Styling is
        expressed via ``classes`` (CSS classes), not an inline ``style=`` attribute —
        see docs/research/12-aesthetics.md §4. Each class must not contain whitespace
        (a single list entry can't smuggle in extra classes). Every argument is fully
        validated before any node is created, so a ``ValueError`` never leaves a
        partial node attached to the tree.
        """
        _validate_name(tag, "tag")
        validated_attrib: list[tuple[str, str]] = []
        if attrib:
            for key, value in attrib.items():
                _validate_name(key, "attribute")
                validated_attrib.append((key, _validate_text(str(value), "attribute value")))
        joined_classes = None
        if classes:
            for class_name in classes:
                _validate_class_name(class_name)
            joined_classes = " ".join(classes)

        target = parent if parent is not None else self.root
        node = ET.SubElement(target, tag)
        for key, value in validated_attrib:
            node.set(key, value)
        if joined_classes is not None:
            node.set("class", joined_classes)
        return node

    def add_text(
        self,
        parent: ET.Element | None,
        text: str,
        attrib: dict[str, str | int | float] | None = None,
        classes: list[str] | None = None,
    ) -> ET.Element:
        """Create a ``<text>`` node whose content is ``text`` (escaped at serialization time)."""
        validated_text = _validate_text(text, "text content")
        node = self.add_node(parent, "text", attrib=attrib, classes=classes)
        node.text = validated_text
        return node

    def semantic_class(self, prefix: str) -> str:
        """Return a semantic, incrementing class name like ``series-1`` — never a random hash."""
        count = self._class_counters.get(prefix, 0) + 1
        self._class_counters[prefix] = count
        return f"{prefix}-{count}"

    def to_string(self, *, pretty: bool = True) -> str:
        """Serialize the document to an SVG string.

        With ``pretty=True`` (the default) the output is indented for readability
        and prefixed with an XML declaration, suitable for a standalone ``.svg``
        file. With ``pretty=False`` the output is a single compact line with no
        XML declaration, intended for inline embedding (e.g. ``_repr_svg_``)
        rather than as a standalone file. Indentation is applied to a copy of the
        tree, so calling ``to_string`` repeatedly (in either mode, in either
        order) never mutates the document or affects later calls.
        """
        if pretty:
            root = copy.deepcopy(self.root)
            ET.indent(root, space="  ")
            body = ET.tostring(root, encoding="unicode")
            return f'<?xml version="1.0" encoding="UTF-8"?>\n{body}\n'
        return ET.tostring(self.root, encoding="unicode")
