from __future__ import annotations

import pytest

from svgplot._svg import SvgDocument
from svgplot.theme.base import Theme
from svgplot.theme.css import render_theme_style


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
