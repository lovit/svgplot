"""heatmap — one rect per (x, y) cell, coloured by a quantised value scale.

Long-form ``(x, y, value)`` input, unlike seaborn's wide-form ``heatmap``. Long form is
this package's baseline everywhere else and mixing the two would make ``heatmap`` the one
chart whose data has to be reshaped first.

Quantised, not continuous
=========================

A cell's value picks one of :data:`LEVELS` colours rather than a point on a ramp. Four
reasons, in order of weight:

1. **Re-theming keeps working.** Nine CSS rules can be edited by hand to recolour the
   whole chart; one rule per cell cannot. Hand-editable output is this package's first
   principle, and a continuous scale quietly gives it up.
2. **The legend comes free.** Nine swatches go straight through the existing
   ``render_legend``. A continuous colour bar needs ``<linearGradient>``/``stop-color`` --
   a new element class, styling outside the CSS-class contract, and its own answer for
   what happens when two charts are composed.
3. Roughly half the output size.
4. Heatmaps are read as bands anyway; the eye does not resolve a continuous ramp.

It also means this package never needs a continuous ``colormap(name, t)`` sampler.
"""

from __future__ import annotations

import math
import warnings

from svgplot.chart.base import Chart
from svgplot.charts._axes import render_x_axis, render_y_axis
from svgplot.charts._layout import (
    LEGEND_X_OFFSET,
    MARGIN_WITH_LEGEND,
    format_coord,
    new_canvas,
)
from svgplot.charts._legend import render_legend
from svgplot.charts._theme_resolve import resolve_theme
from svgplot.data._missing import is_missing
from svgplot.data.ingest import ingest_longform
from svgplot.palette._color import hex_to_rgb01
from svgplot.palette.diverging import DIVERGING_PALETTES, diverging
from svgplot.palette.normalize import Normalize
from svgplot.palette.sequential import SEQUENTIAL_PALETTES, sequential
from svgplot.scales import CategoricalScale
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style
from svgplot.warnings import HeatmapSizeWarning

LEVELS = 9
"""How many colour steps a value is quantised into. Odd, so a ``center=`` lands on a
middle level with the same number of steps either side."""

_BYTES_PER_CELL = 88
"""Measured marginal output cost of one drawn cell."""

_BYTES_PER_TICK = 216
"""Measured marginal output cost of one axis tick (a row or a column label).

Two terms are needed because the two counts come apart on a sparse grid: a 100x100 grid
holding a 100-cell diagonal draws 100 rects but still labels 200 ticks. Estimating from
cells alone put that chart at 8 KB against a real 51 KB; from grid cells alone, at 859 KB.

``drawn * 88 + (rows + cols) * 216`` was fitted on four measured points and is within 5%
of all of them (estimate vs real, as the warning itself prints them): 50x50 dense 235 vs
233 KB, 100x100 dense 901 vs 863 KB, 100x100 diagonal 50 vs 51 KB, 200x200 diagonal 101 vs
102 KB. Worst case +4.4%, on the densest."""

_INK_FLIP_LUMINANCE = math.sqrt(1.05 * 0.05) - 0.05
"""Relative luminance at which black and white give a cell exactly the same contrast.

WCAG contrast is ``(L_light + 0.05) / (L_dark + 0.05)``, so white scores ``1.05 / (L +
0.05)`` and black ``(L + 0.05) / 0.05``; equating them gives this value, ~0.1791. Anything
brighter takes black ink."""

_WARN_CELL_COUNT = 2_500
"""Where the size warning starts. Two independent arguments land near the same number:

- **~233 KB** at this size -- past what is polite to embed in a README. This is the
  argument that actually fixes the number.
- Legibility agrees rather than independently derives it: in the 580x520 plot area this
  chart gets (the legend takes the rest of the width), 50x50 cells are **11.6 x 10.4 px**,
  which is around where an individual value stops being identifiable at
  ``tick_label_font_size=10``. The issue's own derivation assumed a 700px plot and a 14 px
  floor; correcting the width to 580 would put that argument nearer 1,700 cells, so it
  supports the same order rather than pinning 2,500 on its own.

20x5 (100 cells) is 25x under and stays silent -- its cells are 29.0 x 104.0 px. 100x100
is 4x over, warns, and **still renders**: there is deliberately no hard cap.
"""


