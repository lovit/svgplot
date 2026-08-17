"""Qualitative (categorical) palettes."""

from __future__ import annotations

QUALITATIVE_PALETTES: dict[str, list[str]] = {}
"""Named qualitative palettes; default entry must be colorblind-safe (palette.colorblind)."""


def qualitative(name: str, n: int) -> list[str]:
    """Return n colors from the named qualitative palette."""
    raise NotImplementedError
