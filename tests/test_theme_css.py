from __future__ import annotations

import pytest

from svgplot._svg import SvgDocument
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style
from svgplot.theme.presets import PRESETS


def _style_text(document: SvgDocument) -> str:
    style_nodes = document.root.findall("style")
    assert len(style_nodes) == 1
    return style_nodes[0].text or ""


def test_render_theme_style_emits_one_style_element() -> None:
    document = SvgDocument()
    render_theme_style(document, Theme(), ["series-1"])
    style_nodes = document.root.findall("style")
    assert len(style_nodes) == 1


def test_render_theme_style_includes_static_element_rules() -> None:
    document = SvgDocument()
    render_theme_style(document, Theme(), [])
    css = _style_text(document)
    assert ".plot-background" in css
    assert ".grid-line" in css
    assert ".spine" in css
    assert ".tick-line" in css
    assert ".tick-label" in css
    assert ".legend-text" in css


def test_render_theme_style_colors_each_series_from_the_palette_cycling() -> None:
    theme = Theme(palette=("#111111", "#222222"))
    document = SvgDocument()
    render_theme_style(document, theme, ["series-1", "series-2", "series-3"])
    css = _style_text(document)
    assert ".series-1 { stroke: #111111;" in css
    assert ".series-2 { stroke: #222222;" in css
    assert ".series-3 { stroke: #111111;" in css  # cycles back to the first palette entry


def test_render_theme_style_deduplicates_repeated_series_classes() -> None:
    document = SvgDocument()
    render_theme_style(document, Theme(), ["series-1", "series-1"])
    css = _style_text(document)
    assert css.count(".series-1 {") == 1


@pytest.mark.parametrize("field", ["background", "foreground", "grid_color", "spine_color", "tick_color"])
def test_render_theme_style_rejects_css_breakout_attempt_in_color_field(field: str) -> None:
    """A color field containing CSS-breaking characters must be rejected outright,
    not silently interpolated into the <style> block's text.
    """
    malicious = "x} body{background:red} .y{color:red"
    theme = Theme(**{field: malicious})
    document = SvgDocument()
    with pytest.raises(ValueError, match="rrggbb"):
        render_theme_style(document, theme, [])


def test_render_theme_style_rejects_css_breakout_attempt_in_palette_entry() -> None:
    theme = Theme(palette=("} body{background:red} .x{color:red",))
    document = SvgDocument()
    with pytest.raises(ValueError, match="rrggbb"):
        render_theme_style(document, theme, ["series-1"])


def test_render_theme_style_rejects_css_breakout_attempt_in_font_family() -> None:
    theme = Theme(font_family="Arial}} body{background:red} .x{color:red")
    document = SvgDocument()
    with pytest.raises(ValueError, match="font_family"):
        render_theme_style(document, theme, [])


def test_render_theme_style_rejects_css_breakout_attempt_in_series_class_name() -> None:
    document = SvgDocument()
    with pytest.raises(ValueError, match="series class name"):
        render_theme_style(document, Theme(), ["x{}body{background:red}.y"])


def test_render_theme_style_rejects_non_finite_numeric_field() -> None:
    theme = Theme(line_width=float("nan"))
    document = SvgDocument()
    with pytest.raises(ValueError, match="finite"):
        render_theme_style(document, theme, ["series-1"])


def test_render_theme_style_accepts_valid_hex_colors_case_insensitively() -> None:
    theme = Theme(background="#ABCDEF")
    document = SvgDocument()
    render_theme_style(document, theme, [])
    assert "#ABCDEF" in _style_text(document)


def test_render_theme_style_stroke_mark_style_is_the_default_and_emits_a_marker_rule() -> None:
    theme = Theme(palette=("#111111",))
    document = SvgDocument()
    render_theme_style(document, theme, ["series-1"])
    css = _style_text(document)
    assert ".series-1 { stroke: #111111; fill: none;" in css
    assert ".series-1-marker { fill: #111111; stroke: none; }" in css


def test_render_theme_style_fill_mark_style_sets_fill_and_emits_no_marker_rule() -> None:
    """A future fill-based chart type (bar/area/pie) reuses this same shared
    infrastructure — see charts/_legend.py's matching mark_style parameter.
    """
    theme = Theme(palette=("#111111",))
    document = SvgDocument()
    render_theme_style(document, theme, ["series-1"], mark_style="fill")
    css = _style_text(document)
    assert ".series-1 { fill: #111111; stroke: none;" in css
    assert "-marker" not in css


def test_render_theme_style_rejects_unknown_mark_style() -> None:
    document = SvgDocument()
    with pytest.raises(ValueError, match="mark_style"):
        render_theme_style(document, Theme(), ["series-1"], mark_style="bogus")


