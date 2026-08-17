"""Color palette engine: qualitative/sequential/diverging + mini-language + colorblind-safe defaults."""

from __future__ import annotations

from svgplot.palette.colorblind import DEFAULT_PALETTE, is_colorblind_safe
from svgplot.palette.diverging import diverging
from svgplot.palette.minilang import parse_palette_spec
from svgplot.palette.qualitative import qualitative
from svgplot.palette.sequential import sequential

__all__ = [
    "DEFAULT_PALETTE",
    "diverging",
    "is_colorblind_safe",
    "parse_palette_spec",
    "qualitative",
    "sequential",
]
