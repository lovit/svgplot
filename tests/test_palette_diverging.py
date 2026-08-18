from __future__ import annotations

import pytest

from svgplot.palette._color import HEX_COLOR_RE
from svgplot.palette.diverging import DIVERGING_PALETTES, diverging, diverging_sequence

# low/high are exact RGB mirrors of the midpoint, which turns "symmetric about the
# midpoint" into a property that can be checked arithmetically: mirrored samples must
# sum to 255 per channel. A registered map can't be used for this — its two extremes are
# different hues on purpose, so only the *interpolation fractions* mirror, not the RGB.
_MIRRORED_TRIPLE = ("#000000", "#808080", "#ffffff")


def _channels(hex_color: str) -> tuple[int, int, int]:
    return tuple(int(hex_color[index : index + 2], 16) for index in (1, 3, 5))  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# counts and endpoints
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n", [2, 3, 4, 5, 6, 7, 8, 9])
def test_returns_exactly_n_hex_colors(n: int) -> None:
    colors = diverging("coolwarm", n)

    assert len(colors) == n
    assert all(HEX_COLOR_RE.fullmatch(color) for color in colors)


def test_zero_returns_no_colors() -> None:
    assert diverging("coolwarm", 0) == []


def test_one_color_is_the_neutral_midpoint() -> None:
    """A lone sample can only be the centre — either extreme would assert a direction the
    caller never chose.
    """
    low, midpoint, high = DIVERGING_PALETTES["coolwarm"]

    (only,) = diverging("coolwarm", 1)

    assert only == midpoint.lower()
    assert only not in {low.lower(), high.lower()}


@pytest.mark.parametrize("n", [2, 3, 4, 5, 8, 9])
def test_the_extremes_are_the_palettes_own_endpoints(n: int) -> None:
    low, _, high = DIVERGING_PALETTES["coolwarm"]

    colors = diverging("coolwarm", n)

    assert colors[0] == low.lower()
    assert colors[-1] == high.lower()


@pytest.mark.parametrize("n", [3, 5, 7, 9])
def test_an_odd_count_puts_the_neutral_midpoint_dead_centre(n: int) -> None:
    _, midpoint, _ = DIVERGING_PALETTES["coolwarm"]

    assert diverging("coolwarm", n)[n // 2] == midpoint.lower()


@pytest.mark.parametrize("n", [2, 4, 6, 8])
def test_an_even_count_has_no_sample_on_the_midpoint(n: int) -> None:
    """There is no centre slot to occupy, so the neutral colour must be absent rather
    than duplicated into one of the two middle slots.
    """
    _, midpoint, _ = DIVERGING_PALETTES["coolwarm"]

    assert midpoint.lower() not in diverging("coolwarm", n)


# ---------------------------------------------------------------------------
# symmetry — the design guarantee
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n", [3, 4, 5, 6, 7, 8, 9])
def test_samples_are_symmetric_about_the_midpoint(n: int) -> None:
    """Both halves come from the same blend_sequence call shape with the same step count,
    so the k-th sample out from the centre sits at an identical interpolation fraction on
    either side. With mirrored endpoints that shows up as channels summing to 255
    (+/-1 for rgb01_to_hex's rounding of an exact .5).
    """
    low, midpoint, high = _MIRRORED_TRIPLE

    colors = diverging_sequence(low, midpoint, high, n)

    for index in range(n):
        near, far = _channels(colors[index]), _channels(colors[n - 1 - index])
        for near_channel, far_channel in zip(near, far, strict=True):
            assert abs(near_channel + far_channel - 255) <= 1


@pytest.mark.parametrize("n", [4, 6, 8])
def test_an_even_count_stays_symmetric_despite_having_no_centre_sample(n: int) -> None:
    """Dropping the centre of the n+1 odd ramp keeps every surviving pair mirrored;
    shifting the two halves instead would not.
    """
    colors = diverging_sequence(*_MIRRORED_TRIPLE, n)

    first, last = _channels(colors[0]), _channels(colors[-1])
    assert abs(first[0] + last[0] - 255) <= 1
    assert colors[n // 2 - 1] != colors[n // 2]


# ---------------------------------------------------------------------------
# error contract (mirrors sequential())
# ---------------------------------------------------------------------------


def test_rejects_a_non_string_name() -> None:
    with pytest.raises(ValueError, match="must be a string"):
        diverging(["coolwarm"], 3)  # type: ignore[arg-type]


@pytest.mark.parametrize("blocked", ["jet", "rainbow", "hsv"])
def test_rejects_a_blocked_palette_name(blocked: str) -> None:
    with pytest.raises(ValueError, match="blocked"):
        diverging(blocked, 3)


def test_rejects_an_unknown_name_with_a_key_error() -> None:
    """KeyError rather than ValueError, matching sequential()'s split between "bad input"
    and "no such registered map".
    """
    with pytest.raises(KeyError, match="unknown diverging palette"):
        diverging("nope", 3)


def test_rejects_a_negative_count() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        diverging("coolwarm", -1)


# ---------------------------------------------------------------------------
# registered maps
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(DIVERGING_PALETTES))
def test_every_registered_map_renders(name: str) -> None:
    colors = diverging(name, 9)

    assert len(colors) == 9
    assert all(HEX_COLOR_RE.fullmatch(color) for color in colors)


@pytest.mark.parametrize("name", sorted(DIVERGING_PALETTES))
def test_every_registered_map_takes_its_extremes_from_okabe_ito(name: str) -> None:
    """A diverging map's whole point is that direction carries meaning, so both extremes
    must stay distinguishable to a colorblind reader.
    """
    from svgplot.palette.colorblind import DEFAULT_PALETTE

    okabe_ito = {color.lower() for color in DEFAULT_PALETTE}
    low, _, high = DIVERGING_PALETTES[name]

    assert low.lower() in okabe_ito
    assert high.lower() in okabe_ito
