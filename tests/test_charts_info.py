from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest

import svgplot as sp
from svgplot.layout import apply_size, facet

NUMERIC = {"day": [1.0, 2.0, 3.0], "sales": [1200.0, 3400.0, 2500.0]}
SPEC = [("Day", "@day{0.0}"), ("Sales", "@sales{0,0}")]
BAD_SPEC = [("Z", "@not_a_column{%s}")]


def _table_rows(markdown: str) -> list[str]:
    """The table's lines, header and divider included, in document order."""
    return [line for line in markdown.splitlines() if line.startswith("|")]


def _body_rows(markdown: str) -> list[str]:
    return [line for line in _table_rows(markdown) if "---" not in line][1:]


# ---------------------------------------------------------------------------
# the end-to-end shape from the issue
# ---------------------------------------------------------------------------


def test_a_line_chart_with_info_renders_a_footnote_table() -> None:
    chart = sp.lineplot(NUMERIC, x="day", y="sales", info=SPEC)

    assert _table_rows(chart.to_markdown())[:2] == ["| Day | Sales |", "| --- | --- |"]
    assert _body_rows(chart.to_markdown()) == ["| 1.0 | 1,200 |", "| 2.0 | 3,400 |", "| 3.0 | 2,500 |"]


@pytest.mark.parametrize(
    ("build", "expected"),
    [
        (lambda info: sp.lineplot(NUMERIC, x="day", y="sales", info=info), 3),
        (lambda info: sp.scatterplot(NUMERIC, x="day", y="sales", info=info), 3),
        (lambda info: sp.pieplot(NUMERIC, values="sales", labels="day", info=info), 3),
    ],
)
def test_every_row_per_mark_chart_accepts_info(build: Callable[[object], sp.Chart], expected: int) -> None:
    """The three charts where one input row *is* one mark. ``bar``/``area``/``box``/
    ``hist`` are deliberately excluded: they aggregate, so an original-row table beside
    them would contradict the marks rather than annotate them."""
    assert len(_body_rows(build(SPEC).to_markdown())) == expected


def test_info_accepts_a_labelspec_as_well_as_the_raw_pairs() -> None:
    """``info=`` is typed to take both, and ``LabelSpec`` is re-exported at the top level
    precisely so a caller can build one once and reuse it."""
    spec = sp.LabelSpec.parse(SPEC)

    assert (
        sp.lineplot(NUMERIC, x="day", y="sales", info=spec).to_markdown()
        == sp.lineplot(NUMERIC, x="day", y="sales", info=SPEC).to_markdown()
    )


def test_labelspec_is_re_exported_at_the_top_level() -> None:
    assert sp.LabelSpec is not None
    assert "LabelSpec" in sp.__all__


# ---------------------------------------------------------------------------
# info= is optional, and orthogonal to the other output formats
# ---------------------------------------------------------------------------


def test_markdown_without_info_is_the_svg_alone(tmp_path: Path) -> None:
    """Not an error. Markdown is a format, not a feature flag."""
    path = tmp_path / "chart.md"
    sp.lineplot(NUMERIC, x="day", y="sales").save(str(path))

    assert _table_rows(path.read_text(encoding="utf-8")) == []


def test_info_does_not_change_the_drawn_svg() -> None:
    """The table lives beside the chart, never inside it -- adding ``info=`` must not
    move a single coordinate.

    Since issue #118 it *does* add one thing: ``aria-describedby``, pointing at the table
    it now has to point at. That is the whole of the difference, which is what the second
    assertion pins -- deleting the attribute leaves two byte-identical documents.
    """
    without = sp.lineplot(NUMERIC, x="day", y="sales").to_string()
    with_info = sp.lineplot(NUMERIC, x="day", y="sales", info=SPEC).to_string()

    assert 'aria-describedby="svgplot-data-table"' in with_info
    assert without == with_info.replace(' aria-describedby="svgplot-data-table"', "")


