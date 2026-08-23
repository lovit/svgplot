"""Theme — the 26-key style schema (docs-research/12-aesthetics.md §1).

Immutable value object: rendering never mutates global state (unlike
matplotlib rcParams or seaborn's ``set_theme``). Passed explicitly to every
render call.

Security note: every color/text field here is a plain, unvalidated ``str`` **at this layer**.
``Theme`` is a trusted value object — built by the developer, e.g. via ``PRESETS`` or
``parametric_theme`` — not untrusted input, so the validation lives where the values reach
the output rather than here.

``theme/css.py`` is that place, and it is no longer hypothetical: it emits a ``<style>``
block built by interpolating these strings, so XML escaping alone would not stop
``}``/``;``/``@import``/``url(...)`` from breaking out of a CSS rule. It therefore validates
each value as a CSS literal before use — ``_validate_css_color`` requires a strict
``#rrggbb``, and ``_validate_css_font_family`` allows only letters, digits, spaces,
commas, hyphens and apostrophes. (Its ``_validate_css_class_name`` guards the selectors
those values sit in, which come from the chart rather than from ``Theme``.) Anything
else that wires ``Theme`` into rendering has the same obligation, plus ``_svg.py``'s
validated API (``add_node``/``add_text``/``set_attribute``) for XML-structural safety rather
than raw string concatenation — see ``_svg.py``'s own "escape chokepoint" docstring.
"""

from __future__ import annotations

