"""Built-in Theme presets."""

from __future__ import annotations

from svgplot.theme.base import Theme

PRESETS: dict[str, Theme] = {
    "light": Theme(),
    "dark": Theme(
        background="#1e1e1e",
        foreground="#f5f5f5",
        grid_color="#3a3a3a",
        spine_color="#cccccc",
        tick_color="#cccccc",
    ),
    "minimal": Theme(grid_width=0.0, spine_width=0.0, tick_size=0.0),
    # fill_opacity=1.0 on both presets below: translucency is a readability aid for
    # overlapping fills on screen, but it works against what these two exist for.
    # Print reproduces blended translucency unreliably (halftone banding, ink density
    # shifts), and any translucency lowers the figure/ground contrast `high_contrast`
    # is specifically chosen to maximize.
    "print": Theme(
        foreground="#000000",
        spine_color="#000000",
        tick_color="#000000",
        grid_color="#cccccc",
        line_width=2.5,
        fill_opacity=1.0,
    ),
    "high_contrast": Theme(
        background="#ffffff",
        foreground="#000000",
        spine_color="#000000",
        tick_color="#000000",
        palette=("#000000", "#e69f00", "#0072b2", "#009e73", "#d55e00"),
        fill_opacity=1.0,
    ),
}
"""Built-in themes (docs/research/10-feature-matrix.md A4)."""
