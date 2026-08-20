"""Qualitative (categorical) palettes."""

from __future__ import annotations

from svgplot.palette.colorblind import BLOCKED_PALETTES, DEFAULT_PALETTE

QUALITATIVE_PALETTES: dict[str, list[str]] = {
    "colorblind": list(DEFAULT_PALETTE),
    "pastel": ["#a6cee3", "#b2df8a", "#fdbf6f", "#fb9a99", "#cab2d6", "#ffff99"],
    "dark": ["#1b9e77", "#d95f02", "#7570b3", "#e7298a", "#66a61e", "#e6ab02"],
}
"""Named qualitative palettes; default entry (``"colorblind"``) is colorblind-safe (palette.colorblind)."""


def qualitative(name: str, n: int) -> list[str]:
    """Return ``n`` colors from the named qualitative palette.

    If ``n`` exceeds the palette's size, colors repeat (cycle) rather than erroring —
    perceptually-uniform cyclic extension (varying lightness in e.g. OKLCH instead of
    flatly repeating) is a 2차 refinement, docs-research/12-aesthetics.md §2.

    Raises:
        ValueError: if ``name`` isn't a string, is in
            :data:`svgplot.palette.colorblind.BLOCKED_PALETTES`, or if ``n`` is negative.
        KeyError: if ``name`` isn't a registered qualitative palette.
    """
    if not isinstance(name, str):
        raise ValueError(f"palette name must be a string, got {name!r}")
    if name in BLOCKED_PALETTES:
        raise ValueError(
            f"palette {name!r} is blocked (perceptually non-uniform / not colorblind-safe); "
            f"use one of {sorted(QUALITATIVE_PALETTES)}"
        )
    if name not in QUALITATIVE_PALETTES:
        raise KeyError(f"unknown qualitative palette: {name!r} (available: {sorted(QUALITATIVE_PALETTES)})")
    if n < 0:
        raise ValueError(f"n must be non-negative, got {n}")
    base = QUALITATIVE_PALETTES[name]
    if n <= len(base):
        return base[:n]
    return [base[i % len(base)] for i in range(n)]
