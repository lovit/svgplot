"""What the distribution declares, for constraints no test run can exercise."""

from __future__ import annotations

import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

# The first cssselect2 that compiles ``:where()``. 0.4.1 raises
# ``SelectorError: ('Unknown pseudo-class', 'where')`` on every rule this package now emits.
_CSSSELECT2_WHERE_SUPPORT = "0.5"


def _optional(extra: str) -> list[str]:
    return tomllib.loads(PYPROJECT.read_text())["project"]["optional-dependencies"][extra]


def test_the_png_extra_floors_cssselect2_high_enough_for_where() -> None:
    """cairosvg rasterizes through cssselect2 and declares it with no bound of its own, so a
    resolver is free to pick a version that rejects the CSS this package emits -- turning
    ``save("x.png")`` from working into raising.

    Asserted against the declaration rather than the behaviour because nothing here can reach
    the behaviour: ``mise run install`` is ``uv sync --all-groups --extra numpy-parity``, so
    the ``png`` extra is never installed and every test that touches rasterization skips on
    every CI run. That gap is its own issue; this is what can be checked meanwhile.
    """
    pins = {name.split(">=")[0]: name for name in _optional("png")}

    assert "cssselect2" in pins, f"png extra must floor cssselect2; got {sorted(pins)}"
    assert pins["cssselect2"] == f"cssselect2>={_CSSSELECT2_WHERE_SUPPORT}", pins["cssselect2"]