def test_render_theme_style_rejects_font_family_with_unterminated_quote() -> None:
    """An odd number of "'" can't inject a new CSS rule (the character-set allow-list
    already blocks "{"/"}"/";"/":" ), but it does leave a CSS string literal
    unterminated, corrupting every rule after it in the <style> block.
    """
    theme = Theme(font_family="Arial'")
    document = SvgDocument()
    with pytest.raises(ValueError, match="unterminated quote"):
        render_theme_style(document, theme, [])


def test_render_theme_style_accepts_font_family_with_balanced_quotes() -> None:
    theme = Theme(font_family="'Helvetica Neue', Arial")
    document = SvgDocument()
    render_theme_style(document, theme, [])
    assert "'Helvetica Neue', Arial" in _style_text(document)


# ---------------------------------------------------------------------------
# fill_opacity (issue #45)
# ---------------------------------------------------------------------------


def _fill_style_text(theme: Theme, mark_style: str = "fill") -> str:
    document = SvgDocument()
    render_theme_style(document, theme, ["series-1"], mark_style=mark_style)
    return next(element.text or "" for element in document.root if element.tag == "style")


def test_fill_marks_are_translucent_by_default_so_overlaps_stay_visible() -> None:
    """Unstacked multi-hue fills are drawn in sorted-label order, unrelated to value
    magnitude, so an opaque later series can hide an earlier one entirely (issue #45).
    The default must therefore be below 1.0.
    """
    assert "opacity: 0.75; }" in _fill_style_text(Theme())


def test_stroke_marks_keep_full_opacity() -> None:
    """fill_opacity narrows to fills only — a stroked line doesn't occlude what's
    beneath it, so it must not be dimmed by the fill-specific factor.
    """
    assert "opacity: 1; }" in _fill_style_text(Theme(), mark_style="stroke")


def test_fill_opacity_multiplies_with_the_whole_mark_opacity() -> None:
    """The two are independent knobs that compose: `opacity` dims every mark type,
    `fill_opacity` narrows to fills. 0.5 * 0.5 = 0.25.
    """
    assert "opacity: 0.25; }" in _fill_style_text(Theme(opacity=0.5, fill_opacity=0.5))


def test_fill_opacity_can_be_opted_out_without_touching_stroke_marks() -> None:
    """Opting out must leave `opacity` still in effect — asserting only "opacity: 1"
    would pass even with fill_opacity deleted entirely, so this pins a theme where the
    two factors differ: opting out of the fill factor alone yields plain 0.5, not 0.375.
    """
    assert "opacity: 0.5; }" in _fill_style_text(Theme(opacity=0.5, fill_opacity=1.0))


@pytest.mark.parametrize("preset", ["print", "high_contrast"])
def test_presets_that_need_solid_fills_opt_out_of_translucency(preset: str) -> None:
    """print reproduces blended translucency unreliably and high_contrast exists to
    maximize figure/ground contrast, so both deliberately override to 1.0 — pinned here
    because nothing else would catch the override being silently dropped.
    """
    assert PRESETS[preset].fill_opacity == 1.0
    assert "opacity: 1; }" in _fill_style_text(PRESETS[preset])


def test_default_presets_keep_translucent_fills() -> None:
    assert PRESETS["light"].fill_opacity == 0.75


@pytest.mark.parametrize("bad", [5.0, -0.1, float("nan"), float("inf"), True, "0.5"])
def test_theme_rejects_an_out_of_range_or_non_numeric_fill_opacity(bad: object) -> None:
    """Validated on the Theme rather than at CSS-emission time: a finite-but-nonsense
    value like 5.0 passes format_coord's finiteness check and would emit invalid CSS,
    surfacing at render time far from the Theme that caused it.
    """
    with pytest.raises(ValueError, match="fill_opacity"):
        Theme(fill_opacity=bad)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# mark_style="outlined" and level_colors (issue #62)
# ---------------------------------------------------------------------------


def _series_rules(css: str, class_name: str = "series-1") -> list[str]:
    """Only the rules for one class — the shared base rules (.plot-background etc.)
    are asserted elsewhere and would drown out what these tests are about."""
    return [line for line in css.splitlines() if line.startswith(f".{class_name} ")]


def test_outlined_marks_carry_both_a_stroke_and_a_translucent_fill() -> None:
    """Neither existing mark_style can express this: "stroke" forces `fill: none` and
    "fill" forces `stroke: none`, so a bounded-and-filled shape (violin body, filled
    KDE, treemap tile, radar polygon, gauge arc) had no representation at all.
    """
    (rule,) = _series_rules(_fill_style_text(Theme(), mark_style="outlined"))

    assert "stroke: #E69F00;" in rule
    assert "fill: #E69F00;" in rule
    assert "fill-opacity: 0.75;" in rule


