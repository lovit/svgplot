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

Security note (issue #12): ``"style"`` is allowed in ``_TEXT_BEARING_TAGS``
(``"script"`` is not, and never should be — this package emits no JS).
Unlike every other text-bearing tag here, this module's own escaping is
*not* sufficient for ``<style>``: XML text escaping stops ``<``/``&`` from
breaking out of the element, but does nothing to stop ``}``/``;``/``@import``/
``url(...)`` from breaking out of a CSS *rule* once inside. This module still
only guarantees XML-structural safety for ``<style>`` content, exactly as it
does for every other tag; **CSS-semantic safety is the caller's job**, and
every sanctioned caller earns that trust by validating what it embeds:

- ``theme.css.render_theme_style`` — validates colors via a strict ``#rrggbb``
  regex, font family via an allowlisted character set, numbers via
  ``format_coord``, and class names via a CSS-identifier regex.
- ``layout.sizing.apply_size`` — embeds a fixed module-level constant only
  (no interpolation, so nothing to validate).
- ``chart.composition`` — rewrites already-validated selectors produced by
  the two callers above; it interpolates no new user-derived values.

Any *new* ``<style>`` producer must independently validate every value it
interpolates before calling ``add_text``, and be added to this list — the
list is the only record of which code carries that obligation.