def test_saving_svg_with_info_adds_only_the_table_reference(tmp_path: Path) -> None:
    plain, annotated = tmp_path / "a.svg", tmp_path / "b.svg"
    sp.lineplot(NUMERIC, x="day", y="sales").save(str(plain))
    sp.lineplot(NUMERIC, x="day", y="sales", info=SPEC).save(str(annotated))

    written = annotated.read_text(encoding="utf-8")
    assert plain.read_text(encoding="utf-8") == written.replace(' aria-describedby="svgplot-data-table"', "")


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda: sp.lineplot(NUMERIC, "day", "sales", None, SPEC), id="lineplot"),
        pytest.param(lambda: sp.scatterplot(NUMERIC, "day", "sales", None, None, SPEC), id="scatterplot"),
        pytest.param(lambda: sp.pieplot(NUMERIC, "sales", "day", SPEC), id="pieplot"),
    ],
)
def test_info_is_keyword_only(call: Callable[[], sp.Chart]) -> None:
    """Each call passes exactly one positional argument more than the signature allows, so
    it fails only while ``info`` stays behind the ``*``. Overshooting by several arguments
    would raise ``TypeError`` either way and prove nothing."""
    with pytest.raises(TypeError):
        call()


# ---------------------------------------------------------------------------
# the table reports only the rows the chart drew
# ---------------------------------------------------------------------------


def test_rows_the_chart_dropped_are_absent_from_the_table() -> None:
    """The whole point of collecting at plot time: the table must not claim a row the
    chart never plotted."""
    holey = {"day": [1.0, None, 3.0], "sales": [1.0, 2.0, float("nan")]}
    chart = sp.scatterplot(holey, x="day", y="sales", info=[("Day", "@day{0.0}")])

    assert _body_rows(chart.to_markdown()) == ["| 1.0 |"]


def test_a_column_the_chart_never_consulted_may_have_holes() -> None:
    """``note`` is not a channel, so a missing cell there is shown rather than used to
    drop an otherwise plottable row."""
    data = {"day": [1.0, 2.0], "sales": [1.0, 2.0], "note": ["ok", None]}
    chart = sp.scatterplot(data, x="day", y="sales", info=[("Note", "@note{%s}")])

    assert _body_rows(chart.to_markdown()) == ["| ok |", "| — |"]


def test_an_unknown_field_fails_at_plot_time_not_at_save_time() -> None:
    """Deferring to ``save()`` would surface a typo far from the call that made it."""
    with pytest.raises(KeyError, match="field not found in data"):
        sp.lineplot(NUMERIC, x="day", y="sales", info=[("Z", "@nope{0.0}")])


@pytest.mark.parametrize(
    ("call", "match"),
    [
        pytest.param(lambda: sp.lineplot(NUMERIC, x="nope", y="sales", info=BAD_SPEC), "x column not found", id="line"),
        pytest.param(lambda: sp.scatterplot(NUMERIC, x="nope", y="sales", info=BAD_SPEC), "x column not found", id="scatter"),
        pytest.param(
            lambda: sp.pieplot(NUMERIC, values="nope", labels="day", info=BAD_SPEC), "values column not found", id="pie"
        ),
    ],
)
def test_the_chart_s_own_errors_still_come_first(call: Callable[[], sp.Chart], match: str) -> None:
    """Collection sits after the existing validation in all three charts, so a bad channel
    column reports the chart's own error rather than a confusing label error. ``BAD_SPEC``
    names a missing field too, so whichever check runs first is the one that speaks."""
    with pytest.raises(KeyError, match=match):
        call()


# ---------------------------------------------------------------------------
# composition and mutation survive
# ---------------------------------------------------------------------------


