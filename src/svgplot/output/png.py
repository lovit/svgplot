"""PNG raster export via an optional dependency (cairosvg), matching pygal's precedent
of keeping the core install light (docs/research/01-pygal.md A8).

Security note (PR #23 security review): when adding cairosvg as the ``png``
extra in pyproject.toml, pin ``cairosvg>=2.7.0`` — versions below that are
affected by an SSRF issue (CVE-2023-27586) via external references inside
untrusted SVG input. cairosvg's own ``unsafe=False`` default (which this
module relies on implicitly by not overriding it) additionally blocks fetching
non-``data:`` external references regardless of version.
"""

from __future__ import annotations

from svgplot._svg import SvgDocument
from svgplot.output.svg import to_string


def to_png(document: SvgDocument, path: str) -> None:
    """Rasterize an SvgDocument to a PNG file. Requires the ``png`` extra.

    ``path`` is a filesystem path chosen by the caller — this is a library
    function, not a web endpoint. Callers embedding user-supplied filenames
    (e.g. in a web service) are responsible for validating/resolving them
    (same boundary as ``output.svg.save_svg``).
    """
    try:
        import cairosvg
    except (ImportError, OSError) as error:
        # ImportError: the cairosvg package itself isn't installed.
        # OSError: cairosvg is installed but its native libcairo library is missing
        # (cairocffi raises OSError from dlopen in that case) — both mean "not usable".
        raise ImportError(
            "PNG export requires the optional 'png' extra: install with `uv add svgplot[png]` (or `pip install svgplot[png]`)."
        ) from error
    cairosvg.svg2png(bytestring=to_string(document, pretty=False).encode("utf-8"), write_to=path)
