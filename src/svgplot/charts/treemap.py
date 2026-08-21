"""treemap — area-proportional rectangle tiling (squarified layout).

Like ``charts/pie.py`` this is an axis-less, single-column chart: it takes a
``values=`` column (mapped to tile *area*) and an optional ``labels=`` column,
so data access goes through ``data._columns.extract_columns``/``column_length``
rather than the x/y-shaped ``data.ingest.ingest_longform``.

**Single level only.** A hierarchical (nested) treemap needs a tree-shaped input
model that ``data/_columns.py``'s flat column dict cannot express, and inventing
one here would push well past pygal's own ``Treemap``, which is also single-level.
Nesting is deliberately out of scope rather than merely unimplemented.

The layout is squarified (Bruls, Huizing & van Wijk 2000): values are placed in
descending order into a row along the shorter side of the remaining rectangle,
and the row is closed as soon as adding one more tile would make its worst
aspect ratio worse. That greedy rule is what keeps tiles near-square, which is
the whole point — a naive slice-and-dice tiling covers the same area but
degenerates into slivers that are hard to compare visually.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from svgplot.chart.base import Chart
from svgplot.charts._describe import describe, group, number, span
from svgplot.charts._layout import (
    LEGEND_X_OFFSET,
    MARGIN_WITH_SIDE_LEGEND,
    PlotArea,
    fit_margin,
    format_coord,
    new_canvas,
    resolve_size,
)
from svgplot.charts._legend import render_legend
from svgplot.charts._textwidth import needs_full_text, truncate_to_width
from svgplot.charts._theme_resolve import resolve_theme
from svgplot.charts._tooltip import add_tooltip, clause, format_label, format_number
from svgplot.data._columns import column_length, extract_columns
from svgplot.data._missing import is_missing
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style

_MIN_LABEL_WIDTH = 40.0
_MIN_LABEL_HEIGHT = 16.0
"""A tile smaller than this gets no label.

