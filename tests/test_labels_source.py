from __future__ import annotations

import re

import pytest

from svgplot.charts.line import lineplot
from svgplot.charts.pie import pieplot
from svgplot.charts.scatter import scatterplot
from svgplot.labels._source import collect_label_data
from svgplot.labels.spec import LabelSpec
from svgplot.labels.table import MISSING_TEXT, render_table

# One row is dropped for each distinct reason a chart drops rows: a missing x, a missing
# y, and a missing hue. `note` additionally has a hole in a *surviving* row, which is the
# case that must be kept rather than dropped.
MIXED = {
    "x": [1.0, None, 3.0, 4.0, 5.0, 6.0],
    "y": [2.0, 2.0, None, 4.0, 5.0, 6.0],
    "g": ["a", "a", "a", None, "b", "b"],
    "note": ["p", "q", "r", "s", None, "u"],
}
SPEC = LabelSpec.parse([("X", "@x{0.0}"), ("Note", "@note{%s}")])


def _marker_count(svg: str) -> int:
    return len(re.findall(r"<circle\b", svg))


def _vertex_count(svg: str) -> int:
    return sum(len(re.findall(r"[ML] ", path)) for path in re.findall(r'd="([^"]+)"', svg))


# ---------------------------------------------------------------------------
# row selection agrees with what the charts actually draw
# ---------------------------------------------------------------------------


def test_row_selection_matches_what_scatterplot_draws() -> None:
    """The whole point of reusing ``is_missing``: the table must not claim a row the
    chart never plotted, nor omit one it did."""
    data = collect_label_data(MIXED, SPEC, required=("x", "y"))

    assert len(data) == _marker_count(scatterplot(MIXED, x="x", y="y").to_string())


def test_row_selection_matches_what_scatterplot_draws_with_a_hue() -> None:
    """A missing hue drops a row too, so the required channels have to include it."""
    data = collect_label_data(MIXED, SPEC, required=("x", "y", "g"))

    assert len(data) == _marker_count(scatterplot(MIXED, x="x", y="y", hue="g").to_string())


def test_row_selection_matches_what_lineplot_draws() -> None:
    data = collect_label_data(MIXED, SPEC, required=("x", "y", "g"))

    assert len(data) == _vertex_count(lineplot(MIXED, x="x", y="y", hue="g").to_string())


def test_row_selection_matches_what_pieplot_draws() -> None:
    pie_data = {"v": [1.0, None, 3.0], "l": ["a", "b", None]}
    spec = LabelSpec.parse([("V", "@v{0.0}")])
    data = collect_label_data(pie_data, spec, required=("v", "l"))

    slices = len(re.findall(r"<path\b", pieplot(pie_data, values="v", labels="l").to_string()))
    assert len(data) == slices


def test_dropping_is_driven_by_the_required_channels_not_by_every_column() -> None:
    """``note`` has a hole in a row every *channel* fills. Dropping that row would
    silently shrink the table because of a column the chart never consulted."""
    data = collect_label_data(MIXED, SPEC, required=("x", "y"))

    assert data.columns["note"] == ["p", "s", None, "u"]


def test_nan_counts_as_missing_alongside_none() -> None:
    """``is_missing`` treats NaN and ``None`` alike; so must row selection, or a NaN row
    would appear in the table while the chart skipped it."""
    data = {"x": [1.0, float("nan"), 3.0], "y": [1.0, 2.0, 3.0]}
    spec = LabelSpec.parse([("X", "@x{0.0}")])

    assert len(collect_label_data(data, spec, required=("x", "y"))) == 2


# ---------------------------------------------------------------------------
# snapshot shape
# ---------------------------------------------------------------------------


def test_rows_keep_input_order() -> None:
    """Not plot order: ``lineplot`` sorts by x, but a table is a lookup keyed by value,
    and reordering it to match would also group-order it whenever ``hue`` is set."""
    unsorted = {"x": [9.0, 1.0, 5.0], "y": [1.0, 2.0, 3.0]}
    spec = LabelSpec.parse([("X", "@x{0.0}")])

    assert collect_label_data(unsorted, spec, required=("x", "y")).columns["x"] == [9.0, 1.0, 5.0]


def test_snapshot_holds_only_the_spec_fields() -> None:
    """A ``Chart`` keeps this for its lifetime, so it must not pin the caller's whole
    frame -- and a post-plot mutation must not be able to desync the table from the SVG."""
    data = collect_label_data(MIXED, SPEC, required=("x", "y"))

    assert sorted(data.columns) == ["note", "x"]