Security note (issue #12 review): ``"script"`` is rejected by ``add_node``
itself (``_BLOCKED_TAGS``), not merely omitted from ``add_text``'s allow-list
— a node created via ``add_node(parent, "script")`` followed by setting
``.text`` directly on the returned element would otherwise bypass
``add_text`` entirely and reach the tree unvalidated. Blocking it in
``add_node`` makes this a structural guarantee (every node, regardless of
which method creates it) rather than a convention only ``add_text`` happens
to follow. The check normalizes ``tag`` the same way ``_validate_name``
normalizes attribute local names (``rsplit(":", 1)[-1].lower()``) rather than
comparing case-sensitively: this package's actual use case is inline
embedding in markdown/HTML (``to_string(pretty=False)``/``_repr_svg_``), and
an HTML tokenizer lowercases tag names before caring about XML
case-sensitivity, so ``"SCRIPT"``/``"svg:script"`` would still become a live
``<script>`` element there even though a strict XML parser would treat them
as distinct, harmless tag names — a naive case-sensitive block would be a
one-character bypass.
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
_TEXT_BEARING_TAGS = frozenset({"text", "tspan", "title", "desc", "textPath", "style"})

_NEWLINE_RUN_RE = re.compile(r"[\r\n]+")

_MULTILINE_TEXT_TAGS = frozenset({"style"})
"""Text-bearing tags whose newlines are kept. Only ``<style>``: its content is a list of
CSS rules this package generates itself (never user text), and one rule per line is what
makes a nine-line hand edit possible -- the whole point of the CSS-class contract. It
cannot introduce a blank line either, since no rule is ever empty."""
# Enforced in add_node itself (not just add_text's allow-list) so no code path —
# not even one that bypasses add_text by setting .text directly on an add_node
# result — can ever attach a <script> element to the tree. This package emits no JS.
_BLOCKED_TAGS = frozenset({"script"})


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


def _fold_newlines(value: str) -> str:
    """Collapse every run of line breaks in text content to one space.

    Nothing here is about XML: a newline inside a text node is perfectly legal, and
    ``_validate_text`` rightly lets it through. It is about where this package's output
    goes. An SVG meant to be pasted into a markdown document is an HTML block, and
    CommonMark ends a type-7 HTML block at the **first blank line** -- so a label
    containing ``"\\n\\n"`` splits the document there and everything after it, the rest of
    the chart's own source included, is parsed as markdown prose and shown to the reader as
    text. Python-Markdown does not even need the blank line: it has no ``svg`` in its
    block-level tag list, so any multi-line ``<svg>`` becomes a paragraph with ``<br/>``
    inserted mid-element.

    Folding rather than rejecting, because a newline is not an error the caller can be
    expected to have meant something by: no renderer draws it as a line break. SVG 1.1's
    own whitespace rule discards newlines outright, and current browsers apply CSS
    ``white-space: normal``, which turns each run into a single space -- which is exactly
    what this does. So the rendered result is unchanged and only the source is fixed.

    A genuine multi-line label needs ``<tspan>`` elements with explicit ``dy``; this
    package has no font metrics and so does not offer one.
    """
    return _NEWLINE_RUN_RE.sub(" ", value)


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
        ``style``/``on*`` attribute names are rejected outright, and ``tag="script"``
        is rejected outright too (see this module's "Security note (issue #12 review)")
        — this package emits no JS, and that guarantee is enforced here, not just by
        ``add_text``'s allow-list, so it holds regardless of which method a caller
        uses to create a node. ``attrib`` values are coerced to strings; numeric
        values should already be formatted via :func:`_format_number` by the caller
        so coordinates stay literal. Styling is expressed via ``classes`` (CSS
        classes), not an inline ``style=`` attribute — see
        docs/research/12-aesthetics.md §4. Each class must not contain whitespace
        (a single list entry can't smuggle in extra classes). Every argument is fully
        validated before any node is created, so a ``ValueError`` never leaves a
        partial node attached to the tree.
        """
        _validate_name(tag, "tag")
        # Normalized the same way _validate_name normalizes attribute local names
        # (rsplit(":", 1)[-1].lower()) — an inline SVG embedded in markdown/HTML is
        # parsed by an HTML tokenizer, which lowercases tag names, so "SCRIPT" or
        # "svg:script" would still become a live <script> element there even though
        # they're distinct, case-sensitive XML names to a strict XML parser.
        if tag.rsplit(":", 1)[-1].lower() in _BLOCKED_TAGS:
            raise ValueError(f"tag not allowed (this package emits no JS): {tag!r}")
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
        *,
        tag: str = "text",
        attrib: dict[str, str | int | float] | None = None,
        classes: list[str] | None = None,
    ) -> ET.Element:
        """Create a ``<{tag}>`` node (default ``<text>``, an SVG mark) whose content is
        ``text`` (escaped at serialization time). Also used for other text-bearing
        elements like ``<title>``/``<desc>`` (see ``accessibility.py``) — ``tag`` is
        restricted to a fixed allow-list of text-bearing SVG elements (not the general
        tag-name validation :meth:`add_node` uses): unlike attribute values, text
        *content* has no further escaping once inside an element, so allowing an
        arbitrary tag here would let ``<script>`` carry attacker-influenced content
        straight through as executable JS — the value-escaping ElementTree does still
        apply, but it's meaningless for that element's semantics, so ``"script"`` is
        never in the allow-list (and, since this module's "Security note (issue #12
        review)", is also rejected directly by :meth:`add_node`, which this method
        calls into — so the guarantee holds even for a caller that bypasses this
        method). ``"style"`` *is* allowed (see this module's top-level
        "Security note (issue #12)") but only because each of its sanctioned
        callers — listed in that note — independently validates every value it
        embeds before calling this method; this method itself still only guarantees
        XML-structural safety, not CSS-semantic safety, for ``<style>`` content.
        ``tag`` is keyword-only so a caller can never accidentally pass a positional
        ``attrib``/``classes`` argument that lands in this slot instead.
        """
        if tag not in _TEXT_BEARING_TAGS:
            raise ValueError(f"add_text only supports text-bearing tags {sorted(_TEXT_BEARING_TAGS)}, got {tag!r}")
        validated_text = _validate_text(text, "text content")
        if tag not in _MULTILINE_TEXT_TAGS:
            validated_text = _fold_newlines(validated_text)
        node = self.add_node(parent, tag, attrib=attrib, classes=classes)
        node.text = validated_text
        return node

    def set_attribute(self, node: ET.Element, key: str, value: str | int | float) -> None:
        """Set a validated attribute on an already-existing node (e.g. the document root).

        ``add_node``'s ``attrib`` only covers attributes set at creation time;
        this covers the other case — attaching an attribute to a node created
        earlier (or the root, which always exists before any ``add_node`` call).
        Goes through the same name/value validation as node creation. For
        ``key="class"`` specifically, the value is split on whitespace and each
        resulting class name is validated the same way ``add_node``'s ``classes=``
        validates each list entry (rejecting empty or XML-invalid class names) —
        unlike ``add_node``, a space-separated multi-class string here is the
        *correct* way to set several classes at once (it's the final attribute
        value, not a list of atomic entries), so it's accepted, not rejected.

        This does not otherwise restrict *which* attribute can be set (e.g. nothing
        stops overwriting ``xmlns``/``width``/``viewBox`` with an arbitrary value) —
        callers are responsible for only touching attributes they mean to.
        """
        _validate_name(key, "attribute")
        text_value = _validate_text(str(value), "attribute value")
        if key == "class":
            class_names = text_value.split()
            if not class_names:
                raise ValueError(f"invalid CSS class attribute value: {value!r}")
            for class_name in class_names:
                _validate_class_name(class_name)
        node.set(key, text_value)

    def semantic_class(self, prefix: str) -> str:
        """Return a semantic, incrementing class name like ``series-1`` — never a random hash."""
        count = self._class_counters.get(prefix, 0) + 1
        self._class_counters[prefix] = count
        return f"{prefix}-{count}"

    def to_string(self, *, pretty: bool = True, declaration: bool = True) -> str:
        """Serialize the document to an SVG string.

        With ``pretty=True`` (the default) the output is indented for readability
        and prefixed with an XML declaration, suitable for a standalone ``.svg``
        file. With ``pretty=False`` the output is a single compact line with no
        XML declaration, intended for inline embedding (e.g. ``_repr_svg_``)
        rather than as a standalone file. Indentation is applied to a copy of the
        tree, so calling ``to_string`` repeatedly (in either mode, in either
        order) never mutates the document or affects later calls.

        ``declaration=False`` drops the ``<?xml ...?>`` prolog while keeping the
        indentation. Markdown embedding needs exactly that combination: a prolog
        would render as literal text mid-document, but compact output can't be
        hand-edited, which is the whole premise of this package. It is a parameter
        rather than a caller-side ``removeprefix`` so serialization stays in one
        place. Ignored when ``pretty=False``, which never emits a prolog anyway.
        """
        if pretty:
            root = copy.deepcopy(self.root)
            ET.indent(root, space="  ")
            body = ET.tostring(root, encoding="unicode")
            prolog = '<?xml version="1.0" encoding="UTF-8"?>\n' if declaration else ""
            return f"{prolog}{body}\n"
        return ET.tostring(self.root, encoding="unicode")
