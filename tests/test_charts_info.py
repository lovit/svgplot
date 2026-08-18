from __future__ import annotations

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


def test_info_does_not_change_the_svg_output() -> None:
    """The table lives beside the chart, never inside it -- adding ``info=`` must not
    move a single coordinate."""
    without = sp.lineplot(NUMERIC, x="day", y="sales").to_string()
    with_info = sp.lineplot(NUMERIC, x="day", y="sales", info=SPEC).to_string()

    assert without == with_info


def test_saving_svg_with_info_is_unchanged(tmp_path: Path) -> None:
    plain, annotated = tmp_path / "a.svg", tmp_path / "b.svg"
    sp.lineplot(NUMERIC, x="day", y="sales").save(str(plain))
    sp.lineplot(NUMERIC, x="day", y="sales", info=SPEC).save(str(annotated))

    assert plain.read_text(encoding="utf-8") == annotated.read_text(encoding="utf-8")


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
