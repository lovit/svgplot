"""Tests for the text-width estimate the layout leans on.

Every assertion here is about an *approximation*, so the useful ones are about its shape --
wide characters cost more than narrow ones, the result is monotone, truncation lands under
budget -- rather than about exact pixel counts nobody can verify without a font renderer.
"""

from __future__ import annotations

import pytest

from svgplot.charts._textwidth import (
    _CAPITAL_RATIO,
    _ELLIPSIS,
    _NARROW_RATIO,
    _TITLE_THRESHOLD,
    _UNMEASURED_THRESHOLD,
    needs_full_text,
    text_width,
    truncate_to_width,
)


def test_an_empty_string_costs_nothing() -> None:
    assert text_width("", 11.0) == 0.0


def test_a_cjk_character_costs_a_full_em_and_a_latin_one_costs_less() -> None:
    """The whole reason the estimate is not ``len(text)``: eleven Hangul syllables fill the
    room that twenty-one Latin letters do, and charging them the same is what let a Korean
    label run off the canvas."""
    assert text_width("가", 10.0) == 10.0
    assert text_width("a", 10.0) == 10.0 * _NARROW_RATIO
    assert text_width("가", 10.0) > text_width("a", 10.0)


@pytest.mark.parametrize("wide", ["가", "漢", "あ", "\uff21", "\uff01"])
def test_every_east_asian_wide_form_is_charged_as_wide(wide: str) -> None:
    """Hangul, Han, kana and the fullwidth Latin/punctuation forms are all square."""
    assert text_width(wide, 10.0) == 10.0


@pytest.mark.parametrize("ambiguous", ["\u03b1", "\u00b1", "\u03c9"])
def test_ambiguous_width_characters_follow_the_same_case_rule(ambiguous: str) -> None:
    """``east_asian_width`` calls these ``A``: wide in a terminal font picked for CJK,
    narrow in the proportional fonts an SVG is read in. This is a deliberate call, not an
    oversight -- charging them wide would truncate Greek and Cyrillic labels early. They are
    then charged by case like anything else, so lowercase Greek is narrow."""
    assert text_width(ambiguous, 10.0) == 10.0 * _NARROW_RATIO


@pytest.mark.parametrize(("char", "ratio"), [("\u042f", _CAPITAL_RATIO), ("\u0391", _CAPITAL_RATIO)])
def test_ambiguous_capitals_are_charged_as_capitals(char: str, ratio: float) -> None:
    """Cyrillic and Greek capitals measure like Latin ones, not like lowercase."""
    assert text_width(char, 10.0) == 10.0 * ratio


@pytest.mark.parametrize("dash", ["\u2026", "\u2014", "\u2015", "\u2500"])
def test_em_wide_punctuation_is_charged_a_full_em(dash: str) -> None:
    """Measured at exactly 1.0 em in Arial, Helvetica and Times despite not being East
    Asian. The ellipsis is the one that matters: this module inserts it, and charging it
    0.55 made every truncated label 0.45 em too long -- 5px at the default legend size."""
    assert text_width(dash, 10.0) == 10.0


def test_width_scales_with_the_font_size() -> None:
    assert text_width("abc", 22.0) == 2 * text_width("abc", 11.0)


def test_width_is_additive_over_characters() -> None:
    """A mixed string is the sum of its parts, so a caller can reason about a prefix."""
    assert text_width("a가b", 10.0) == pytest.approx(text_width("a", 10.0) + text_width("가", 10.0) + text_width("b", 10.0))


# ---------------------------------------------------------------------------
# truncation
# ---------------------------------------------------------------------------


def test_a_label_that_fits_is_returned_untouched() -> None:
    """Most labels are short, and their output has to be byte-identical to before -- an
    ellipsis appearing on a label that fit would be a regression in every existing chart."""
    assert truncate_to_width("짧음", 11.0, 200.0) == "짧음"
    assert truncate_to_width("", 11.0, 200.0) == ""


def test_a_label_that_does_not_fit_is_cut_and_marked() -> None:
    """The marker is asserted as a **literal**. Referring to ``_ELLIPSIS`` instead let
    ``_ELLIPSIS = ""`` pass the entire suite -- ``endswith("")`` is true of every string, so
    the one thing that tells a reader something was cut could vanish undetected."""
    result = truncate_to_width("a" * 40, 11.0, 96.0)

    assert result != "a" * 40
    assert result.endswith("…")
    assert _ELLIPSIS == "…"


@pytest.mark.parametrize("text", ["a" * 40, "가" * 40, "0" * 40, "한글 섞인 mixed label 입니다 길게"])
def test_the_result_is_estimated_to_fit_the_budget(text: str) -> None:
    """The point of truncating. Checking only that it got shorter would pass for a function
    that cut one character off a label twice too long."""
    assert text_width(truncate_to_width(text, 11.0, 96.0), 11.0) <= 96.0


