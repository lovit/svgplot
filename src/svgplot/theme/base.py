"""Theme — the ~25-key style schema (docs/research/12-aesthetics.md §1).

Immutable value object: rendering never mutates global state (unlike
matplotlib rcParams or seaborn's ``set_theme``). Passed explicitly to every
render call.
"""

from __future__ import annotations

from dataclasses import dataclass

# Colorblind-safe (Okabe-Ito) default palette — see docs/research/12-aesthetics.md §2/§4.
# Duplicated here (rather than imported from palette.colorblind) because that module
# isn't implemented yet; a future issue can point both at one shared constant.
_OKABE_ITO_PALETTE: tuple[str, ...] = (
    "#E69F00",
    "#56B4E9",
    "#009E73",
    "#F0E442",
    "#0072B2",
    "#D55E00",
    "#CC79A7",
    "#000000",
)


@dataclass(frozen=True)
class Theme:
    """A complete, immutable set of visual defaults for a chart.

    ~25 keys grouped by concern (background/foreground, palette, grid, spines,
    ticks, marks, per-element font sizes, legend) — deliberately far short of
    matplotlib's 344 rcParams or pygal's 83-key config, matching the
    "what actually makes a theme identity" set matplotlib's own defaults imply
    (docs/research/02-matplotlib.md A4). Immutability plus explicit
    render-call passing (rather than a global "current theme") is the design
    principle: two renders using the same ``Theme`` instance always look
    identical, and no render can leak style state into another.
    """

    # background / foreground
    background: str = "#ffffff"
    foreground: str = "#111111"
    # palette — colorblind-safe by default (docs/research/12-aesthetics.md §2)
    palette: tuple[str, ...] = _OKABE_ITO_PALETTE
    # grid (가이드선)
    grid_color: str = "#e0e0e0"
    grid_width: float = 1.0
    grid_style: str = "solid"
    # spines / axis lines
    spine_color: str = "#333333"
    spine_width: float = 1.0
    # ticks
    tick_color: str = "#333333"
    tick_size: float = 4.0
    tick_direction: str = "out"
    # marks
    line_width: float = 2.0
    marker_size: float = 5.0
    opacity: float = 1.0
    corner_radius: float = 0.0
    # fonts — one family, size per element (docs/research/12-aesthetics.md §3,
    # the "8-set" font structure collapsed into theme fields instead of pygal's
    # separate Style/Config split)
    font_family: str = "sans-serif"
    title_font_size: float = 18.0
    subtitle_font_size: float = 13.0
    axis_label_font_size: float = 12.0
    tick_label_font_size: float = 10.0
    legend_font_size: float = 11.0
    annotation_font_size: float = 10.0
    tooltip_font_size: float = 10.0
    caption_font_size: float = 9.0
    # legend
    legend_position: str = "right"

    def __post_init__(self) -> None:
        if isinstance(self.palette, list):
            object.__setattr__(self, "palette", tuple(self.palette))
