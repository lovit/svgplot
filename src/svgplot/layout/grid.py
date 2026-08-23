"""row/column (1D) and grid (2D, span-aware) chart arrangement — Bokeh vocabulary
translated to a static two-layer model (docs-research/16-layout-vocabulary.md).

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

_EPSILON = 1e-9
"""Slack for comparing track sizes while filling. Sizes are pixel lengths built from chart
dimensions, so differences this small are float noise rather than layout."""

_TupleCell = tuple[Chart | Composition, int, int, int, int]
"""A span-aware cell. The first element is a ``Chart`` **or** a ``Composition``: the matrix
form has always accepted either -- it never asks, it calls ``chart_size`` -- and the span form
refusing one made "put this facet across the top two columns of a dashboard" fail at exactly
the feature spans exist for (#260)."""


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
        if not isinstance(chart, Chart | Composition):
            raise ValueError(f"grid tuple cell's first element must be a Chart or Composition, got {type(chart).__name__}")
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

    def _grow(tracks: list[float], covered: range, extra: float) -> None:
        """Add ``extra`` across ``covered``, filling the smallest tracks first.

        Not ``extra / len(covered)`` each. Even division is order-dependent once two spans share
        a track: whichever ran first leaves its share behind, the second sees a larger ``have``,
        and the same cells listed in a different order produce a different figure -- measured at
        132px on a five-column grid before this was written that way (#270).

        Filling low tracks up to the next level, then raising that level together, converges on
        one answer regardless of who asked. It also makes spans that share tracks agree about
        them rather than stack their demands.
        """
        remaining = extra
        # A span that already fits asks for nothing: ``extra`` is zero or negative and the loop
        # below never runs. That is the only place this decision is made -- callers hand over the
        # shortfall whatever its sign.
        #
        # Bounded, not ``while remaining > 0``. Each pass either exhausts ``remaining`` or merges
        # the lowest tracks into the next level up, so ``len(covered)`` passes reach the state
        # where every track is level and the last shares out whatever is left -- one more than
        # that is slack. An unbounded loop *hangs* rather than terminating when a step comes out
        # too small to move a float, which a mutation of the span ordering actually produced.
        for _ in range(len(covered) + 1):
            if remaining <= _EPSILON:
                break
            floor_size = min(tracks[track] for track in covered)
            lowest = [track for track in covered if tracks[track] <= floor_size + _EPSILON]
            above = [tracks[track] for track in covered if tracks[track] > floor_size + _EPSILON]
            # Raise the lowest tracks to the next distinct level, or share out what is left.
            headroom = (min(above) - floor_size) if above else remaining
            step = min(headroom, remaining / len(lowest))
            for track in lowest:
                tracks[track] += step
            remaining -= step * len(lowest)

    def _tracks(
        sizes: dict[int, list[float]], spans: list[tuple[int, int, float]], count: int, fallback: float
    ) -> list[float]:
        """Track sizes: each track takes its own members, then spans top up what they cover.

        Three rules, in this order.

        **A track is as big as its largest single-track member.** A spanning child has no size
        *for one track* -- its size is satisfied by all the tracks it covers plus the gutters
        between them -- so letting it drive one track would over-size every other cell in that
        track. (Folding it in with ``max`` did exactly that until #260: ``fallback_width``, the
        widest cell anywhere, became a floor under every column and a narrow chart beside a wide
        one was given the wide one's width.)

        **Then each span tops up its own tracks, shortest span first, and only if they fall
        short.** A track covered only by spans starts at zero and is sized entirely by them --
        giving it "the widest cell anywhere" instead is what made a 1612px header across two
        columns produce a 2424px figure (#270). Shortest first because a shorter span constrains
        fewer tracks, so settling it leaves the longer one a fixed floor to measure against.

        A track that **nothing** reaches -- no member, no span, which ``ncols=`` can produce --
        keeps ``fallback``. That is the one case the old rule was right about, and it is the same
        answer :func:`_matrix_placements` gives an all-empty track.

        This resembles CSS Grid's "distribute extra space across spanned tracks" and is **not** a
        port of it -- the spec freezes tracks at growth limits, which this has no concept of. An
        earlier version of this comment claimed it *was* what CSS Grid does, and that was wrong
        in the way that mattered: the spec fills the smallest tracks first and the code divided
        evenly, which is exactly the difference that made the result depend on cell order.
        """
        reached = set(sizes) | {track for start, length, _ in spans for track in range(start, start + length)}
        tracks = [max(sizes.get(track, [0.0])) if track in reached else fallback for track in range(count)]
        # Sorted by the span's own numbers, not by where it sat in cells: a key of just
        # length leaves ties in caller order, and a tie is exactly where two spans compete
        # for the same tracks. (length, start, needed) makes two spans that sort equal
        # indistinguishable in every way that matters here, so the result cannot depend on which
        # was listed first -- measured at 15 of 400 random layouts before this (#270).
        for start, length, needed in sorted(spans, key=lambda span: (span[1], span[0], span[2])):
            covered = range(start, start + length)
            have = sum(tracks[track] for track in covered) + spacing * (length - 1)
            # No ``if needed > have`` -- :func:`_grow` returns immediately on a non-positive
            # amount, so the outer test was a second copy of the same decision. Removed after a
            # mutation showed it could go without changing an answer; the rule it expressed now
            # lives in one place, stated in ``_grow``'s own first line.
            _grow(tracks, covered, needed - have)
        return tracks

    width_members: dict[int, list[float]] = {}
    height_members: dict[int, list[float]] = {}
    width_spans: list[tuple[int, int, float]] = []
    height_spans: list[tuple[int, int, float]] = []
    for chart, row_index, col, rowspan, colspan in cells:
        chart_width, chart_height = chart_size(chart)
        if colspan == 1:
            width_members.setdefault(col, []).append(chart_width)
        else:
            width_spans.append((col, colspan, chart_width))
        if rowspan == 1:
            height_members.setdefault(row_index, []).append(chart_height)
        else:
            height_spans.append((row_index, rowspan, chart_height))

    col_widths = _tracks(width_members, width_spans, inferred_ncols, fallback_width)
    row_heights = _tracks(height_members, height_spans, nrows, fallback_height)

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

    ``spacing`` is the gutter in pixels between neighbouring cells, applied both ways in a
    2D grid; ``0`` is allowed and makes panels touch.

    ``ncols`` fixes the grid's width rather than capping it: it pads every short row with
    empty cells so the columns line up, and a grid of one chart with ``ncols=4`` is four
    columns wide, three of them blank. A row already wider than ``ncols`` is refused rather
    than wrapped -- padding cannot narrow a row, and letting one overflow silently would make
    the number mean nothing. ``None`` (the default) takes the width from the widest row.

    ``titles`` supplies one heading per cell, rendered above it — the static
    replacement for Bokeh's ``Tabs`` adopted as the default idiom in
    docs-research/16-layout-vocabulary.md. For the matrix form, entries are in
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


def row(charts: list[Chart | None], *, spacing: int = 12, titles: list[str | None] | None = None) -> Composition:
    """Arrange charts in a single horizontal row. ``None`` entries render as empty cells.

    ``spacing`` is the gutter in pixels between neighbouring cells, and ``titles`` supplies one
    heading per cell, rendered above it — the static "Tabs 대체" idiom from
    docs-research/16-layout-vocabulary.md. Both are handed straight to :func:`grid`, which is
    where their rules live.

    Raises:
        ValueError: if ``charts`` is empty, or (via :func:`grid`) if ``spacing`` is negative or
            ``titles`` has a different length than ``charts``.
    """
    if not charts:
        raise ValueError("row requires at least one cell")
    return grid([list(charts)], spacing=spacing, titles=titles)


def column(charts: list[Chart | None], *, spacing: int = 12, titles: list[str | None] | None = None) -> Composition:
    """Arrange charts in a single vertical column. ``None`` entries render as empty cells.

    ``titles`` renders a heading above each chart — the default "Tabs 대체" idiom
    from docs-research/16-layout-vocabulary.md. ``spacing`` is the gutter in pixels between
    neighbouring cells. Both are handed straight to :func:`grid`, which is where their rules
    live.

    Raises:
        ValueError: if ``charts`` is empty, or (via :func:`grid`) if ``spacing`` is negative or
            ``titles`` has a different length than ``charts``.
    """
    if not charts:
        raise ValueError("column requires at least one cell")
    return grid([[chart] for chart in charts], spacing=spacing, titles=titles)
