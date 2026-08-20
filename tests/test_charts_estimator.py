"""``estimator=``: what happens to several rows that share one x (issue #119).

The acceptance criterion is that the aggregate is **recomputed and checked**, not that
some number of elements exist. So the assertions here read the drawn geometry back and
turn it into a value, using a second category that holds exactly one row as the ruler --
no test below trusts the chart's own arithmetic to check the chart's arithmetic.

The fixture that matters is ``DUPLICATED``: category ``"a"`` holds ``[10, 20, 60]``, whose
last row (60), mean (30), median (20) and sum (90) are four different numbers. Any two of
those coinciding would let a wrong estimator pass, which is the failure this file exists
to rule out.
"""

from __future__ import annotations

import math
import re
import statistics
import warnings
from datetime import datetime

import pytest

import svgplot as sp
from svgplot.charts._aggregate import ESTIMATORS, apply_estimator, resolve_estimator
from svgplot.charts._layout import DEFAULT_HEIGHT, DEFAULT_WIDTH, MARGIN_WITH_LEGEND, MARGIN_WITHOUT_LEGEND, plot_area
from svgplot.layout import facet

# "a" is the group under test; "anchor" is a single row, and the largest value, so it pins
# the top of the value axis and becomes the ruler every recomputation divides by.
DUPLICATED = {"x": ["a", "a", "a", "anchor"], "y": [10.0, 20.0, 60.0, 100.0]}
ANCHOR_VALUE = 100.0
LAST, MEAN, MEDIAN, TOTAL = 60.0, 30.0, 20.0, 90.0

_RECT_RE = re.compile(r"<rect\b[^>]*/>")
_ATTR_RE = re.compile(r'([\w:-]+)="([^"]*)"')


def _bars(svg: str, *, legend: bool = False) -> list[dict[str, str]]:
    """Every drawn bar, in document order, as its attribute dict.

    Two filters, and both are load-bearing. The class filter drops the plot background,
    which is also a ``<rect>``. The plot-area filter drops the **legend swatch**, which is
    a ``<rect>`` carrying the very same ``series-N`` class as the bars — a helper keyed on
    the class alone counts it as a bar, which silently corrupted the hue and stacked
    assertions in this file until it was caught. Filtering on the swatch's *size* instead
    would go blind exactly when a bar's size is what changed, which is the failure mode
    this repo has been bitten by before.
    """
    area = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=MARGIN_WITH_LEGEND if legend else MARGIN_WITHOUT_LEGEND)
    tags = [dict(_ATTR_RE.findall(match.group())) for match in _RECT_RE.finditer(svg)]
    return [
        tag
        for tag in tags
        if any(name.startswith("series-") for name in tag.get("class", "").split()) and float(tag["x"]) < area.right
    ]


def _bar_value(chart: sp.Chart, *, index: int = 0, anchor: int = -1, anchor_value: float = ANCHOR_VALUE) -> float:
    """The data value a bar stands for, recovered from pixels alone.

    ``height / anchor_height * anchor_value`` inverts the linear value scale without
    knowing the plot area's size, the margin preset, or the scale's implementation -- the
    anchor bar is a row this test wrote, so the ratio is checkable by hand.
    """
    bars = _bars(chart.to_string())
    return float(bars[index]["height"]) / float(bars[anchor]["height"]) * anchor_value


def _axis_top(chart: sp.Chart) -> float:
    """The largest numeric tick label, read from the text nodes rather than the raw string."""
    return max(float(text) for text in re.findall(r">([-0-9.]+)</text>", chart.to_string()))


def _quiet(build):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", sp.AggregationWarning)
        return build()


# --- the issue's own example ---------------------------------------------------------


