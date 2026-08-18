"""Theme — the ~25-key style schema (docs/research/12-aesthetics.md §1).

Immutable value object: rendering never mutates global state (unlike
matplotlib rcParams or seaborn's ``set_theme``). Passed explicitly to every
render call.

Security note (forward-looking — no render path consumes ``Theme`` yet): every
color/text field here is a plain, unvalidated ``str`` — this is a trusted value
object (built by the developer, e.g. via ``PRESETS``/``parametric_theme``), not
untrusted input. Whoever wires ``Theme`` into rendering must insert these
values through ``_svg.py``'s validated API (``add_node``/``add_text``/
``set_attribute``), never via raw string concatenation — see ``_svg.py``'s own
"escape chokepoint" docstring. That covers XML-structural safety, but **not**
CSS syntax: `_svg.py`'s validation rejects the `style=` attribute and inline
event handlers, but if a future renderer emits a `<style>` block (CSS text,
not an XML attribute) built by directly interpolating these color strings, XML
escaping alone doesn't stop `}`/`;`/`@import`/`url(...)` from breaking out of a
CSS rule — a value bound for a `<style>` block needs its own CSS-literal
validation, not just this module's implicit trust.
"""

from __future__ import annotations

from dataclasses import dataclass

from svgplot.palette.colorblind import DEFAULT_PALETTE

# Snapshot as an immutable tuple at import time: DEFAULT_PALETTE is a plain (mutable)
# list in palette.colorblind, and a dataclass field default is evaluated once at class
# definition — using the list directly would make Theme()'s default palette vulnerable
# to later in-place mutation of the shared list.
_DEFAULT_PALETTE: tuple[str, ...] = tuple(DEFAULT_PALETTE)


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
    palette: tuple[str, ...] = _DEFAULT_PALETTE
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
    # Filled marks (bars/areas/pie slices) get an *additional* opacity factor on top of
    # `opacity`, because they occlude rather than merely overlap: an unstacked multi-hue
    # area chart draws series in sorted-label order, unrelated to value magnitude, so a
    # fully opaque later series can hide an earlier one entirely (issue #45). The two
    # multiply — `opacity` stays the whole-mark knob applying to stroked and filled marks
    # alike, `fill_opacity` narrows to fills only — so a theme opts out of translucency
    # with `fill_opacity=1.0` without disturbing stroke marks. 0.75 is a judgement call in
    # the spirit of how seaborn treats overlapping distributions (it applies translucency
    # selectively rather than as a global default): 25% bleed-through reads clearly as
    # "something is underneath" while a lone fill still looks solid rather than washed out.
    # It applies to every `mark_style="fill"` chart — bars, areas, pie slices and scatter
    # markers — including ones whose marks rarely overlap (pie slices are disjoint), where
    # it is a small cost paid for one uniform rule rather than a per-chart-type default.
    fill_opacity: float = 0.75
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
        palette = tuple(self.palette) if isinstance(self.palette, list) else self.palette
        if not palette:
            raise ValueError("palette must not be empty")
        object.__setattr__(self, "palette", palette)
        # Validated here rather than left to theme.css's format_coord: an out-of-range
        # (but finite) value like 5.0 would sail past that check and emit nonsense CSS
        # ("opacity: 5"), and the failure would surface at render time far from the Theme
        # that caused it. Both opacity fields get this — they reach CSS the same way, so
        # validating only one would leave the identical hole open on the other.
        for field in ("opacity", "fill_opacity"):
            value = getattr(self, field)
            if not isinstance(value, int | float) or isinstance(value, bool):
                raise ValueError(f"{field} must be a real number, got {value!r}")
            # A range check alone rejects nan/inf too (every comparison with nan is False,
            # and inf fails the upper bound), so no separate isfinite() call is needed.
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field} must be a number in [0, 1], got {value!r}")