Purely a geometry threshold: this package has no font metrics by design
(docs-research/12-aesthetics.md §3), so "does the text fit?" cannot be measured
and is approximated by "is the tile at least this big?" instead.
"""


@dataclass(frozen=True)
class _Tile:
    """One laid-out rectangle, in SVG pixel coordinates."""

    label: str
    value: float
    """The tile's *pixel area*, which is what the layout compares. Not the caller's number."""
    source: float
    """The value the caller gave, carried through so a tile can name it.

    A tile cannot be looked up by label afterwards: repeated labels are legal (the legend
    already draws a row per repeat), and a ``{label: value}`` map collapses them last-wins.
    Measured before this field existed, on ``["dup", "dup", "other"] / [10, 30, 60]``: the tile
    drawn at 10% of the plot area said ``dup · value: 30 · 30.0%``, and the three shares summed
    to 120%.
    """
    x: float
    y: float
    width: float
    height: float


def _worst_aspect_ratio(row: list[float], side: float, total: float) -> float:
    """Worst (largest) width/height ratio among ``row``'s tiles, laid along ``side``.

    ``total`` is the row's summed value; ``side`` is the length of the edge the row
    runs along. Returns ``inf`` for a degenerate row so that any real candidate
    compares better.
    """
    if not row or total <= 0 or side <= 0:
        return math.inf
    side_squared = side * side
    total_squared = total * total
    # A zero value has zero area, so its aspect ratio is degenerate rather than merely
    # large -- report it as infinite instead of dividing by zero. Zero-valued rows are
    # legal input (a category that happens to have no magnitude this period).
    return max(
        math.inf if value <= 0 else max(side_squared * value / total_squared, total_squared / (side_squared * value))
        for value in row
    )


def _layout_row(row: list[tuple[str, float, float]], row_total: float, area: PlotArea, vertical: bool) -> list[_Tile]:
    """Place one closed row of tiles along the short side of ``area``.

    ``vertical`` selects which way the row runs: when the remaining rectangle is
    wider than it is tall the row stacks down the left edge -- along the shorter,
    vertical side -- otherwise it runs across the top. Reading this backwards is
    what produces the sliver layout squarified exists to avoid, so it must agree
    with the caller's ``vertical = width > height``.
    """
    width, height = area.right - area.left, area.bottom - area.top
    tiles: list[_Tile] = []
    offset = 0.0
    if vertical:
        row_width = row_total / height if height > 0 else 0.0
        for label, value, source in row:
            tile_height = (value / row_total) * height if row_total > 0 else 0.0
            tiles.append(_Tile(label, value, source, area.left, area.top + offset, row_width, tile_height))
            offset += tile_height
    else:
        row_height = row_total / width if width > 0 else 0.0
        for label, value, source in row:
            tile_width = (value / row_total) * width if row_total > 0 else 0.0
            tiles.append(_Tile(label, value, source, area.left + offset, area.top, tile_width, row_height))
            offset += tile_width
    return tiles


def _remaining_area(area: PlotArea, row_total: float, vertical: bool) -> PlotArea:
    """The rectangle left over after a row consuming ``row_total`` area is removed."""
    width, height = area.right - area.left, area.bottom - area.top
    if vertical:
        consumed = row_total / height if height > 0 else 0.0
        return PlotArea(left=area.left + consumed, top=area.top, right=area.right, bottom=area.bottom)
    consumed = row_total / width if width > 0 else 0.0
    return PlotArea(left=area.left, top=area.top + consumed, right=area.right, bottom=area.bottom)


def _squarify(entries: list[tuple[str, float, float]], area: PlotArea) -> list[_Tile]:
    """Tile ``area`` with one rectangle per entry, area-proportional and near-square.

    ``entries`` must already be sorted by value descending and scaled so their sum
    equals ``area``'s area — that scaling is what makes "value" and "pixel area"
    the same quantity throughout, so the greedy aspect-ratio comparisons below are
    comparing like with like.
    """
    tiles: list[_Tile] = []
    remaining = list(entries)
    current = area

    while remaining:
        width = current.right - current.left
        height = current.bottom - current.top
        if width <= 0 or height <= 0:
            # Numerically exhausted: emit the rest as zero-area tiles at the corner so
            # every entry still yields exactly one rect (the count is part of the contract).
            tiles.extend(
                _Tile(label, value, source, current.left, current.top, 0.0, 0.0) for label, value, source in remaining
            )
            break

        # Rows run along the *shorter* edge — that is what keeps tiles near-square.
        # A rectangle wider than it is tall therefore gets a column stacked down its
        # left edge (each tile spanning a slice of the full height), not a row across
        # the top; getting this backwards still tiles the area exactly but degenerates
        # into slivers, which is precisely what squarified exists to avoid.
        vertical = width > height
        side = min(width, height)

        row: list[tuple[str, float, float]] = [remaining[0]]
        row_total = remaining[0][1]
        index = 1
        while index < len(remaining):
            candidate_total = row_total + remaining[index][1]
            current_worst = _worst_aspect_ratio([value for _, value, _source in row], side, row_total)
            candidate_worst = _worst_aspect_ratio(
                [value for _, value, _source in row] + [remaining[index][1]], side, candidate_total
            )
            if candidate_worst > current_worst:
                break
            row.append(remaining[index])
            row_total = candidate_total
            index += 1

        tiles.extend(_layout_row(row, row_total, current, vertical))
        current = _remaining_area(current, row_total, vertical)
        remaining = remaining[index:]

    return tiles


def _tile_tooltip(*, values: str, label: str, value: float, total: float) -> str:
    """What one tile's ``<title>`` says: its name, its value, and its share of the whole.

    **The name is the part the picture cannot always give.** A tile draws its label only when
    it is at least ``_MIN_LABEL_WIDTH`` x ``_MIN_LABEL_HEIGHT``, and a long name is shortened
    to fit even then -- so the smallest tiles, which are exactly the ones a reader has to look
    up, are anonymous rectangles. The legend names them, but matching a legend row to a tile in
    a squarified layout means hunting by colour.

    The share is here because it is what a treemap encodes: area is proportional to value, so
    "12.4%" is a reading of the picture rather than an extra fact about the data. Rounded to
    one decimal -- a share is a proportion of a total the reader can also see, not a
    measurement, and seventeen digits of one would be the longest thing in the tooltip.
    """
    parts = []
    if (shown := format_label(label)) is not None:
        parts.append(shown)
    parts.append(clause(values, format_number(value)))
    parts.append(f"{value / total * 100:.1f}%")
    return " · ".join(parts)


def treemap(
    data: object,
    values: str,
    labels: str | None = None,
    *,
    tooltip: bool = False,
    width: float | None = None,
    height: float | None = None,
    theme: Theme | str | None = None,
) -> Chart:
    """Draw a treemap from ``values`` (tile area) and, optionally, ``labels``
    (legend text; defaults to 1-based tile position when omitted).

    Tiles exactly partition the plot area — no gaps, no overlaps — with each
    tile's area proportional to its value, laid out squarified so tiles stay
    near-square rather than degenerating into slivers.

    Only a single level of tiles is drawn; nested/hierarchical treemaps are out
    of scope (see this module's docstring).

    ``tooltip=True`` gives every tile a ``<title>`` naming it, its value and its share of the
    whole. **It is how a tile too small for a label says its name**: a label is drawn only at
    40x16 px or larger, so the smallest tiles -- the ones a reader has to look up -- are
    anonymous rectangles, and matching a legend row to one in a squarified layout means hunting
    by colour. The share is a reading of the picture rather than an extra fact: this chart
    encodes value as area, so "40.0%" is what the tile's size means.

    Turning it on also gives the in-tile labels ``pointer-events: none``. A label sits *inside*
    its tile and intercepts the pointer exactly where the reader is looking, so without that the
    tile's own ``<title>`` is unreachable there and the label's truncation ``<title>`` comes up
    instead. With ``tooltip=False`` that label ``<title>`` is the only thing under the pointer,
    and taking the label out of the way would delete the one way to read the full name -- which
    is why the rule is conditional.

    ``tooltip=False`` is the default; off, the file is what it was.

    ``width``/``height`` set the canvas in pixels; ``None`` (the default) means 800x600, so a
    call that does not mention them is byte-identical to one written before they existed. The
    margin presets shrink to keep the plot area the majority of a small canvas and the tick
    count follows the plot extent — see ``charts/_layout.py``. Canvases below 240x180 are
    refused rather than clamped, and a chart may refuse a larger one if its own legend does
    not fit.

    ``theme=`` takes a :class:`~svgplot.theme.base.Theme`, the name of a preset
    (``"light"``, ``"dark"``, ``"minimal"``, ``"high_contrast"``, ``"print"``), or ``None``
    for the default theme. Fonts, line widths, opacities and the grid/spine/tick colours come
    from it, along with every colour this chart's own arguments do not set. No render reads or
    writes global style state, so two charts given the same ``Theme`` are styled alike no
    matter what was drawn in between.

    ``data`` is long-form -- one row per tile -- and is read by column name: only ``values``
    and, if given, ``labels`` are consulted, and the remaining columns are ignored rather
    than refused.

    Raises:
        KeyError: if ``values``/``labels`` isn't a column in ``data``, or if
            ``theme`` is a string that isn't a registered preset name.
        TypeError: if ``theme`` is neither a ``Theme``, a preset name, nor ``None``.
        ValueError: if ``data`` has no rows, if no rows remain after dropping
            missing values, if any value is negative or non-finite, or if all
            values are zero.
    """
    resolved_theme = resolve_theme(theme)
    columns = extract_columns(data)
    if values not in columns:
        raise KeyError(f"values column not found in data: {values!r}")
    if labels is not None and labels not in columns:
        raise KeyError(f"labels column not found in data: {labels!r}")
    length = column_length(columns)
    if length == 0:
        raise ValueError("data must contain at least one row")

    raw_values = columns[values]
    raw_labels = columns[labels] if labels is not None else [str(index + 1) for index in range(length)]
    pairs = [
        (str(label), float(value))
        for label, value in zip(raw_labels, raw_values, strict=True)
        if not is_missing(label) and not is_missing(value)
    ]
    if not pairs:
        raise ValueError("no rows with both a non-missing label and value present after dropping missing values")
    for label, value in pairs:
        # Checked here rather than left to format_coord: an inf survives the negative
        # check, becomes nan once divided into a proportion, and only then fails -- with
        # a message about a coordinate, naming neither the offending value nor its row.
        if not math.isfinite(value):
            raise ValueError(f"treemap values must be finite, got {value!r} for label {label!r}")
        if value < 0:
            raise ValueError(f"treemap values must be non-negative, got {value!r} for label {label!r}")
    total = sum(value for _, value in pairs)
    if total == 0:
        raise ValueError("treemap values must not all be zero (sum is 0)")

    canvas_width, canvas_height = resolve_size(width, height)
    document, area = new_canvas(
        fit_margin(MARGIN_WITH_SIDE_LEGEND, canvas_width, canvas_height),
        width=canvas_width,
        height=canvas_height,
    )

    # Scale values into pixel area up front so the layout's aspect-ratio comparisons
    # operate in one unit, and sort descending (squarified's precondition).
    plot_pixels = area.width * area.height
    # The caller's value rides along beside the scaled one: a tile cannot be looked up by label
    # afterwards, because repeated labels are legal and a map of them collapses last-wins.
    scaled = sorted(((label, value / total * plot_pixels, value) for label, value in pairs), key=lambda entry: -entry[1])
    tiles = _squarify(scaled, area)

    series_classes: list[str] = []
    legend_entries: list[tuple[str, str]] = []
    for tile in tiles:
        series_class = document.semantic_class("series")
        series_classes.append(series_class)
        legend_entries.append((tile.label, series_class))
        rect = document.add_node(
            None,
            "rect",
            attrib={
                "x": format_coord(tile.x),
                "y": format_coord(tile.y),
                "width": format_coord(tile.width),
                "height": format_coord(tile.height),
            },
            classes=[series_class],
        )
        if tooltip:
            add_tooltip(document, rect, _tile_tooltip(values=values, label=tile.label, value=tile.source, total=total))
        if tile.width >= _MIN_LABEL_WIDTH and tile.height >= _MIN_LABEL_HEIGHT:
            # Centred in its tile, so a long label runs out both sides, over the neighbouring
            # tiles and their labels. Measured before this, ``"W" * 40`` on a 196.7px tile
            # rendered 415.3px wide and overran the tile by 218.6px -- 109.3px each side.
            # A tile near the right edge takes that past the canvas as well.
            shown = truncate_to_width(tile.label, resolved_theme.legend_font_size, tile.width)
            label_node = document.add_text(
                None,
                shown,
                tag="text",
                attrib={
                    "x": format_coord(tile.x + tile.width / 2),
                    "y": format_coord(tile.y + tile.height / 2),
                    "text-anchor": "middle",
                },
                # See ``pie-value`` in charts/pie.py for why this is an addition rather than a
                # replacement. Here the problem is already visible: a tile label carries its own
                # <title> when the name had to be shortened, so hovering the label shows "the
                # full name" where the tile would have shown the value.
                classes=["treemap-label", "legend-text"],
            )
            if shown != tile.label or needs_full_text(tile.label, resolved_theme.legend_font_size, tile.width):
                add_tooltip(document, label_node, tile.label)

    render_legend(
        document,
        legend_entries,
        x=area.right + LEGEND_X_OFFSET,
        y=area.top,
        mark_style="fill",
        font_size=resolved_theme.legend_font_size,
    )
    # mark_style="outlined" (issue #62, landing concurrently) is the intended final
    # style here so tile seams stay visible; "fill" is the closest thing available today.
    render_theme_style(
        document,
        resolved_theme,
        series_classes,
        mark_style="fill",
        # Only when the tiles have something to say. With ``tooltip=False`` the label's own
        # ``<title>`` -- the full name, when the name had to be shortened -- is the only thing
        # under the pointer there, and taking the label out of the pointer's way would delete
        # the one way to read it.
        transparent_to_pointer=("treemap-label",) if tooltip else (),
    )

    magnitudes = [value for _, value in pairs]
    description = describe(
        "Treemap",
        group([label for label, _ in pairs], "tile"),
        span("values", min(magnitudes), max(magnitudes)),
        f"total {number(total)}",
    )
    return Chart(document, description=description)
