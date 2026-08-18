from __future__ import annotations

import re

import pytest

from svgplot.chart.composition import CAPTION_HEIGHT, TITLE_HEIGHT, Composition, chart_document
from svgplot.charts.line import lineplot
from svgplot.layout.caption import add_caption
from svgplot.layout.grid import column, grid, row
from svgplot.layout.sizing import SIZE_MODES, apply_size

DATA = {"x": [1, 2, 3], "y": [1.0, 2.0, 3.0]}
HUE_DATA = {"x": [1, 2, 3, 1, 2, 3], "y": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0], "g": ["a", "a", "a", "b", "b", "b"]}
CHART_WIDTH = 800.0
CHART_HEIGHT = 600.0
SPACING = 12.0


def make_chart(theme: str | None = None):
    return lineplot(DATA, x="x", y="y", theme=theme)


def root_size(svg: str) -> tuple[float, float]:
    root = re.match(r"<svg[^>]*>", svg).group(0)
    match = re.search(r'width="([\d.]+)" height="([\d.]+)"', root)
    return float(match.group(1)), float(match.group(2))


def nested_rects(svg: str) -> list[tuple[float, float, float, float]]:
    """(x, y, width, height) of every placed child, in document order."""
    return [
        (float(x), float(y), float(w), float(h))
        for x, y, w, h in re.findall(r'<svg x="([\d.-]+)" y="([\d.-]+)" width="([\d.]+)" height="([\d.]+)"', svg)
    ]


def style_blocks(svg: str) -> list[str]:
    return re.findall(r"<style>(.*?)</style>", svg, re.S)


# ---------------------------------------------------------------------------
# CSS class namespacing — the correctness core of composing standalone charts
# ---------------------------------------------------------------------------


def test_composed_children_keep_their_own_theme_colors() -> None:
    """Every chart emits the same class names (``.plot-background``, ``.series-1``,
    ...) because ``semantic_class`` restarts per document, and CSS classes ignore
    nested-<svg> boundaries. Without per-child namespacing the second child's
    <style> would restyle the first child's marks, so a light+dark pair would
    render in one theme. Each child must keep its own colors.
    """
    light, dark = make_chart("light"), make_chart("dark")
    light_bg = "#ffffff"
    dark_bg = "#1e1e1e"

    svg = row([light, dark]).to_string(pretty=False)

    rules = "\n".join(style_blocks(svg))
    assert f".c0-plot-background {{ fill: {light_bg}; }}" in rules
    assert f".c1-plot-background {{ fill: {dark_bg}; }}" in rules
    # ...and no rule may address the bare class, which would hit both children.
    assert ".plot-background {" not in rules


def test_composed_children_elements_carry_namespaced_classes() -> None:
    svg = row([make_chart(), make_chart()]).to_string(pretty=False)

    classes = {name for attribute in re.findall(r'class="([^"]+)"', svg) for name in attribute.split()}

    assert any(name.startswith("c0-") for name in classes)
    assert any(name.startswith("c1-") for name in classes)
    assert not any(name.startswith("series-") or name in {"plot-background", "grid-line"} for name in classes)


def test_no_child_style_rule_escapes_its_namespace() -> None:
    """Rules for classes no element currently uses (theme/css.py emits
    ``.series-N-marker`` speculatively) must be namespaced too — an un-prefixed
    rule stays document-global and silently collides once some chart type starts
    using that class.
    """
    svg = row([lineplot(HUE_DATA, x="x", y="y", hue="g"), make_chart()]).to_string(pretty=False)

    for block in style_blocks(svg):
        for line in block.splitlines():
            if line.startswith("."):
                assert re.match(r"\.(c\d+-|composition-)", line), f"un-namespaced rule leaked: {line!r}"


def test_composing_a_chart_does_not_mutate_it() -> None:
    chart = make_chart()
    before = chart.to_string(pretty=False)

    row([chart, make_chart()])

    assert chart.to_string(pretty=False) == before


# ---------------------------------------------------------------------------
# row / column
# ---------------------------------------------------------------------------


def test_row_places_charts_side_by_side_with_spacing() -> None:
    svg = row([make_chart(), make_chart()], spacing=int(SPACING)).to_string(pretty=False)

    rects = nested_rects(svg)
    assert [rect[0] for rect in rects] == [0.0, CHART_WIDTH + SPACING]
    assert {rect[1] for rect in rects} == {0.0}
    assert root_size(svg) == (CHART_WIDTH * 2 + SPACING, CHART_HEIGHT)


