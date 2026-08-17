"""SVG document builder.

Low-level XML tree construction used internally by ``chart.base.Chart`` and
``chart.composition.Composition``. Responsible for node creation, pretty-print
serialization, and assigning semantic (non-random) ``class``/``id`` values so
the generated SVG stays hand-editable (see docs/research/14-scope-recommendation.md,
핵심 원칙 1). Not part of the public API — always accessed through Chart/Composition.

Security note (PR #23 security review): this is the package's single escape
chokepoint. Every user-supplied string (labels, titles, data values) must be
inserted through this module's node/text-creation API — never via string
concatenation elsewhere — so text/attribute escaping happens in exactly one
place. Implementers: add ``_escape_text()``/``_escape_attr()`` here when
filling in the node API, and route all text through them.
"""

from __future__ import annotations


class SvgDocument:
    """A single SVG document being built up as a tree of nodes.

    Coordinates and other computed values are written as literals (not
    formulas) so the resulting markup can be read and hand-edited directly.
    """

    def __init__(self) -> None:
        raise NotImplementedError
