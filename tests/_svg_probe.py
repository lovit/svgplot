"""Reading an SVG back the way a test needs to read it.

Four test modules each grew their own ``_tags`` and three of them meant different things --
two matched a class by substring and one only saw self-closing tags. A helper whose meaning
you have to open the file to learn is worse than no helper: the tests using it look alike and
are not, and the two that were fixed after a review left the other two behind.
"""

from __future__ import annotations

import re

_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')


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
    return [
        attributes
        for attributes in (dict(_ATTR_RE.findall(tag)) for tag in re.findall(rf"<{element}\b[^>]*?/?>", svg))
        if css_class in attributes.get("class", "").split()
    ]