def test_facet_forwards_info_to_every_panel() -> None:
    """``facet`` already passes ``**kwargs`` through, so this needs no code -- which is
    exactly why it needs a test: nothing else would notice if that stopped working."""
    data = {
        "x": [1.0, 2.0, 3.0, 4.0],
        "y": [1.0, 2.0, 3.0, 4.0],
        "region": ["north", "north", "south", "south"],
    }
    composition = facet(sp.lineplot, data, col="region", x="x", y="y", info=[("X", "@x{0.0}")])

    panels = [_body_rows(f"{chart._label_table()}") for chart in composition.charts]
    assert panels == [["| 1.0 |", "| 2.0 |"], ["| 3.0 |", "| 4.0 |"]]


def test_apply_size_keeps_the_labels() -> None:
    """``apply_size`` mutates in place and returns the same chart, so the snapshot has to
    survive the in-place pass. The identity assertion is part of the claim: without it this
    test inspects the original object and would pass even against an implementation that
    returned a fresh, table-less copy."""
    chart = sp.scatterplot(NUMERIC, x="day", y="sales", info=SPEC)

    assert apply_size(chart, "responsive") is chart
    assert _body_rows(chart.to_markdown()) == ["| 1.0 | 1,200 |", "| 2.0 | 3,400 |", "| 3.0 | 2,500 |"]


def test_set_title_keeps_the_labels() -> None:
    chart = sp.scatterplot(NUMERIC, x="day", y="sales", info=SPEC).set_title("Sales")

    assert len(_body_rows(chart.to_markdown())) == 3


def test_editing_the_source_data_after_plotting_does_not_change_the_table() -> None:
    """The snapshot is taken at plot time, so the table and the SVG can never disagree."""
    mutable = {"day": [1.0, 2.0], "sales": [1.0, 2.0]}
    chart = sp.lineplot(mutable, x="day", y="sales", info=[("Day", "@day{0.0}")])

    mutable["day"].append(99.0)
    mutable["sales"].append(99.0)

    assert _body_rows(chart.to_markdown()) == ["| 1.0 |", "| 2.0 |"]


# ---------------------------------------------------------------------------
# escaping
# ---------------------------------------------------------------------------


def test_table_structure_characters_in_values_and_labels_are_escaped() -> None:
    """The table sits in the same file as the SVG, so an unescaped ``|`` desynchronises
    it and a raw ``<script>`` is an XSS vector in the rendered markdown."""
    evil = {"x": [1.0, 2.0], "y": [1.0, 2.0], "note": ["a|b", "<script>x</script>"]}
    markdown = sp.scatterplot(evil, x="x", y="y", info=[("N|ote", "@note{%s}")]).to_markdown()

    assert "<script>" not in markdown
    assert "&lt;script&gt;" in markdown
    assert _table_rows(markdown)[0] == r"| N\|ote |"
    assert r"| a\|b |" in _table_rows(markdown)


def test_a_newline_in_a_value_cannot_split_a_table_row() -> None:
    data = {"x": [1.0, 2.0], "y": [1.0, 2.0], "note": ["a\nb", "c"]}
    markdown = sp.scatterplot(data, x="x", y="y", info=[("Note", "@note{%s}")]).to_markdown()

    assert len(_body_rows(markdown)) == 2
    assert "| a b |" in _table_rows(markdown)


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(lambda data, info: sp.lineplot(data, x="x", y="y", hue="g", info=info), id="line-hue"),
        pytest.param(lambda data, info: sp.scatterplot(data, x="x", y="y", hue="g", info=info), id="scatter-hue"),
        pytest.param(lambda data, info: sp.scatterplot(data, x="x", y="y", size="g", info=info), id="scatter-size"),
    ],
)
def test_an_optional_channel_still_drops_its_missing_rows(build: Callable[[object, object], sp.Chart]) -> None:
    """``hue``/``size`` are optional, so it is easy to leave them out of the collected
    channels -- and then the table lists a row the chart refused to draw. Only a fixture
    whose *only* hole is in that channel can tell the difference."""
    data = {"x": [1.0, 2.0, 3.0], "y": [1.0, 2.0, 3.0], "g": [1.0, None, 3.0]}

    assert _body_rows(build(data, [("X", "@x{0.0}")]).to_markdown()) == ["| 1.0 |", "| 3.0 |"]


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(lambda data, info: sp.lineplot(data, x="a", y="b", info=info), id="line"),
        pytest.param(lambda data, info: sp.scatterplot(data, x="a", y="b", info=info), id="scatter"),
    ],
)
@pytest.mark.parametrize("holed", ["a", "b"])
def test_every_required_channel_drops_its_own_missing_rows(build: Callable[[object, object], sp.Chart], holed: str) -> None:
    """One fixture per channel, each with a hole in *only* that channel. A shared fixture
    holed in several at once cannot tell a forgotten channel from a remembered one -- the
    surviving rows come out the same either way."""
    data = {"a": [1.0, 2.0, 3.0], "b": [1.0, 2.0, 3.0]}
    data[holed] = [1.0, None, 3.0]

    assert len(_body_rows(build(data, [("A", "@a{0.0}")]).to_markdown())) == 2


