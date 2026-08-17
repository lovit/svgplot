"""Smoke test — confirms the package imports and CI actually runs pytest."""

import svgplot


def test_import() -> None:
    assert svgplot.__version__ == "0.1.0"
