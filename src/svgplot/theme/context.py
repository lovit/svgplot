"""stylexcontext separation and parametric (seed-color) themes.

context scales font/line-width the way seaborn's paper/notebook/talk/poster
does, but as a pure function (no rcParams mutation) — see
docs/research/12-aesthetics.md §1. Scoped context-manager application is a
2차 addition planned for this same file.
"""

from __future__ import annotations

from svgplot.theme.base import Theme


def parametric_theme(seed_color: str) -> Theme:
    """Derive a full Theme from a single brand seed color (pygal parametric-style precedent)."""
    raise NotImplementedError