def test_column_stacks_charts_with_spacing() -> None:
    svg = column([make_chart(), make_chart()], spacing=int(SPACING)).to_string(pretty=False)

    rects = nested_rects(svg)
    assert [rect[1] for rect in rects] == [0.0, CHART_HEIGHT + SPACING]
    assert {rect[0] for rect in rects} == {0.0}
    assert root_size(svg) == (CHART_WIDTH, CHART_HEIGHT * 2 + SPACING)


def test_row_none_entry_occupies_its_slot() -> None:
    """Bokeh's None-blank idiom: the gap is a real cell, so the following chart
    keeps its column position rather than sliding left.
    """
    svg = row([make_chart(), None, make_chart()]).to_string(pretty=False)

    rects = nested_rects(svg)
    assert len(rects) == 2
    assert [rect[0] for rect in rects] == [0.0, (CHART_WIDTH + SPACING) * 2]
    assert root_size(svg)[0] == CHART_WIDTH * 3 + SPACING * 2


def test_row_with_a_single_chart_matches_that_chart_size() -> None:
    svg = row([make_chart()]).to_string(pretty=False)

    assert root_size(svg) == (CHART_WIDTH, CHART_HEIGHT)
    assert nested_rects(svg) == [(0.0, 0.0, CHART_WIDTH, CHART_HEIGHT)]


def test_row_rejects_an_empty_list() -> None:
    with pytest.raises(ValueError, match="at least one cell"):
        row([])


def test_column_rejects_an_empty_list() -> None:
    with pytest.raises(ValueError, match="at least one cell"):
        column([])


def test_row_rejects_all_none_cells() -> None:
    with pytest.raises(ValueError, match="at least one non-None chart"):
        row([None, None])


def test_grid_rejects_negative_spacing() -> None:
    with pytest.raises(ValueError, match="spacing must be non-negative"):
        row([make_chart()], spacing=-1)


# ---------------------------------------------------------------------------
# grid — matrix form
# ---------------------------------------------------------------------------


def test_grid_matrix_lays_out_rows_and_columns() -> None:
    svg = grid([[make_chart(), make_chart()], [None, make_chart()]]).to_string(pretty=False)

    rects = nested_rects(svg)
    assert [(rect[0], rect[1]) for rect in rects] == [
        (0.0, 0.0),
        (CHART_WIDTH + SPACING, 0.0),
        (CHART_WIDTH + SPACING, CHART_HEIGHT + SPACING),
    ]
    assert root_size(svg) == (CHART_WIDTH * 2 + SPACING, CHART_HEIGHT * 2 + SPACING)


def test_grid_matrix_pads_short_rows_to_ncols() -> None:
    svg = grid([[make_chart(), make_chart()], [make_chart()]], ncols=2).to_string(pretty=False)

    assert root_size(svg)[0] == CHART_WIDTH * 2 + SPACING
    assert len(nested_rects(svg)) == 3


def test_grid_matrix_rejects_ncols_smaller_than_a_row() -> None:
    with pytest.raises(ValueError, match="too small"):
        grid([[make_chart(), make_chart()]], ncols=1)


def test_grid_rejects_empty_cells() -> None:
    with pytest.raises(ValueError, match="at least one cell"):
        grid([])


# ---------------------------------------------------------------------------
# grid — (chart, row, col, rowspan, colspan) tuple form
# ---------------------------------------------------------------------------


def test_grid_tuple_form_supports_spans() -> None:
    """The spanning chart covers both columns plus the spacing between them."""
    svg = grid([(make_chart(), 0, 0, 1, 2), (make_chart(), 1, 0, 1, 1), (make_chart(), 1, 1, 1, 1)]).to_string(pretty=False)

    rects = nested_rects(svg)
    assert rects[0] == (0.0, 0.0, CHART_WIDTH * 2 + SPACING, CHART_HEIGHT)
    assert rects[1] == (0.0, CHART_HEIGHT + SPACING, CHART_WIDTH, CHART_HEIGHT)
    assert rects[2] == (CHART_WIDTH + SPACING, CHART_HEIGHT + SPACING, CHART_WIDTH, CHART_HEIGHT)


def test_grid_tuple_form_supports_rowspan() -> None:
    svg = grid([(make_chart(), 0, 0, 2, 1), (make_chart(), 0, 1, 1, 1), (make_chart(), 1, 1, 1, 1)]).to_string(pretty=False)

    rects = nested_rects(svg)
    assert rects[0][3] == CHART_HEIGHT * 2 + SPACING


