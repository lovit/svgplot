"""Colorblind-safe default palette and known-bad-colormap blocking.

The default palette is colorblind-safe (Okabe-Ito family) — not opt-in, see
docs/research/12-aesthetics.md §2 and docs/research/10-feature-matrix.md A9.
Perceptually problematic colormaps (e.g. "jet") are rejected, following
seaborn's ``"jet" -> ValueError`` precedent.
"""

from __future__ import annotations

DEFAULT_PALETTE: list[str] = [
    "#E69F00",
    "#56B4E9",
    "#009E73",
    "#F0E442",
    "#0072B2",
    "#D55E00",
    "#CC79A7",
    "#000000",
]
"""The default qualitative palette used when no palette is specified. Must be colorblind-safe
(Okabe & Ito, 2008) — also the canonical form of this palette in the package: ``theme.base.Theme``
imports this rather than keeping its own copy.
"""

BLOCKED_PALETTES: set[str] = {"jet", "rainbow", "hsv"}
"""Palette/colormap names rejected outright rather than silently accepted — all
perceptually non-uniform (misleading apparent magnitude jumps) and not colorblind-safe.
"""

_COLORBLIND_SAFE_PALETTE_NAMES: frozenset[str] = frozenset({"colorblind"})


def is_colorblind_safe(name: str) -> bool:
    """Report whether the named palette is known to be colorblind-safe."""
    return name in _COLORBLIND_SAFE_PALETTE_NAMES