def test_the_issue_s_example_still_draws_the_last_row_by_default() -> None:
    """``sp.barplot({"x": ["a","a","a"], "y": [10., 20., 30.]})`` draws 30. Kept, on
    purpose: changing the default would silently redraw every chart already built."""
    chart = _quiet(lambda: sp.barplot({"x": ["a", "a", "a"], "y": [10.0, 20.0, 30.0]}, x="x", y="y"))

    # One category, so the bar fills the axis and there is no second bar to measure it
    # against; the axis top is what carries the folded value. It has to be read off the tick
    # *text nodes*: an earlier version of this test asked whether "30" appeared anywhere in
    # the document, which is true under every estimator -- mean and median put the ticks at
    # 0..20 and the substring still matched a coordinate. It passed with ``bar.py`` folding
    # to the *first* row instead of the last, which is the one thing it exists to pin.
    assert _axis_top(chart) == 30.0  # not 20.0 (mean, median) and not 60.0 (sum)
    assert len(_bars(chart.to_string())) == 1


def test_the_same_example_with_an_estimator_draws_the_mean() -> None:
    """seaborn's answer to the same input, available by asking for it."""
    data = {"x": ["a", "a", "a", "anchor"], "y": [10.0, 20.0, 30.0, 100.0]}
    chart = sp.barplot(data, x="x", y="y", estimator="mean")

    assert _bar_value(chart) == pytest.approx(20.0)


# --- the estimators, recomputed ------------------------------------------------------


@pytest.mark.parametrize(
    ("estimator", "expected"),
    [(None, LAST), ("mean", MEAN), ("median", MEDIAN), ("sum", TOTAL)],
    ids=["default-last-row", "mean", "median", "sum"],
)
def test_each_estimator_folds_the_group_to_its_own_number(estimator: object, expected: float) -> None:
    """Four estimators, four different answers on the same three rows -- so no pair of
    them can pass for another."""
    chart = _quiet(lambda: sp.barplot(DUPLICATED, x="x", y="y", estimator=estimator))

    assert _bar_value(chart) == pytest.approx(expected)


def test_the_four_expected_values_really_are_distinct() -> None:
    """The guard on the fixture itself: if a future edit makes two of these coincide, the
    table above stops proving anything and this fails first."""
    assert len({LAST, MEAN, MEDIAN, TOTAL}) == 4


def test_the_expected_values_are_what_the_stdlib_computes() -> None:
    """The constants are checked against an independent implementation rather than
    against the chart, so a wrong constant cannot make a wrong chart look right."""
    group = [10.0, 20.0, 60.0]
    assert pytest.approx(statistics.fmean(group)) == MEAN
    assert pytest.approx(statistics.median(group)) == MEDIAN
    assert pytest.approx(math.fsum(group)) == TOTAL
    assert group[-1] == LAST


def test_a_callable_estimator_is_used_as_given() -> None:
    chart = sp.barplot(DUPLICATED, x="x", y="y", estimator=lambda values: min(values))

    assert _bar_value(chart) == pytest.approx(10.0)


def test_a_callable_receives_the_group_s_values_in_row_order() -> None:
    """Row order, not sorted order -- an estimator like "first" or a weighted mean is
    meaningless otherwise."""
    seen: list[list[float]] = []

    def record(values: list[float]) -> float:
        seen.append(list(values))
        return values[0]

    chart = sp.barplot(DUPLICATED, x="x", y="y", estimator=record)

    assert seen == [[10.0, 20.0, 60.0], [100.0]]
    assert _bar_value(chart) == pytest.approx(10.0)


def test_a_group_of_one_is_folded_too_rather_than_passed_through() -> None:
    """``sum`` of one value is that value, but a caller's callable need not be, and the
    anchor column must go through the same path as everything else."""
    calls: list[list[float]] = []
    sp.barplot(DUPLICATED, x="x", y="y", estimator=lambda values: calls.append(list(values)) or 1.0)

    assert [100.0] in calls


# --- the estimator applies per group, not across the chart ---------------------------


def test_hue_folds_within_each_series_not_across_them() -> None:
    """Folding across series would average two lines that the legend says are separate."""
    data = {
        "x": ["a", "a", "anchor", "a", "a", "anchor"],
        "y": [10.0, 20.0, 100.0, 60.0, 80.0, 100.0],
        "g": ["north", "north", "north", "south", "south", "south"],
    }
    chart = sp.barplot(data, x="x", y="y", hue="g", estimator="mean")
    bars = _bars(chart.to_string(), legend=True)

    north = [bar for bar in bars if "series-1" in bar["class"].split()]
    south = [bar for bar in bars if "series-2" in bar["class"].split()]
    ruler = float(north[-1]["height"]) / ANCHOR_VALUE  # the anchor bar, worth 100
    assert float(north[0]["height"]) / ruler == pytest.approx(15.0)
    assert float(south[0]["height"]) / ruler == pytest.approx(70.0)