def test_grid_tuple_form_rejects_overlapping_cells() -> None:
    with pytest.raises(ValueError, match="overlap"):
        grid([(make_chart(), 0, 0, 1, 2), (make_chart(), 0, 1, 1, 1)])


def test_grid_tuple_form_rejects_negative_position() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        grid([(make_chart(), -1, 0, 1, 1)])


def test_grid_tuple_form_rejects_non_positive_span() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        grid([(make_chart(), 0, 0, 1, 0)])


def test_grid_tuple_form_rejects_a_malformed_tuple() -> None:
    with pytest.raises(ValueError, match="must be"):
        grid([(make_chart(), 0, 0)])


def test_grid_tuple_form_rejects_ncols_smaller_than_needed() -> None:
    with pytest.raises(ValueError, match="too small"):
        grid([(make_chart(), 0, 0, 1, 3)], ncols=2)


# ---------------------------------------------------------------------------
# titles (Tabs replacement)
# ---------------------------------------------------------------------------


def test_column_titles_render_above_each_chart() -> None:
    svg = column([make_chart(), make_chart()], titles=["연도별", "지역별"]).to_string(pretty=False)

    assert re.findall(r'class="composition-title">([^<]*)', svg) == ["연도별", "지역별"]
    # Each chart is pushed down by its title band.
    assert [rect[1] for rect in nested_rects(svg)] == [TITLE_HEIGHT, TITLE_HEIGHT * 2 + CHART_HEIGHT + SPACING]


def test_titles_expand_the_canvas_by_one_band_per_titled_row() -> None:
    plain = root_size(column([make_chart(), make_chart()]).to_string(pretty=False))
    titled = root_size(column([make_chart(), make_chart()], titles=["A", "B"]).to_string(pretty=False))

    assert titled[1] == plain[1] + TITLE_HEIGHT * 2


def test_titles_are_escaped_not_injected() -> None:
    svg = column([make_chart()], titles=["<script>alert(1)</script>"]).to_string(pretty=False)

    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg


def test_titles_length_must_match_cell_count() -> None:
    with pytest.raises(ValueError, match="one entry per cell"):
        column([make_chart(), make_chart()], titles=["only one"])


# ---------------------------------------------------------------------------
# caption
# ---------------------------------------------------------------------------


def test_add_caption_below_grows_the_canvas_and_leaves_children_in_place() -> None:
    composition = row([make_chart()])
    before_rects = nested_rects(composition.to_string(pretty=False))

    svg = add_caption(composition, "Figure 3. 분기별 매출 추이").to_string(pretty=False)

    assert root_size(svg) == (CHART_WIDTH, CHART_HEIGHT + CAPTION_HEIGHT)
    assert nested_rects(svg) == before_rects
    assert "Figure 3. 분기별 매출 추이" in svg


def test_add_caption_above_shifts_children_down() -> None:
    composition = row([make_chart()])
    before_rects = nested_rects(composition.to_string(pretty=False))

    svg = add_caption(composition, "위 캡션", location="above").to_string(pretty=False)

    assert root_size(svg) == (CHART_WIDTH, CHART_HEIGHT + CAPTION_HEIGHT)
    assert [rect[1] for rect in nested_rects(svg)] == [rect[1] + CAPTION_HEIGHT for rect in before_rects]


def test_add_caption_above_also_shifts_titles() -> None:
    composition = column([make_chart()], titles=["소제목"])
    before = float(re.search(r'class="composition-title"[^>]*/?>', composition.to_string(pretty=False)) is not None)
    assert before == 1.0

    svg = add_caption(composition, "캡션", location="above").to_string(pretty=False)

    title_y = float(re.search(r'<text x="[\d.]+" y="([\d.]+)" class="composition-title"', svg).group(1))
    caption_y = float(re.search(r'y="([\d.]+)" text-anchor="middle" class="composition-caption"', svg).group(1))
    assert caption_y < title_y


def test_add_caption_rejects_an_unknown_location() -> None:
    with pytest.raises(ValueError, match="location must be"):
        add_caption(row([make_chart()]), "text", location="sideways")


def test_add_caption_rejects_empty_text() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        add_caption(row([make_chart()]), "   ")


def test_add_caption_escapes_its_text() -> None:
    svg = add_caption(row([make_chart()]), "<script>alert(1)</script>").to_string(pretty=False)

    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg


# ---------------------------------------------------------------------------
# sizing
# ---------------------------------------------------------------------------


def test_apply_size_fixed_sets_explicit_dimensions_without_viewbox() -> None:
    svg = apply_size(make_chart(), "fixed").to_string(pretty=False)

    root = re.match(r"<svg[^>]*>", svg).group(0)
    assert 'width="800"' in root
    assert 'height="600"' in root
    assert "viewBox" not in root