def _cell_values(columns: dict[str, list], x: str, y: str, values: str) -> dict[tuple[str, str], float]:
    """Map ``(x, y)`` to its value, dropping rows missing any of the three channels.

    Raises:
        ValueError: if two rows name the same cell. A silent last-one-wins would hide half
            the data behind a rect that looks like every other rect -- there is no visual
            cue that a cell was overwritten, unlike a bar chart where the same rule at
            least draws something the reader can compare against the axis.
    """
    cells: dict[tuple[str, str], float] = {}
    for xv, yv, value in zip(columns[x], columns[y], columns[values], strict=True):
        if is_missing(xv) or is_missing(yv) or is_missing(value):
            continue
        key = (str(xv), str(yv))
        if key in cells:
            raise ValueError(f"duplicate cell for x={key[0]!r}, y={key[1]!r}: heatmap needs one value per cell")
        cells[key] = float(value)
    return cells


def _ordered(columns: list, keep: set[str]) -> list[str]:
    """Distinct stringified values in first-seen order, restricted to ``keep``."""
    seen: list[str] = []
    for value in columns:
        if is_missing(value):
            continue
        text = str(value)
        if text in keep and text not in seen:
            seen.append(text)
    return seen


def _warn_if_large(cell_count: int, *, drawn: int, ticks: int) -> None:
    """Warn on the *grid* size but size the estimate by the cells actually drawn.

    The two differ on a sparse grid, and each is right for its own half of the argument:
    legibility is set by how small a grid cell gets, output size by how many rects exist.
    Using the grid count for both overestimated a 100-cell diagonal by 17x.
    """
    if cell_count <= _WARN_CELL_COUNT:
        return
    estimate = (drawn * _BYTES_PER_CELL + ticks * _BYTES_PER_TICK) // 1024
    warnings.warn(
        f"heatmap has {cell_count} cells (~{estimate} KB of SVG); "
        f"above {_WARN_CELL_COUNT} cells the output gets large and each cell too small to read. "
        'Render to a raster instead if that matters: chart.save("heatmap.png") with the "png" extra.',
        HeatmapSizeWarning,
        stacklevel=3,
    )


