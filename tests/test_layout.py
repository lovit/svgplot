from __future__ import annotations

import re

import pytest

from svgplot.chart.base import Chart
from svgplot.chart.composition import (
    CAPTION_HEIGHT,
    TITLE_HEIGHT,
    Composition,
    chart_document,
    composition_document,
    composition_title,
)
from svgplot.charts.bar import barplot
from svgplot.charts.line import lineplot
from svgplot.layout.caption import add_caption
from svgplot.layout.facet import facet
from svgplot.layout.grid import column, grid, row
from svgplot.layout.sizing import SIZE_MODES, apply_size

DATA = {"x": [1, 2, 3], "y": [1.0, 2.0, 3.0]}
HUE_DATA = {"x": [1, 2, 3, 1, 2, 3], "y": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0], "g": ["a", "a", "a", "b", "b", "b"]}
CHART_WIDTH = 800.0
CHART_HEIGHT = 600.0
SPACING = 12.0


def make_chart(theme: str | None = None):
    return lineplot(DATA, x="x", y="y", theme=theme)


FACET_DATA = {
    "x": [1, 2, 1, 2, 1, 2],
    "y": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
    "c": ["L", "L", "R", "R", "R", "R"],
    "r": ["top", "top", "top", "top", "bot", "bot"],
}
"""Three of four (row, col) facet combinations — the ``(bot, L)`` cell renders blank.
Used by the accessibility tests to check that a blank cell is neither announced as a
panel nor given accessibility markup of its own."""


def describe(svg: str) -> str:
    """The text of the composition's ``<desc>`` element."""
    return re.search(r"<desc>([^<]*)</desc>", svg).group(1)


def accessible_name(svg: str) -> str:
    """The rendered ``aria-label`` — the name assistive tech actually announces."""
    return re.search(r'\baria-label="([^"]*)"', svg).group(1)


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


# ---------------------------------------------------------------------------
# accessibility (issue #55)
# ---------------------------------------------------------------------------


def test_composition_carries_accessibility_defaults_without_any_setup() -> None:
    svg = row([make_chart(), make_chart()]).to_string()

    assert 'role="img"' in svg
    assert f'aria-label="{Composition.DEFAULT_TITLE}"' in svg
    assert f"<title>{Composition.DEFAULT_TITLE}</title>" in svg
    assert "<desc>" in svg


def test_composition_children_do_not_carry_their_own_accessibility() -> None:
    """A composed figure must announce one name, not one per panel. Children are
    nested from chart_document() — the charts' raw documents, before Chart's own
    accessibility pass — so exactly one role/title/desc should exist in the output.
    """
    svg = grid([[make_chart(), make_chart()], [make_chart(), None]]).to_string()

    assert svg.count('role="img"') == 1
    assert svg.count("<title>") == 1
    assert svg.count("<desc>") == 1


def test_composition_default_name_differs_from_a_single_charts() -> None:
    """A screen-reader user should be able to tell a multi-panel figure from a single
    chart without exploring it.

    Compares the two *rendered* names rather than the two class constants: asserting
    ``Composition.DEFAULT_TITLE != Chart.DEFAULT_TITLE`` would keep passing even if a
    render path stopped reading its constant altogether, which is the regression that
    actually matters here.
    """
    composed = accessible_name(row([make_chart(), make_chart()]).to_string())
    single = accessible_name(make_chart().to_string())

    assert composed == Composition.DEFAULT_TITLE
    assert single == Chart.DEFAULT_TITLE
    assert composed != single


def test_add_caption_becomes_the_accessible_name() -> None:
    """A caption is the figure's name — announcing the generic default while a visible
    caption reads "Figure 3. ..." would be strictly worse."""
    composition = add_caption(row([make_chart(), make_chart()]), "Figure 3. Quarterly revenue")

    svg = composition.to_string()
    assert 'aria-label="Figure 3. Quarterly revenue"' in svg
    assert "<title>Figure 3. Quarterly revenue</title>" in svg


def test_an_explicit_set_title_wins_over_a_later_caption() -> None:
    composition = row([make_chart(), make_chart()]).set_title("Explicit name")

    add_caption(composition, "Some caption")

    assert 'aria-label="Explicit name"' in composition.to_string()


