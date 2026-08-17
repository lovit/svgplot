"""Tests for svgplot.palette.{qualitative,sequential,minilang,colorblind}."""

from __future__ import annotations

import time

import pytest

from svgplot.palette import (
    BLOCKED_PALETTES,
    DEFAULT_PALETTE,
    QUALITATIVE_PALETTES,
    SEQUENTIAL_PALETTES,
    diverging,
    is_colorblind_safe,
    parse_palette_spec,
    qualitative,
    sequential,
)
from svgplot.palette._color import rgb01_to_hex
from svgplot.palette.sequential import blend_sequence, cubehelix_sequence

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


def test_parse_bare_name_that_collides_with_a_reserved_prefix_still_falls_back() -> None:
    """Regression: "dark" (no colon) used to be misrouted to the dark: prefix handler
    (str.partition on a colon-less string still fills `prefix` with the whole string),
    making the registered "dark" qualitative palette unreachable through this entry point.
    """
    assert parse_palette_spec("dark") == qualitative("dark", 6)


def test_parse_bare_name_matching_a_reserved_prefix_but_unregistered_raises_key_error() -> None:
    """ "light" isn't a registered qualitative palette, but the point is it must fail
    via the qualitative-name fallback (KeyError), not get misrouted to the light:
    prefix handler and fail on a missing hex argument (ValueError) instead.
    """
    with pytest.raises(KeyError):
        parse_palette_spec("light")


def test_parse_light_spec_with_extra_colon_is_rejected() -> None:
    with pytest.raises(ValueError, match="light:"):
        parse_palette_spec("light:#3366cc:extra")


def test_parse_cubehelix_spec_allows_whitespace_around_commas() -> None:
    assert parse_palette_spec("ch: s=.25 , r=-.5 ") == parse_palette_spec("ch:s=.25,r=-.5")


def test_parse_cubehelix_spec_rejects_duplicate_keyword_parameter() -> None:
    with pytest.raises(ValueError, match="more than once"):
        parse_palette_spec("ch:s=.1,s=.2")


def test_parse_cubehelix_spec_positional_fills_slot_not_claimed_by_keyword() -> None:
    """Regression: a positional token used to always fill 'start' first regardless of
    which slots a preceding keyword token had already claimed, silently overwriting
    an explicitly-given value (e.g. "ch:s=0.5,0.3" used to discard the 0.3 into
    `start`, clobbering the explicit s=0.5, instead of filling the remaining `rot`).
    """
    assert parse_palette_spec("ch:s=0.5,0.3") == parse_palette_spec("ch:s=0.5,r=0.3")


def test_parse_cubehelix_spec_rejects_positional_after_both_slots_already_claimed() -> None:
    """Once both start/rot are claimed by keyword tokens, a further positional token
    has nowhere left to go — this used to instead silently overwrite `start` with 3.
    """
    with pytest.raises(ValueError, match="too many positional"):
        parse_palette_spec("ch:s=1,r=2,3")


def test_parse_cubehelix_spec_rejects_implausibly_long_input_via_length_cap() -> None:
    """This specific input is caught by the spec-length cap before parsing ever starts
    (a genuine parameter-magnitude overflow needs many more digits than the cap allows —
    see test_cubehelix_sequence_rejects_out_of_range_parameters for that path instead).
    """
    with pytest.raises(ValueError, match="too long"):
        parse_palette_spec("ch:s=" + "9" * 300)


def test_parse_spec_rejects_non_string() -> None:
    with pytest.raises(ValueError, match="string"):
        parse_palette_spec(None)  # type: ignore[arg-type]


def test_parse_spec_rejects_implausibly_long_input() -> None:
    with pytest.raises(ValueError, match="too long"):
        parse_palette_spec("ch:s=" + "9" * 100_000)


def test_parse_cubehelix_regex_does_not_exhibit_catastrophic_backtracking() -> None:
    """Regression: the value pattern's dot placement made a long run of digits
    followed by one invalid character take O(n^2) to reject (~21s for 100KB input);
    it must now reject in well under a second (the length cap alone should catch
    this, but this pins the underlying regex fix too via a still-under-the-cap input).
    """
    start_time = time.monotonic()
    with pytest.raises(ValueError):
        parse_palette_spec("ch:s=" + "9" * 200 + "x")
    assert time.monotonic() - start_time < 1.0


def test_cubehelix_sequence_rejects_non_finite_parameters() -> None:
    with pytest.raises(ValueError, match="finite"):
        cubehelix_sequence(6, hue=float("inf"))
    with pytest.raises(ValueError, match="finite"):
        cubehelix_sequence(6, gamma=float("nan"))


def test_qualitative_rejects_non_string_name() -> None:
    with pytest.raises(ValueError, match="string"):
        qualitative(["colorblind"], 3)  # type: ignore[arg-type]


def test_sequential_rejects_non_string_name() -> None:
    with pytest.raises(ValueError, match="string"):
        sequential(["blues"], 3)  # type: ignore[arg-type]


def test_blocked_palettes_is_immutable() -> None:
    with pytest.raises(AttributeError):
        BLOCKED_PALETTES.add("colorblind")  # type: ignore[attr-defined]


def test_rgb01_to_hex_rejects_non_finite_channel() -> None:
    with pytest.raises(ValueError, match="finite"):
        rgb01_to_hex((float("nan"), 0.5, 0.5))
    with pytest.raises(ValueError, match="finite"):
        rgb01_to_hex((0.5, float("inf"), 0.5))


def test_rgb01_to_hex_clamps_extreme_but_finite_channels_instead_of_overflowing() -> None:
    """Regression: clamping happened after round(channel * 255) — the multiplication
    itself could overflow to inf for a finite-but-huge channel (e.g. 1e306), raising a
    raw OverflowError. Clamping before the multiplication closes that gap structurally.
    """
    assert rgb01_to_hex((1e306, 0.0, 0.0)) == "#ff0000"
    assert rgb01_to_hex((-1e306, 0.0, 0.0)) == "#000000"


def test_cubehelix_sequence_rejects_out_of_range_parameters() -> None:
    """A merely-finite start/rot/gamma/hue isn't automatically safe: gamma feeds
    x**gamma (can overflow for large negative exponents even with finite x), and
    start/rot feed a sum inside math.cos/math.sin (that sum can itself overflow to
    inf even with both addends finite, then math.cos(inf) raises its own unrelated
    "math domain error"). These used to leak OverflowError/an opaque ValueError;
    now they're all rejected with a message naming the actual out-of-range parameter.
    """
    with pytest.raises(ValueError, match="hue"):
        cubehelix_sequence(6, hue=1e308)
    with pytest.raises(ValueError, match="gamma"):
        cubehelix_sequence(6, gamma=-1e308)
    with pytest.raises(ValueError, match="gamma"):
        cubehelix_sequence(6, gamma=0)
    with pytest.raises(ValueError, match="start"):
        cubehelix_sequence(6, start=1e308, rot=1e308)


def test_is_colorblind_safe_returns_false_for_non_string_instead_of_raising() -> None:
    assert is_colorblind_safe(["colorblind"]) is False  # type: ignore[arg-type]


def test_blend_sequence_and_cubehelix_sequence_handle_n_equals_one() -> None:
    assert blend_sequence("#3366cc", "#cc3366", 1) == ["#3366cc"]
    assert len(cubehelix_sequence(1)) == 1


def test_diverging_is_still_an_unimplemented_stub() -> None:
    with pytest.raises(NotImplementedError):
        diverging("RdBu", 5)