def test_wide_text_is_cut_sooner_than_narrow_text() -> None:
    """Eleven CJK characters take the room twenty-one Latin ones do, so the same budget has
    to keep roughly half as many. A model that ignored width keeps the same count."""
    latin = truncate_to_width("a" * 40, 11.0, 96.0)
    cjk = truncate_to_width("가" * 40, 11.0, 96.0)

    assert len(cjk) < len(latin)
    assert len(latin) >= 2 * (len(cjk) - 1) - 1


def test_truncation_is_monotone_in_the_budget() -> None:
    """More room never yields a shorter label. An off-by-one in the accumulator can break
    this at one budget without breaking any single-value check."""
    lengths = [len(truncate_to_width("가나다라마바사아자차", 11.0, budget)) for budget in range(0, 140, 4)]

    assert lengths == sorted(lengths)


def test_a_budget_too_small_for_anything_still_says_something_was_cut() -> None:
    """An empty label beside a swatch reads as a rendering bug; an ellipsis says there was
    more text here."""
    assert truncate_to_width("가나다", 11.0, 1.0) == "…"
    assert truncate_to_width("가나다", 11.0, 0.0) == "…"
    assert truncate_to_width("가나다", 11.0, -50.0) == "…"


def test_a_trailing_space_is_not_left_before_the_ellipsis() -> None:
    """``"long name …"`` reads as a gap rather than a cut.

    The budget matters: at 60.0 the kept prefix ends in a letter anyway, so ``rstrip()``
    never runs and removing it passes. This budget keeps a prefix that really does end in a
    space."""
    result = truncate_to_width("abcdefgh ijklmnop", 11.0, 66.0)

    assert not result.removesuffix("…").endswith(" ")
    assert result.endswith("h…")


def test_the_class_charges_cover_the_worst_ascii_character_in_their_class() -> None:
    """Every number in this module is a measurement, and nothing pinned them: the ratios
    could drift to any value with the suite still green, because each test computed its
    expectation from the constant it was checking.

    The right-hand sides are Arial advances read from the font's ``hmtx`` table (upm 2048),
    written as literals so this test fails when a ratio drops below what it must cover -- not
    when it merely changes."""
    assert _NARROW_RATIO >= 0.5840, "+ < = > ~ cost 0.584 and would overflow"
    assert _NARROW_RATIO >= 0.5562, "digits and a b d e g h n o p q u cost 0.5562"
    assert _CAPITAL_RATIO >= 0.7222, "C D H N R U cost 0.7222"


def test_a_label_near_the_budget_keeps_its_full_text_even_when_it_was_not_cut() -> None:
    """The model can be wrong in the direction that says "this fits", and that is the case
    with no fallback -- the tail lands outside the viewBox and nowhere in the file.

    The label has to be one that is *not* truncated, or this proves nothing: ``"W" * 19``
    estimates 198.6px against a 118px budget, so it is cut and gets its title from that
    branch instead, and every threshold from 0.10 to 1.68 passed. ``"a" * 15`` estimates
    97.4px -- inside the budget, above 0.80 of it."""
    assert text_width("a" * 15, 11.0) < 118.0, "must not be a truncated label"
    assert needs_full_text("a" * 15, 11.0, 118.0)
    assert not needs_full_text("a" * 12, 11.0, 118.0)


def test_the_bounded_threshold_is_where_the_docstring_says() -> None:
    """Pinned as a literal for the same reason the ratios are. The band between them is what
    the test above walks, and a single call cannot fix both ends."""
    assert _TITLE_THRESHOLD == 0.80


@pytest.mark.parametrize("text", ["\u0635" * 14, "\u00a9" * 14, "\u00e6" * 14, "\u2030" * 14, "\u2116" * 14])
def test_a_label_outside_the_measured_repertoire_keeps_its_text_far_sooner(text: str) -> None:
    """The hole 0.80 alone left open, and the one case that breaks the module's contract:
    not truncated, no ``<title>``, and 51px past the canvas edge (``ص`` x14 estimates 90.8px
    and renders at 169.1px in Arial).

    All five estimate the same 90.8px -- comfortable under 0.80 of a 118px budget, which is
    94.4px -- and all five render between 1.3x and 2.0x that. The fix is not a smaller threshold for everyone;
    it is a smaller one for the characters the estimate was never measured against."""
    assert text_width(text, 11.0) < 118.0, "must not be a truncated label"
    assert text_width(text, 11.0) < 118.0 * _TITLE_THRESHOLD, "the bounded threshold calls this comfortable"
    assert needs_full_text(text, 11.0, 118.0)