def test_stacking_stacks_the_estimated_values_not_the_raw_rows() -> None:
    """The stack's height is the sum of what each series *drew*, so an estimator has to
    reach the totals too or the axis stops matching the bars."""
    data = {
        "x": ["a", "a", "a", "a"],
        "y": [10.0, 20.0, 60.0, 80.0],
        "g": ["north", "north", "south", "south"],
    }
    chart = sp.barplot(data, x="x", y="y", hue="g", stacked=True, estimator="mean")
    bars = _bars(chart.to_string(), legend=True)

    # north folds to 15, south to 70, so the stack is 85 and fills the axis; the two
    # segments must be in 15:70 proportion.
    heights = [float(bar["height"]) for bar in bars]
    assert heights[0] / sum(heights) == pytest.approx(15.0 / 85.0)
    assert heights[1] / sum(heights) == pytest.approx(70.0 / 85.0)


def test_a_horizontal_bar_chart_folds_the_same_way() -> None:
    chart = sp.barplot(DUPLICATED, x="x", y="y", orient="h", estimator="mean")
    bars = _bars(chart.to_string())

    assert float(bars[0]["width"]) / float(bars[-1]["width"]) * ANCHOR_VALUE == pytest.approx(MEAN)


# --- the warning ---------------------------------------------------------------------


def test_the_default_says_out_loud_how_many_rows_it_dropped() -> None:
    """The issue's actual complaint: it "조용히 데이터의 2/3를 버린다"."""
    with pytest.warns(sp.AggregationWarning, match="kept 2 of 4 rows"):
        sp.barplot(DUPLICATED, x="x", y="y")


def test_the_warning_names_the_way_out() -> None:
    with pytest.warns(sp.AggregationWarning, match="estimator='mean'"):
        sp.barplot(DUPLICATED, x="x", y="y")


def test_the_warning_fires_once_per_call_not_once_per_category() -> None:
    """A hundred duplicated categories is one decision, not a hundred."""
    data = {"x": [f"c{index // 2}" for index in range(40)], "y": [float(index) for index in range(40)]}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        sp.barplot(data, x="x", y="y")

    assert [warning for warning in caught if issubclass(warning.category, sp.AggregationWarning)].__len__() == 1


def test_nothing_is_warned_about_when_nothing_was_dropped() -> None:
    """Advice about a fold that folded nothing is noise."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", sp.AggregationWarning)
        sp.barplot({"x": ["a", "b"], "y": [1.0, 2.0]}, x="x", y="y")


def test_nothing_is_warned_about_once_an_estimator_is_chosen() -> None:
    """The caller has already answered the question the warning asks."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", sp.AggregationWarning)
        sp.barplot(DUPLICATED, x="x", y="y", estimator="mean")


def test_duplicates_inside_one_hue_group_are_counted_but_across_groups_are_not() -> None:
    """Two series each holding one row for category "a" is not a duplicate -- they are two
    bars. Counting them would warn about every grouped bar chart ever drawn."""
    data = {"x": ["a", "a"], "y": [1.0, 2.0], "g": ["north", "south"]}
    with warnings.catch_warnings():
        warnings.simplefilter("error", sp.AggregationWarning)
        sp.barplot(data, x="x", y="y", hue="g")


def test_the_warning_is_silenceable_as_a_package_wide_category() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        warnings.filterwarnings("ignore", category=sp.SvgplotWarning)
        sp.barplot(DUPLICATED, x="x", y="y")


# --- areaplot ------------------------------------------------------------------------


