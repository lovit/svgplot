"""Curve interpolation: quadratic/cubic/hermite/lagrange/trigonometric (pygal precedent, docs/research/01-pygal.md A7)."""

from __future__ import annotations

METHODS = ("quadratic", "cubic", "hermite", "lagrange", "trigonometric")


def interpolate(x: list[float], y: list[float], method: str = "cubic", precision: int = 250) -> object:
    """Interpolate (x, y) points for smooth line rendering. Display-only, not a statistical fit."""
    raise NotImplementedError
