"""Colorblind-safe default palette and known-bad-colormap blocking.

The default palette is colorblind-safe (Okabe-Ito family) — not opt-in, see
docs/research/12-aesthetics.md §2 and docs/research/10-feature-matrix.md A9.
Perceptually problematic colormaps (e.g. "jet") are rejected, following
seaborn's ``"jet" -> ValueError`` precedent.
"""

from __future__ import annotations

DEFAULT_PALETTE: list[str] = []
"""The default qualitative palette used when no palette is specified. Must be colorblind-safe."""

BLOCKED_PALETTES: set[str] = {"jet"}
"""Palette/colormap names rejected outright rather than silently accepted."""


def is_colorblind_safe(name: str) -> bool:
    """Report whether the named palette is known to be colorblind-safe."""
    raise NotImplementedError