@pytest.mark.parametrize("text", ["caf\u00e9", "\ub9e4\ucd9c \ucd94\uc774", "Seoul"])
def test_a_short_label_gets_no_title_whatever_script_it_is_in(text: str) -> None:
    """The stricter threshold buys its safety with markup, so it has to stop somewhere. A
    label at a quarter of the budget is not a candidate for overflow in any font measured,
    and burying it in a ``<title>`` would trade a real problem for a cluttered file (핵심
    원칙 1: the output stays hand-editable)."""
    assert not needs_full_text(text, 11.0, 118.0)


def test_the_unmeasured_threshold_is_below_the_worst_measured_error() -> None:
    """Derived, not chosen: a label estimated at fraction *f* of the budget renders at up to
    2.63 *f* of it (Tahoma's worst), so it stays inside only while *f* < 1/2.63 = 0.380."""
    assert _UNMEASURED_THRESHOLD < 1 / 2.63
    assert _UNMEASURED_THRESHOLD == 0.35


def test_an_empty_label_in_no_room_at_all_stays_empty() -> None:
    """``available <= 0`` versus ``< 0``. Unreachable from the charts today -- every caller
    has positive room -- but the ellipsis exists to say "there was more text here", and there
    was not."""
    assert truncate_to_width("", 11.0, 0.0) == ""
    assert truncate_to_width("", 11.0, -1.0) == ""


def test_a_character_exactly_filling_the_budget_is_kept() -> None:
    """``used + width > budget`` and ``>=`` differ only when a character lands exactly on
    the boundary -- and a label that fits to the pixel should not lose its last letter."""
    per_char = text_width("a", 10.0)
    budget = text_width("…", 10.0) + per_char * 3

    assert truncate_to_width("a" * 9, 10.0, budget) == "aaa…"


def test_a_label_exactly_the_width_of_its_budget_is_not_cut() -> None:
    """``<=`` versus ``<`` in the early return. Off by one character on a label that fits
    exactly, which is the case a caller sizing a legend by hand will hit first."""
    exact = text_width("abc", 11.0)

    assert truncate_to_width("abc", 11.0, exact) == "abc"


def test_truncation_keeps_a_prefix_and_never_reorders() -> None:
    """``break`` versus ``continue`` in the accumulator. With ``continue`` a character too
    wide to fit is skipped and a *later*, narrower one takes its place -- so the label comes
    out with a hole in it, reading as different text rather than as shortened text."""
    result = truncate_to_width("가i 나", 11.0, 20.0)

    assert result.removesuffix("…") == "가i 나"[: len(result) - 1].rstrip() or result == "…"
    assert "i" not in result or result.startswith("가")


def test_a_kept_prefix_ending_in_a_space_is_stripped_not_the_leading_one() -> None:
    """``rstrip()`` versus ``strip()``. A label whose *first* character is a space has one
    for a reason -- alignment in a hand-built legend -- and eating it changes the text."""
    assert truncate_to_width(" abcdefghijklmnop", 11.0, 66.0).startswith(" ")


# Arial advances read from the font's own ``hmtx`` table at upm 2048, as literals. Computing
# the expectation from ``_CAPITAL_RATIO``/``_NARROW_RATIO`` -- constants in the module under
# test -- let every one of these be shrunk to its class charge plus a thousandth with the
# suite still green, and ``W`` at 0.721 puts ``W`` x40 28px past the canvas edge.
_ARIAL_ADVANCES = {
    "@": 1.0151,
    "W": 0.9438,
    "%": 0.8892,
    "m": 0.8330,
    "M": 0.8330,
    "G": 0.7778,
    "O": 0.7778,
    "Q": 0.7778,
    "w": 0.7222,
    "&": 0.6670,
}


@pytest.mark.parametrize(("char", "advance"), sorted(_ARIAL_ADVANCES.items()))
def test_each_measured_outlier_is_charged_at_least_what_it_costs(char: str, advance: float) -> None:
    """The ten literals exist because their real advance exceeds what their class would be
    charged, so each has to cover its own measurement -- not merely beat its class."""
    assert text_width(char, 10.0) >= 10.0 * advance


@pytest.mark.parametrize(("char", "advance"), sorted(_ARIAL_ADVANCES.items()))
def test_each_measured_outlier_is_still_an_outlier(char: str, advance: float) -> None:
    """The other half: an entry that no longer exceeds its class is dead weight in a table
    whose whole cost is being ten hand-maintained literals."""
    klass = _CAPITAL_RATIO if (char.isupper() or char.isdigit()) else _NARROW_RATIO

    assert advance > klass, f"{char!r} no longer needs its own entry"