def test_repeated_composition_renders_do_not_stack_title_and_desc() -> None:
    composition = row([make_chart(), make_chart()])

    composition.to_string()
    composition._repr_svg_()
    svg = composition.to_string()

    assert svg.count("<title>") == 1
    assert svg.count("<desc>") == 1


def test_composition_rendering_leaves_its_own_document_untouched() -> None:
    composition = row([make_chart(), make_chart()])

    composition.to_string()

    assert "<title>" not in composition_document(composition).to_string()


def test_a_blank_composition_title_falls_back_to_the_default() -> None:
    svg = row([make_chart(), make_chart()]).set_title("   ").to_string()

    assert f'aria-label="{Composition.DEFAULT_TITLE}"' in svg


def test_saved_composition_file_also_carries_accessibility(tmp_path) -> None:
    target = tmp_path / "figure.svg"

    row([make_chart(), make_chart()]).set_title("Saved figure").save(str(target))

    written = target.read_text(encoding="utf-8")
    assert 'role="img"' in written
    assert "<title>Saved figure</title>" in written


def test_column_carries_one_accessible_name_too() -> None:
    """Issue #55's AC names row/column/grid/facet; ``column`` is a distinct entry point."""
    svg = column([make_chart(), make_chart()]).to_string()

    assert svg.count('role="img"') == 1
    assert f'aria-label="{Composition.DEFAULT_TITLE}"' in svg
    assert svg.count("<title>") == 1


def test_facet_output_carries_one_accessible_name() -> None:
    """``facet`` is the only entry point that generates blank cells on its own, so it is
    the likeliest place for a per-panel accessibility regression to appear.
    """
    svg = facet(lineplot, FACET_DATA, col="c", row="r", x="x", y="y").to_string()

    assert svg.count('role="img"') == 1
    assert svg.count("<title>") == 1
    assert svg.count("<desc>") == 1


def test_blank_cells_are_not_announced_as_charts() -> None:
    """``FACET_DATA`` fills three of four (row, col) cells, so the fourth renders blank.
    The description must count placed charts, not grid cells — telling a screen-reader
    user there are four panels when one is empty sends them hunting for a panel that
    isn't there.
    """
    assert describe(facet(lineplot, FACET_DATA, col="c", row="r", x="x", y="y").to_string()) == (
        "A figure composed of 3 charts."
    )
    assert describe(grid([[make_chart(), make_chart()], [make_chart(), None]]).to_string()) == (
        "A figure composed of 3 charts."
    )


def test_a_one_chart_composition_is_described_in_the_singular() -> None:
    """``row([chart])`` is legal, and "composed of 1 charts" is read aloud verbatim."""
    assert describe(row([make_chart()]).to_string()) == "A figure composed of 1 chart."


def test_a_whitespace_only_title_does_not_block_caption_adoption() -> None:
    """``set_title("   ")`` falls back to the default at render time, so it must also
    read as unset when ``add_caption`` decides whether to adopt its text. If the two
    disagreed, this figure would show the caption while announcing the generic default.
    """
    composition = row([make_chart(), make_chart()]).set_title("   ")

    add_caption(composition, "Figure 3. Quarterly revenue")

    assert 'aria-label="Figure 3. Quarterly revenue"' in composition.to_string()


def test_a_set_title_after_a_caption_still_wins() -> None:
    """The other precedence order: an explicit name overrides an already-adopted caption."""
    composition = add_caption(row([make_chart(), make_chart()]), "Some caption")

    composition.set_title("Explicit name")

    assert 'aria-label="Explicit name"' in composition.to_string()


def test_a_second_caption_does_not_rename_the_figure() -> None:
    """Both caption bands render, but the first stays the figure's name — a later band
    adds to the figure rather than correcting what it is called.
    """
    composition = add_caption(row([make_chart(), make_chart()]), "First caption")

    add_caption(composition, "Second caption", location="above")

    svg = composition.to_string()
    assert "First caption" in svg
    assert "Second caption" in svg
    assert 'aria-label="First caption"' in svg


def test_a_caption_is_escaped_before_it_reaches_the_accessible_name() -> None:
    """Captions are caller input and land in both an attribute and element text."""
    svg = add_caption(row([make_chart(), make_chart()]), "</title><script>alert(1)</script>").to_string()

    assert "<script>" not in svg
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in svg


