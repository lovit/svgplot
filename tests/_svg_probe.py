"""Reading an SVG back the way a test needs to read it.

Four test modules each grew their own ``_tags`` and three of them meant different things --
two matched a class by substring and one only saw self-closing tags. A helper whose meaning
you have to open the file to learn is worse than no helper: the tests using it look alike and
are not, and the two that were fixed after a review left the other two behind.
"""

from __future__ import annotations

import re

_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')


def _matches(svg: str, element: str, css_class: str) -> list[tuple[str, dict[str, str]]]:
    """Opening tags of ``element`` carrying ``css_class``, each with its own source text."""
    return [
        (tag, attributes)
        for tag, attributes in ((tag, dict(_ATTR_RE.findall(tag))) for tag in re.findall(rf"<{element}\b[^>]*?/?>", svg))
        if css_class in attributes.get("class", "").split()
    ]


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
    """
    return [
        svg[svg.index(tag) + len(tag) :].split("<", 1)[0]
        for tag, _ in _matches(svg, element, css_class)
        if not tag.endswith("/>")
    ]
