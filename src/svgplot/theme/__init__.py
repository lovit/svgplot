"""Theme: style x context schema, built-in presets, parametric (seed-color) themes."""

from __future__ import annotations

from svgplot.theme.base import Theme
from svgplot.theme.context import CONTEXTS, apply_context, parametric_theme
from svgplot.theme.presets import PRESETS

__all__ = ["CONTEXTS", "PRESETS", "Theme", "apply_context", "parametric_theme"]
