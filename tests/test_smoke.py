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


def _named_types(chart: str) -> set[str]:
    """Capitalised names appearing in one chart's parameter annotations."""
    return (
        {
            token.split(".")[0]
            for spec in inspect.signature(getattr(svgplot, chart)).parameters.values()
            if spec.annotation is not inspect.Parameter.empty
            for token in re.findall(r"[A-Za-z_][A-Za-z0-9_.]*", str(spec.annotation))
            if token.split(".")[0][:1].isupper()
        }
        - set(dir(typing))
        - set(dir(builtins))
    )


def test_every_type_a_chart_parameter_names_can_be_imported() -> None:
    """A chart parameter whose annotation names a type the caller cannot import is a leak.

    ``barplot(estimator: Estimator | None = None)`` said its argument's type out loud while
    ``Estimator`` lived in ``charts/_aggregate`` -- a private module -- so a caller writing
    their own folding function had nothing to type it against, and nothing here noticed.
    The direction matters: ``test_public_api_matches_all`` is a subset check, which a *removed*
    export satisfies trivially. This asks the opposite question, of every chart parameter
    rather than of one name, so the next alias to reach one is covered without anyone
    remembering to come back.

    **Chart parameters only**, which is narrower than "every public signature": ``Chart`` and
    ``Composition`` name ``SvgDocument``, ``LabelData`` and ``Domains`` in their constructors,
    and ``Chart.domains`` returns a ``Domains`` -- none of the three importable. The
    constructors are documented as "not usually built by hand"; the property is a real gap and
    is left for the issue that widens this, rather than pretended away by a name that claims
    more than the code asks.
    """
    per_chart = {chart: _named_types(chart) for chart in svgplot.charts.__all__}
    leaked = set().union(*per_chart.values())

    # What this test reads is *source text*, and it is source text only because every chart
    # module carries ``from __future__ import annotations``. Nothing in the lint config enforces
    # that import. Without it an annotation is evaluated, and an evaluated *alias* loses its
    # name -- ``Estimator`` becomes ``str | collections.abc.Callable[[list[float]], float]``,
    # which has nothing capitalised left to check -- while an evaluated *class* keeps hers, so
    # ``Theme`` would go on satisfying any "did we find anything" check. Asserting the
    # annotations are strings is what pins it, and it is the alias that this test is for.
    eager = sorted(
        chart
        for chart in svgplot.charts.__all__
        for spec in inspect.signature(getattr(svgplot, chart)).parameters.values()
        if spec.annotation is not inspect.Parameter.empty and not isinstance(spec.annotation, str)
    )
    assert not eager, f"{eager} evaluate their annotations -- `from __future__ import annotations` is missing"
    assert leaked <= set(
        svgplot.__all__
    ), f"chart parameters name types that are not exported: {sorted(leaked - set(svgplot.__all__))}"


def _iter_submodule_names() -> list[str]:
    names = []
    for module_info in pkgutil.walk_packages(svgplot.__path__, prefix="svgplot."):
        names.append(module_info.name)
    return names


@pytest.mark.parametrize("module_name", _iter_submodule_names())
def test_submodule_imports_cleanly(module_name: str) -> None:
    importlib.import_module(module_name)