def test_pieplot_drops_rows_whose_value_is_missing() -> None:
    """The mirror of the labels case: ``values`` is a required channel too, and a slice
    with no value is not drawn."""
    data = {"v": [1.0, None, 3.0], "l": ["a", "b", "c"]}
    chart = sp.pieplot(data, values="v", labels="l", info=[("L", "@l{%s}")])

    assert _body_rows(chart.to_markdown()) == ["| a |", "| c |"]


def test_an_absent_optional_channel_drops_nothing() -> None:
    """The mirror case: passing ``hue=None`` must not be read as a column named ``None``
    and must not filter anything out."""
    data = {"x": [1.0, 2.0, 3.0], "y": [1.0, 2.0, 3.0], "g": [1.0, None, 3.0]}

    assert len(_body_rows(sp.lineplot(data, x="x", y="y", info=[("X", "@x{0.0}")]).to_markdown())) == 3


def test_pieplot_drops_rows_whose_label_is_missing() -> None:
    """``labels`` is a channel for ``pieplot`` the way ``hue`` is for the others: a slice
    with no label is not drawn, so it must not appear in the table either."""
    data = {"v": [1.0, 2.0, 3.0], "l": ["a", None, "c"]}
    chart = sp.pieplot(data, values="v", labels="l", info=[("V", "@v{0.0}")])

    assert _body_rows(chart.to_markdown()) == ["| 1.0 |", "| 3.0 |"]


def test_pieplot_without_labels_keeps_every_valued_row() -> None:
    """``labels=None`` means positions are generated, so nothing is dropped for it -- the
    ``None`` must be filtered out of the required channels rather than looked up."""
    data = {"v": [1.0, 2.0, 3.0]}
    chart = sp.pieplot(data, values="v", info=[("V", "@v{0.0}")])

    assert len(_body_rows(chart.to_markdown())) == 3


@pytest.mark.parametrize(
    ("data", "info"),
    [
        pytest.param({"x": [1.0, 2.0], "y": [1.0, 2.0], "n": [float("inf"), 1.0]}, [("N", "@n{0.0}")], id="infinite"),
        pytest.param({"x": [1.0, 2.0], "y": [1.0, 2.0], "n": ["5", "6"]}, [("N", "@n{0,0}")], id="numeric-string"),
        pytest.param({"x": [1.0, 2.0], "y": [1.0, 2.0]}, [("X", "@x{%Y-%m-%d}")], id="float-under-datetime-spec"),
    ],
)
def test_a_value_the_spec_cannot_format_fails_at_markdown_time(data: dict[str, list], info: list) -> None:
    """A *missing* value gets a dash; a present-but-unformattable one has no substitute, so
    it raises. Pinned because the failure lands at ``to_markdown()``/``save()`` rather than
    where ``info=`` was passed -- the chart itself builds and renders to SVG fine."""
    chart = sp.scatterplot(data, x="x", y="y", info=info)

    assert chart.to_string()
    with pytest.raises(ValueError):
        chart.to_markdown()


