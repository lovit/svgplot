"""style x context separation and parametric (seed-color) themes.

context scales font/line-width the way seaborn's paper/notebook/talk/poster
does, but as a pure function (no rcParams mutation) — see
docs/research/12-aesthetics.md §1. Scoped context-manager application is a
2차 addition planned for this same file.
"""

from __future__ import annotations

import colorsys
from dataclasses import replace

from svgplot.theme.base import Theme

CONTEXTS: dict[str, float] = {
    "paper": 0.8,
    "notebook": 1.0,
    "talk": 1.3,
    "poster": 1.6,
}
"""Named scale factors (seaborn precedent) applied to font sizes and line/marker/tick weight."""


def apply_context(theme: Theme, context: str) -> Theme:
    """Return a new ``Theme`` with sizes scaled for ``context`` — a pure function;
    ``theme`` itself (and any other ``Theme`` referencing the same style) is untouched.

    Raises:
        ValueError: if ``context`` isn't one of :data:`CONTEXTS`.
    """
    if context not in CONTEXTS:
        raise ValueError(f"unknown context: {context!r} (expected one of {sorted(CONTEXTS)})")
    scale = CONTEXTS[context]
    return replace(
        theme,
        line_width=theme.line_width * scale,
        marker_size=theme.marker_size * scale,
        tick_size=theme.tick_size * scale,
        title_font_size=theme.title_font_size * scale,
        subtitle_font_size=theme.subtitle_font_size * scale,
        axis_label_font_size=theme.axis_label_font_size * scale,
        tick_label_font_size=theme.tick_label_font_size * scale,
        legend_font_size=theme.legend_font_size * scale,
        annotation_font_size=theme.annotation_font_size * scale,
        tooltip_font_size=theme.tooltip_font_size * scale,
        caption_font_size=theme.caption_font_size * scale,
    )


def _hex_to_rgb01(hex_color: str) -> tuple[float, float, float]:
    """Parse a ``#rrggbb`` hex color into 0-1 RGB channels."""
    stripped = hex_color.lstrip("#")
    if len(stripped) != 6:
        raise ValueError(f"expected a 6-digit hex color like '#1a2b3c', got {hex_color!r}")
    try:
        r, g, b = (int(stripped[i : i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError as error:
        raise ValueError(f"expected a 6-digit hex color like '#1a2b3c', got {hex_color!r}") from error
    return r, g, b


def _rgb01_to_hex(rgb: tuple[float, float, float]) -> str:
    """Format 0-1 RGB channels back into a ``#rrggbb`` hex color, clamped to range."""
    return "#" + "".join(f"{max(0, min(255, round(channel * 255))):02x}" for channel in rgb)


def _rotate_hue_palette(seed_color: str, count: int = 6) -> tuple[str, ...]:
    """Generate ``count`` colors by rotating hue evenly around ``seed_color``, keeping
    its saturation/lightness — a small, dependency-free brand-color-to-palette scheme
    (stdlib ``colorsys`` only; no numpy/colour-science dependency needed for v1).
    """
    hue, lightness, saturation = colorsys.rgb_to_hls(*_hex_to_rgb01(seed_color))
    return tuple(
        _rgb01_to_hex(colorsys.hls_to_rgb((hue + index / count) % 1.0, lightness, saturation)) for index in range(count)
    )


def parametric_theme(seed_color: str) -> Theme:
    """Derive a full Theme from a single brand seed color (pygal parametric-style precedent).

    The seed color anchors the palette (used to generate a hue-rotated qualitative
    palette) and the spine/tick color; background/foreground stay at ``Theme``'s
    neutral defaults.
    """
    return Theme(palette=_rotate_hue_palette(seed_color), spine_color=seed_color, tick_color=seed_color)
