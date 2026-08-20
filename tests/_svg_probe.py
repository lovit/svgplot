"""Reading an SVG back the way a test needs to read it.

Four test modules each grew their own ``_tags`` and three of them meant different things --
two matched a class by substring and one only saw self-closing tags. A helper whose meaning
you have to open the file to learn is worse than no helper: the tests using it look alike and
are not, and the two that were fixed after a review left the other two behind.

Six modules use it now: the original four plus ``regression`` and ``gauge``, both of which
held the same idea under a different name. Three still do not, and they are listed rather
than left to be rediscovered -- ``test_charts_ecdf.py``, ``test_charts_kde.py`` and
``test_charts_scatter.py`` each match ``/>``-only and test the class by substring. Nothing
over-matches in them today, which is exactly what was true of the four before a class with a
longer name would have appeared. Issue #117 named four; these are the follow-up.
"""

from __future__ import annotations

import re

_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')


def _matches(svg: str, element: str, css_class: str) -> list[tuple[re.Match[str], dict[str, str]]]:
    """Opening tags of ``element`` carrying ``css_class``, each with its match position.

    The match rather than the tag string, because two elements can have byte-identical opening
    tags -- two labels at the same coordinates, say -- and looking the tag up by ``str.index``
    to find what follows it then returns the *first* one's content for both.
    """
    return [
        (match, attributes)
        for match, attributes in (
            (match, dict(_ATTR_RE.findall(match.group()))) for match in re.finditer(rf"<{element}\b[^>]*?/?>", svg)
        )
        if css_class in attributes.get("class", "").split()
    ]


def every_tag(svg: str, element: str) -> list[dict[str, str]]:
    """Every opening tag of ``element``, whatever classes it carries.

    The class-filtered helpers below answer "where are the marks I asked about"; this one
    answers "what is on the canvas at all", which is what a *completeness* assertion needs —
    ``test_charts_gauge.py``'s check that every drawn class appears in the ``<style>`` block
    cannot name the classes in advance, because the whole point is to catch one that nobody
    named. Consolidating the four ``_tags`` copies dropped that check from the ``<text>``
    elements for want of this function; it is here so the next completeness test does not
    have to reach for a raw regex again.
    """
    return [dict(_ATTR_RE.findall(match.group())) for match in re.finditer(rf"<{element}\b[^>]*?/?>", svg)]


def tags(svg: str, element: str, css_class: str) -> list[dict[str, str]]:
    """Opening tags of ``element`` whose class list carries ``css_class`` as a token.

    **A token, not a substring.** ``css_class in tag`` matches ``grid-line`` inside a future
    ``grid-line-major``, and matches it inside any other attribute that happens to contain
    those characters -- a ``<title>`` naming a series "grid-line", a path ``d`` that never
    could, an ``id``. A test that counts one thing and silently counts two is worse than a
    failing one.

    Both tag shapes, not only ``.../>``. The ``violinplot`` copy matched self-closing tags
    alone, so every assertion it could have made about a ``<text>`` element was unwritable --
    and nothing said so, because the helper simply returned nothing to assert on.
    """
    return [attributes for _, attributes in _matches(svg, element, css_class)]


def texts(svg: str, element: str, css_class: str) -> list[str]:
    """The text content of each matching ``element``, in document order.

    Built on the same match as :func:`tags` rather than on a second regex. Writing the second
    regex by hand is how the substring bug gets reintroduced -- a ``class="[^"]*X[^"]*"``
    pattern is exactly the form this module exists to replace, and it reads as harmless right
    up until a ``X-major`` class appears.

    "Content" means the text up to the first child element, so
    ``<text>before<tspan>mid</tspan>after</text>`` gives ``"before"``. Whitespace is kept, and
    entities are not unescaped -- what the file says, not what a browser would show. A
    self-closing element has no content and contributes nothing rather than whatever happens
    to follow it.
    """
    return [
        svg[match.end() :].split("<", 1)[0]
        for match, _ in _matches(svg, element, css_class)
        if not match.group().endswith("/>")
    ]
