"""What each chart's ``<desc>`` actually says (issue #118).

Every assertion here is on the **wording**, not on the element's existence. The bug this
file exists to prevent is the one the issue opened with: a ``<desc>`` that parses, passes
``"<desc>" in svg``, and tells a screen-reader user nothing.
"""

from __future__ import annotations

import re
from datetime import datetime

import pytest

import svgplot as sp
from svgplot.charts._describe import MAX_NAME_CHARS, MAX_NAMES, describe, group, plural, span

CATEGORICAL = {"x": ["Mon", "Tue", "Wed"], "y": [1.0, 5.0, 9.0], "g": ["north", "north", "south"]}
XY = {"x": [1.0, 2.0, 3.0], "y": [3.0, 20.0, 7.0], "s": [1.0, 2.0, 3.0], "g": ["north", "south", "north"]}
SAMPLES = {"x": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]}
GROUPED = {"x": ["a", "a", "a", "b", "b", "b"], "y": [1.0, 2.0, 3.0, 4.0, 5.0, 9.0]}
WEIGHTED = {"v": [1.0, 2.0, 3.0], "l": ["alpha", "beta", "gamma"]}


def desc_of(chart: sp.Chart) -> str:
    match = re.search(r"<desc>(.*?)</desc>", chart.to_string(), re.S)
    assert match is not None, "every chart writes a <desc>"
    return match.group(1)


# --- what each of the 16 chart types says ------------------------------------------------

EVERY_CHART = [
    (
        "barplot",
        lambda: sp.barplot(CATEGORICAL, x="x", y="y"),
        "Bar chart, 3 categories (Mon, Tue, Wed), values 1 to 9.",
    ),
    (
        "lineplot",
        lambda: sp.lineplot(XY, x="x", y="y"),
        "Line chart, 3 points, x 1 to 3, y 3 to 20.",
    ),
    (
        "scatterplot",
        lambda: sp.scatterplot(XY, x="x", y="y"),
        "Scatter plot, 3 points, x 1 to 3, y 3 to 20.",
    ),
    (
        "areaplot",
        lambda: sp.areaplot(XY, x="x", y="y"),
        "Area chart, 3 points, x 1 to 3, y 0 to 20.",
    ),
    (
        "histplot",
        lambda: sp.histplot(SAMPLES, x="x"),
        "Histogram, 8 observations in 4 bins, x 1 to 8, counts 0 to 2.",
    ),
    (
        "kdeplot",
        lambda: sp.kdeplot(SAMPLES, x="x"),
        "Density plot, 8 observations, x -3.848182 to 12.848182, density 0 to 0.123509.",
    ),
    (
        "ecdfplot",
        lambda: sp.ecdfplot(SAMPLES, x="x"),
        "Cumulative distribution plot, 8 observations, x 1 to 8, proportion 0 to 1.",
    ),
    (
        "boxplot",
        lambda: sp.boxplot(GROUPED, x="x", y="y"),
        "Box plot, 2 categories (a, b) over 6 observations, y 1 to 9, 1.5IQR whiskers.",
    ),
    (
        "violinplot",
        lambda: sp.violinplot(GROUPED, x="x", y="y"),
        "Violin plot, 2 categories (a, b) over 6 observations, y -2.371564 to 15.371564, with an inner box.",
    ),
    (
        "pieplot",
        lambda: sp.pieplot(WEIGHTED, values="v", labels="l"),
        "Pie chart, 3 slices (alpha, beta, gamma), values 1 to 3, total 6.",
    ),
    (
        "treemap",
        lambda: sp.treemap(WEIGHTED, values="v", labels="l"),
        "Treemap, 3 tiles (alpha, beta, gamma), values 1 to 3, total 6.",
    ),
    (
        "sparkline",
        lambda: sp.sparkline({"y": [1.0, 2.0, 3.0, 4.0]}, y="y"),
        "Sparkline, 4 points, values 1 to 4.",
    ),
    (
        "regplot",
        lambda: sp.regplot({"x": [1.0, 2.0, 3.0, 4.0, 5.0], "y": [2.0, 4.0, 5.0, 4.0, 6.0]}, x="x", y="y"),
        "Regression plot, fitted over 5 points, x 1 to 5, y 1.73913 to 8.3, with a 95% confidence band.",
    ),
    (
        "heatmap",
        lambda: sp.heatmap({"x": ["a", "b", "a"], "y": ["p", "p", "q"], "v": [1.0, 2.0, 3.0]}, x="x", y="y", values="v"),
        "Heatmap, 2 columns (a, b), 2 rows (p, q), 3 of 4 cells filled, values 1 to 3, quantised into 9 levels.",
    ),
    (
        "radarplot",
        lambda: sp.radarplot({"x": ["a", "b", "c"], "y": [1.0, 2.0, 3.0]}, x="x", y="y"),
        "Radar chart, 3 spokes (a, b, c), values 0 to 3.",
    ),
    (
        "gaugeplot",
        lambda: sp.gaugeplot({"v": [3.0, 7.0]}, value="v"),
        "Gauge, 2 arcs (1, 2), values 3 to 7, range 0 to 7.",
    ),
]


