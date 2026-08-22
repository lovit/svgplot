"""The grid ``kdeplot`` and ``violinplot`` share, and the claim its docstring makes.

``charts/_density_grid.py`` argues for the union rule by showing what pooling would do instead,
with three numbers in its docstring. Two earlier versions of that paragraph asserted a
*direction* -- that pooling is "too wide", then that it "shrinks" -- and both were wrong,
because the direction depends on the groups rather than on the rule. The third version stopped
asserting a direction and showed the numbers instead, which only helps if somebody runs them.

Nothing in this repo runs doctests: ``pyproject.toml`` sets no ``--doctest-modules`` and the
only collected item for this module is its import smoke test. So the doctest is executed here,
deliberately, rather than left as decoration.
"""

from __future__ import annotations

import doctest

import pytest

from svgplot.charts import _density_grid
from svgplot.charts._density_grid import union_grid_range


def test_the_docstring_numbers_are_real() -> None:
    """Run the module's own doctest.

    The three bandwidths it prints are the whole argument for the union rule. If ``stats.kde``'s
    bandwidth rule ever changes they stop being true, and this is what says so.
    """
    results = doctest.testmod(_density_grid, verbose=False)

    assert results.attempted > 0, "no doctest ran — the examples stopped being examples"
    assert results.failed == 0, f"{results.failed} of {results.attempted} doctest examples failed"


def test_the_union_is_wider_than_any_single_group() -> None:
    """The rule itself: every group keeps the span it would have chosen alone."""
    groups = [("narrow", [10.0, 10.1, 10.2]), ("wide", [0.0, 50.0, 100.0])]
    each = {label: union_grid_range([(label, values)], _fixed_bandwidth, 3.0) for label, values in groups}

    low, high = union_grid_range(groups, _fixed_bandwidth, 3.0)

    assert low == min(span[0] for span in each.values())
    assert high == max(span[1] for span in each.values())


def test_the_bandwidth_function_is_the_callers(monkeypatch: pytest.MonkeyPatch) -> None:
    """One call per group, in order, with the caller's own function.

    The callback exists so each chart keeps its error attribution -- ``kdeplot`` names the hue
    group, ``violinplot`` the category. That only holds if the failure raised is the caller's,
    from the group the caller would have named, so the order and the count both matter.
    """
    seen: list[object] = []

    def spy(values: list[float], label: object) -> float:
        seen.append(label)
        return 1.0

    union_grid_range([("first", [1.0]), ("second", [2.0]), ("third", [3.0])], spy, 2.0)

    assert seen == ["first", "second", "third"]


def test_a_failing_group_raises_before_the_rest_are_measured() -> None:
    """The caller's exception reaches the caller, and names the group it came from.

    Asserted because the violin path builds a generator: if that changed when the groups were
    materialised, a later group's failure could surface instead of the first one's, and the
    error would name the wrong violin.
    """

    def explode(values: list[float], label: object) -> float:
        if label == "second":
            raise ValueError(f"group {label!r}")
        return 1.0

    with pytest.raises(ValueError, match="group 'second'"):
        union_grid_range([("first", [1.0]), ("second", [2.0]), ("third", [3.0])], explode, 2.0)


def _fixed_bandwidth(values: list[float], label: object) -> float:
    """A bandwidth that does not depend on the values, so the span arithmetic is checkable."""
    return 1.0
