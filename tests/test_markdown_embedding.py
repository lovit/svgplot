"""Every chart's output must survive being pasted into a markdown document.

That is what this package is for, and it is a property of the *whole surface*, not of any
one chart: a blank line anywhere in the serialized SVG ends its CommonMark HTML block, and
everything after the break -- the rest of the chart's own source -- is shown to the reader
as prose. So the check here is deliberately exhaustive rather than sampled, and the
registry below is asserted to cover ``svgplot.charts.__all__`` so a new chart cannot ship
without being checked.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

import svgplot as sp
import svgplot.charts as charts
from svgplot.chart.base import Chart

# A label carrying a blank line, a lone newline, and a Windows line ending, in every string
# channel a chart accepts: category values, hue values, and the legend labels of the charts
# that take their own labels column.
POISON = "before\n\nafter\rtail\r\nend"

DATA = {
    "day": [1, 2, 3, 4, 1, 2, 3, 4],
    "value": [10.0, 15.0, 7.0, 20.0, 5.0, 8.0, 3.0, 12.0],
    "weight": [1.0, 4.0, 2.0, 5.0, 3.0, 1.0, 4.0, 2.0],
    "category": [POISON, "b", "c", "d", POISON, "b", "c", "d"],
    "group": [POISON, POISON, POISON, POISON, "y", "y", "y", "y"],
}

CHARTS: dict[str, Callable[[], Chart]] = {
    "lineplot": lambda: sp.lineplot(DATA, x="day", y="value", hue="group"),
    "scatterplot": lambda: sp.scatterplot(DATA, x="day", y="value", size="weight", hue="group"),
    "barplot": lambda: sp.barplot(DATA, x="category", y="value", hue="group"),
    "histplot": lambda: sp.histplot(DATA, x="value", bins=4, hue="group"),
    "areaplot": lambda: sp.areaplot(DATA, x="day", y="value", hue="group"),
    "pieplot": lambda: sp.pieplot(DATA, values="value", labels="category"),
    "boxplot": lambda: sp.boxplot(DATA, x="category", y="value"),
    "ecdfplot": lambda: sp.ecdfplot(DATA, x="value", hue="group"),
    "kdeplot": lambda: sp.kdeplot(DATA, x="value", hue="group"),
    "violinplot": lambda: sp.violinplot(DATA, x="group", y="value"),
    "regplot": lambda: sp.regplot(DATA, x="day", y="value", seed=0),
    "treemap": lambda: sp.treemap(DATA, values="value", labels="category"),
    "sparkline": lambda: sp.sparkline(DATA, y="value"),
}


def test_the_registry_covers_every_public_chart() -> None:
    """Without this the file quietly stops being exhaustive the first time a chart ships,
    and the guarantee it exists to hold would decay silently instead of failing."""
    assert set(CHARTS) == set(charts.__all__)


@pytest.mark.parametrize("name", sorted(CHARTS), ids=sorted(CHARTS))
def test_no_chart_can_be_made_to_emit_a_blank_line(name: str) -> None:
    """A blank line ends the SVG's own HTML block. Every string a caller can put into a
    chart is routed here to prove none of them reaches the output as one."""
    svg = CHARTS[name]().to_string()

    assert "\n\n" not in svg
    assert not any(line.strip() == "" for line in svg.splitlines())


@pytest.mark.parametrize("name", sorted(CHARTS), ids=sorted(CHARTS))
def test_no_chart_leaves_a_stray_line_break_inside_an_element(name: str) -> None:
    """A single newline does not break CommonMark, but Python-Markdown -- MkDocs' default,
    and this package's own docs engine -- has no ``svg`` in its block-level tag list, so it
    treats a multi-line ``<svg>`` as a paragraph and inserts ``<br/>`` mid-element. The
    only line breaks left in the output must be the pretty-printer's own, between tags."""
    for line in CHARTS[name]().to_string().splitlines():
        stripped = line.strip()
        assert not stripped or stripped.startswith("<") or stripped.startswith(".") or stripped.startswith("?")


def test_the_poison_actually_reaches_the_output() -> None:
    """Otherwise every test above would pass against a chart that silently dropped the
    label, and the file would be checking nothing at all."""
    svg = CHARTS["barplot"]().to_string()

    assert "before after tail end" in svg


def test_a_composition_of_poisoned_charts_is_clean_too() -> None:
    """Composition re-serializes its children through its own document, so it is a second
    path to the same output and needs its own check."""
    composition = sp.row([CHARTS["barplot"](), CHARTS["lineplot"]()])

    assert "\n\n" not in composition.to_string()


def test_a_poisoned_title_and_caption_survive_too() -> None:
    """Titles reach ``<title>``/``<desc>`` rather than ``<text>``, and a caption reaches a
    third node -- all three are text content and all three are user-supplied."""
    chart = CHARTS["barplot"]().set_title(POISON)
    captioned = sp.add_caption(sp.row([chart]), POISON)

    assert "\n\n" not in chart.to_string()
    assert "\n\n" not in captioned.to_string()


def test_the_markdown_output_of_a_poisoned_chart_is_produced_rather_than_refused() -> None:
    """``output/markdown`` still guards against a blank line, but nothing a caller can do
    should reach that guard now -- if it does, the fix here has a hole."""
    markdown = CHARTS["barplot"]().to_markdown()

    assert markdown.startswith("<div>\n<svg")
    assert "\n\n" not in markdown.rstrip("\n")