def test_a_composition_carries_no_table_even_when_its_children_have_one() -> None:
    """Today's deliberate behaviour, pinned so the follow-up that gathers children's tables
    has to change this test on purpose. Each panel *does* hold the right snapshot -- that is
    what ``test_facet_forwards_info_to_every_panel`` checks -- but the composition's own
    markdown shows the charts only."""
    data = {"x": [1.0, 2.0, 3.0, 4.0], "y": [1.0, 2.0, 3.0, 4.0], "region": ["n", "n", "s", "s"]}
    composition = facet(sp.lineplot, data, col="region", x="x", y="y", info=[("X", "@x{0.0}")])

    assert _table_rows(composition.to_markdown()) == []


# ---------------------------------------------------------------------------
# one declaration fills both the table and the tooltips
# ---------------------------------------------------------------------------

# Built so that no positional pairing can be right. Row 2 is dropped -- by the chart and by the
# table alike -- so the surviving rows are not ``range(4)``; and ``hue=`` sorts the series so the
# points come out r3, r4, r0, r1 while the table stays in input order r0, r1, r3, r4. An
# implementation that walks the table alongside the marks answers every point with another
# point's row and still produces four plausible tooltips.
MISALIGNING = {
    "x": [1.0, 2.0, None, 4.0, 5.0],
    "y": [10.0, 20.0, 30.0, 40.0, 50.0],
    "team": ["b", "b", "b", "a", "a"],
    "who": ["r0", "r1", "r3-was-index-3", "r3", "r4"],
}
PAIRING = [("Who", "@who"), ("Y", "@y")]


def _tooltips(chart: sp.Chart) -> list[str]:
    """Every mark's ``<title>``, in document order, without the chart's own trailing one."""
    return re.findall(r"<title>([^<]*)</title>", chart.to_string())[:-1]


def test_a_point_is_named_by_the_row_it_was_drawn_from_not_the_one_beside_it() -> None:
    """The pairing is by original row index, so it survives both ways the two orders differ.

    This is the whole risk in letting ``info=`` speak for a mark. The table's rows and the
    chart's marks come out of one declaration but two traversals, and the traversals disagree
    about order under ``hue=`` and about numbering wherever a row was dropped. Nothing about a
    wrongly paired tooltip looks wrong -- it is a real row of the caller's data, on the wrong
    mark.
    """
    chart = sp.scatterplot(MISALIGNING, x="x", y="y", hue="team", info=PAIRING, tooltip=True)

    assert _tooltips(chart) == [
        "Who: r3 · Y: 40",
        "Who: r4 · Y: 50",
        "Who: r0 · Y: 10",
        "Who: r1 · Y: 20",
    ]


def test_the_table_and_the_tooltips_describe_the_same_rows() -> None:
    """Stated once more without leaning on either order, since that is the claim being made.

    The test above pins the exact sentences, which also pins the draw order; if the palette
    order ever changes it fails for a reason that has nothing to do with pairing. This one
    would survive that and still catch a tooltip pointing at a row the table doesn't hold.
    """
    chart = sp.scatterplot(MISALIGNING, x="x", y="y", hue="team", info=PAIRING, tooltip=True)

    from_marks = {tuple(title.split(" · ")) for title in _tooltips(chart)}
    from_table = {
        tuple(f"{name}: {cell}" for name, cell in zip(("Who", "Y"), row.strip("| ").split(" | "), strict=True))
        for row in _body_rows(chart.to_markdown())
    }

    assert from_marks == from_table


