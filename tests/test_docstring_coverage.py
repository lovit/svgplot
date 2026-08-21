"""Every public parameter is named where a reader would look for it.

Coverage as a gate rather than a habit. The holes this closes were not exotic: ``info=`` was
undocumented on two of the three charts that take it, ``violinplot`` never mentioned the
``hue=`` a whole CHANGELOG section argues for, and ``row`` documented neither of its two
keyword arguments. Each was invisible because nothing looked.

The check is "the name appears in the docstring", not "there is an ``Args:`` block". This
package explains parameters in running prose -- ``Args:`` appears three times in all of
``src/`` -- and mandating a block would put every parameter in two places, one of which
would go stale. Prose that names the parameter is what a reader can actually find.

There is deliberately no allowlist. ``tests/test_gallery.py`` already recorded why: an empty
escape hatch is one somebody widens later without anyone deciding to.
"""

from __future__ import annotations

import inspect

import pytest

import svgplot as sp

_PUBLIC = sorted(
    name
    for name in sp.__all__
    if callable(getattr(sp, name)) and not isinstance(getattr(sp, name), type) and not name.startswith("_")
)


def _signature(name: str) -> inspect.Signature | None:
    try:
        return inspect.signature(getattr(sp, name))
    except (TypeError, ValueError):  # pragma: no cover - no builtin is exported today
        return None


def test_the_registry_is_not_empty() -> None:
    """Without this, a change that emptied ``__all__`` or broke the filter would turn every
    parametrized case below into zero cases and the file into a green no-op."""
    assert len(_PUBLIC) >= 20, _PUBLIC


@pytest.mark.parametrize("name", _PUBLIC)
def test_every_public_parameter_is_named_in_its_docstring(name: str) -> None:
    signature = _signature(name)
    if signature is None:
        pytest.skip(f"{name} has no introspectable signature")
    doc = getattr(sp, name).__doc__ or ""

    missing = [parameter for parameter in signature.parameters if parameter not in doc]

    assert doc.strip(), f"{name} has no docstring"
    assert not missing, f"{name} never names {missing} in its docstring"


@pytest.mark.parametrize("name", _PUBLIC)
def test_every_public_function_documents_what_it_refuses(name: str) -> None:
    """This package refuses a lot on purpose -- 290 raise sites, and the refusals are the
    part a caller meets first. A function that raises without saying so sends them to the
    traceback to find out what the contract was."""
    assert "Raises:" in (getattr(sp, name).__doc__ or ""), f"{name} has no Raises: block"