def _path_points(svg: str, css_class: str) -> list[tuple[float, float]]:
    match = re.search(rf'<path d="([^"]*)"[^>]*class="[^"]*\b{css_class}\b', svg)
    assert match is not None, f"no <path> carrying {css_class}"
    return [
        (float(pair.split(",")[0]), float(pair.split(",")[1]))
        for pair in re.findall(r"[ML] ([\d.-]+,[\d.-]+)", match.group(1))
    ]


def test_areaplot_keeps_summing_by_default() -> None:
    """This chart's historical rule, unchanged."""
    data = {"x": [1.0, 1.0, 1.0, 2.0], "y": [10.0, 20.0, 60.0, 100.0]}
    points = _path_points(sp.areaplot(data, x="x", y="y").to_string(), "area-series")

    # The first vertex is x=1; its height relative to the x=2 vertex gives the value back.
    area = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=MARGIN_WITHOUT_LEGEND)
    first, second = points[0], points[1]
    assert (area.bottom - first[1]) / (area.bottom - second[1]) * ANCHOR_VALUE == pytest.approx(TOTAL)


def test_areaplot_estimator_sum_is_the_same_chart_as_the_default() -> None:
    """Writing the historical rule out by name is documentation, not a behaviour change --
    CPython 3.12+ already compensates ``sum()`` over floats."""
    data = {"x": [1.0, 1.0, 1.0, 2.0], "y": [10.0, 20.0, 60.0, 100.0]}

    assert sp.areaplot(data, x="x", y="y").to_string() == sp.areaplot(data, x="x", y="y", estimator="sum").to_string()


@pytest.mark.parametrize(("estimator", "expected"), [("mean", MEAN), ("median", MEDIAN)])
def test_areaplot_folds_with_the_estimator_it_is_given(estimator: str, expected: float) -> None:
    data = {"x": [1.0, 1.0, 1.0, 2.0], "y": [10.0, 20.0, 60.0, 100.0]}
    points = _path_points(sp.areaplot(data, x="x", y="y", estimator=estimator).to_string(), "area-series")

    area = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=MARGIN_WITHOUT_LEGEND)
    assert (area.bottom - points[0][1]) / (area.bottom - points[1][1]) * ANCHOR_VALUE == pytest.approx(expected)


def test_areaplot_never_warns_because_it_never_discards() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", sp.AggregationWarning)
        sp.areaplot({"x": [1.0, 1.0, 2.0], "y": [1.0, 2.0, 3.0]}, x="x", y="y")


# --- lineplot ------------------------------------------------------------------------


def test_lineplot_keeps_both_vertices_by_default() -> None:
    """Two rows at one x draw a vertical segment. Nothing is lost, which is why this chart
    never warns."""
    data = {"x": [1.0, 1.0, 2.0], "y": [10.0, 60.0, 100.0]}
    points = _path_points(sp.lineplot(data, x="x", y="y").to_string(), "line-series")

    assert len(points) == 3
    assert points[0][0] == points[1][0]


def test_lineplot_folds_to_one_vertex_per_x_with_an_estimator() -> None:
    """Two single-row anchors bracket the folded vertex, so the y domain is fixed by rows
    this test wrote rather than by the value under test — otherwise the folded vertex would
    define the very axis it is being measured against, and any estimator would "pass"."""
    data = {"x": [1.0, 1.0, 1.0, 2.0, 3.0], "y": [10.0, 20.0, 60.0, 100.0, 5.0]}
    points = _path_points(sp.lineplot(data, x="x", y="y", estimator="mean").to_string(), "line-series")

    assert len(points) == 3
    area = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=MARGIN_WITHOUT_LEGEND)
    folded = 5.0 + (area.bottom - points[0][1]) / (area.bottom - area.top) * (100.0 - 5.0)
    assert folded == pytest.approx(MEAN)


def test_lineplot_groups_datetimes_by_the_instant_not_by_their_rendering() -> None:
    data = {
        "x": [datetime(2024, 1, 1), datetime(2024, 1, 1), datetime(2024, 3, 1)],
        "y": [10.0, 60.0, 100.0],
    }
    points = _path_points(sp.lineplot(data, x="x", y="y", estimator="mean").to_string(), "line-series")

    assert len(points) == 2


