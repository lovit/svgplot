"""row/column (1D) and grid (2D, span-aware) chart arrangement — Bokeh vocabulary
translated to a static two-layer model (docs/research/16-layout-vocabulary.md).

``row``/``column`` are thin wrappers over ``grid``: the research doc's design
principle 1 is that a single 1D + 2D pair covers Bokeh's four-level hierarchy,
so there is one placement algorithm here, not three.

Track sizes come from the children's own canvas sizes (a chart knows how big it
wants to be), so a grid of equally-sized charts lays out on an exact pixel
lattice with no scaling. A child whose cell ends up larger — because it spans
tracks, or shares a track with a bigger sibling — scales up via its nested
``<svg>``'s viewBox (see ``chart.composition``), but *letterboxed*, not
stretched: SVG's default ``preserveAspectRatio="xMidYMid meet"`` keeps the
child's aspect ratio and centers it, so a chart in a cell of a different
aspect ratio is padded rather than distorted. Distorting a chart would
misrepresent its data (a circle in a pie chart must stay circular), so the
padding is the deliberate trade-off.
"""

from __future__ import annotations

from svgplot.chart.base import Chart
from svgplot.chart.composition import TITLE_HEIGHT, Composition, Placement, chart_size, compose

_TupleCell = tuple[Chart, int, int, int, int]


def _is_tuple_form(cells: object) -> bool:
    return isinstance(cells, list) and bool(cells) and all(isinstance(cell, tuple) for cell in cells)


def _titles_for(titles: list[str | None] | None, count: int) -> list[str | None]:
    if titles is None:
        return [None] * count
    if len(titles) != count:
        raise ValueError(f"titles must have one entry per cell ({count}), got {len(titles)}")
    return list(titles)


def _matrix_placements(
    matrix: list[list[Chart | None]],
    titles: list[str | None],
    spacing: float,
) -> tuple[list[Placement], float, float]:
    """Lay out a rectangular matrix of cells (``None`` = an empty cell that still
    occupies its slot, Bokeh's None-blank idiom).
    """
    nrows = len(matrix)
    ncols = max(len(row_cells) for row_cells in matrix)
    charts = [cell for row_cells in matrix for cell in row_cells if cell is not None]
    fallback_width, fallback_height = (
        max(chart_size(chart)[0] for chart in charts),
        max(chart_size(chart)[1] for chart in charts),
    )

    # A track is sized by its largest member; an all-empty track falls back to the
    # composition's largest chart so blank cells stay visually regular.
    col_widths = [fallback_width] * ncols
    row_heights = [fallback_height] * nrows
    for col in range(ncols):
        sizes = [chart_size(matrix[r][col])[0] for r in range(nrows) if col < len(matrix[r]) and matrix[r][col] is not None]
        if sizes:
            col_widths[col] = max(sizes)
    for row_index, row_cells in enumerate(matrix):
        sizes = [chart_size(cell)[1] for cell in row_cells if cell is not None]
        if sizes:
            row_heights[row_index] = max(sizes)

    # A row reserves title space only if some cell in it actually has a title.
    cell_titles = [
        [titles[row_index * ncols + col] if row_index * ncols + col < len(titles) else None for col in range(ncols)]
        for row_index in range(nrows)
    ]
    row_title_heights = [TITLE_HEIGHT if any(t is not None for t in row_titles) else 0.0 for row_titles in cell_titles]

    placements: list[Placement] = []
    y = 0.0
    for row_index, row_cells in enumerate(matrix):
        x = 0.0
        title_band = row_title_heights[row_index]
        for col in range(ncols):
            cell = row_cells[col] if col < len(row_cells) else None
            if cell is not None:
                placements.append(
                    Placement(
                        chart=cell,
                        x=x,
                        y=y + title_band,
                        width=col_widths[col],
                        height=row_heights[row_index],
                        title=cell_titles[row_index][col],
                    )
                )
            x += col_widths[col] + spacing
        y += title_band + row_heights[row_index] + spacing

    width = sum(col_widths) + spacing * (ncols - 1)
    height = sum(row_heights) + sum(row_title_heights) + spacing * (nrows - 1)
    return placements, width, height


