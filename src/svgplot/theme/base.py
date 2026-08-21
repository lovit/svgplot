"""Theme — the ~25-key style schema (docs-research/12-aesthetics.md §1).

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

    26 fields ordered by concern (background/foreground, palette, grid, spines, ticks, marks,
    per-element font sizes, legend) — deliberately far short of matplotlib's 344 rcParams or
    pygal's 83-key config, matching the "what actually makes a theme identity" set
    matplotlib's own defaults imply (docs-research/02-matplotlib.md A4). Immutability plus
    explicit render-call passing (rather than a global "current theme") is the design
    principle: two renders using the same ``Theme`` instance always look identical, and no
    render can leak style state into another.

    **Nine of the 26 change no output byte on any of the sixteen charts today** --
    ``grid_style``, ``tick_direction``, ``legend_position``, and six of the font sizes. Each
    says so in its own docstring rather than in a list here, so a reader meets the fact where
    they meet the field. ``tests/test_theme_fields.py`` measures the split by rendering, so
    the docstrings cannot quietly go stale in either direction: implementing one of them fails
    the test until its docstring is corrected.
    """

    background: str = "#ffffff"
    """The plot background, drawn as a full-canvas rect before anything else."""

    foreground: str = "#111111"
    """Text colour for tick labels and legend entries."""

    palette: tuple[str, ...] = _DEFAULT_PALETTE
    """Series colours, cycled in series order. Colorblind-safe by default
    (docs-research/12-aesthetics.md §2).

    Accepts a list and stores a tuple: ``Theme`` is frozen, and a list default would let a
    caller mutate the palette of a theme two charts share. Must not be empty -- a chart would
    have no colour to assign and the cycle would divide by zero.
    """

    grid_color: str = "#e0e0e0"
    """Guide-line colour."""

    grid_width: float = 1.0
    """Guide-line stroke width in pixels."""

    grid_style: str = "solid"
    """Guide-line dash pattern. **Not consumed by any render path yet** -- the CSS emits no
    ``stroke-dasharray``, so changing this changes no output byte on any of the sixteen
    charts."""

    spine_color: str = "#333333"
    """Axis-line colour."""

    spine_width: float = 1.0
    """Axis-line stroke width in pixels."""

    tick_color: str = "#333333"
    """Tick-mark colour. The tick *label* takes :attr:`foreground`, not this."""

    tick_size: float = 4.0
    """Tick-mark length in pixels. Also the gap the axis leaves for its labels, so a larger
    value moves the labels out with the ticks rather than letting them overlap."""

    tick_direction: str = "out"
    """Which side of the axis the ticks sit on. **Not consumed by any render path yet** --
    every axis draws its ticks outward."""

    line_width: float = 2.0
    """Stroke width for line-like marks in pixels."""

    marker_size: float = 5.0
    """Marker radius in pixels. ``scatterplot(size=)`` maps its column into 0.5x to 2.5x of
    this, so it stays the centre of that range rather than a floor or a ceiling."""

    opacity: float = 1.0
    """Whole-mark opacity, applied to stroked and filled marks alike. Must be in ``[0, 1]``."""

    fill_opacity: float = 0.75
    """An *additional* opacity factor for filled marks (bars, areas, pie slices, scatter
    markers), multiplied with :attr:`opacity`. Must be in ``[0, 1]``.

    Filled marks occlude rather than merely overlap: an unstacked multi-hue area chart draws
    series in sorted-label order, unrelated to value magnitude, so a fully opaque later series
    can hide an earlier one entirely (issue #45). Keeping it separate from :attr:`opacity` is
    what lets a theme opt out of translucency with ``fill_opacity=1.0`` without disturbing
    stroke marks. 0.75 is a judgement call in the spirit of how seaborn treats overlapping
    distributions (it applies translucency selectively rather than as a global default): 25%
    bleed-through reads clearly as "something is underneath" while a lone fill still looks
    solid rather than washed out. It applies to every ``mark_style="fill"`` chart including
    ones whose marks rarely overlap (pie slices are disjoint), where it is a small cost paid
    for one uniform rule rather than a per-chart-type default.
    """

    corner_radius: float = 0.0
    """Corner rounding in pixels for rectangular marks: ``barplot`` bars, ``histplot`` bars and
    ``boxplot`` bodies. Treemap tiles keep square corners -- a tile's neighbours are its own
    edges, and rounding them opens gaps that read as gaps in the data."""

    font_family: str = "sans-serif"
    """One family for every text element. Also what the width estimator measures against, so
    a change here moves the layout as well as the glyphs."""

    title_font_size: float = 18.0
    """Size for a drawn chart title. **Nothing draws one yet** -- ``Chart.set_title`` writes
    the title into the SVG's ``<title>``/``aria-label``, which is metadata a browser and a
    screen reader present in their own type. :func:`~svgplot.theme.context.apply_context`
    scales this field, so it is ready for the renderer that will use it."""

    subtitle_font_size: float = 13.0
    """Size for a drawn subtitle. **Nothing draws one yet**; see :attr:`title_font_size`."""

    axis_label_font_size: float = 12.0
    """Size for an axis *name* ("Sales", "Year"). **Nothing draws one yet** -- no chart emits
    an axis title; :attr:`tick_label_font_size` is the one that sizes the numbers."""

    tick_label_font_size: float = 10.0
    """Size for tick labels. The most load-bearing font field: the axis measures label widths
    at this size to decide the left margin, how many ticks fit, and whether a category label
    has to be shortened."""

    legend_font_size: float = 11.0
    """Size for legend entries. Also measured, for the same reason -- it sets how much width
    the legend reserves."""

    annotation_font_size: float = 10.0
    """Size for in-plot annotations. **Nothing draws one at this size yet** -- the labels
    inside pie slices, treemap tiles and gauges take :attr:`legend_font_size`, which is what
    styles them today."""

    tooltip_font_size: float = 10.0
    """Size for tooltip text. **Unreachable, not merely unimplemented**: ``tooltip=True``
    emits ``<title>`` elements, which browsers render as native chrome outside the document.
    No CSS this package writes can reach them, so this field would need a tooltip built out
    of SVG elements before it could mean anything."""

    caption_font_size: float = 9.0
    """Size for a caption below the plot. **Nothing draws one yet**; see
    :attr:`title_font_size`."""

    legend_position: str = "right"
    """Where the legend sits. **Not consumed by any render path yet** -- every chart that
    draws a legend puts it to the right of the plot area."""

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