def test_lineplot_folds_equal_x_values_not_merely_coincident_pixels() -> None:
    """``"1"`` and ``1.0`` are two x values — the default path draws two vertices for them,
    and an estimator must not quietly redefine which rows count as the same row. They land
    on the same pixel, so a rule keyed on plotted position would fold them; this pins that
    the rule is equality instead, and that it matches the default path exactly."""
    data = {"x": ["1", 1.0, 2.0], "y": [10.0, 60.0, 100.0]}
    default = _path_points(sp.lineplot(data, x="x", y="y").to_string(), "line-series")
    folded = _path_points(sp.lineplot(data, x="x", y="y", estimator="mean").to_string(), "line-series")

    assert len(default) == 3
    assert folded == default


def test_lineplot_never_warns() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", sp.AggregationWarning)
        sp.lineplot({"x": [1.0, 1.0, 2.0], "y": [1.0, 2.0, 3.0]}, x="x", y="y")


def test_lineplot_refuses_an_estimator_beside_an_info_table() -> None:
    """The table lists one row per mark; an estimator is exactly what breaks that."""
    data = {"x": [1.0, 1.0, 2.0], "y": [1.0, 2.0, 3.0]}
    with pytest.raises(ValueError, match="estimator= and info= cannot be combined"):
        sp.lineplot(data, x="x", y="y", estimator="mean", info=[("X", "@x{0.0}")])


def test_lineplot_still_accepts_each_of_them_alone() -> None:
    data = {"x": [1.0, 1.0, 2.0], "y": [1.0, 2.0, 3.0]}

    assert sp.lineplot(data, x="x", y="y", estimator="mean") is not None
    assert sp.lineplot(data, x="x", y="y", info=[("X", "@x{0.0}")]) is not None


# --- which charts take the argument at all -------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda: sp.scatterplot(DUPLICATED, x="x", y="y", estimator="mean"), id="scatterplot"),
        pytest.param(lambda: sp.boxplot(DUPLICATED, x="x", y="y", estimator="mean"), id="boxplot"),
        pytest.param(lambda: sp.violinplot(DUPLICATED, x="x", y="y", estimator="mean"), id="violinplot"),
        pytest.param(lambda: sp.histplot(DUPLICATED, x="y", estimator="mean"), id="histplot"),
        pytest.param(lambda: sp.kdeplot(DUPLICATED, x="y", estimator="mean"), id="kdeplot"),
        pytest.param(lambda: sp.ecdfplot(DUPLICATED, x="y", estimator="mean"), id="ecdfplot"),
        pytest.param(lambda: sp.radarplot(DUPLICATED, x="x", y="y", estimator="mean"), id="radarplot"),
        pytest.param(lambda: sp.pieplot(DUPLICATED, values="y", labels="x", estimator="mean"), id="pieplot"),
        pytest.param(lambda: sp.treemap(DUPLICATED, values="y", labels="x", estimator="mean"), id="treemap"),
        pytest.param(lambda: sp.gaugeplot(DUPLICATED, value="y", estimator="mean"), id="gaugeplot"),
        pytest.param(lambda: sp.sparkline(DUPLICATED, y="y", estimator="mean"), id="sparkline"),
        pytest.param(lambda: sp.regplot(DUPLICATED, x="y", y="y", estimator="mean"), id="regplot"),
    ],
)
def test_charts_outside_the_decided_scope_do_not_take_an_estimator(call) -> None:
    """The scope decision, pinned. ``charts/_aggregate.py`` records why each of these is
    out -- distributions would lose their spread, one-row-one-mark charts have nothing to
    fold, and ``heatmap`` refuses duplicates outright. A future PR that adds the argument
    to one of them should have to delete its line here and say so."""
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        call()


def test_heatmap_still_refuses_duplicates_rather_than_folding_them() -> None:
    data = {"x": ["a", "a"], "y": ["p", "p"], "v": [1.0, 2.0]}
    with pytest.raises(ValueError):
        sp.heatmap(data, x="x", y="y", values="v")


