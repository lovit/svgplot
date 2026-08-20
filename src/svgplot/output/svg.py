"""SVG string/file export — pretty-printed by default (see docs-research/14-scope-recommendation.md, 핵심 원칙 1)."""

from __future__ import annotations

from pathlib import Path

from svgplot._svg import SvgDocument


def to_string(document: SvgDocument, *, pretty: bool = True, declaration: bool = True) -> str:
    """Serialize an SvgDocument to an SVG string.

    ``declaration=False`` drops the XML prolog while keeping the indentation — what
    markdown embedding needs. See :meth:`svgplot._svg.SvgDocument.to_string`.
    """
    return document.to_string(pretty=pretty, declaration=declaration)


def save_svg(document: SvgDocument, path: str, *, pretty: bool = True) -> None:
    """Write an SvgDocument to a .svg file.

    ``path`` is a filesystem path chosen by the caller — this is a library
    function, not a web endpoint. Callers embedding user-supplied filenames
    (e.g. in a web service) are responsible for validating/resolving them.
    """
    Path(path).write_text(to_string(document, pretty=pretty), encoding="utf-8")