import math
import numbers
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
    """Guide-line dash pattern. **Changes no output byte today** -- the CSS emits no
    ``stroke-dasharray``, so no chart can tell one value from another."""

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
    """Which side of the axis the ticks sit on. **Changes no output byte today** -- every axis
    draws its ticks outward whatever this says."""

    line_width: float = 2.0
    """Stroke width for line-like marks in pixels."""

    marker_size: float = 5.0
    """Marker radius in pixels, and the radius every marker takes when ``size=`` is not given.

    ``scatterplot(size=)`` maps its column linearly onto 0.5x to 2.5x of this, so this value
    is the *smallest* end plus a quarter of the range rather than its middle -- the midpoint
    of that interval is 1.5x. A chart that raised ``marker_size`` to make its points easier to
    see grows the largest ones by the same factor as the smallest.
    """

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
    """Corner rounding in pixels, applied to ``barplot`` bars, ``histplot`` bars and
    ``boxplot`` bodies.

    Three other rectangles ignore it, and only the first is a decision: treemap tiles keep
    square corners because a tile's neighbours are its own edges and rounding them opens gaps
    that read as gaps in the data, and the same argument covers ``heatmap`` cells. The third,
    ``violinplot(inner="box")``'s quartile box, is simply inconsistent -- ``violin.py`` never
    reads this field, so that box stays square while the ``boxplot`` it is drawn to coincide
    with rounds.

    A **legend swatch follows the marks it names**, at the same radius. A key shaped differently
    from what it points at reads as "not that one", and a rounded bar beside a square swatch was
    an inconsistency rather than a decision -- this paragraph is the one that was missing when
    the other three had reasons written down (#265). The radius is not scaled for the swatch's
    16x10: SVG clamps ``rx`` at half the shorter side, so a value big enough to make a swatch a
    lozenge has already done the same to the bars, and the two agree at every setting rather
    than only small ones. ``boxplot`` has no swatch to round -- its legend is drawn with
    ``<line>`` -- so this reaches ``barplot`` and ``histplot``.
    """

    font_family: str = "sans-serif"
    """The family every text element a *chart* draws is set in, and what the width estimator
    measures against -- so a change here moves the layout as well as the glyphs.

    A composition's own text does not follow it: ``layout.add_caption``'s caption and
    ``grid(titles=)``'s headings are written at a hardcoded ``sans-serif``, because they
    belong to the figure rather than to any one chart in it and a figure has no theme.
    """

    title_font_size: float = 18.0
    """Size for a drawn chart title. **Changes no output byte today.** ``Chart.set_title`` writes the
    title into the SVG's ``<title>``/``aria-label``, which is metadata a browser and a screen
    reader present in their own type; ``grid(titles=)`` does draw visible headings, but at a
    hardcoded 13px belonging to the composition rather than to a chart's theme.
    :func:`~svgplot.theme.context.apply_context` scales this field, so it is ready for the
    renderer that will use it."""

    subtitle_font_size: float = 13.0
    """Size for a drawn subtitle. **Changes no output byte today** -- no chart and no
    composition emits a subtitle at all, so unlike :attr:`title_font_size` there is not even a
    hardcoded size for this to disagree with."""

    axis_label_font_size: float = 12.0
    """Size for an axis *name* ("Sales", "Year"). **Changes no output byte today** -- no chart
    emits an axis title; :attr:`tick_label_font_size` is the one that sizes the numbers."""

    tick_label_font_size: float = 10.0
    """Size for tick labels. The most load-bearing font field: the axis measures label widths
    at this size to decide the left margin, how many ticks fit, and whether a category label
    has to be shortened."""

    legend_font_size: float = 11.0
    """Size for legend entries. Also measured, for the same reason -- it sets how much width
    the legend reserves."""

    annotation_font_size: float = 10.0
    """Size for in-plot annotations. **Changes no output byte today.** The labels inside pie
    slices, treemap tiles and gauges take :attr:`legend_font_size`, and ``heatmap(annot=True)``
    -- the one thing this package's own argument calls an annotation -- writes its numbers with
    the ``tick-label`` class, so they take :attr:`tick_label_font_size`."""

    tooltip_font_size: float = 10.0
    """Size for tooltip text. **Changes no output byte today, and cannot be made to**: ``tooltip=True``
    emits ``<title>`` elements, which browsers render as native chrome outside the document.
    No CSS this package writes can reach them, so this field would need a tooltip built out
    of SVG elements before it could mean anything."""

    caption_font_size: float = 9.0
    """Size for a caption below the plot. **Changes no output byte today** -- ``layout.add_caption``
    does draw a caption, at a hardcoded 14px, for the same reason ``grid``'s headings ignore
    :attr:`title_font_size`: the text belongs to the figure and a figure has no theme."""

    legend_position: str = "right"
    """Where the legend sits. **Changes no output byte today** -- every chart that draws a
    legend puts it to the right of the plot area."""

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
            # ``numbers.Real``, the same width every other numeric argument uses -- see
            # ``charts/_layout._finite``. ``Theme`` is public and passed to every render call, so
            # ``Theme(opacity=np.float32(0.8))`` being refused while ``width=np.float32(400)`` is
            # accepted is the same split, one layer up (#274).
            if not isinstance(value, numbers.Real) or isinstance(value, bool):
                raise ValueError(f"{field} must be a real number, got {value!r}")
            # A range check alone rejects nan/inf too (every comparison with nan is False,
            # and inf fails the upper bound), so no separate isfinite() call is needed.
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field} must be a number in [0, 1], got {value!r}")
        # Same argument as the two above, one field further on: a corner_radius that is not a
        # non-negative finite number reaches ``rx`` on a ``<rect>``, where a negative value is
        # invalid SVG and ``inf``/``nan`` cannot be written at all. It used to fail three
        # different ways depending on which chart was drawn -- ``rx="-5"`` from ``boxplot`` and
        # ``histplot``, no ``rx`` at all from ``barplot``, and for ``nan`` a ValueError from two
        # of the three (#258). Bounded only from below: there is no largest sensible rounding,
        # and a radius past half the rect's side is already clamped by SVG itself.
        if not isinstance(self.corner_radius, numbers.Real) or isinstance(self.corner_radius, bool):
            raise ValueError(f"corner_radius must be a real number, got {self.corner_radius!r}")
        # Converted first, then asked -- the shape the other four validators in this package use
        # (``charts/_layout._finite``, ``chart/_domain``, ``palette/normalize``, ``labels/spec``).
        # ``math.isfinite`` on the original object converts too, and on a ``Real`` too large for a
        # float it raises instead of answering: widening the type test above to ``numbers.Real``
        # is exactly what let ``Fraction(10**400)`` reach this line, so the two changes belong
        # together. This was the *fifth* site of that pattern and the only one this change itself
        # opened (#274).
        #
        # ``>= 0.0`` is false for nan and true for inf, so inf needs the explicit finiteness test
        # that the [0, 1] range check above got for free.
        try:
            radius = float(self.corner_radius)
        except (OverflowError, TypeError, ValueError) as error:
            raise ValueError(f"corner_radius must be a non-negative finite number, got {self.corner_radius!r}") from error
        if not (radius >= 0.0 and math.isfinite(radius)):
            raise ValueError(f"corner_radius must be a non-negative finite number, got {self.corner_radius!r}")
