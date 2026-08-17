"""Sequential colormaps (needed for heatmap-family charts, docs/research/10-feature-matrix.md A5).

Generation algorithms here (light/dark gray-anchor ramp, blend, cubehelix) are
also reused by ``minilang.py`` for the ``light:``/``dark:``/``blend:``/``ch:``
mini-language specs — those parse a spec string and dispatch into the same
generators a named ``sequential()`` colormap uses.
"""

from __future__ import annotations

import colorsys
import math

from svgplot.palette._color import hex_to_rgb01, rgb01_to_hex
from svgplot.palette.colorblind import BLOCKED_PALETTES

SEQUENTIAL_PALETTES: dict[str, str] = {
    "blues": "#08519c",
    "greens": "#238b45",
    "oranges": "#d94801",
}
"""Named sequential colormaps: each maps to a seed color ramped light-to-seed
(docs/research/12-aesthetics.md §2, seaborn's ``light_palette``/``dark_palette``
"same-hue gray anchor" precedent).
"""


def sequential(name: str, n: int) -> list[str]:
    """Return ``n`` colors sampled from the named sequential colormap.

    Raises:
        ValueError: if ``name`` isn't a string, is in
            :data:`svgplot.palette.colorblind.BLOCKED_PALETTES`, or if ``n`` is negative.
        KeyError: if ``name`` isn't a registered sequential colormap.
    """
    if not isinstance(name, str):
        raise ValueError(f"palette name must be a string, got {name!r}")
    if name in BLOCKED_PALETTES:
        raise ValueError(f"palette {name!r} is blocked (perceptually non-uniform); use one of {sorted(SEQUENTIAL_PALETTES)}")
    if name not in SEQUENTIAL_PALETTES:
        raise KeyError(f"unknown sequential palette: {name!r} (available: {sorted(SEQUENTIAL_PALETTES)})")
    if n < 0:
        raise ValueError(f"n must be non-negative, got {n}")
    return light_dark_sequence(SEQUENTIAL_PALETTES[name], n, dark=False)


def light_dark_sequence(seed_color: str, n: int, *, dark: bool) -> list[str]:
    """Ramp from a near-white (or, if ``dark``, near-black) gray anchor to ``seed_color``,
    keeping ``seed_color``'s hue/saturation throughout (seaborn's ``light_palette``/
    ``dark_palette`` "same-hue gray anchor" algorithm — see module docstring).
    """
    hue, lightness, saturation = colorsys.rgb_to_hls(*hex_to_rgb01(seed_color))
    anchor_lightness = 0.15 if dark else 0.95
    if n <= 0:
        return []
    steps = max(n - 1, 1)
    return [
        rgb01_to_hex(colorsys.hls_to_rgb(hue, anchor_lightness + (index / steps) * (lightness - anchor_lightness), saturation))
        for index in range(n)
    ]


def blend_sequence(hex_a: str, hex_b: str, n: int) -> list[str]:
    """Linearly interpolate ``n`` colors between two hex colors (RGB space)."""
    r1, g1, b1 = hex_to_rgb01(hex_a)
    r2, g2, b2 = hex_to_rgb01(hex_b)
    if n <= 0:
        return []
    steps = max(n - 1, 1)
    return [
        rgb01_to_hex((r1 + (index / steps) * (r2 - r1), g1 + (index / steps) * (g2 - g1), b1 + (index / steps) * (b2 - b1)))
        for index in range(n)
    ]


def cubehelix_sequence(n: int, *, start: float = 0.5, rot: float = -1.5, gamma: float = 1.0, hue: float = 1.0) -> list[str]:
    """Generate ``n`` colors along Green (2011)'s cubehelix color scheme — a
    perceptually-monotonic-lightness rainbow ramp (the ``ch:`` mini-language spec).

    Raises:
        ValueError: if ``start``/``rot``/``gamma``/``hue`` isn't finite — an
            overflowed (``inf``) or invalid (``nan``) parameter would otherwise
            propagate into ``math.cos``/``math.sin`` (raising an unrelated-looking
            ``math domain error``) or into the final clamped hex encoding
            (raising ``OverflowError``, which isn't this function's documented
            exception type).
    """
    if n <= 0:
        return []
    for param_name, value in (("start", start), ("rot", rot), ("gamma", gamma), ("hue", hue)):
        if not math.isfinite(value):
            raise ValueError(f"cubehelix {param_name} must be finite, got {value!r}")
    dark, light = 0.15, 0.85
    steps = max(n - 1, 1)
    colors = []
    for index in range(n):
        x = dark + (index / steps) * (light - dark)
        # Green (2011) Table 1's fixed RGB rotation-matrix coefficients — not
        # tunable parameters, just this color scheme's defining constants.
        lam = x**gamma
        phi = 2 * math.pi * (start / 3 + rot * x)
        amplitude = hue * lam * (1 - lam) / 2
        r = lam + amplitude * (-0.14861 * math.cos(phi) + 1.78277 * math.sin(phi))
        g = lam + amplitude * (-0.29227 * math.cos(phi) - 0.90649 * math.sin(phi))
        b = lam + amplitude * (1.97294 * math.cos(phi))
        colors.append(rgb01_to_hex((r, g, b)))
    return colors