def test_every_drawn_point_has_a_row_in_the_table() -> None:
    """The two filters agree today, and this is what notices if one of them stops agreeing.

    ``collect_label_data`` keeps a row when no required channel ``is_missing``; the point loop
    keeps it when ``numeric_or_none`` returns a number for x, y and size -- which is exactly
    when ``is_missing`` is false. The tooltip falls back to its channel clauses for a point the
    table dropped, so a drift would not crash; it would quietly stop honouring ``info=`` for
    some of the marks. Counting is enough to see it.
    """
    chart = sp.scatterplot(MISALIGNING, x="x", y="y", size="y", hue="team", info=PAIRING, tooltip=True)

    assert len(_tooltips(chart)) == len(_body_rows(chart.to_markdown()))
    assert all(title.startswith("Who: ") for title in _tooltips(chart)), "a point fell back to its channels"


def test_info_replaces_the_channel_clauses_it_would_otherwise_repeat() -> None:
    """``info=`` almost always names the columns the chart is drawn from; saying both is a bug."""
    chart = sp.scatterplot(NUMERIC, x="day", y="sales", info=SPEC, tooltip=True)

    assert _tooltips(chart) == ["Day: 1.0 · Sales: 1,200", "Day: 2.0 · Sales: 3,400", "Day: 3.0 · Sales: 2,500"]
    assert "day: 1" not in chart.to_string(), "the point kept its channel clause as well"


def test_a_slice_keeps_the_shares_info_cannot_hold() -> None:
    """A pie computes two things no column holds, so ``info=`` replaces the row and not those.

    The middle row is dropped for a missing label, which is what makes this a pairing test as
    well: the second slice is the third row, so a slice that asked ``info=`` by its position
    among the slices would answer it with the dropped row's neighbour.
    """
    data = {
        "region": ["동부", None, "서부"],
        "sales": [40.0, 5.0, 60.0],
        "who": ["A팀", "빠진팀", "B팀"],
    }

    chart = sp.pieplot(data, values="sales", labels="region", info=[("팀", "@who")], tooltip=True)

    assert _tooltips(chart) == ["팀: A팀 · 40.0% · 40.0% cumulative", "팀: B팀 · 60.0% · 100.0% cumulative"]


def test_a_hole_is_spelled_the_same_in_the_tooltip_and_in_the_table() -> None:
    """``info=`` may name a column the chart never required, so it may have holes the marks don't."""
    data = {"day": [1.0, 2.0], "sales": [10.0, 20.0], "note": ["첫날", None]}

    chart = sp.scatterplot(data, x="day", y="sales", info=[("메모", "@note")], tooltip=True)

    assert _tooltips(chart) == ["메모: 첫날", "메모: —"]
    assert _body_rows(chart.to_markdown()) == ["| 첫날 |", "| — |"]


def test_an_info_spec_too_long_to_repeat_leaves_the_channel_clauses_alone() -> None:
    """The cap is per mark, and ``info=`` is caller text: an unbounded spec times a thousand
    points is the same failure the label cap was written for, arriving through another door."""
    data = {"day": [1.0], "sales": [10.0], "essay": ["가" * 200]}

    chart = sp.scatterplot(data, x="day", y="sales", info=[("긴", "@essay")], tooltip=True)

    assert _tooltips(chart) == ["day: 1 · sales: 10"]
    assert "가" * 200 in chart.to_markdown(), "the table is not capped -- only the per-mark copy is"


def test_info_does_not_turn_tooltips_on_by_itself() -> None:
    """Declaring a table is not asking for a title on every mark.

    ``info=`` does move the picture on its own -- it adds the ``aria-describedby`` that points
    at the table, and that was true before a tooltip could read the spec. What must not change
    is the number of elements: ``tooltip=False`` is the default, and one ``<title>`` per mark
    is the cost the default exists to avoid.
    """
    svg = sp.scatterplot(NUMERIC, x="day", y="sales", info=SPEC).to_string()

    assert svg.count("<title>") == 1, "only the chart's own title belongs in a default render"
    assert 'aria-describedby="svgplot-data-table"' in svg, "the table reference is info='s own doing"
