"""Confining a chart's CSS to that chart, so two of them can share one HTML document.

An inline ``<svg>``'s ``<style>`` is *not* scoped to the SVG — it applies to the whole host
document. Every chart numbers its series from ``series-1``, so two charts inlined together
both define ``.series-1``, with opposite rules::

    lineplot   .series-1 { stroke: #E69F00; fill: none; stroke-width: 2; opacity: 1; }
    barplot    .series-1 { fill: #E69F00; stroke: none; opacity: 0.75; }

The later one wins and repaints the earlier. Since this package exists to put charts into
markdown and HTML, a default output that breaks when two are embedded together is the bug.

**Selectors are rewritten; ``class`` attributes are not.** ``.series-1`` stays ``.series-1``
on the element, and the rule that styles it becomes ``:where(.svgplot-fXXXXXXXX) .series-1``.
``:where()`` contributes no specificity, so the rule keeps the ``(0,1,0)`` it has today and a
reader's own ``.series-1 { stroke: red }`` still behaves exactly as it did. A bare prefix
(``.svgplot-fXXXXXXXX .series-1``) would raise it to ``(0,2,0)`` and quietly beat the very
overrides this package is built to accept. ``:is()`` has the same problem — it takes the
maximum specificity of its argument. Verified against ``cssselect2``, the selector engine
cairosvg rasterizes through: ``:where(.s) .m`` compiles, matches, reports ``(0, 1, 0)``, and
produces a byte-identical PNG to the unscoped rule.

The token is a hash of the document rather than of the rule text. Equal rule text would be a
tempting key — two charts sharing a token would then share identical rules, so sharing is
harmless — but that holds only while every rule is rule-local. A future selector that reaches
across the scope element (``:where(.scope):has(.series-1:hover)``) would make two charts with
identical palettes interfere. Hashing the whole document narrows token sharing to "the same
picture, byte for byte", where sharing is harmless by construction rather than by argument.
"""

from __future__ import annotations

import hashlib
import re

from svgplot._svg import SvgDocument

RESPONSIVE_CLASS = "svgplot-responsive"
# No caller input reaches this CSS — it is a literal constant, the safest case of
# the "CSS-semantic safety is the caller's job" contract in _svg.py's security note.
RESPONSIVE_CSS = f".{RESPONSIVE_CLASS} {{ max-width: 100%; height: auto; }}"
"""Lives here rather than in ``layout.sizing`` so the producer of this rule and the predicate
that must skip it read from one definition. See :func:`apply_scope` for why it is skipped."""

CSS_CLASS_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def validate_css_class_name(value: str, *, kind: str = "series") -> str:
    """Reject a class name that would not survive being written into a CSS selector.

    Lives here rather than in ``theme.css`` only because both that module and
    :meth:`svgplot.chart.base.Chart.set_scope` need it, and this module is a leaf --
    ``theme.css`` sits downstream of ``charts``, which imports ``Chart``.

    Stricter than ``_svg.validate_element_id``, deliberately: that one enforces XML 1.0,
    which permits ``{``/``}``/``;`` -- CSS-unsafe but XML-safe. A name like
    ``"x{}body{background:red}.y"`` is a CSS-breakout vector the XML rule would wave through.
    """
    if not isinstance(value, str) or not CSS_CLASS_NAME_RE.fullmatch(value):
        raise ValueError(f"{kind} class name must match {CSS_CLASS_NAME_RE.pattern!r} for safe CSS embedding, got {value!r}")
    return value


_TOKEN_PREFIX = "svgplot-f"
_TOKEN_LENGTH = 8

_SELECTOR_AND_BODY = re.compile(r"^(?P<selectors>[^{]+)(?P<body>\{.*)$")


def scope_token(document: SvgDocument) -> str:
    """A deterministic scope class for ``document``, derived from its own bytes.

    ``hashlib`` rather than ``hash()``: the latter is salted per process, and this package
    guarantees the same input yields the same SVG. Prefixed because a CSS class may not begin
    with a digit — ``validate_css_class_name`` rejects one that does.
    """
    digest = hashlib.sha256(document.to_string(pretty=False, declaration=False).encode()).hexdigest()
    return f"{_TOKEN_PREFIX}{digest[:_TOKEN_LENGTH]}"


def _scope_rule(rule: str, token: str) -> str:
    """Prefix every selector in one rule, leaving the declarations untouched.

    Splitting on commas rather than prefixing the line once: ``a, b { … }`` would otherwise
    scope only ``a`` and leave ``b`` document-global — the exact leak this module exists to
    close, hidden in the one shape that still looks scoped.
    """
    match = _SELECTOR_AND_BODY.match(rule)
    if match is None:
        return rule
    selectors = ", ".join(f":where(.{token}) {part.strip()}" for part in match["selectors"].split(","))
    return f"{selectors} {match['body']}"


def apply_scope(document: SvgDocument, scope: str | None = None) -> str:
    """Confine ``document``'s CSS to itself and return the scope class used.

    Mutates in place; callers pass a copy (see :meth:`svgplot.chart.base.Chart._accessible_document`).

    ``RESPONSIVE_CSS`` is skipped, and must be: its class sits on the *root*, and a descendant
    combinator cannot match the element carrying the scope class. Scoping it would leave the
    class in place, the rule syntactically fine, and responsive sizing silently dead — the
    failure mode with no symptom. It stays a global hook a host page can target, which is what
    it was always documented to be.

    The rewrite is a token substitution rather than a CSS parse, which is sound only because
    ``theme.css.render_theme_style`` is the sole producer of chart CSS and validates every
    value it interpolates, so a selector token can never appear inside a declaration. Chart
    ``<style>`` is therefore required to stay flat: one rule per line, no at-rules. A ``@media``
    block would put a line starting with ``@`` and a bare closing brace through this function.
    """
    token = scope or scope_token(document)
    for element in document.root.iter():
        if element.tag != "style" or not element.text or element.text == RESPONSIVE_CSS:
            continue
        element.text = "\n".join(_scope_rule(line, token) if line.strip() else line for line in element.text.split("\n"))

    existing = document.root.get("class", "").split()
    if token not in existing:
        document.set_attribute(document.root, "class", " ".join([*existing, token]))
    return token
