"""LabelSpec — field selection + format spec, ported from Bokeh's ``tooltips=[("label", "@field{format}")]``
mini-language (docs/research/17-static-hover-alternative.md). numeral/datetime/printf are the three
format schemes; ``{safe}``-style raw HTML is deliberately not supported.

Security note (PR #23 security review): the "printf" scheme's format string
comes from user input. Do not pass it to ``str.format()``/``%`` directly —
that allows attribute access injection (e.g. ``{0.__class__.__init__.__globals__}``).
Implementers: parse only a whitelisted set of printf-style conversion
specifiers instead of delegating to Python's general string formatting.
"""

from __future__ import annotations

FORMAT_SCHEMES = ("numeral", "datetime", "printf")


class LabelSpec:
    """A field+format specification shared by every static label renderer (table/inline/panel)."""

    def __init__(self, fields: list[tuple[str, str]]) -> None:
        raise NotImplementedError

    @classmethod
    def parse(cls, spec: list[tuple[str, str]] | str) -> LabelSpec:
        raise NotImplementedError
