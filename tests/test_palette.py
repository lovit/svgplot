"""Tests for svgplot.palette.{qualitative,sequential,minilang,colorblind}."""

from __future__ import annotations

import pytest

from svgplot.palette import (
    BLOCKED_PALETTES,
    DEFAULT_PALETTE,
    QUALITATIVE_PALETTES,
    SEQUENTIAL_PALETTES,
    is_colorblind_safe,
    parse_palette_spec,
    qualitative,
    sequential,
)

# ---------------------------------------------------------------------------
# colorblind.py — DEFAULT_PALETTE / BLOCKED_PALETTES / is_colorblind_safe
# ---------------------------------------------------------------------------


def test_default_palette_is_colorblind_safe_okabe_ito() -> None:
    assert len(DEFAULT_PALETTE) >= 6
    assert all(color.startswith("#") and len(color) == 7 for color in DEFAULT_PALETTE)


def test_is_colorblind_safe_true_for_default_palette() -> None:
    assert is_colorblind_safe("colorblind") is True


def test_is_colorblind_safe_false_for_unknown_or_blocked_name() -> None:
    assert is_colorblind_safe("jet") is False
    assert is_colorblind_safe("nonexistent") is False


def test_jet_and_friends_are_blocked() -> None:
    assert "jet" in BLOCKED_PALETTES


# ---------------------------------------------------------------------------
# qualitative.py
# ---------------------------------------------------------------------------


def test_qualitative_returns_n_colors_from_named_palette() -> None:
    colors = qualitative("colorblind", 3)

    assert colors == DEFAULT_PALETTE[:3]


def test_qualitative_default_palette_matches_default_palette_constant() -> None:
    assert qualitative("colorblind", len(DEFAULT_PALETTE)) == DEFAULT_PALETTE


def test_qualitative_cycles_when_n_exceeds_palette_size() -> None:
    base = QUALITATIVE_PALETTES["dark"]
    colors = qualitative("dark", len(base) + 2)

    assert len(colors) == len(base) + 2
    assert colors[: len(base)] == base
    assert colors[len(base)] == base[0]
    assert colors[len(base) + 1] == base[1]


def test_qualitative_rejects_blocked_palette() -> None:
    with pytest.raises(ValueError, match="blocked"):
        qualitative("jet", 5)


def test_qualitative_rejects_unknown_palette() -> None:
    with pytest.raises(KeyError):
        qualitative("nonexistent", 5)


def test_qualitative_rejects_negative_n() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        qualitative("colorblind", -1)


def test_qualitative_zero_n_returns_empty_list() -> None:
    assert qualitative("colorblind", 0) == []


# ---------------------------------------------------------------------------
# sequential.py
# ---------------------------------------------------------------------------


def test_sequential_returns_n_colors() -> None:
    colors = sequential("blues", 5)

    assert len(colors) == 5
    assert all(color.startswith("#") and len(color) == 7 for color in colors)


def test_sequential_is_monotonically_darkening() -> None:
    """light_dark_sequence ramps from a light anchor toward the (darker) seed."""
    colors = sequential("blues", 4)

    def luminance(hex_color: str) -> int:
        return int(hex_color[1:3], 16) + int(hex_color[3:5], 16) + int(hex_color[5:7], 16)

    luminances = [luminance(color) for color in colors]
    assert luminances == sorted(luminances, reverse=True)


def test_sequential_rejects_blocked_palette() -> None:
    with pytest.raises(ValueError, match="blocked"):
        sequential("jet", 5)


def test_sequential_rejects_unknown_palette() -> None:
    with pytest.raises(KeyError):
        sequential("nonexistent", 5)


def test_sequential_rejects_negative_n() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        sequential("blues", -1)


def test_sequential_zero_n_returns_empty_list() -> None:
    assert sequential("blues", 0) == []


def test_sequential_single_color_does_not_crash() -> None:
    assert len(sequential("blues", 1)) == 1


def test_all_registered_sequential_palettes_work() -> None:
    for name in SEQUENTIAL_PALETTES:
        assert len(sequential(name, 4)) == 4


# ---------------------------------------------------------------------------
# minilang.py — parse_palette_spec
# ---------------------------------------------------------------------------


def test_parse_light_spec() -> None:
    colors = parse_palette_spec("light:#3366cc")

    assert len(colors) == 6
    assert all(color.startswith("#") and len(color) == 7 for color in colors)


def test_parse_dark_spec() -> None:
    colors = parse_palette_spec("dark:#3366cc")

    assert len(colors) == 6


def test_light_and_dark_specs_differ() -> None:
    assert parse_palette_spec("light:#3366cc") != parse_palette_spec("dark:#3366cc")


def test_parse_light_spec_rejects_invalid_color() -> None:
    with pytest.raises(ValueError, match="light:"):
        parse_palette_spec("light:not-a-color")


def test_parse_dark_spec_rejects_missing_argument() -> None:
    with pytest.raises(ValueError, match="dark:"):
        parse_palette_spec("dark:")


def test_parse_blend_spec() -> None:
    colors = parse_palette_spec("blend:#3366cc,#cc3366")

    assert len(colors) == 6
    assert colors[0] == "#3366cc"
    assert colors[-1] == "#cc3366"


def test_parse_blend_spec_rejects_wrong_argument_count() -> None:
    with pytest.raises(ValueError, match="blend:"):
        parse_palette_spec("blend:#3366cc")


def test_parse_blend_spec_rejects_invalid_color() -> None:
    with pytest.raises(ValueError, match="blend:"):
        parse_palette_spec("blend:#3366cc,not-a-color")


def test_parse_cubehelix_spec_keyword_form() -> None:
    colors = parse_palette_spec("ch:s=.25,r=-.5")

    assert len(colors) == 6
    assert all(color.startswith("#") and len(color) == 7 for color in colors)


def test_parse_cubehelix_spec_positional_form() -> None:
    colors = parse_palette_spec("ch:0.25,-0.5")

    assert len(colors) == 6


def test_parse_cubehelix_keyword_and_positional_forms_match() -> None:
    assert parse_palette_spec("ch:s=0.25,r=-0.5") == parse_palette_spec("ch:0.25,-0.5")


def test_parse_cubehelix_spec_rejects_unknown_parameter() -> None:
    with pytest.raises(ValueError, match="unknown ch"):
        parse_palette_spec("ch:x=1")


def test_parse_cubehelix_spec_rejects_malformed_value() -> None:
    with pytest.raises(ValueError, match="invalid ch"):
        parse_palette_spec("ch:s=abc")


def test_parse_cubehelix_spec_rejects_too_many_positional_params() -> None:
    with pytest.raises(ValueError, match="too many positional"):
        parse_palette_spec("ch:0.1,0.2,0.3")


def test_parse_cubehelix_spec_rejects_empty() -> None:
    with pytest.raises(ValueError, match="ch:"):
        parse_palette_spec("ch:")


def test_parse_bare_name_falls_back_to_qualitative() -> None:
    assert parse_palette_spec("colorblind") == qualitative("colorblind", 6)


def test_parse_bare_blocked_name_raises() -> None:
    with pytest.raises(ValueError, match="blocked"):
        parse_palette_spec("jet")


def test_parse_bare_unknown_name_raises() -> None:
    with pytest.raises(KeyError):
        parse_palette_spec("totally-unknown-palette")