def heatmap(
    data: object,
    x: str,
    y: str,
    values: str,
    *,
    cmap: str = "blues",
    center: float | None = None,
    annot: bool = False,
    theme: Theme | str | None = None,
) -> Chart:
    """Draw a heatmap from long-form ``(x, y, value)`` rows.

    Values are quantised into :data:`LEVELS` colour steps -- see this module's docstring
    for why that is not a continuous ramp. ``center=`` switches to a diverging colormap
    normalised about that value, so the middle level means "at the centre" rather than
    "halfway between the extremes" -- which means ``center=`` and ``cmap=`` have to be set
    together: ``cmap``'s default is sequential.

    A cell with no row is left **empty**, not drawn as zero: a hole and a zero look
    nothing alike to a reader, and conflating them invents data.

    ``annot=True`` writes each value into its cell. Placement uses the cell's own geometry
    only -- this package has no font metrics, so a label is centred on the rect rather than
    fitted to it.

    Warns:
        HeatmapSizeWarning: above :data:`_WARN_CELL_COUNT` cells. The chart still renders;
            the warning carries the cell count, an estimated size, and the one mitigation.

    Raises:
        KeyError: if ``x``/``y``/``values`` isn't a column in ``data``, if ``theme`` is a
            string that isn't a registered preset name, or (via ``palette``) if ``cmap`` is
            in neither colormap registry.
        TypeError: if ``theme`` is neither a ``Theme``, a preset name, nor ``None``.
        ValueError: if ``data`` has no rows, if no row has all three channels, if two rows
            name the same cell, or if ``cmap`` and ``center`` disagree -- a diverging
            colormap needs a ``center`` to diverge about, and a ``center`` needs a diverging
            colormap. The two registries are disjoint, so exactly one pairing is valid.
    """
    resolved_theme = resolve_theme(theme)
    longform = ingest_longform(data, x, y)
    # ingest_longform validates two channels; the third is this chart's own.
    if values not in longform.columns:
        raise KeyError(f"values column not found in data: {values!r}")
    if len(longform) == 0:
        raise ValueError("data must contain at least one row")

    cells = _cell_values(longform.columns, x, y, values)
    if not cells:
        raise ValueError("no rows with x, y and values all present after dropping missing values")

    columns = _ordered(longform.columns[x], {key[0] for key in cells})
    rows = _ordered(longform.columns[y], {key[1] for key in cells})
    _warn_if_large(len(columns) * len(rows), drawn=len(cells), ticks=len(columns) + len(rows))

    magnitudes = list(cells.values())
    normalize = Normalize.from_values(magnitudes, center=center)
    colors = _colormap(cmap, center=center)

    document, area = new_canvas(MARGIN_WITH_LEGEND)

    x_scale = CategoricalScale(columns, (area.left, area.right))
    y_scale = CategoricalScale(rows, (area.top, area.bottom))
    render_x_axis(document, x_scale, area, tick_length=resolved_theme.tick_size)
    render_y_axis(document, y_scale, area, tick_length=resolved_theme.tick_size)

    # One class per level, minted up front so every cell of the same level shares a rule --
    # which is what makes a nine-line hand edit recolour the whole chart.
    level_classes = [document.semantic_class("level") for _ in range(LEVELS)]
    level_colors = dict(zip(level_classes, colors, strict=True))

    cell_width, cell_height = x_scale.bandwidth, y_scale.bandwidth
    for column in columns:
        for row in rows:
            magnitude = cells.get((column, row))
            if magnitude is None:
                continue  # a hole, not a zero
            level = min(int(normalize(magnitude) * LEVELS), LEVELS - 1)
            left, top = x_scale(column), y_scale(row)
            document.add_node(
                None,
                "rect",
                attrib={
                    "x": format_coord(left),
                    "y": format_coord(top),
                    "width": format_coord(cell_width),
                    "height": format_coord(cell_height),
                },
                classes=[level_classes[level], "heatmap-cell"],
            )
            if annot:
                document.add_text(
                    None,
                    format_coord(magnitude),
                    attrib={
                        "x": format_coord(left + cell_width / 2),
                        "y": format_coord(top + cell_height / 2),
                        "text-anchor": "middle",
                        "dominant-baseline": "middle",
                    },
                    # Two classes doing two jobs. "tick-label" supplies the font, which is
                    # the theme's business; the per-level class supplies the ink, which is
                    # not -- a cell's colour comes from the colormap and is identical under
                    # every preset, so a theme foreground picked to read against the
                    # *canvas* is a guess about the *cell*. Measured on the dark preset,
                    # borrowing it put 5 of 9 levels below 3:1 contrast, worst 1.04:1.
                    classes=[f"{level_classes[level]}-annotation", "tick-label", "heatmap-annotation"],
                )

    render_legend(
        document,
        [(_level_label(index, normalize), level_classes[index]) for index in range(LEVELS)],
        x=area.right + LEGEND_X_OFFSET,
        y=area.top,
        mark_style="fill",
        font_size=resolved_theme.legend_font_size,
    )
    # Only when there are annotations to colour: nine dead rules would be nine more lines
    # to read past in a chart a reader is meant to be able to hand-edit.
    ink_colors = (
        {
            f"{name}-annotation": _readable_ink(
                _composited(color, over=resolved_theme.background, opacity=resolved_theme.opacity)
            )
            for name, color in level_colors.items()
        }
        if annot
        else None
    )
    render_theme_style(document, resolved_theme, [], mark_style="fill", level_colors=level_colors, ink_colors=ink_colors)

    return Chart(document)