def test_a_title_cannot_break_out_of_the_aria_label_attribute() -> None:
    """``aria-label`` is an attribute-context sink this feature newly introduces, so it
    needs pinning separately from the element-text case above.
    """
    svg = row([make_chart(), make_chart()]).set_title('" onload="alert(1)').to_string()

    assert 'onload="alert(1)"' not in svg
    assert accessible_name(svg) == "&quot; onload=&quot;alert(1)"


def test_an_xml_illegal_title_is_rejected_rather_than_corrupting_the_output() -> None:
    """A character XML 1.0 forbids must fail loudly at render time. Silently dropping it
    would emit an SVG that no parser accepts, which is worse than an exception.
    """
    composition = row([make_chart(), make_chart()]).set_title("bad\x00title")

    with pytest.raises(ValueError, match="XML 1.0"):
        composition.to_string()


def test_the_png_branch_also_writes_the_accessible_document(monkeypatch, tmp_path) -> None:
    """``save`` builds the accessible document once and hands it to whichever writer the
    extension selects. The ``.svg`` test can't catch a ``.png`` branch that passed
    ``self._svg_document`` instead, since the two are separate lines. Spying on the
    writer keeps this runnable whether or not cairosvg is installed.
    """
    captured: dict[str, str] = {}

    def spy(document, path: str) -> None:
        captured["svg"] = document.to_string()

    monkeypatch.setattr("svgplot.chart.composition.to_png", spy)

    row([make_chart(), make_chart()]).set_title("PNG figure").save(str(tmp_path / "figure.png"))

    assert 'role="img"' in captured["svg"]
    assert "<title>PNG figure</title>" in captured["svg"]


# ---------------------------------------------------------------------------
# a rejected caption leaves nothing behind (issue #58)
# ---------------------------------------------------------------------------


def _caption_state(composition: Composition) -> tuple[float, str | None, str | None, list[str | None]]:
    """Everything ``add_caption`` would mutate, as one comparable snapshot."""
    document = composition_document(composition)
    return (
        document.height,
        document.root.get("height"),
        document.root.get("viewBox"),
        [element.get("y") for element in document.root if element.tag in ("svg", "text")],
    )


def _one_chart_composition() -> Composition:
    return row([barplot({"x": ["a"], "y": [1.0]}, x="x", y="y")])


@pytest.mark.parametrize("location", ["below", "above"])
def test_a_rejected_caption_does_not_resize_the_canvas(location: str) -> None:
    """Every mutation in ``add_caption`` used to run before the text was validated, so a
    caption holding a character XML forbids raised *and* left the figure permanently
    taller with nothing in the new band."""
    composition = _one_chart_composition()
    before = _caption_state(composition)

    with pytest.raises(ValueError, match="not allowed in XML"):
        add_caption(composition, "bad\x00caption", location=location)

    assert _caption_state(composition) == before


def test_a_rejected_caption_does_not_shift_the_children() -> None:
    """``location="above"`` moves every child down before writing the text, so a rejected
    caption slid the charts off their own layout."""
    composition = _one_chart_composition()
    before = _caption_state(composition)[3]

    with pytest.raises(ValueError):
        add_caption(composition, "bad\x00caption", location="above")

    assert _caption_state(composition)[3] == before


@pytest.mark.parametrize("location", ["below", "above"])
def test_repeated_rejections_do_not_accumulate(location: str) -> None:
    """The failure mode a user actually hits: fix the caption, try again, and find the
    figure has grown by a band for every earlier attempt."""
    composition = _one_chart_composition()
    before = _caption_state(composition)

    for _ in range(3):
        with pytest.raises(ValueError):
            add_caption(composition, "bad\x00caption", location=location)

    assert _caption_state(composition) == before


def test_a_rejected_caption_does_not_become_the_accessible_name() -> None:
    composition = _one_chart_composition()

    with pytest.raises(ValueError):
        add_caption(composition, "bad\x00caption")

    assert composition_title(composition) is None


@pytest.mark.parametrize("location", ["below", "above"])
def test_a_good_caption_still_applies_after_a_rejected_one(location: str) -> None:
    """The point of leaving the document untouched: the retry has to behave exactly as if
    the bad attempt never happened."""
    failed = _one_chart_composition()
    with pytest.raises(ValueError):
        add_caption(failed, "bad\x00caption", location=location)
    add_caption(failed, "good caption", location=location)

    clean = _one_chart_composition()
    add_caption(clean, "good caption", location=location)

    assert failed.to_string() == clean.to_string()