def test_an_estimate_larger_than_every_raw_value_redefines_the_axis() -> None:
    """The value axis is built from what the chart *drew*, so a sum that overtops every raw
    row has to take the top of the axis with it — the anchor then shrinks against it. Every
    other case here keeps the estimate below the anchor, so this path was never exercised.
    """
    data = {"x": ["a", "a", "anchor"], "y": [60.0, 80.0, 100.0]}
    bars = _bars(sp.barplot(data, x="x", y="y", estimator="sum").to_string())

    assert float(bars[0]["height"]) == pytest.approx(520.0)  # 140 fills the axis
    # The y axis has to have followed. A ratio between the two bars would not show this --
    # both are scaled by the same zero-based scale, so it holds whatever the axis top is.
    assert "140" in sp.barplot(data, x="x", y="y", estimator="sum").to_string()


def test_a_callable_returning_a_negative_value_is_still_refused_by_barplot() -> None:
    """An estimator is not a way around a chart's own rules. ``barplot`` refuses negative
    values, and it has to refuse an estimate that is negative just as it refuses a row."""
    with pytest.raises(ValueError, match="doesn't support negative values"):
        sp.barplot({"x": ["a", "a"], "y": [10.0, 20.0]}, x="x", y="y", estimator=lambda values: values[0] - values[1])


def test_facet_forwards_the_estimator_to_every_panel() -> None:
    """``facet`` passes ``**kwargs`` through, so this needs no code — which is exactly why
    it needs a test: nothing else would notice if that stopped working."""
    data = {
        "x": ["a", "a", "anchor", "a", "a", "anchor"],
        "y": [10.0, 20.0, 100.0, 60.0, 80.0, 100.0],
        "panel": ["p", "p", "p", "q", "q", "q"],
    }
    composed = facet(sp.barplot, data, col="panel", x="x", y="y", estimator="mean")

    values = [
        float(_bars(chart.to_string())[0]["height"]) / float(_bars(chart.to_string())[-1]["height"]) * 100.0
        for chart in composed.charts
    ]
    assert values == [pytest.approx(15.0), pytest.approx(70.0)]


def test_facet_carries_the_estimator_through_hue_as_well() -> None:
    """``facet`` and ``hue=`` know nothing about each other, and the fold happens per
    (panel, series, category). Each axis is pinned alone above; this is the three of them
    together."""
    # Four folds, four different numbers, and none of them equal to any row that went in:
    # panel q used to fold both of its series to 40, so swapping the two series was invisible
    # there -- and only the *first* series of each panel was read at all.
    data = {
        "x": ["a", "a", "anchor"] * 4,
        "y": [10.0, 20.0, 100.0, 60.0, 80.0, 100.0, 30.0, 50.0, 100.0, 10.0, 30.0, 100.0],
        "g": ["north"] * 3 + ["south"] * 3 + ["north"] * 3 + ["south"] * 3,
        "panel": ["p"] * 6 + ["q"] * 6,
    }
    composed = facet(sp.barplot, data, col="panel", x="x", y="y", hue="g", estimator="mean")

    folded = []
    for chart in composed.charts:
        # Per series: its category-"a" bar and then its own anchor bar, which is the ruler.
        bars = _bars(chart.to_string(), legend=True)
        folded += [round(float(bars[i]["height"]) / (float(bars[i + 1]["height"]) / ANCHOR_VALUE), 6) for i in (0, 2)]
    assert folded == [15.0, 70.0, 40.0, 20.0]
    assert len(set(folded)) == 4  # so no pair of them can stand in for another


def test_facet_warns_once_per_panel_when_it_forwards_no_estimator() -> None:
    """Once per call means once per *chart*, and a facet builds one chart per panel.

    Not once per *render*. Sharing an axis draws the panels up to three times and returns
    only the last, so warning as it went made this emit six times for two panels -- the
    warning would tell a reader about panels that were measured and thrown away. Measured on
    ``main`` at the moment ``estimator=`` met shared axes; ``facet`` now keeps each pass's
    warnings aside and replays only the winning pass's.
    """
    data = {"x": ["a", "a", "a", "a"], "y": [1.0, 2.0, 3.0, 4.0], "panel": ["p", "p", "q", "q"]}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        facet(sp.barplot, data, col="panel", x="x", y="y")

    assert len([w for w in caught if issubclass(w.category, sp.AggregationWarning)]) == 2