def test_outlined_keeps_the_stroke_opaque_while_softening_only_the_interior() -> None:
    """The stroke is the shape's boundary and must stay at theme.opacity; only the
    interior takes the fill factor. Pre-multiplying the two into one `opacity` would
    fade the outline too, losing the boundary that makes the mark "outlined".
    """
    (rule,) = _series_rules(_fill_style_text(Theme(opacity=0.5, fill_opacity=0.4), mark_style="outlined"))

    assert "opacity: 0.5;" in rule
    assert "fill-opacity: 0.4;" in rule
    assert "opacity: 0.2;" not in rule  # the pre-multiplied product must not appear


def test_outlined_emits_no_marker_companion_rule() -> None:
    """Unlike "stroke", an outlined mark already fills itself — a separate `-marker`
    fill rule would be dead CSS."""
    css = _fill_style_text(Theme(), mark_style="outlined")

    assert "-marker" not in css


def test_render_theme_style_rejects_an_unknown_mark_style() -> None:
    document = SvgDocument()

    with pytest.raises(ValueError, match="mark_style"):
        render_theme_style(document, Theme(), ["series-1"], mark_style="dotted")


def test_level_colors_emit_one_rule_per_class_from_the_given_color() -> None:
    """A heatmap cell's color comes from its value, not from a palette cycle position,
    so the caller supplies the color explicitly rather than by index."""
    document = SvgDocument()
    render_theme_style(document, Theme(), [], level_colors={"level-1": "#08519c", "level-2": "#6baed6"})
    css = _style_text(document)

    assert ".level-1 { fill: #08519c; stroke: none; opacity: 1; }" in css
    assert ".level-2 { fill: #6baed6; stroke: none; opacity: 1; }" in css


def test_level_colors_are_not_dimmed_by_fill_opacity() -> None:
    """A level color *is* the data encoding — blending the background into it reports a
    different value for every cell, uniformly enough that the distortion is invisible.
    fill_opacity exists to stop overlapping marks occluding each other; tiled cells
    never had that problem. Pinned against the CSS text because a regression here is
    silently wrong output rather than an error.
    """
    document = SvgDocument()
    render_theme_style(document, Theme(opacity=0.8, fill_opacity=0.5), [], level_colors={"level-1": "#08519c"})

    (rule,) = _series_rules(_style_text(document), "level-1")
    assert "opacity: 0.8;" in rule
    assert "opacity: 0.4;" not in rule  # 0.8 * 0.5, the product used by mark_style="fill"


def test_level_colors_work_alongside_palette_colored_series() -> None:
    document = SvgDocument()
    render_theme_style(document, Theme(), ["series-1"], mark_style="fill", level_colors={"level-1": "#08519c"})
    css = _style_text(document)

    assert _series_rules(css, "series-1")
    assert _series_rules(css, "level-1")


def test_a_class_in_both_series_and_level_colors_is_rejected() -> None:
    """Two rules for one class would leave the winner decided by emission order — a
    silent, position-dependent override rather than a visible error."""
    document = SvgDocument()

    with pytest.raises(ValueError, match="both series_classes and level_colors"):
        render_theme_style(document, Theme(), ["series-1"], level_colors={"series-1": "#08519c"})


@pytest.mark.parametrize("bad_key", ["level}1", "level 1", ".level-1", "1level", "level{}x", ""])
def test_level_colors_reject_a_css_unsafe_class_name(bad_key: str) -> None:
    """Same breakout vector as an unvalidated series class: _svg.py's XML-only class
    validation permits `{`/`}`/`;`, which are CSS-unsafe."""
    document = SvgDocument()

    with pytest.raises(ValueError, match="class name"):
        render_theme_style(document, Theme(), [], level_colors={bad_key: "#08519c"})


@pytest.mark.parametrize("bad_color", ["red", "#08519", "#08519cc", "} body { background: red", 42, None])
def test_level_colors_reject_a_non_hex_color(bad_color: object) -> None:
    document = SvgDocument()

    with pytest.raises(ValueError, match="level_colors"):
        render_theme_style(document, Theme(), [], level_colors={"level-1": bad_color})  # type: ignore[dict-item]


def test_level_rules_survive_composition_namespacing() -> None:
    """The whole reason level colors go through CSS classes rather than a `fill=`
    presentation attribute: composition rewrites child selectors so two charts can't
    cross-theme each other. A `fill=` attribute would be invisible to that rewrite and
    would silently mis-theme a composed pair.
    """
    from svgplot.chart.base import Chart
    from svgplot.chart.composition import Placement, compose

    document = SvgDocument(width=100, height=100)
    document.add_node(None, "rect", attrib={"x": 0, "y": 0, "width": 10, "height": 10}, classes=["level-1"])
    render_theme_style(document, Theme(), [], level_colors={"level-1": "#08519c"})

    composed = compose([Placement(Chart(document), x=0, y=0, width=100, height=100)], width=100, height=100)
    svg = composed.to_string()

    assert ".c0-level-1 {" in svg
    assert 'class="c0-level-1"' in svg
    assert ".level-1 {" not in svg


