"""SVG string/file export — pretty-printed by default (see docs/research/14-scope-recommendation.md, 핵심 원칙 1)."""

from __future__ import annotations


def to_string(document: object, *, pretty: bool = True) -> str:
    """Serialize an SvgDocument to an SVG string."""
    raise NotImplementedError


def save_svg(document: object, path: str, *, pretty: bool = True) -> None:
    """Write an SvgDocument to a .svg file."""
    raise NotImplementedError