def test_the_snapshot_does_not_alias_the_caller_s_columns() -> None:
    source = {"x": [1.0, 2.0], "y": [1.0, 2.0]}
    spec = LabelSpec.parse([("X", "@x{0.0}")])
    data = collect_label_data(source, spec, required=("x", "y"))

    source["x"].append(3.0)

    assert data.columns["x"] == [1.0, 2.0]


def test_no_info_means_no_collection() -> None:
    assert collect_label_data(MIXED, None, required=("x", "y")) is None


def test_optional_channels_may_be_none() -> None:
    """Callers pass ``hue=`` straight through, so a ``None`` entry has to be ignored
    rather than looked up as a column named ``None``."""
    data = collect_label_data(MIXED, SPEC, required=("x", "y", None))

    assert len(data) == 4


def test_an_all_missing_channel_yields_an_empty_snapshot() -> None:
    data = {"x": [None, None], "y": [1.0, 2.0]}
    spec = LabelSpec.parse([("X", "@x{0.0}")])
    collected = collect_label_data(data, spec, required=("x", "y"))

    assert len(collected) == 0
    assert collected.columns["x"] == []


# ---------------------------------------------------------------------------
# errors surface at collection time
# ---------------------------------------------------------------------------


def test_an_unknown_spec_field_raises_at_collection_time() -> None:
    """Deferring this to ``save()`` would surface a typo far from the call that made it.

    The message is pinned, not just the exception type: dropping the explicit check would
    still raise ``KeyError`` when the column is finally indexed, but with a bare key and
    no hint that the *spec* is what named it."""
    spec = LabelSpec.parse([("Z", "@nope{%s}")])

    with pytest.raises(KeyError, match="field not found in data"):
        collect_label_data(MIXED, spec, required=("x", "y"))


def test_an_unknown_required_channel_raises_at_collection_time() -> None:
    """Pinned by message for the same reason, and with wording distinct from the spec-field
    case so the two failures stay tellable apart."""
    with pytest.raises(KeyError, match="channel column not found in data"):
        collect_label_data(MIXED, SPEC, required=("x", "not-a-column"))


# ---------------------------------------------------------------------------
# render_table(missing=)
# ---------------------------------------------------------------------------


def test_render_table_still_raises_without_the_opt_in() -> None:
    """The default must stay a refusal: a caller handing this function a table's worth of
    data directly gets told about the hole rather than shown an invented dash."""
    spec = LabelSpec.parse([("A", "@a{%s}")])

    with pytest.raises(ValueError, match="missing"):
        render_table({"a": [None]}, spec)


def test_render_table_substitutes_the_opted_in_text() -> None:
    spec = LabelSpec.parse([("A", "@a{%s}")])

    assert render_table({"a": ["x", None]}, spec, missing=MISSING_TEXT).splitlines()[3] == f"| {MISSING_TEXT} |"


def test_the_substitute_is_escaped_like_any_other_cell() -> None:
    """``missing=`` must not become an escaping bypass -- the substitute is produced
    upstream of the renderers so it flows through the same neutralising path. A literal
    ``<script>`` reaching the output would be an XSS vector in the markdown this package
    exists to be embedded in, and a bare ``|`` would desynchronise the table."""
    spec = LabelSpec.parse([("A", "@a{%s}")])

    markdown = render_table({"a": [None]}, spec, missing="<script>|x")
    html_table = render_table({"a": [None]}, spec, format="html", missing="<script>|x")

    assert "<script>" not in markdown
    assert "&lt;script&gt;" in markdown
    assert r"\|" in markdown
    assert "<script>" not in html_table
    assert "&lt;script&gt;" in html_table


def test_a_nan_cell_is_substituted_too() -> None:
    spec = LabelSpec.parse([("A", "@a{0.0}")])

    assert MISSING_TEXT in render_table({"a": [float("nan")]}, spec, missing=MISSING_TEXT)


def test_an_empty_substitute_is_honoured_rather_than_treated_as_absent() -> None:
    """``missing=""`` is a legitimate request for a blank cell. Testing ``if missing:``
    instead of ``if missing is not None:`` would silently fall back to raising."""
    spec = LabelSpec.parse([("A", "@a{%s}")])

    assert render_table({"a": [None]}, spec, missing="").splitlines()[2] == "|  |"
