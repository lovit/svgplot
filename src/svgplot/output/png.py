"""PNG raster export via an optional dependency (cairosvg), matching pygal's precedent
of keeping the core install light (docs/research/01-pygal.md A8).

Security note (PR #23 security review): when adding cairosvg as the ``png``
extra in pyproject.toml, pin ``cairosvg>=2.7.0`` — versions below that are
affected by an SSRF issue (CVE-2023-27586) via external references inside
untrusted SVG input.
"""

from __future__ import annotations

from svgplot._svg import SvgDocument


def to_png(document: SvgDocument, path: str) -> None:
    """Rasterize an SvgDocument to a PNG file. Requires the ``png`` extra."""
    raise NotImplementedError