@pytest.mark.parametrize(("name", "build", "expected"), EVERY_CHART, ids=[case[0] for case in EVERY_CHART])
def test_every_chart_type_describes_kind_size_and_range(name: str, build, expected: str) -> None:
    """The issue's first acceptance criterion, one row per chart type: kind, how much data,
    and what it spans -- for all 16."""
    assert desc_of(build()) == expected


def test_every_public_chart_function_is_covered() -> None:
    """The 16-of-16 claim above is only worth anything if 16 is still all of them. A 17th
    chart added without a row here fails this, rather than quietly shipping the tautology.
    """
    covered = {name for name, _, _ in EVERY_CHART}
    assert covered == set(sp.charts.__all__)


def test_the_old_tautology_is_gone() -> None:
    """The exact sentence the issue was filed about."""
    chart = sp.barplot(CATEGORICAL, x="x", y="y").set_title("매출")
    output = chart.to_string()

    assert "<title>매출</title>" in output
    assert 'A chart titled "매출".' not in output


def test_the_title_is_not_repeated_into_the_description() -> None:
    """A description that only echoes the name adds nothing a screen reader hasn't already
    read out from ``aria-label``. Retitling must not move the description at all."""
    plain = desc_of(sp.barplot(CATEGORICAL, x="x", y="y"))
    titled = desc_of(sp.barplot(CATEGORICAL, x="x", y="y").set_title("Quarterly revenue"))

    assert plain == titled
    assert "Quarterly revenue" not in titled


# --- the variants that change the sentence ----------------------------------------------


def test_hue_adds_a_named_series_clause() -> None:
    assert desc_of(sp.barplot(CATEGORICAL, x="x", y="y", hue="g")) == (
        "Bar chart, 3 categories (Mon, Tue, Wed), 2 series (north, south), values 1 to 9."
    )


def test_stacking_is_named_and_carries_the_stacked_total() -> None:
    """The value axis of a stacked bar chart runs to the tallest *stack*, not the largest
    bar -- describing only the raw values would understate the axis by the whole stack."""
    assert desc_of(sp.barplot(CATEGORICAL, x="x", y="y", hue="g", stacked=True)) == (
        "Stacked bar chart, 3 categories (Mon, Tue, Wed), 2 series (north, south), " "values 1 to 9, stacked totals up to 9."
    )


def test_stacked_areas_are_named_and_span_the_stack() -> None:
    """Same reason as the stacked bars: the y axis runs to the top of the stack, so a
    description built from the raw values alone would understate it -- here 4 instead of 6.
    """
    data = {"x": [1.0, 2.0, 1.0, 2.0], "y": [1.0, 2.0, 3.0, 4.0], "g": ["a", "a", "b", "b"]}

    assert desc_of(sp.areaplot(data, x="x", y="y", hue="g", stacked=True)) == (
        "Stacked area chart, 2 series (a, b) over 4 points, x 1 to 2, y 0 to 6."
    )
    assert desc_of(sp.areaplot(data, x="x", y="y", hue="g")) == (
        "Area chart, 2 series (a, b) over 4 points, x 1 to 2, y 0 to 4."
    )


def test_orientation_is_named() -> None:
    assert desc_of(sp.barplot(CATEGORICAL, x="x", y="y", orient="h")).startswith("Horizontal bar chart,")


def test_a_time_axis_is_described_as_dates_not_epoch_seconds() -> None:
    """``x 1704034800 to 1709218800`` is technically the domain and useless to a listener."""
    data = {"x": [datetime(2024, 1, 1), datetime(2024, 3, 1)], "y": [1.0, 2.0]}
    assert desc_of(sp.lineplot(data, x="x", y="y")) == "Line chart, 2 points, x 2024-01-01 to 2024-03-01, y 1 to 2."


def test_a_time_of_day_survives_when_it_is_not_midnight() -> None:
    data = {"x": [datetime(2024, 1, 1, 9, 30), datetime(2024, 1, 1, 17, 0)], "y": [1.0, 2.0]}
    assert "x 2024-01-01 09:30:00 to 2024-01-01 17:00:00" in desc_of(sp.lineplot(data, x="x", y="y"))


def test_interpolation_is_named_only_when_it_is_not_linear() -> None:
    data = {"x": [1.0, 2.0, 3.0, 4.0], "y": [1.0, 4.0, 2.0, 5.0]}
    assert "interpolation" not in desc_of(sp.lineplot(data, x="x", y="y"))
    assert desc_of(sp.lineplot(data, x="x", y="y", interpolate="cubic")).endswith("cubic interpolation.")


