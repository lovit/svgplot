"""SVG string/file export — pretty-printed by default (see docs/research/14-scope-recommendation.md, 핵심 원칙 1)."""

from __future__ import annotations

from svgplot._svg import SvgDocument


def to_string(document: SvgDocument, *, pretty: bool = True) -> str:
    """Serialize an SvgDocument to an SVG string."""
    raise NotImplementedError


def save_svg(document: SvgDocument, path: str, *, pretty: bool = True) -> None:
    """Write an SvgDocument to a .svg file.

    ``path`` is a filesystem path chosen by the caller — this is a library
    function, not a web endpoint. Callers embedding user-supplied filenames
    (e.g. in a web service) are responsible for validating/resolving them.
    """
    raise NotImplementedError
