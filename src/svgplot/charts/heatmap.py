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
from svgplot.charts._axes import fit_left_margin, fit_rotated_labels, render_x_axis, render_y_axis
from svgplot.charts._describe import describe, group, plural, span
from svgplot.charts._layout import (
    LEGEND_X_OFFSET,
    MARGIN_WITH_LEGEND,
    TICK_SPACING_X,
    TICK_SPACING_Y,
    fit_margin,
    format_coord,
    new_canvas,
    resolve_size,
    ticks_for,
)
from svgplot.charts._legend import render_legend
from svgplot.charts._theme_resolve import resolve_theme
from svgplot.charts._tooltip import add_tooltip, clause, format_label, format_number
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

_BYTES_PER_CELL = 85
"""Marginal output cost of one drawn cell -- fitted, see ``_BYTES_PER_TICK``."""

_BYTES_FIXED = 2879
"""Output cost that does not scale with the grid: the ``<style>`` block, the axes, the
legend, the accessibility nodes.

Added when document scoping (#182) started wrapping every rule in ``:where(.svgplot-fXXXXXXXX)``.
That is ~27 bytes times the rule count -- a constant, and a two-term model has nowhere to put
a constant except by smearing it across the per-cell and per-tick terms. Doing so cost real
accuracy: the best two-term refit lands at 4.90% worst error against a 5% assertion, which
would leave the next person a test that fails for reasons unrelated to their change.

Its value is **anchored to a measurement rather than fitted freely**: a one-cell heatmap
serializes to 3,282 bytes, and the constant is whatever makes the model reproduce that exactly
(``3282 - 1*85 - 2*159``). So it is not a pure measurement either -- it inherits the two
slopes -- but it is pinned to a chart that exists rather than chosen to flatter four points.

That pinning costs accuracy on the four grid points, 3.08% worst against 2.40% for a free
constant, and buys the model being right about the chart it was anchored to. A free 3800
overpredicts that chart by 28%, and 6520 -- which reaches 1.05% on the four points -- exceeds
the entire chart, so neither can honestly be called a fixed cost."""

_BYTES_PER_TICK = 159
"""Marginal output cost of one axis tick (a row or a column label) -- fitted, not measured.

Two terms are needed because the two counts come apart on a sparse grid: a 100x100 grid
holding a 100-cell diagonal draws 100 rects but still labels 200 ticks. Estimating from
cells alone put that chart at 8 KB against a real 41 KB; from grid cells alone, at 859 KB.

``drawn * 85 + (rows + cols) * 159 + 2879`` was fitted on four measured points and is within 4%
of all of them. The error is the integer estimate the warning prints against the **exact**
size in KB, which is what ``tests/test_charts_heatmap.py`` compares -- an earlier version of
this paragraph claimed the integer-divided figure instead, and the two disagree enough to
reverse the argument below (2.33% vs 3.08%). Measured: 50x50 dense 225 vs 230.4 KB (-2.35%),
100x100 dense 863 vs 855.4 KB (+0.89%), 100x100 diagonal 42 vs 43.3 KB (-3.08%), 200x200
diagonal 81 vs 80.1 KB (+1.15%). Worst case -3.08%, on the 100x100 diagonal.

Refitted when axis labels gained rotation (#133), and again when document scoping (#182) added
a fixed cost the two-term model had been absorbing into these two.

The two slopes are searched exhaustively with the constant pinned by them (see
``_BYTES_FIXED``), so the search is over two parameters rather than three. Read this as
"slopes fitted, constant anchored" -- it is not a global minimum, and deliberately so.

Refitted whenever the drawn output changes, because it is a fit and not a derivation. It has
moved twice: once when label thinning stopped the tick count tracking the grid, and once when
long labels started carrying a ``<title>`` of their own."""

_BYTES_PER_TOOLTIP = 70
"""What ``tooltip=True`` adds per *drawn* cell -- fitted the same way as :data:`_BYTES_PER_CELL`.

A term rather than a footnote because this is the chart where the size warning is load-bearing.
A 200x200 dense grid with tooltips serializes to 6,345.6 KB: with this term the warning says
6,037, without it 3,385 -- **46.7% low**. A warning that understates a 6 MB file by half is
worse than none, because the reader acts on it.

Fitted over the same four points :data:`_BYTES_PER_TICK` cites, worst error **2.27%**: 50x50
dense 396 vs 404.1 KB (-2.01%), 100x100 dense 1,547 vs 1,555.5 KB (-0.54%), 100x100 diagonal 49
vs 50.1 KB (-2.27%), 200x200 diagonal 95 vs 94.0 KB (+1.05%). Those fixtures label their axes
``x0``..``x199`` and hold values ``0.0``..``39999.0``, and a cell's ``<title>`` repeats both
labels, both column names and the value -- so like every other term here it is a fit against
ordinary labels, not a bound. Long ones cost more, up to ``_tooltip.MAX_TOOLTIP_CHARS``.

Scaled by the *drawn* count, not the grid count, for :func:`_warn_if_large`'s reason: an undrawn
cell has no rect and so no ``<title>``.
"""

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