@pytest.mark.parametrize("mark_style", ["stroke", "fill", "outlined"])
def test_level_rules_are_identical_regardless_of_mark_style(mark_style: str) -> None:
    """Level rules are mark_style-independent by design — a value-encoding mark is a
    filled region, and an outline would read as a second visual channel carrying no
    data. Pinned across all three styles because five downstream charts will read this
    contract, and `outlined` + `level_colors` silently producing un-outlined marks
    would look like a bug rather than the intended behavior.
    """
    document = SvgDocument()
    render_theme_style(document, Theme(), ["series-1"], mark_style=mark_style, level_colors={"level-1": "#08519c"})
    css = next(element.text or "" for element in document.root if element.tag == "style")

    level_rule = next(line for line in css.split("\n") if line.startswith(".level-1 "))
    assert level_rule == ".level-1 { fill: #08519c; stroke: none; opacity: 1; }"


# ---------------------------------------------------------------------------
# ink_colors (issue #74 review)
# ---------------------------------------------------------------------------


def test_ink_colors_emit_fill_and_nothing_else() -> None:
    """An ink colour is chosen *against* the mark it sits on, so anything that blends it
    back toward that mark undoes the choice. ``opacity`` is the reason this parameter is
    separate from ``level_colors`` at all; ``stroke`` matters for a different reason -- SVG
    text defaults to ``stroke: none``, so setting one puts a visible outline on every
    glyph. Neither was pinned, and both mutations passed the whole suite."""
    document = SvgDocument()

    render_theme_style(document, Theme(opacity=0.4), [], ink_colors={"level-1-annotation": "#000000"})
    rule = next(line for line in _style_text(document).splitlines() if line.startswith(".level-1-annotation"))

    assert rule == ".level-1-annotation { fill: #000000; }"


def test_ink_colors_are_independent_of_mark_style() -> None:
    """Ink is text, not a mark, so none of the three mark styles has anything to say
    about it."""
    rules = []
    for mark_style in ("stroke", "fill", "outlined"):
        document = SvgDocument()
        render_theme_style(document, Theme(), ["series-1"], mark_style=mark_style, ink_colors={"ink-1": "#ffffff"})
        rules.append(next(line for line in _style_text(document).splitlines() if line.startswith(".ink-1")))

    assert len(set(rules)) == 1


@pytest.mark.parametrize("other", ["series_classes", "level_colors"])
def test_a_class_in_both_ink_colors_and_another_mapping_is_rejected(other: str) -> None:
    """Two rules for one class leave the winner decided by emission order. Downgrading this
    to a skip is worse than it sounds: the ink is what silently disappears, and the level
    colour then paints the glyphs the same colour as the cell behind them."""
    document = SvgDocument()
    kwargs: dict[str, object] = {"level_colors": {"shared": "#08519c"}} if other == "level_colors" else {}
    series = ["shared"] if other == "series_classes" else []

    with pytest.raises(ValueError, match="appears in both ink_colors and another color mapping"):
        render_theme_style(document, Theme(), series, ink_colors={"shared": "#000000"}, **kwargs)


@pytest.mark.parametrize("bad_key", ["x{}body{background:red}.y", "has space", "1leading-digit", ""])
def test_ink_colors_reject_a_css_unsafe_class_name(bad_key: str) -> None:
    """Caller-controlled just like ``level_colors``' keys, so it needs the same rejection --
    ``_svg``'s XML validation permits characters that break out of a CSS rule."""
    document = SvgDocument()

    with pytest.raises(ValueError, match="ink class name must match"):
        render_theme_style(document, Theme(), [], ink_colors={bad_key: "#000000"})


@pytest.mark.parametrize("bad_color", ["red", "#fff", "#0085 19c", "rgb(0,0,0)", None])
def test_ink_colors_reject_a_color_that_is_not_strict_hex(bad_color: object) -> None:
    document = SvgDocument()

    with pytest.raises(ValueError, match="ink_colors"):
        render_theme_style(document, Theme(), [], ink_colors={"ink-1": bad_color})  # type: ignore[dict-item]


def test_omitting_ink_colors_emits_no_extra_rules() -> None:
    """Every existing caller passes nothing, and their output has to be byte-identical."""
    without, with_none = SvgDocument(), SvgDocument()

    render_theme_style(without, Theme(), ["series-1"], mark_style="fill")
    render_theme_style(with_none, Theme(), ["series-1"], mark_style="fill", ink_colors=None)

    assert _style_text(without) == _style_text(with_none)
