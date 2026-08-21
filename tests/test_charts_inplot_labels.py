"""Three charts write a label *into the plot* and style it with the legend's class.

``pieplot`` puts the value beside its slice, ``treemap`` the name inside its tile, ``gaugeplot``
the number in the hole. All three reuse ``legend-text`` because the size and colour are right,
and that was fine while nothing needed to talk about them separately.

Inlining the gallery (#185) made it not fine. A label drawn on top of a mark takes the pointer,
so the mark's own ``<title>`` never shows -- and in ``treemap`` this is not hypothetical: the
tile label carries a ``<title>`` of its own whenever the name had to be shortened, so hovering
a tile shows the full *name* where the tile is about to offer the *value*. Fixing it means a
page rule saying ``pointer-events: none`` about these labels and **not** about the legend's,
which needs a class that tells them apart.

The hook is added, never substituted. Dropping ``legend-text`` would mean a new rule in
``theme/css.py``, and that block is emitted by every chart -- so a purely local need would
rewrite all seventeen gallery pages and put sixteen independent chart PRs in a queue.
"""

from __future__ import annotations

import pytest

from _svg_probe import every_tag, style_rules, tags, texts
from svgplot.charts.gauge import gaugeplot
from svgplot.charts.pie import pieplot
from svgplot.charts.treemap import treemap

_SLICES = {"이름": ["가", "나", "다"], "값": [5.0, 3.0, 2.0]}
_TILES = {"이름": ["가", "나", "다"], "값": [9.0, 4.0, 1.0]}
_DIAL = {"이름": ["가", "나"], "값": [40.0, 70.0]}

# (chart svg, the hook, how many in-plot labels it should be on)
_CASES = [
    pytest.param(lambda: pieplot(_SLICES, values="값", labels="이름").to_string(), "pie-value", 3, id="pieplot"),
    pytest.param(lambda: treemap(_TILES, values="값", labels="이름").to_string(), "treemap-label", 3, id="treemap"),
    pytest.param(lambda: gaugeplot(_DIAL, value="값", labels="이름").to_string(), "gauge-number", 2, id="gaugeplot"),
]


@pytest.mark.parametrize(("render", "hook", "count"), _CASES)
def test_every_in_plot_label_carries_the_hook(render, hook: str, count: int) -> None:
    """One hook per label the chart draws inside the plot -- not one per chart, and not one
    per row that happens to have been drawn."""
    svg = render()

    assert len(tags(svg, "text", hook)) == count


@pytest.mark.parametrize(("render", "hook", "count"), _CASES)
def test_the_legend_does_not_carry_the_hook(render, hook: str, count: int) -> None:
    """The half that makes the hook worth having. A rule keyed on it must reach the labels on
    the plot and stop there; if the legend's rows answered to it too, ``pointer-events: none``
    would silently take the legend out of the pointer's reach as well.

    Two assertions with different jobs: the strict inequality says the legend has rows this
    hook does *not* reach, whatever their number, and the equality pins how many labels the
    chart draws inside the plot.
    """
    svg = render()
    all_labels = len(tags(svg, "text", "legend-text"))
    hooked = len(tags(svg, "text", hook))

    assert all_labels > hooked, "this chart has no legend rows to tell apart"
    assert hooked == count


@pytest.mark.parametrize(("render", "hook", "count"), _CASES)
def test_the_hook_lands_on_a_text_and_nothing_else(render, hook: str, count: int) -> None:
    """The half a review found missing, by finding it broken.

    ``gauge-value`` looked like the obvious name for the dial's numbers and was already on the
    dial's **arcs**. With both carrying it, a page writing ``pointer-events: none`` about the
    hook would have taken the arcs out of the pointer's reach -- the exact failure this hook
    exists to prevent, aimed at the marks instead of the legend. Nothing caught it: the only
    check that noticed was the gallery byte-diff, which goes quiet as soon as you rebuild.

    Enumerated over every element rather than asked about ``<text>``, because the question is
    "what else carries this", and a check that only looks at texts cannot answer it.
    """
    svg = render()
    carriers = {
        element
        for element in ("path", "text", "line", "rect", "circle", "g")
        for tag in every_tag(svg, element)
        if hook in tag.get("class", "").split()
    }

    assert carriers == {"text"}, f"{hook} is also on {sorted(carriers - {'text'})}"


@pytest.mark.parametrize(("render", "hook", "count"), _CASES)
def test_the_hook_is_added_beside_legend_text_and_not_instead_of_it(render, hook: str, count: int) -> None:
    """``legend-text`` is what gives these labels their size and colour. Replacing it would need
    a new rule in ``theme/css.py``, and that rule list is the same for every chart -- so a
    change wanted by three charts would put a rule in all sixteen charts' ``<style>``."""
    svg = render()

    for label in tags(svg, "text", hook):
        assert "legend-text" in label["class"].split(), f"{hook} replaced legend-text instead of joining it"


@pytest.mark.parametrize(("render", "hook", "count"), _CASES)
def test_the_hook_is_not_styled_by_the_chart(render, hook: str, count: int) -> None:
    """A pure hook: the chart says which elements these are and says nothing about how they
    look. The day one of them gets a rule of its own, the ``<style>`` block grows and every
    committed gallery page is rewritten -- so that should be a decision, not a side effect."""
    svg = render()

    assert not [rule for rule in style_rules(svg) if rule.startswith(f".{hook} ")]


def test_a_shortened_tile_name_is_the_case_that_made_this_necessary() -> None:
    """Not an abstraction. A tile whose name does not fit keeps the full text in a ``<title>``
    on the *label*, and the label is drawn over the tile -- so the pointer finds the name where
    the reader is reaching for the value. The page can only separate them by class."""
    long_name = "아주 긴 항목 이름 " * 4
    # A narrow tile: the long name takes 1/10 of the total, so its rectangle is far too small
    # to hold it and the label really is cut. With a wide tile the name fits and the <title>
    # arrives only because the estimate calls it close, which is a different case.
    svg = treemap({"이름": ["나", long_name], "값": [9.0, 1.0]}, values="값", labels="이름").to_string()
    shown = texts(svg, "text", "treemap-label")

    assert f"<title>{long_name}</title>" in svg, "the full name is not recoverable anywhere"
    assert long_name not in shown, f"the fixture stopped being the shortened case: {shown}"
    assert any("…" in label for label in shown)
