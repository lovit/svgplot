"""Sequential colormaps (needed for heatmap-family charts, docs-research/10-feature-matrix.md A5).

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

_MAX_CUBEHELIX_MAGNITUDE = 1e6
"""Sane upper bound on cubehelix's start/rot/gamma/hue — conventional values are
all well under 10, so this is generous headroom, not a real usage limit. It exists
purely to keep the trig/exponent math inside cubehelix_sequence's loop from ever
overflowing (see that function's docstring for exactly which computations that
protects), not because a legitimate parameter would ever approach it.
"""

SEQUENTIAL_PALETTES: dict[str, str] = {
    "blues": "#08519c",
    "greens": "#238b45",
    "oranges": "#d94801",
}
"""Named sequential colormaps: each maps to a seed color ramped light-to-seed
(docs-research/12-aesthetics.md §2, seaborn's ``light_palette``/``dark_palette``
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
        ValueError: if ``start``/``rot``/``hue`` isn't finite or exceeds a sane
            magnitude, or if ``gamma`` isn't a finite positive number exceeding
            a sane magnitude. A merely-finite-but-extreme parameter isn't
            enough to guarantee safety on its own: ``gamma`` feeds ``x**gamma``,
            which can overflow for large negative exponents even with a finite
            ``x``; ``start``/``rot`` feed a sum inside ``math.cos``/``math.sin``,
            which can itself overflow to ``inf`` even with both addends finite
            (``math.cos(inf)`` then raises its own unrelated-looking
            ``math domain error``). Bounding the inputs' magnitude up front
            keeps every downstream computation safely finite instead of trying
            to catch each way that could go wrong after the fact.
    """
    if n <= 0:
        return []
    if not math.isfinite(gamma) or gamma <= 0 or gamma > _MAX_CUBEHELIX_MAGNITUDE:
        raise ValueError(f"cubehelix gamma must be a finite positive number up to {_MAX_CUBEHELIX_MAGNITUDE:g}, got {gamma!r}")
    for param_name, value in (("start", start), ("rot", rot), ("hue", hue)):
        if not math.isfinite(value) or abs(value) > _MAX_CUBEHELIX_MAGNITUDE:
            raise ValueError(
                f"cubehelix {param_name} must be finite with magnitude up to {_MAX_CUBEHELIX_MAGNITUDE:g}, got {value!r}"
            )
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