def test_apply_size_responsive_keeps_viewbox_and_attaches_the_scaling_class() -> None:
    svg = apply_size(make_chart(), "responsive").to_string(pretty=False)

    root = re.match(r"<svg[^>]*>", svg).group(0)
    assert 'viewBox="0 0 800 600"' in root
    assert "svgplot-responsive" in root
    assert ".svgplot-responsive { max-width: 100%; height: auto; }" in svg


def test_apply_size_returns_the_same_chart_for_chaining() -> None:
    chart = make_chart()
    assert apply_size(chart, "responsive") is chart


def test_apply_size_round_trips_between_modes() -> None:
    chart = make_chart()

    apply_size(chart, "responsive")
    apply_size(chart, "fixed")
    root = re.match(r"<svg[^>]*>", chart.to_string(pretty=False)).group(0)

    assert "viewBox" not in root
    assert "svgplot-responsive" not in root


def test_apply_size_responsive_is_idempotent() -> None:
    chart = make_chart()

    apply_size(chart, "responsive")
    apply_size(chart, "responsive")
    svg = chart.to_string(pretty=False)

    assert svg.count("max-width: 100%") == 1
    assert re.match(r"<svg[^>]*>", svg).group(0).count("svgplot-responsive") == 1


def test_apply_size_rejects_an_unknown_mode() -> None:
    with pytest.raises(ValueError, match="mode must be one of"):
        apply_size(make_chart(), "stretch_both")


def test_size_modes_are_the_two_documented_options() -> None:
    assert SIZE_MODES == ("fixed", "responsive")


# ---------------------------------------------------------------------------
# Composition — same serialization surface as Chart
# ---------------------------------------------------------------------------


def test_composition_to_string_pretty_and_compact() -> None:
    composition = row([make_chart()])

    pretty = composition.to_string()
    compact = composition.to_string(pretty=False)

    assert pretty.startswith("<?xml")
    assert "\n" in pretty
    assert not compact.startswith("<?xml")


def test_composition_repr_svg_matches_compact_output() -> None:
    composition = row([make_chart()])

    assert composition._repr_svg_() == composition.to_string(pretty=False)


def test_composition_save_writes_an_svg_file(tmp_path) -> None:
    path = tmp_path / "figure.svg"

    row([make_chart(), make_chart()]).save(str(path))

    assert path.read_text(encoding="utf-8").startswith("<?xml")


def test_composition_save_rejects_an_unsupported_extension(tmp_path) -> None:
    with pytest.raises(ValueError, match="unsupported file extension"):
        row([make_chart()]).save(str(tmp_path / "figure.gif"))


def test_composition_exposes_its_children() -> None:
    first, second = make_chart(), make_chart()

    composition = row([first, second])

    assert composition.charts == [first, second]


def test_composition_charts_property_returns_a_copy() -> None:
    composition = row([make_chart()])

    composition.charts.append(make_chart())

    assert len(composition.charts) == 1


def test_layout_functions_return_a_composition() -> None:
    assert isinstance(row([make_chart()]), Composition)
    assert isinstance(column([make_chart()]), Composition)
    assert isinstance(grid([[make_chart()]]), Composition)


def test_nested_children_keep_their_own_viewbox() -> None:
    """A child placed into a differently-sized cell must still map its internal
    coordinates through its own viewBox, or a spanning chart would draw at the
    wrong scale.
    """
    svg = grid([(make_chart(), 0, 0, 1, 2), (make_chart(), 1, 0, 1, 1)]).to_string(pretty=False)

    nested = re.findall(r"<svg x=\"[\d.]+\"[^>]*>", svg)
    assert all('viewBox="0 0 800 600"' in tag for tag in nested)


def test_compose_restores_viewbox_for_a_fixed_sized_child() -> None:
    """apply_size(..., "fixed") strips viewBox, but nesting scales a child to its
    cell only via viewBox — without one the child keeps its intrinsic coordinates
    and is clipped whenever the cell is smaller. Composition restores it so the two
    features don't silently interact (review finding, PR #46).
    """
    fixed_chart = apply_size(make_chart(), "fixed")
    assert "viewBox" not in chart_document(fixed_chart).root.attrib

    svg = row([fixed_chart, make_chart()]).to_string()

    nested = re.findall(r"<svg ([^>]*\bx=[^>]*)>", svg)
    assert nested, "expected nested child <svg> elements"
    assert all("viewBox" in attrs for attrs in nested)