def _warn_if_large(cell_count: int, *, drawn: int, ticks: int, tooltip: bool) -> None:
    """Warn on the *grid* size but size the estimate by the cells actually drawn.

    The two differ on a sparse grid, and each is right for its own half of the argument:
    legibility is set by how small a grid cell gets, output size by how many rects exist.
    Using the grid count for both overestimated a 100-cell diagonal by 17x.
    """
    if cell_count <= _WARN_CELL_COUNT:
        return
    per_cell = _BYTES_PER_CELL + (_BYTES_PER_TOOLTIP if tooltip else 0)
    estimate = (drawn * per_cell + ticks * _BYTES_PER_TICK + _BYTES_FIXED) // 1024
    warnings.warn(
        f"heatmap has {cell_count} cells (~{estimate} KB of SVG); "
        f"above {_WARN_CELL_COUNT} cells the output gets large and each cell too small to read. "
        'Render to a raster instead if that matters: chart.save("heatmap.png") with the "png" extra.',
        HeatmapSizeWarning,
        stacklevel=3,
    )


def _cell_tooltip(*, x: str, y: str, values: str, column: object, row: object, magnitude: float, level: int) -> str:
    """What one cell's ``<title>`` says: where it is, what it holds, and which shade that is.

    **The exact value is the point.** A heatmap quantises into :data:`LEVELS` shades, so the
    colour a reader sees is a *bucket*: two cells one shade apart can differ by almost nothing,
    and two cells the same shade by almost a whole step. Nothing else in the picture recovers
    the number -- ``annot=True`` draws it, but only where the cells are big enough to hold text,
    and the legend labels the steps rather than the cells.

    The level is said too, and 1-based, because it is what the legend is keyed on: a reader
    comparing a cell to the scale beside it is asking which of the nine entries this is. Saying
    the value alone would leave them counting shades.
    """
    parts = []
    if (shown := format_label(column)) is not None:
        parts.append(clause(x, shown))
    if (shown := format_label(row)) is not None:
        parts.append(clause(y, shown))
    parts.append(clause(values, format_number(magnitude)))
    parts.append(f"level {level + 1} of {LEVELS}")
    return " · ".join(parts)


def heatmap(
    data: object,
    x: str,
    y: str,
    values: str,
    *,
    cmap: str = "blues",
    center: float | None = None,
    annot: bool = False,
    tooltip: bool = False,
    width: float | None = None,
    height: float | None = None,
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

    ``tooltip=True`` gives every cell a ``<title>`` naming its row, its column, its exact value
    and which of the :data:`LEVELS` shades that is. **It is the only way to recover the value.**
    The colour is a bucket, so two cells one shade apart can differ by almost nothing and two
    cells the same shade by almost a whole step; ``annot=True`` draws the number but only where
    the cells are big enough to hold text, and the legend labels the steps rather than the
    cells. A browser shows the ``<title>`` on hover and it is also the cell's accessible name,
    so the grid becomes named nodes rather than one anonymous block. It works only where the SVG
    is *inlined* into the page: inside an ``<img>`` the file is a separate document and the
    browser draws it without interaction.

    ``tooltip=False`` is the default, and this is the chart where that matters most: a
    ``<title>`` per cell is an element per cell, and cell counts here run to the thousands --
    see the warning below, which exists for the same reason. Off, the file is what it was.

    Warns:
        HeatmapSizeWarning: above :data:`_WARN_CELL_COUNT` cells. The chart still renders;
            the warning carries the cell count, an estimated size, and the one mitigation.

    ``width``/``height`` set the canvas in pixels; ``None`` (the default) means 800x600, so a
    call that does not mention them is byte-identical to one written before they existed. The
    margin presets shrink to keep the plot area the majority of a small canvas and the tick
    count follows the plot extent — see ``charts/_layout.py``. Canvases below 240x180 are
    refused rather than clamped, and a chart may refuse a larger one if its own legend does
    not fit.

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
    _warn_if_large(len(columns) * len(rows), drawn=len(cells), ticks=len(columns) + len(rows), tooltip=tooltip)

    magnitudes = list(cells.values())
    normalize = Normalize.from_values(magnitudes, center=center)
    colors = _colormap(cmap, center=center)

    canvas_width, canvas_height = resolve_size(width, height)
    fitted = fit_left_margin(MARGIN_WITH_LEGEND, rows, width=canvas_width, font_size=resolved_theme.tick_label_font_size)
    fitted, turn_labels = fit_rotated_labels(
        fitted,
        columns,
        height=canvas_height,
        plot_width=canvas_width - fitted[3] - fitted[1],
        font_size=resolved_theme.tick_label_font_size,
        tick_length=resolved_theme.tick_size,
    )
    document, area = new_canvas(
        fit_margin(fitted, canvas_width, canvas_height),
        width=canvas_width,
        height=canvas_height,
    )

    x_scale = CategoricalScale(columns, (area.left, area.right))
    y_scale = CategoricalScale(rows, (area.top, area.bottom))
    render_x_axis(
        document,
        x_scale,
        area,
        tick_count=ticks_for(area.width, TICK_SPACING_X),
        tick_length=resolved_theme.tick_size,
        font_size=resolved_theme.tick_label_font_size,
        rotate=turn_labels,
    )
    render_y_axis(
        document,
        y_scale,
        area,
        tick_count=ticks_for(area.height, TICK_SPACING_Y),
        tick_length=resolved_theme.tick_size,
        font_size=resolved_theme.tick_label_font_size,
    )

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
            cell = document.add_node(
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
            if tooltip:
                add_tooltip(
                    document,
                    cell,
                    _cell_tooltip(x=x, y=y, values=values, column=column, row=row, magnitude=magnitude, level=level),
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

    description = describe(
        "Heatmap",
        group(columns, "column"),
        group(rows, "row"),
        f"{len(cells)} of {len(columns) * len(rows)} cells filled",
        span("values", min(magnitudes), max(magnitudes)),
        f'quantised into {plural(LEVELS, "level")}',
    )
    return Chart(document, description=description)


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