def test_the_warning_counts_rows_across_every_hue_group() -> None:
    """Two groups each discarding one row is two discarded rows, not one -- and not two
    warnings either."""
    data = {
        "x": ["a", "a", "a", "a", "b", "b"],
        "y": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        "g": ["north", "north", "south", "south", "north", "south"],
    }

    with pytest.warns(sp.AggregationWarning, match="kept 4 of 6 rows"):
        sp.barplot(data, x="x", y="y", hue="g")


def test_every_axis_of_barplot_folds_at_once() -> None:
    """orient, stacking, hue and the estimator all touch the same fold. Each is checked
    alone above; this is the one case where all four are on together."""
    data = {"x": ["a", "a", "a", "a"], "y": [10.0, 20.0, 60.0, 80.0], "g": ["north", "north", "south", "south"]}
    bars = _bars(sp.barplot(data, x="x", y="y", hue="g", orient="h", stacked=True, estimator="mean").to_string(), legend=True)

    widths = [float(bar["width"]) for bar in bars]
    assert widths[0] / sum(widths) == pytest.approx(15.0 / 85.0)
    assert widths[1] / sum(widths) == pytest.approx(70.0 / 85.0)


# --- argument validation ---------------------------------------------------------------


def test_an_unknown_estimator_name_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="estimator must be one of"):
        sp.barplot(DUPLICATED, x="x", y="y", estimator="average")


@pytest.mark.parametrize("bad", [1, 1.5, True, ["mean"], object()])
def test_something_that_is_neither_a_name_nor_a_callable_is_a_type_error(bad: object) -> None:
    with pytest.raises(TypeError, match="estimator must be"):
        sp.barplot(DUPLICATED, x="x", y="y", estimator=bad)


def test_a_bad_name_is_reported_before_any_rendering_happens() -> None:
    """So a typo does not surface halfway through a drawn chart."""
    with pytest.raises(ValueError):
        sp.barplot({"x": ["a"], "y": [float("nan")]}, x="x", y="y", estimator="average")


@pytest.mark.parametrize(
    ("returns", "match"),
    [
        (lambda values: None, "non-numeric"),
        (lambda values: True, "non-numeric"),
        (lambda values: 1 + 2j, "non-numeric"),
        (lambda values: [1.0], "non-numeric"),
        (lambda values: "12", "non-numeric"),
        (lambda values: float("nan"), "non-finite"),
        (lambda values: float("inf"), "non-finite"),
    ],
)
def test_a_callable_returning_something_unplottable_is_reported_with_its_group(returns, match: str) -> None:
    """Otherwise it surfaces as a message about an SVG coordinate, naming neither the
    estimator nor the group."""
    with pytest.raises(ValueError, match=match) as caught:
        sp.barplot(DUPLICATED, x="x", y="y", estimator=returns)

    assert "'a'" in str(caught.value)


def test_a_callable_that_raises_keeps_its_own_message() -> None:
    def explode(values: list[float]) -> float:
        raise KeyError("no such thing")

    with pytest.raises(ValueError, match="estimator failed on group 'a'") as caught:
        sp.barplot(DUPLICATED, x="x", y="y", estimator=explode)

    assert isinstance(caught.value.__cause__, KeyError)


def test_a_numpy_bool_is_refused_like_a_python_one() -> None:
    """``numpy.bool_`` is not a ``bool`` subclass, so a rule that named ``bool`` left the
    same mistake open through the one library a caller is most likely to be using --
    ``estimator=lambda values: np.mean(values) > threshold`` returns exactly this."""
    numpy = pytest.importorskip("numpy")

    with pytest.raises(ValueError, match="non-numeric"):
        sp.barplot(DUPLICATED, x="x", y="y", estimator=lambda values: numpy.True_)


