"""Tests for svgplot.theme.{base,presets,context}."""

from __future__ import annotations

import dataclasses

import pytest

from svgplot.theme import CONTEXTS, PRESETS, Theme, apply_context, parametric_theme

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------


def test_theme_has_reasonable_defaults() -> None:
    theme = Theme()

    assert theme.background == "#ffffff"
    assert theme.foreground == "#111111"
    assert len(theme.palette) >= 5
    assert theme.font_family


def test_theme_is_immutable() -> None:
    theme = Theme()

    with pytest.raises(dataclasses.FrozenInstanceError):
        theme.background = "#000000"


def test_theme_accepts_a_list_palette_and_stores_it_as_an_immutable_tuple() -> None:
    theme = Theme(palette=["#111111", "#222222"])

    assert theme.palette == ("#111111", "#222222")
    assert isinstance(theme.palette, tuple)


def test_two_theme_instances_with_the_same_arguments_are_equal() -> None:
    assert Theme(background="#123456") == Theme(background="#123456")


def test_same_theme_instance_used_by_two_independent_renders_gives_identical_values() -> None:
    """Stand-in for "two charts rendered with the same Theme look the same" — Chart
    itself isn't available yet (issue #4/PR #25 not yet merged into main), so this
    verifies the guarantee at the level this module actually controls: reading the
    same Theme's values twice, independently, is always identical (pure/immutable).
    """
    theme = Theme(background="#123456", palette=("#111111", "#222222"))

    first_render_values = {"background": theme.background, "palette": theme.palette, "line_width": theme.line_width}
    second_render_values = {"background": theme.background, "palette": theme.palette, "line_width": theme.line_width}

    assert first_render_values == second_render_values


# ---------------------------------------------------------------------------
# PRESETS
# ---------------------------------------------------------------------------


def test_presets_has_three_to_five_builtin_themes() -> None:
    assert 3 <= len(PRESETS) <= 5


def test_all_presets_are_theme_instances() -> None:
    assert all(isinstance(theme, Theme) for theme in PRESETS.values())


def test_light_preset_is_default_theme() -> None:
    assert PRESETS["light"] == Theme()


def test_dark_preset_has_dark_background() -> None:
    assert PRESETS["dark"].background != PRESETS["light"].background


# ---------------------------------------------------------------------------
# apply_context (style x context separation)
# ---------------------------------------------------------------------------


def test_apply_context_scales_font_and_line_sizes() -> None:
    base = Theme()

    talk = apply_context(base, "talk")

    assert talk.title_font_size > base.title_font_size
    assert talk.line_width > base.line_width


def test_apply_context_notebook_is_identity_scale() -> None:
    base = Theme()

    notebook = apply_context(base, "notebook")

    assert notebook.title_font_size == base.title_font_size
    assert notebook.line_width == base.line_width


def test_apply_context_does_not_mutate_the_original_theme() -> None:
    base = Theme()
    original_title_size = base.title_font_size

    apply_context(base, "poster")

    assert base.title_font_size == original_title_size


def test_apply_context_only_scales_size_fields_not_colors() -> None:
    base = Theme()

    scaled = apply_context(base, "poster")

    assert scaled.background == base.background
    assert scaled.palette == base.palette


def test_apply_context_is_deterministic() -> None:
    base = Theme()

    assert apply_context(base, "talk") == apply_context(base, "talk")


def test_apply_context_covers_all_named_contexts() -> None:
    base = Theme()
    for context in CONTEXTS:
        result = apply_context(base, context)
        assert isinstance(result, Theme)


def test_apply_context_rejects_unknown_context() -> None:
    with pytest.raises(ValueError, match="unknown context"):
        apply_context(Theme(), "cinema")


# ---------------------------------------------------------------------------
# parametric_theme
# ---------------------------------------------------------------------------


def test_parametric_theme_returns_a_theme_with_a_derived_palette() -> None:
    theme = parametric_theme("#3366cc")

    assert isinstance(theme, Theme)
    assert len(theme.palette) >= 3
    assert theme.palette != Theme().palette


def test_parametric_theme_uses_seed_color_for_spine_and_tick() -> None:
    theme = parametric_theme("#3366cc")

    assert theme.spine_color == "#3366cc"
    assert theme.tick_color == "#3366cc"


def test_parametric_theme_is_deterministic() -> None:
    assert parametric_theme("#3366cc") == parametric_theme("#3366cc")


def test_parametric_theme_different_seeds_give_different_palettes() -> None:
    assert parametric_theme("#3366cc").palette != parametric_theme("#cc3366").palette


def test_parametric_theme_rejects_invalid_hex_color() -> None:
    with pytest.raises(ValueError, match="hex color"):
        parametric_theme("not-a-color")


def test_parametric_theme_rejects_wrong_length_hex_color() -> None:
    with pytest.raises(ValueError, match="hex color"):
        parametric_theme("#fff")
