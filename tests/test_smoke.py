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

    **Chart parameters only**, which is narrower than "every public signature". Three names
    reach a public signature and are not importable, at three sites: ``Chart``'s constructor
    takes ``SvgDocument``, ``LabelData`` and ``Domains``; ``Composition``'s takes
    ``SvgDocument`` (and ``Chart``, which is exported); and ``Chart.domains`` returns a
    ``Domains``. The three do not answer the same way.

    Both constructors document themselves as things a caller does not build: ``Chart``'s class
    docstring says it is "constructed by the chart functions, not usually by hand", and
    ``Composition.__init__`` says its ``document`` "is the composed canvas built by a
    ``svgplot.layout`` function" -- so neither set of annotations is really addressed to a
    caller. ``Chart.domains`` is the one that is: a property, returning a type nothing exports.
    It disclaims its own status in the same breath -- "Not part of the public API surface yet
    -- it is a chart's report about itself, and the shape of that report is still settling" --
    and that is a question for the issue that settles the shape, not one to answer here by
    giving this test a name claiming more than its body asks.
    """
    per_chart = {chart: _named_types(chart) for chart in svgplot.charts.__all__}
    leaked = set().union(*per_chart.values())

    # What this test reads is *source text*, and it is source text only because every chart
    # module carries ``from __future__ import annotations``. Nothing in the lint config enforces
    # that import, and without it a whole module goes quiet at once: an evaluated alias loses
    # its name (``Estimator`` becomes ``str | collections.abc.Callable[[list[float]], float]``)
    # and an evaluated class gains a dotted path whose first token is lowercase
    # (``svgplot.theme.base.Theme``), which the capitalisation filter above drops. Both halves
    # of the two assertions are needed: ``eager`` catches the module that stopped being source
    # text, and naming the three types it must find catches the extraction itself going blind --
    # point the regex at nothing and ``set() <= anything`` is quietly true. The three rather
    # than "at least one", because finding only ``Theme`` is the shape a half-broken extraction
    # takes: it is on all sixteen charts, and the two aliases are on three each.
    eager = sorted(
        chart
        for chart in svgplot.charts.__all__
        for spec in inspect.signature(getattr(svgplot, chart)).parameters.values()
        if spec.annotation is not inspect.Parameter.empty and not isinstance(spec.annotation, str)
    )
    assert not eager, f"{eager} evaluate their annotations -- `from __future__ import annotations` is missing"
    assert leaked >= {"Estimator", "LabelSpec", "Theme"}, f"the extraction found only {sorted(leaked)}"
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