def test_a_size_channel_names_its_column() -> None:
    assert desc_of(sp.scatterplot(XY, x="x", y="y", size="s")).endswith('marker size from "s".')


def test_donut_and_pie_are_different_kinds() -> None:
    assert desc_of(sp.pieplot(WEIGHTED, values="v", labels="l", inner_radius=0.5)).startswith("Donut chart,")
    assert desc_of(sp.pieplot(WEIGHTED, values="v", labels="l")).startswith("Pie chart,")


def test_the_ecdf_y_clause_names_the_statistic_it_shows() -> None:
    assert desc_of(sp.ecdfplot(SAMPLES, x="x", stat="count")).endswith("count 0 to 8.")
    assert desc_of(sp.ecdfplot(SAMPLES, x="x", complementary=True)).startswith("Complementary cumulative distribution plot,")


def test_a_regression_without_a_band_says_so() -> None:
    data = {"x": [1.0, 2.0, 3.0, 4.0, 5.0], "y": [2.0, 4.0, 5.0, 4.0, 6.0]}
    assert desc_of(sp.regplot(data, x="x", y="y", ci=None)).endswith("no confidence band.")


def test_the_heatmap_counts_holes_rather_than_pretending_the_grid_is_full() -> None:
    """A hole is not a zero (``charts/heatmap.py``'s own rule) -- so ``4 cells`` for a 2x2
    grid with one missing pair would be a count of cells that were never drawn."""
    data = {"x": ["a", "b", "a"], "y": ["p", "p", "q"], "v": [1.0, 2.0, 3.0]}
    assert "3 of 4 cells filled" in desc_of(sp.heatmap(data, x="x", y="y", values="v"))


# --- the summary cap ---------------------------------------------------------------------


def test_names_are_listed_in_full_up_to_the_count_cap() -> None:
    names = [f"c{index}" for index in range(MAX_NAMES)]
    data = {"x": names, "y": [float(index) for index in range(MAX_NAMES)]}

    assert f"{MAX_NAMES} categories ({', '.join(names)})" in desc_of(sp.barplot(data, x="x", y="y"))


def test_past_the_count_cap_the_rest_are_counted_not_listed() -> None:
    """A 100-category chart must not read out 100 names -- the issue's own example."""
    names = [f"c{index}" for index in range(100)]
    data = {"x": names, "y": [float(index) for index in range(100)]}
    described = desc_of(sp.barplot(data, x="x", y="y"))

    assert f"100 categories ({', '.join(names[:MAX_NAMES])} and {100 - MAX_NAMES} more)" in described
    assert f"c{MAX_NAMES}" not in described


def test_the_character_cap_binds_where_the_count_cap_does_not() -> None:
    """Six names is not a length bound: these six are under the count cap and still far
    past what a listener can hold, so the character cap has to be the one that cuts."""
    names = ["n" * 20 + str(index) for index in range(MAX_NAMES)]
    data = {"x": names, "y": [float(index) for index in range(MAX_NAMES)]}
    described = desc_of(sp.barplot(data, x="x", y="y"))

    listed = re.search(r"categories \((.*?)\)", described).group(1)
    assert listed == f"{names[0]}, {names[1]} and 4 more"
    assert len(listed.split(" and ")[0]) <= MAX_NAME_CHARS


def test_a_name_is_never_shortened_to_make_it_fit() -> None:
    """A truncated label is a different label. The whole parenthetical is dropped instead."""
    long_name = "z" * (MAX_NAME_CHARS + 1)
    data = {"x": [long_name, "b"], "y": [1.0, 2.0]}
    described = desc_of(sp.barplot(data, x="x", y="y"))

    assert described == "Bar chart, 2 categories, values 1 to 2."
    assert "z" * 10 not in described


def test_the_listed_names_are_a_prefix_not_whatever_happens_to_fit() -> None:
    """Skipping an oversized first name to list the short second one would tell a listener
    that the short one comes first."""
    data = {"x": ["z" * (MAX_NAME_CHARS + 1), "b", "c"], "y": [1.0, 2.0, 3.0]}

    assert "(b" not in desc_of(sp.barplot(data, x="x", y="y"))


def _labels(count: int) -> list[str]:
    return [f"s{index}" for index in range(count)]


