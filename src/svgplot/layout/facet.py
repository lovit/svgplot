"""col=/row= faceting — groups data via svgplot.data.semantic and arranges the
resulting per-group charts with svgplot.layout.grid (docs/research/10-feature-matrix.md A1).

Faceting is deliberately a thin composition of two existing pieces rather than a
new subsystem: ``data.semantic.extract_channels`` already splits long-form data
into per-group column-dicts, and ``layout.grid`` already places charts (including
``None`` blanks and per-cell titles). ``facet`` only decides *which* group lands
in *which* cell.

Panels share their axes by default, and that is a data-level decision rather than a
layout one -- docs/research/16-layout-vocabulary.md, 설계 원칙 3 draws that line and names
a ``shared_x=``-style parameter as the mechanism. ``sharex=``/``sharey=`` are that
parameter. The *default* is the part worth arguing: unshared panels put two lines at the
same height while one means 3 and the other 300, and nothing on the page says so. A reader
who does not check every axis reads it wrong, silently. seaborn's ``FacetGrid`` defaults
both to ``True`` for the same reason.

Sharing costs a second render: a panel's domain cannot be predicted from the input columns
(``histplot``'s y is a bin count, ``kdeplot``'s a density), so the panels are drawn once to
find out what they used and again against the union. See ``chart/_domain.py``. Measured at
1.7x on six panels of 600 rows (2.7ms -> 4.5ms), and paid only when there is actually
something to share -- one panel, or panels that record no domains, skip the second pass.

Charts that record no domains -- ``pieplot``, ``treemap``, ``gaugeplot``, ``radarplot``,
``sparkline``, ``heatmap`` -- skip the second pass entirely. Most of them have no cartesian
axes at all; ``heatmap`` is the exception, with two categorical axes it simply does not
report yet. Three kinds of domain are **deliberately left open** and will read differently
per panel until they are closed:

- ``heatmap``'s row/column categories and its value-to-colour scale
- ``radarplot``/``gaugeplot``'s radial extent
- **``hue=`` group colours on every chart.** Two panels whose hue values differ assign the
  palette independently, so the same group can be blue in one and orange in the next. This
  PR fixed exactly that problem for *categorical axis* colours (see ``barplot``/``boxplot``/
  ``violinplot``'s ``categories=``) and did not fix it for ``hue=`` -- which is worse than
  before in one respect, since aligned axes invite a reader to assume the colours align too.
"""

from __future__ import annotations

from collections.abc import Callable

from svgplot.chart._domain import Domains, union
from svgplot.chart.base import Chart
from svgplot.chart.composition import Composition
from svgplot.data.semantic import extract_channels
from svgplot.layout.grid import column as arrange_column, grid as arrange_grid, row as arrange_row


def _sorted_unique(values: list[object]) -> list[object]:
    """Deterministic facet order. ``str`` keying (rather than natural ordering)
    matches how every chart module already orders its hue groups, and it is total
    across the mixed value types a data column can hold — sorting those directly
    would raise ``TypeError``.
    """
    return sorted(dict.fromkeys(values), key=str)


def _is_drawable(span: tuple[float, float] | None) -> bool:
    """Whether a shared span is something a chart can be told to draw against.

    A union of panels that all show the same constant is ``(5.0, 5.0)``. ``apply_limit``
    refuses that, and rightly so for a *caller's* override -- a zero-width window maps every
    value to one pixel. But a chart handed no override copes with its own constant data
    perfectly well, so forwarding the degenerate union would turn a chart that rendered on
    ``main`` into a ``ValueError``. Leaving it out lets each panel fall back to its own
    handling, which is identical across panels anyway when the data is constant.
    """
    return span is not None and span[0] < span[1]


def _may_override(name: str, explicit: dict[str, object]) -> bool:
    """Whether the caller left ``name`` for the union to decide.

    ``bins`` is exempt, because naming it is not a decision the union can contradict.
    ``histogram_bins`` takes a string or an int and nothing else: an int already pins every
    panel to that many, so the union carries it back unchanged, and a *strategy* --
    ``"auto"``, ``"sturges"`` -- names how each panel should choose **alone**, which is the
    thing that has to stop when the panels are being made to agree. Either way the count the
    union carries is the one the caller's own setting produced.
    """
    if name not in explicit or explicit[name] is None:
        return True
    return name == "bins"


