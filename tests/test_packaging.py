"""What the distribution declares, for constraints no test run here can exercise."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

# Each entry: the package, and a version its constraint must exclude.
#
# Stated as "this version must be refused" rather than as the constraint's text, because the
# text is not the fact. An earlier version of this file asserted ``"cssselect2>=0.5"`` verbatim
# and failed on ``>=0.5.0``, on ``>= 0.5``, and -- worst -- on ``>=0.9.0``, telling whoever
# raised the floor that their stricter constraint was wrong. A version to exclude is
# monotonic: every constraint at least as strict as the current one still passes.
_MUST_REFUSE = {
    # 0.4.1 raises SelectorError('Unknown pseudo-class', 'where') on every rule this package
    # emits since #182, and cairosvg -- which rasterizes through it -- declares it unbounded.
    "cssselect2": "0.4.1",
    # CVE-2023-27586: SSRF via external references in untrusted SVG input, fixed in 2.7.0.
    "cairosvg": "2.6.0",
}


def _png_extra() -> dict[str, Requirement]:
    declared = tomllib.loads(PYPROJECT.read_text())["project"]["optional-dependencies"]["png"]
    return {Requirement(text).name: Requirement(text) for text in declared}


def test_the_png_extra_declares_every_package_with_a_known_bad_version() -> None:
    """A constraint cannot refuse a version if the package is not declared at all."""
    assert set(_MUST_REFUSE) <= set(_png_extra())


@pytest.mark.parametrize(("package", "bad"), sorted(_MUST_REFUSE.items()))
def test_the_png_extra_refuses_versions_that_are_known_to_break(package: str, bad: str) -> None:
    """Asserted against the declaration rather than the behaviour because nothing here can
    reach the behaviour: ``mise run install`` is ``uv sync --all-groups --extra numpy-parity``,
    so the ``png`` extra is never installed and every test that touches rasterization skips on
    every CI run. That gap is its own problem; this is what can be checked meanwhile.
    """
    requirement = _png_extra()[package]

    assert not requirement.specifier.contains(bad), f"{requirement} still admits {package} {bad}"
