"""Shared pytest fixtures for svgplot's test suite."""

from __future__ import annotations

import pytest


def _cairosvg_usable() -> bool:
    """cairosvg can fail to import with either ImportError (package not installed) or
    OSError (package installed but its native libcairo library is missing) — both mean
    "not usable" from svgplot's perspective.
    """
    try:
        import cairosvg  # noqa: F401
    except (ImportError, OSError):
        return False
    return True


@pytest.fixture
def require_cairosvg() -> None:
    """Skip the test unless cairosvg is actually usable (installed + native library present)."""
    if not _cairosvg_usable():
        pytest.skip("cairosvg is not usable in this environment (not installed or missing libcairo)")


@pytest.fixture
def cairosvg_unavailable() -> None:
    """Skip the test unless cairosvg is unusable, so the missing-dependency path is exercised."""
    if _cairosvg_usable():
        pytest.skip("cairosvg is usable in this environment; the missing-dependency path isn't exercised")
