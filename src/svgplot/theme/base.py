"""Theme — the ~25-key style schema (docs/research/12-aesthetics.md §1).

Immutable value object: rendering never mutates global state (unlike
matplotlib rcParams or seaborn's ``set_theme``). Passed explicitly to every
render call.
"""

from __future__ import annotations


class Theme:
    """A complete, immutable set of visual defaults for a chart."""

    def __init__(
        self,
        *,
        background: str = "#ffffff",
        foreground: str = "#111111",
        palette: list[str] | None = None,
        font_family: str = "sans-serif",
    ) -> None:
        raise NotImplementedError