CAPPED_LISTS = [
    # (name, builder, how many things it names) -- one entry per kind of list a chart makes.
    ("pie slices", lambda n: sp.pieplot({"v": _values(n), "l": _labels(n)}, values="v", labels="l"), 40),
    ("treemap tiles", lambda n: sp.treemap({"v": _values(n), "l": _labels(n)}, values="v", labels="l"), 40),
    # 12, not 40: a gauge refuses more rows than it can draw readable rings for.
    ("gauge arcs", lambda n: sp.gaugeplot({"v": _values(n), "l": _labels(n)}, value="v", labels="l"), 12),
    ("bar series", lambda n: sp.barplot({"x": ["a"] * n, "y": _values(n), "g": _labels(n)}, x="x", y="y", hue="g"), 40),
    ("radar spokes", lambda n: sp.radarplot({"x": _labels(n), "y": _values(n)}, x="x", y="y"), 40),
    ("heatmap axes", lambda n: sp.heatmap({"x": _labels(n), "y": _labels(n), "v": _values(n)}, x="x", y="y", values="v"), 40),
]


def _values(count: int) -> list[float]:
    return [float(index + 1) for index in range(count)]


@pytest.mark.parametrize(("name", "build", "count"), CAPPED_LISTS, ids=[case[0] for case in CAPPED_LISTS])
def test_the_cap_applies_to_every_kind_of_name_a_chart_lists(name: str, build, count: int) -> None:
    """Categories are not the only list -- series, slices, spokes, arcs, tiles and both
    heatmap axes are too, and a cap that only held for one of them would still read out
    forty names."""
    described = desc_of(build(count))

    assert f"and {count - MAX_NAMES} more" in described
    assert f"s{count - 1}" not in described


def test_the_sentence_length_grows_only_with_the_digits_of_the_counts() -> None:
    """``MAX_NAMES``/``MAX_NAME_CHARS`` document a measured worst case near 222 characters
    on ``heatmap``, the one chart type that names two groups. Past the caps the only thing
    still growing is the width of the numbers -- 224 at 20 names, 229 at 100 -- so a cap
    change that made the sentence grow with the *data* instead would fail here."""
    described = [
        desc_of(sp.heatmap({"x": names, "y": names, "v": _values(len(names))}, x="x", y="y", values="v"))
        for names in (["n" * 10 + str(index) for index in range(20)],)
    ]

    assert len(described[0]) <= 230


# --- the escape chokepoint ---------------------------------------------------------------


def test_a_newline_in_a_label_is_folded_by_the_svg_chokepoint() -> None:
    """``_svg.add_text`` folds line runs; the description must inherit that rather than
    carrying a raw newline into the file (which would end its markdown HTML block)."""
    data = {"x": ["a\n\nb", "c"], "y": [1.0, 2.0]}
    described = desc_of(sp.barplot(data, x="x", y="y"))

    assert described == "Bar chart, 2 categories (a b, c), values 1 to 2."
    assert "\n" not in described


def test_a_multiline_label_still_produces_saveable_markdown() -> None:
    """The fold is what keeps the blank-line guard in ``output/markdown`` satisfied -- a
    description is a second place a caller's newline can now reach the file."""
    data = {"x": ["a\n\nb", "c"], "y": [1.0, 2.0]}

    assert "\n\n<" not in sp.barplot(data, x="x", y="y").to_markdown()


def test_markup_in_a_label_is_escaped_not_injected() -> None:
    data = {"x": ['<script>&"', "c"], "y": [1.0, 2.0]}
    output = sp.barplot(data, x="x", y="y").to_string()

    # A double quote is left alone: this is text content, not an attribute value, so there
    # is no quoting context for it to escape from. The two that matter here are.
    assert '<desc>Bar chart, 2 categories (&lt;script&gt;&amp;", c), values 1 to 2.</desc>' in output


def test_a_control_character_in_a_label_is_refused_by_the_chokepoint() -> None:
    """Not swallowed into a description that then fails to parse."""
    data = {"x": ["a\x00b", "c"], "y": [1.0, 2.0]}

    with pytest.raises(ValueError, match="not allowed in XML 1.0"):
        sp.barplot(data, x="x", y="y").to_string()


# --- the assembler's own rules -----------------------------------------------------------


def test_empty_clauses_are_dropped_rather_than_left_as_gaps() -> None:
    assert describe("Bar chart", None, "3 categories", "", "values 1 to 2") == "Bar chart, 3 categories, values 1 to 2."


def test_a_kind_with_no_clauses_is_still_a_sentence() -> None:
    assert describe("Sparkline") == "Sparkline."


def test_counts_agree_with_their_nouns() -> None:
    assert plural(1, "category") == "1 category"
    assert plural(2, "category") == "2 categories"
    assert plural(1, "series") == "1 series"
    assert plural(3, "series") == "3 series"
    assert plural(1, "point") == "1 point"
    assert plural(0, "point") == "0 points"


def test_a_single_name_is_not_pluralized_by_the_group_clause() -> None:
    assert group(["only"], "category") == "1 category (only)"


def test_a_range_reads_low_to_high() -> None:
    assert span("x", 1.5, 2.0) == "x 1.5 to 2"
