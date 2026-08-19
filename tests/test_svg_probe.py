"""Tests for the shared SVG probe.

The probe exists because four copies of it disagreed, so the thing to pin is the disagreement
itself: token-vs-substring matching, and whether a tag with content is seen at all. Without
these, a future copy could quietly relax back to either and every test using it would still
be green while counting something else.
"""

from __future__ import annotations

import pytest

from _svg_probe import tags, texts

_SVG = """
<svg>
  <rect x="1" class="grid-line"/>
  <rect x="2" class="grid-line-major"/>
  <rect x="3" class="series-1 grid-line"/>
  <rect x="6" class="grid-line series-3"/>
  <rect x="7"/>
  <text x="4" class="tick-label">grid-line</text>
  <text x="5" class="tick-label"><title>grid-line</title></text>
  <path d="M0 0" id="grid-line-path" class="series-2"/>
</svg>
"""


def test_a_class_matches_as_a_token_not_as_a_substring() -> None:
    """``css_class in tag`` also matched ``grid-line-major``, which is a different class, and
    it is the exact defect a review caught in two of the four copies. Counting one thing and
    silently counting two is worse than failing."""
    matched = tags(_SVG, "rect", "grid-line")

    assert [tag["x"] for tag in matched] == ["1", "3", "6"]


def test_a_class_only_matches_the_class_attribute() -> None:
    """The substring form also matched the characters anywhere in the tag -- an ``id``, a
    ``d``, a title naming a series. Here the ``<path>`` carries ``grid-line`` in its ``id``
    and is not a grid line."""
    assert tags(_SVG, "path", "grid-line") == []


def test_a_tag_with_content_is_seen_and_not_only_a_self_closing_one() -> None:
    """The ``violinplot`` copy matched ``.../>`` alone, so every assertion it could have made
    about a ``<text>`` element was unwritable -- and nothing said so, because the helper
    returned an empty list rather than an error."""
    matched = tags(_SVG, "text", "tick-label")

    assert [tag["x"] for tag in matched] == ["4", "5"]


def test_the_text_inside_a_tag_is_not_searched_for_the_class() -> None:
    """Both ``<text>`` elements above have ``grid-line`` in their content. Neither is one."""
    assert tags(_SVG, "text", "grid-line") == []


def test_a_class_that_is_not_there_finds_nothing_rather_than_everything() -> None:
    assert tags(_SVG, "rect", "no-such-class") == []


@pytest.mark.parametrize(
    ("element", "css_class", "expected"),
    [("rect", "series-1", 1), ("path", "series-2", 1), ("text", "tick-label", 2), ("rect", "grid-line", 3)],
)
def test_every_attribute_of_a_matched_tag_comes_back(element: str, css_class: str, expected: int) -> None:
    """Callers index the result (``tag["d"]``, ``tag["x"]``), so a probe that returned only
    the class would be useless in a way each caller would have to discover.

    The count is asserted first, and that is the load-bearing half. An earlier version put
    both assertions inside a ``for`` loop over the matches, so a probe that returned *nothing*
    passed without asserting anything -- and a mutation narrowing the class match to the last
    token alone did exactly that, with all eight tests in this file green."""
    matched = tags(_SVG, element, css_class)

    assert len(matched) == expected
    for tag in matched:
        assert "class" in tag
        assert len(tag) > 1


def test_a_class_is_found_wherever_it_sits_in_the_list() -> None:
    """First token, last token, only token. The fixture used to carry exactly one multi-class
    tag and the query happened to name its last token, so "match only the last token" was
    indistinguishable from matching properly."""
    assert [tag["x"] for tag in tags(_SVG, "rect", "series-1")] == ["3"], "series-1 sits first"
    assert [tag["x"] for tag in tags(_SVG, "rect", "series-3")] == ["6"], "series-3 sits last"
    assert [tag["x"] for tag in tags(_SVG, "rect", "grid-line")] == ["1", "3", "6"], "either position"


def test_a_tag_with_no_class_at_all_is_skipped_rather_than_crashing() -> None:
    """``.get("class", "")`` and not ``.get("class")``. Real charts emit unclassed elements --
    a background ``<rect>``, a clip path -- and a probe that raised ``AttributeError`` on the
    first one would fail in a way that reads as a bug in the chart."""
    assert tags(_SVG, "rect", "no-such-class") == []
    assert [tag["x"] for tag in tags(_SVG, "rect", "grid-line")] == ["1", "3", "6"]


def test_the_text_of_a_matched_element_comes_back_in_document_order() -> None:
    """``texts`` shares :func:`tags`' match rather than growing a second regex, because the
    hand-written ``class="[^"]*X[^"]*"`` is the very form this module replaces."""
    assert texts(_SVG, "text", "tick-label") == ["grid-line", ""]
    assert texts(_SVG, "text", "no-such-class") == []
