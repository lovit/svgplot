"""Color palette engine: qualitative/sequential/diverging + mini-language + colorblind-safe defaults."""

from __future__ import annotations

from svgplot.palette.colorblind import BLOCKED_PALETTES, DEFAULT_PALETTE, is_colorblind_safe
from svgplot.palette.diverging import diverging
from svgplot.palette.minilang import parse_palette_spec
from svgplot.palette.qualitative import QUALITATIVE_PALETTES, qualitative
from svgplot.palette.sequential import SEQUENTIAL_PALETTES, sequential

__all__ = [
    "BLOCKED_PALETTES",
    "DEFAULT_PALETTE",
    "QUALITATIVE_PALETTES",
    "SEQUENTIAL_PALETTES",
    "diverging",
    "is_colorblind_safe",
    "parse_palette_spec",
    "qualitative",
    "sequential",
]