def _composited(color: str, *, over: str, opacity: float) -> str:
    """``color`` drawn at ``opacity`` on top of ``over``, as the reader will see it.

    A cell rule carries ``theme.opacity``, so what reaches the eye is the colormap colour
    blended toward the plot background. Choosing ink against the *unblended* colour picks
    for a cell nobody sees: measured on the light preset at ``opacity=0.5``, ink chosen
    that way rendered at 2.23:1 while the same ink chosen against the composite gives
    8.47:1. At the shipped presets' ``opacity=1.0`` this is the identity.
    """
    front, back = hex_to_rgb01(color), hex_to_rgb01(over)
    blended = (front[index] * opacity + back[index] * (1.0 - opacity) for index in range(3))
    return "#" + "".join(f"{round(channel * 255):02x}" for channel in blended)


def _colormap(cmap: str, *, center: float | None) -> list[str]:
    """The :data:`LEVELS` colours for this chart, from whichever registry ``center`` selects.

    ``cmap`` and ``center`` are two arguments that have to agree, and the registries are
    disjoint -- so getting the pair wrong is the likeliest mistake here, and the palette
    functions cannot name it: each sees only its own half and reports the caller's perfectly
    valid colormap as an unknown one. **Both directions already failed**, just unhelpfully:
    ``center=1.0`` with the default ``cmap="blues"`` raised ``KeyError: unknown diverging
    palette: 'blues'``, which names the wrong thing twice (it is not unknown, and the key is
    not what the caller got wrong), and a diverging map without a ``center`` raised the
    mirror image from the sequential registry. Neither ever rendered, so this changes the
    error rather than the behaviour.

    The reverse direction is refused rather than allowed because allowing it would mean
    routing a diverging map through the sequential path, which puts its pale midpoint at the
    middle of the *data range* instead of at a value the caller chose -- a centre that is
    not there. Measured on data spanning 1..6, the neutral ``#f7f7f7`` level would cover
    3.22..3.78, straddling the range's midpoint of 3.5.

    Raises:
        ValueError: if ``cmap`` names a colormap from the other registry, i.e. if a
            diverging map is used without ``center=`` or a sequential map with it.
        KeyError: (via ``palette``) if ``cmap`` is in neither registry.
    """
    if center is None and cmap in DIVERGING_PALETTES:
        raise ValueError(
            f"cmap={cmap!r} is a diverging colormap, which needs a center= to diverge about; "
            f"pass center=, or use a sequential colormap ({', '.join(sorted(SEQUENTIAL_PALETTES))})"
        )
    if center is not None and cmap in SEQUENTIAL_PALETTES:
        raise ValueError(
            f"center= needs a diverging colormap, but cmap={cmap!r} is sequential; "
            f"pass one of {', '.join(sorted(DIVERGING_PALETTES))}, or drop center="
        )
    return diverging(cmap, LEVELS) if center is not None else sequential(cmap, LEVELS)


def _readable_ink(background: str) -> str:
    """Black or white, whichever reads better on ``background``.

    The threshold is the one that falls out of WCAG's contrast formula rather than a
    hand-picked midpoint: black beats white exactly when the background's relative
    luminance exceeds ``sqrt(1.05 * 0.05) - 0.05``. Splitting at 0.5 instead would flip the
    choice on mid-tone cells and lose up to 1.7x of contrast on them.

    Both candidates are theme-independent on purpose. A cell's colour comes from the
    colormap, not the palette, so the ink that reads on it is a property of the data
    encoding; a reader who wants different ink edits nine CSS rules, as with everything
    else here.
    """
    red, green, blue = hex_to_rgb01(background)
    channels = [
        channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4 for channel in (red, green, blue)
    ]
    luminance = 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
    return "#000000" if luminance > _INK_FLIP_LUMINANCE else "#ffffff"


def _level_label(index: int, normalize: Normalize) -> str:
    """The value a level's colour starts at, so the legend reads as a scale.

    Asked of ``Normalize`` rather than interpolated between ``vmin`` and ``vmax``: with a
    ``center`` the mapping is two straight lines, and assuming one slope mislabels every
    step on the shorter side -- measured six of nine wrong, by up to two levels.
    """
    return format_coord(normalize.inverse(index / LEVELS))
