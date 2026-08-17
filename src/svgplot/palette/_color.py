"""Shared hex-color <-> RGB conversion, used by every generator in this package
(and by ``theme.context``'s parametric theme, which imports from here rather
than keeping its own copy — see git history for the duplication this replaced).

Private/internal — not re-exported from ``svgplot.palette``.
"""

from __future__ import annotations

import math
import re

# Anchored explicitly (not relying on fullmatch alone) so this stays strict even if a
# future refactor swaps .fullmatch() for .match()/.search() — matching _svg.py's
# _NAME_RE belt-and-braces style.
HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def hex_to_rgb01(hex_color: str) -> tuple[float, float, float]:
    """Parse a strict ``#rrggbb`` hex color (``#`` required, exactly 6 ASCII hex
    digits — not the more permissive syntax Python's own ``int(x, 16)`` would accept)
    into 0-1 RGB channels.
    """
    if not isinstance(hex_color, str) or not HEX_COLOR_RE.fullmatch(hex_color):
        raise ValueError(f"expected a 6-digit hex color like '#1a2b3c', got {hex_color!r}")
    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return r, g, b


def rgb01_to_hex(rgb: tuple[float, float, float]) -> str:
    """Format 0-1 RGB channels back into a ``#rrggbb`` hex color, clamped to range.

    Raises:
        ValueError: if any channel isn't finite (``nan``/``inf``) — the clamp
            below only bounds *finite* values; ``round()`` raises its own
            (undocumented-here) exception for non-finite input, which this
            turns into a clear, consistent error instead.
    """
    for channel in rgb:
        if not math.isfinite(channel):
            raise ValueError(f"cannot format a non-finite color channel: {channel!r}")
    return "#" + "".join(f"{max(0, min(255, round(channel * 255))):02x}" for channel in rgb)


def normalize_hex_color(hex_color: str) -> str:
    """Validate and re-encode a hex color, so equal colors always compare/print equal
    regardless of the input's case (round-trips through the same clamped encoder
    :func:`rgb01_to_hex` every generator in this package already uses).
    """
    return rgb01_to_hex(hex_to_rgb01(hex_color))
