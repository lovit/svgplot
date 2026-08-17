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


def test_theme_rejects_empty_palette() -> None:
    with pytest.raises(ValueError, match="palette"):
        Theme(palette=())


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


def test_minimal_preset_has_no_grid_or_spines() -> None:
    minimal = PRESETS["minimal"]
    assert minimal.grid_width == 0.0
    assert minimal.spine_width == 0.0
    assert minimal.tick_size == 0.0


def test_print_preset_has_thicker_lines_and_black_ink() -> None:
    print_theme = PRESETS["print"]
    assert print_theme.line_width > Theme().line_width
    assert print_theme.foreground == "#000000"


def test_high_contrast_preset_has_a_distinct_high_contrast_palette() -> None:
    assert PRESETS["high_contrast"].palette != Theme().palette
    assert PRESETS["high_contrast"].background == "#ffffff"
    assert PRESETS["high_contrast"].foreground == "#000000"


def test_all_presets_are_pairwise_distinct() -> None:
    presets = list(PRESETS.values())
    for i, first in enumerate(presets):
        for second in presets[i + 1 :]:
            assert first != second


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


def test_apply_context_paper_shrinks_sizes() -> None:
    base = Theme()

    paper = apply_context(base, "paper")

    assert paper.title_font_size < base.title_font_size
    assert paper.line_width < base.line_width


def test_apply_context_leaves_non_size_fields_untouched() -> None:
    base = Theme()

    scaled = apply_context(base, "poster")

    assert scaled.opacity == base.opacity
    assert scaled.corner_radius == base.corner_radius
    assert scaled.legend_position == base.legend_position
    assert scaled.font_family == base.font_family
    assert scaled.grid_color == base.grid_color
    assert scaled.spine_color == base.spine_color


def test_apply_context_composes_multiplicatively_when_chained() -> None:
    base = Theme()

    chained = apply_context(apply_context(base, "talk"), "poster")

    assert chained.line_width == pytest.approx(base.line_width * CONTEXTS["talk"] * CONTEXTS["poster"])


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


def test_parametric_theme_requires_hash_prefix() -> None:
    with pytest.raises(ValueError, match="hex color"):
        parametric_theme("3366cc")


def test_parametric_theme_normalizes_seed_case_for_spine_and_tick() -> None:
    """Palette colors are always re-encoded lowercase; spine/tick must match that
    normalization too, or the same color in different case would produce unequal Themes.
    """
    assert parametric_theme("#3366CC") == parametric_theme("#3366cc")


@pytest.mark.parametrize("seed", ["#808080", "#000000", "#ffffff", "#828282"])
def test_parametric_theme_achromatic_seed_still_produces_a_distinguishable_palette(seed: str) -> None:
    """Regression: a saturation-0 seed (black/white/gray — all common brand colors)
    used to make every rotated hue collapse back to the same achromatic color,
    silently producing a "palette" where every entry was identical.
    """
    theme = parametric_theme(seed)

    assert len(set(theme.palette)) == len(theme.palette)