def _tuple_placements(
    cells: list[_TupleCell],
    titles: list[str | None],
    spacing: float,
    ncols: int | None,
) -> tuple[list[Placement], float, float]:
    """Lay out ``(chart, row, col, rowspan, colspan)`` placements."""
    occupied: dict[tuple[int, int], int] = {}
    for index, cell in enumerate(cells):
        if len(cell) != 5:
            raise ValueError(f"grid tuple cells must be (chart, row, col, rowspan, colspan), got {cell!r}")
        chart, row_index, col, rowspan, colspan = cell
        if not isinstance(chart, Chart):
            raise ValueError(f"grid tuple cell's first element must be a Chart, got {type(chart).__name__}")
        if row_index < 0 or col < 0:
            raise ValueError(f"grid cell row/col must be non-negative, got row={row_index}, col={col}")
        if rowspan < 1 or colspan < 1:
            raise ValueError(f"grid cell rowspan/colspan must be at least 1, got rowspan={rowspan}, colspan={colspan}")
        for r in range(row_index, row_index + rowspan):
            for c in range(col, col + colspan):
                if (r, c) in occupied:
                    raise ValueError(f"grid cells overlap at (row={r}, col={c}): cell {occupied[(r, c)]} and cell {index}")
                occupied[(r, c)] = index

    nrows = max(row_index + rowspan for _, row_index, _, rowspan, _ in cells)
    inferred_ncols = max(col + colspan for _, _, col, _, colspan in cells)
    if ncols is not None:
        if ncols < inferred_ncols:
            raise ValueError(f"ncols={ncols} is too small for the given cells (need at least {inferred_ncols})")
        inferred_ncols = ncols

    fallback_width = max(chart_size(cell[0])[0] for cell in cells)
    fallback_height = max(chart_size(cell[0])[1] for cell in cells)
    col_widths = [fallback_width] * inferred_ncols
    row_heights = [fallback_height] * nrows
    # Size tracks from single-track children only; a spanning child's size is
    # satisfied by the tracks it covers plus the spacing between them, so letting
    # it drive a single track's size would over-size every other cell in it.
    for chart, row_index, col, rowspan, colspan in cells:
        chart_width, chart_height = chart_size(chart)
        if colspan == 1:
            col_widths[col] = max(col_widths[col], chart_width)
        if rowspan == 1:
            row_heights[row_index] = max(row_heights[row_index], chart_height)

    row_title_heights = [0.0] * nrows
    for index, (_, row_index, _, _, _) in enumerate(cells):
        if index < len(titles) and titles[index] is not None:
            row_title_heights[row_index] = TITLE_HEIGHT

    col_offsets = [0.0] * inferred_ncols
    offset = 0.0
    for col in range(inferred_ncols):
        col_offsets[col] = offset
        offset += col_widths[col] + spacing
    row_offsets = [0.0] * nrows
    offset = 0.0
    for row_index in range(nrows):
        row_offsets[row_index] = offset
        offset += row_title_heights[row_index] + row_heights[row_index] + spacing

    placements = []
    for index, (chart, row_index, col, rowspan, colspan) in enumerate(cells):
        span_width = sum(col_widths[col : col + colspan]) + spacing * (colspan - 1)
        span_height = (
            sum(row_heights[row_index : row_index + rowspan])
            + sum(row_title_heights[row_index + 1 : row_index + rowspan])
            + spacing * (rowspan - 1)
        )
        placements.append(
            Placement(
                chart=chart,
                x=col_offsets[col],
                y=row_offsets[row_index] + row_title_heights[row_index],
                width=span_width,
                height=span_height,
                title=titles[index] if index < len(titles) else None,
            )
        )

    width = sum(col_widths) + spacing * (inferred_ncols - 1)
    height = sum(row_heights) + sum(row_title_heights) + spacing * (nrows - 1)
    return placements, width, height


def grid(
    cells: list[list[Chart | None]] | list[_TupleCell],
    *,
    ncols: int | None = None,
    spacing: int = 12,
    titles: list[str | None] | None = None,
) -> Composition:
    """Arrange charts in a 2D grid. Accepts either a matrix of charts (None = empty cell)
    or a list of (chart, row, col, rowspan, colspan) tuples for span-aware placement.

    ``titles`` supplies one heading per cell, rendered above it — the static
    replacement for Bokeh's ``Tabs`` adopted as the default idiom in
    docs/research/16-layout-vocabulary.md. For the matrix form, entries are in
    row-major order (including ``None`` cells); for the tuple form, one entry per
    tuple, in the same order.

    Raises:
        ValueError: if ``cells`` is empty or contains no chart, if ``spacing`` is
            negative, if ``titles`` has the wrong length, or (tuple form) if a cell
            is malformed, has a negative index or non-positive span, overlaps another
            cell, or exceeds ``ncols``.
    """
    if spacing < 0:
        raise ValueError(f"spacing must be non-negative, got {spacing}")
    if not cells:
        raise ValueError("grid requires at least one cell")

    if _is_tuple_form(cells):
        tuple_cells: list[_TupleCell] = cells  # type: ignore[assignment]
        resolved_titles = _titles_for(titles, len(tuple_cells))
        placements, width, height = _tuple_placements(tuple_cells, resolved_titles, float(spacing), ncols)
    else:
        matrix: list[list[Chart | None]] = cells  # type: ignore[assignment]
        if not all(isinstance(row_cells, list) for row_cells in matrix):
            raise ValueError("grid matrix form requires a list of lists of Chart|None")
        if ncols is not None:
            too_wide = [len(row_cells) for row_cells in matrix if len(row_cells) > ncols]
            if too_wide:
                raise ValueError(f"ncols={ncols} is too small for a row of {max(too_wide)} cells")
            matrix = [[*row_cells, *[None] * (ncols - len(row_cells))] for row_cells in matrix]
        if not any(cell is not None for row_cells in matrix for cell in row_cells):
            raise ValueError("grid requires at least one non-None chart")
        cell_count = len(matrix) * max(len(row_cells) for row_cells in matrix)
        resolved_titles = _titles_for(titles, cell_count)
        placements, width, height = _matrix_placements(matrix, resolved_titles, float(spacing))

    document = compose(placements, width, height)
    return Composition(document, [placement.chart for placement in placements])


def row(charts: list[Chart | None], spacing: int = 12, *, titles: list[str | None] | None = None) -> Composition:
    """Arrange charts in a single horizontal row. ``None`` entries render as empty cells."""
    if not charts:
        raise ValueError("row requires at least one cell")
    return grid([list(charts)], spacing=spacing, titles=titles)


def column(charts: list[Chart | None], spacing: int = 12, *, titles: list[str | None] | None = None) -> Composition:
    """Arrange charts in a single vertical column. ``None`` entries render as empty cells.

    ``titles`` renders a heading above each chart — the default "Tabs 대체" idiom
    from docs/research/16-layout-vocabulary.md.
    """
    if not charts:
        raise ValueError("column requires at least one cell")
    return grid([[chart] for chart in charts], spacing=spacing, titles=titles)
