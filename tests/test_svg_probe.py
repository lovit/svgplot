"""Tests for the shared SVG probe.

The probe exists because four copies of it disagreed, so the thing to pin is the disagreement
itself: token-vs-substring matching, and whether a tag with content is seen at all. Without
these, a future copy could quietly relax back to either and every test using it would still
be green while counting something else.
"""

from __future__ import annotations

import pytest

from _svg_probe import tags

_SVG = """
<svg>
  <rect x="1" class="grid-line"/>
  <rect x="2" class="grid-line-major"/>
  <rect x="3" class="series-1 grid-line"/>
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

    assert [tag["x"] for tag in matched] == ["1", "3"]


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


@pytest.mark.parametrize("element", ["rect", "text", "path"])
def test_every_attribute_of_a_matched_tag_comes_back(element: str) -> None:
    """Callers index the result (``tag["d"]``, ``tag["x"]``), so a probe that returned only
    the class would be useless in a way each caller would have to discover."""
    for tag in tags(_SVG, element, "series-1") + tags(_SVG, element, "series-2") + tags(_SVG, element, "tick-label"):
        assert "class" in tag
        assert len(tag) > 1
