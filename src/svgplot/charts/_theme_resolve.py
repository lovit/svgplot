"""Resolve a chart function's ``theme: Theme | str | None`` parameter into a
concrete ``Theme`` — shared by every chart type (``None`` -> the default
``Theme()``, a preset name -> ``theme.presets.PRESETS[name]``, a ``Theme``
instance -> used as-is).

Private/internal — not re-exported from ``svgplot.charts``.
"""

from __future__ import annotations

from svgplot.theme.base import Theme
from svgplot.theme.presets import PRESETS


def resolve_theme(theme: Theme | str | None) -> Theme:
    """Raises:
    KeyError: if ``theme`` is a string that isn't a registered preset name.
    TypeError: if ``theme`` is neither a ``Theme``, a preset name, nor ``None``.
    """
    if theme is None:
        return Theme()
    if isinstance(theme, Theme):
        return theme
    if isinstance(theme, str):
        if theme not in PRESETS:
            raise KeyError(f"unknown theme preset: {theme!r} (available: {sorted(PRESETS)})")
        return PRESETS[theme]
    raise TypeError(f"theme must be a Theme, a preset name, or None, got {type(theme).__name__}")
