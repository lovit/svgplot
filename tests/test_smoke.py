"""Package-wide smoke test.

Confirms svgplot imports cleanly, its public API is re-exported, and every
submodule (including ones not yet wired into svgplot/__init__.py) imports
without circular-reference errors. This is the safety net later milestone
issues rely on when they start filling in the NotImplementedError stubs.
"""

import builtins
import importlib
import inspect
import pkgutil
import re
import typing

import pytest

import svgplot


def test_import() -> None:
    assert svgplot.__version__ == "0.1.0"


def test_public_api_matches_all() -> None:
    assert set(svgplot.__all__) <= set(dir(svgplot))


def test_every_type_a_public_signature_names_can_be_imported() -> None:
    """A public annotation naming a type the caller cannot import is a leak.

    ``barplot(estimator: Estimator | None = None)`` said its argument's type out loud while
    ``Estimator`` lived in ``charts/_aggregate`` -- a private module -- so a caller writing
    their own folding function had nothing to type it against, and nothing here noticed.
    The direction matters: ``test_public_api_matches_all`` is a subset check, which a *removed*
    export satisfies trivially. This asks the opposite question, and it asks it of every
    annotation rather than of one name, so the next alias to reach a public signature is
    covered without anyone remembering to come back.
    """
    leaked = (
        {
            token.split(".")[0]
            for chart in svgplot.charts.__all__
            for spec in inspect.signature(getattr(svgplot, chart)).parameters.values()
            if spec.annotation is not inspect.Parameter.empty
            for token in re.findall(r"[A-Za-z_][A-Za-z0-9_.]*", str(spec.annotation))
            if token.split(".")[0][:1].isupper()
        }
        - set(dir(typing))
        - set(dir(builtins))
    )

    assert leaked, "found no named types at all -- this test would pass on any package"
    assert leaked <= set(
        svgplot.__all__
    ), f"public signatures name types that are not exported: {sorted(leaked - set(svgplot.__all__))}"


def _iter_submodule_names() -> list[str]:
    names = []
    for module_info in pkgutil.walk_packages(svgplot.__path__, prefix="svgplot."):
        names.append(module_info.name)
    return names


@pytest.mark.parametrize("module_name", _iter_submodule_names())
def test_submodule_imports_cleanly(module_name: str) -> None:
    importlib.import_module(module_name)
