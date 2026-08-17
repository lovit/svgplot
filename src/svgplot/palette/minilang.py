"""Palette mini-language parser (``"ch:..."``, ``"light:X"``, ``"dark:X"``, ``"blend:a,b"``).

Ported from seaborn's ``color_palette()`` grammar but reimplemented with an
explicit parser instead of ad-hoc ``split(":")``/``startswith`` checks, for
better error messages (docs/research/12-aesthetics.md §2).
"""

from __future__ import annotations


def parse_palette_spec(spec: str) -> list[str]:
    """Parse a palette mini-language string into a concrete color list."""
    raise NotImplementedError