def test_a_numpy_complex_is_refused_rather_than_silently_losing_its_imaginary_part() -> None:
    """The same blind spot as ``numpy.bool_``, one type over. A plain ``complex`` is caught
    either way -- ``float(3+2j)`` raises, so the fallback below the type check reports it with
    the same message -- which left ``numbers.Real`` and ``numbers.Number`` indistinguishable
    to this file. ``numpy.complex128`` separates them: ``float()`` accepts it and returns the
    real part, so under ``numbers.Number`` a chart would quietly draw 3.0 for ``3+2j``."""
    numpy = pytest.importorskip("numpy")

    with pytest.raises(ValueError, match="non-numeric"):
        sp.barplot(DUPLICATED, x="x", y="y", estimator=lambda values: numpy.complex128(3 + 2j))


def test_a_zero_dimensional_numpy_array_is_refused() -> None:
    """It is not a scalar, however much it prints like one -- and ``float()`` accepts it, so
    nothing further down would have caught it."""
    numpy = pytest.importorskip("numpy")

    with pytest.raises(ValueError, match="non-numeric"):
        sp.barplot(DUPLICATED, x="x", y="y", estimator=lambda values: numpy.array(3.0))


def test_a_numpy_float_is_accepted_like_a_python_one() -> None:
    """The same rule must not shut out the numeric types it exists to admit."""
    numpy = pytest.importorskip("numpy")
    chart = sp.barplot(DUPLICATED, x="x", y="y", estimator=lambda values: numpy.float64(min(values)))

    assert _bar_value(chart) == pytest.approx(10.0)


def test_a_decimal_is_accepted() -> None:
    """``Decimal`` is deliberately not registered as ``numbers.Real`` and is perfectly
    plottable, so the rule names it rather than letting the abstraction decide."""
    from decimal import Decimal

    chart = sp.barplot(DUPLICATED, x="x", y="y", estimator=lambda values: Decimal(str(min(values))))

    assert _bar_value(chart) == pytest.approx(10.0)


def test_a_string_returned_that_python_would_coerce_is_still_refused() -> None:
    """``float("12")`` succeeds, so a permissive check would let a string through and make
    the estimator's contract depend on what the string happened to look like."""
    with pytest.raises(ValueError, match="non-numeric"):
        sp.barplot(DUPLICATED, x="x", y="y", estimator=lambda values: "12")


# --- the helpers directly ---------------------------------------------------------------


def test_resolve_returns_none_for_none() -> None:
    assert resolve_estimator(None) is None


@pytest.mark.parametrize("name", ESTIMATORS)
def test_every_advertised_name_resolves(name: str) -> None:
    assert callable(resolve_estimator(name))


def test_the_advertised_names_are_exactly_the_documented_three() -> None:
    assert ESTIMATORS == ("mean", "median", "sum")


def test_apply_names_the_group_in_its_message() -> None:
    with pytest.raises(ValueError, match="group 'Q1'"):
        apply_estimator(lambda values: None, [1.0], group="Q1")


def test_apply_passes_a_good_value_straight_through_as_a_float() -> None:
    result = apply_estimator(lambda values: 3, [1.0, 5.0], group="g")

    assert result == 3.0
    assert isinstance(result, float)


def test_a_real_number_too_large_for_a_float_is_reported_as_a_value_error() -> None:
    """``Fraction`` is a ``numbers.Real``, so it passes the type check and reaches ``float()``,
    which raises ``OverflowError`` -- a type this function's contract does not mention. Without
    it in the ``except``, the raw ``OverflowError`` escapes past a message naming the group."""
    from fractions import Fraction

    with pytest.raises(ValueError, match="non-numeric"):
        sp.barplot(DUPLICATED, x="x", y="y", estimator=lambda values: Fraction(10**400, 1))


def test_the_discard_warning_points_at_the_callers_line_not_this_packages() -> None:
    """``stacklevel`` is what makes a warning actionable: it has to name the ``sp.barplot(...)``
    the reader wrote. Nothing else in this file would notice it pointing inside ``_aggregate``."""
    with pytest.warns(sp.AggregationWarning) as caught:
        sp.barplot(DUPLICATED, x="x", y="y")

    assert caught[0].filename == __file__