def _shared_kwargs(panels: list[Chart], *, sharex: bool, sharey: bool, explicit: dict[str, object]) -> dict[str, object]:
    """The overrides that make every panel agree, or ``{}`` if there is nothing to share.

    Empty when no panel recorded a domain (a grid of pies), when both flags are off, when only
    one panel exists, or when every panel already agrees -- in each case the second render
    would reproduce the first exactly, and paying for it would be waste dressed up as
    correctness.

    ``explicit`` is what the caller already passed through to ``plot_fn``. Anything named
    there wins: ``facet(..., ylim=(0, 500))`` is a caller stating the window they want, and
    a computed union has no business overruling it -- nor may it be passed alongside, which
    is a ``TypeError`` for a duplicate keyword rather than anything the caller can read.

    ``ylim=None`` is not such a statement. It is what a wrapper passes when it has nothing
    to say, and every chart here already reads it as "no override" -- so keying off the name
    alone would let ``facet(plot_fn, data, col="g", ylim=None)`` silently turn sharing off
    while both flags still read ``True``.
    """
    if len(panels) < 2 or not (sharex or sharey):
        return {}
    # ``isinstance`` because ``plot_fn`` may return a ``Composition`` -- a nested facet, or
    # ``add_caption`` around a chart -- which reports no domains.
    recorded = [panel.domains for panel in panels if isinstance(panel, Chart)]
    # One guard, three cases that are the same case: nobody reported a domain, everybody
    # reported an empty one, or everybody already agrees. In each the second render would
    # reproduce the first exactly.
    if not recorded or all(domain == recorded[0] for domain in recorded):
        return {}
    shared: Domains = union(recorded)
    overrides: dict[str, object] = {}
    if sharex and _is_drawable(shared.x):
        overrides["xlim"] = shared.x
        if shared.x_steps is not None:
            # A binned x axis needs its division shared as well as its range; see
            # ``Domains.x_steps``. ``bins`` is the name every binned chart already uses.
            overrides["bins"] = shared.x_steps
    if sharey and _is_drawable(shared.y):
        overrides["ylim"] = shared.y
    # Under whichever flag names the axis the categories were actually drawn on -- a
    # horizontal bar chart puts them up the left edge, where "sharex" has no business.
    if shared.categories is not None and (sharex if shared.categories_axis == "x" else sharey):
        overrides["categories"] = shared.categories
    return {name: value for name, value in overrides.items() if _may_override(name, explicit)}


def facet(
    plot_fn: Callable[..., object],
    data: object,
    col: str | None = None,
    row: str | None = None,
    *,
    sharex: bool = True,
    sharey: bool = True,
    **kwargs: object,
) -> Composition:
    """Call ``plot_fn`` once per ``col=``/``row=`` group and arrange the results in a grid.

    ``col=`` alone lays the panels out left-to-right, ``row=`` alone top-to-bottom,
    and both together form a 2D grid (rows by ``row=``'s values, columns by
    ``col=``'s). A (row, col) combination with no rows in ``data`` renders as an
    empty cell rather than shifting its neighbours. Panels are ordered by
    ``str(value)`` so output is stable across runs, and each is titled with its
    facet value(s).

    ``plot_fn`` is called as ``plot_fn(group_data, **kwargs)``, where ``group_data``
    is that group's rows across *all* of ``data``'s columns. Any chart function
    taking its data positionally works — the differing keyword signatures
    (``lineplot``'s ``x=``/``y=``, ``pieplot``'s ``values=``/``labels=``,
    ``barplot``'s ``orient=``) are the caller's to supply via ``**kwargs``, so no
    chart type is special-cased here.

    A group whose rows ``plot_fn`` rejects (e.g. every row missing the plotted
    column) propagates that function's own exception rather than being silently
    dropped: a panel vanishing without explanation is harder to debug than a
    failure naming the column.

    Raises:
        ValueError: if neither ``col`` nor ``row`` is given (nothing to facet by).
        KeyError: if ``col``/``row`` isn't a column in ``data`` (from
            :func:`~svgplot.data.semantic.extract_channels`).
    """
    if col is None and row is None:
        raise ValueError("facet requires at least one of col= or row=")

    groups = extract_channels(data, col=col, row=row)

    if col is not None and row is not None:
        # extract_channels keys multi-channel groups as a (hue, col, row) tuple,
        # omitting unrequested channels — here that is (col_value, row_value).
        col_values = _sorted_unique([key[0] for key in groups])
        row_values = _sorted_unique([key[1] for key in groups])

        def build(extra: dict[str, object]) -> tuple[list[list[Chart | None]], list[str | None]]:
            matrix: list[list[Chart | None]] = []
            titles: list[str | None] = []
            for row_value in row_values:
                cells: list[Chart | None] = []
                for col_value in col_values:
                    group = groups.get((col_value, row_value))
                    if group is None:
                        cells.append(None)
                        titles.append(None)
                        continue
                    cells.append(plot_fn(group, **{**kwargs, **extra}))  # type: ignore[arg-type]
                    titles.append(f"{row} = {row_value}, {col} = {col_value}")
                matrix.append(cells)
            return matrix, titles

        matrix, titles = build({})
        drawn = [cell for cells in matrix for cell in cells if cell is not None]
        overrides = _shared_kwargs(drawn, sharex=sharex, sharey=sharey, explicit=kwargs)
        if overrides:
            matrix, titles = build(overrides)
        return arrange_grid(matrix, titles=titles)

    channel = col if col is not None else row
    values = _sorted_unique(list(groups))
    charts: list[Chart | None] = [plot_fn(groups[value], **kwargs) for value in values]  # type: ignore[arg-type,misc]
    overrides = _shared_kwargs([chart for chart in charts if chart is not None], sharex=sharex, sharey=sharey, explicit=kwargs)
    if overrides:
        charts = [plot_fn(groups[value], **{**kwargs, **overrides}) for value in values]  # type: ignore[arg-type,misc]
    titles = [f"{channel} = {value}" for value in values]
    if col is not None:
        return arrange_row(charts, titles=titles)
    return arrange_column(charts, titles=titles)
