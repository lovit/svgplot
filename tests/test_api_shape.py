"""Sixteen chart functions, one signature shape.

Each chart grew on its own issue, and each arrived with tests asserting *its* behaviour. That
is how the palette defect in #194 survived: `barplot` drew one colour, `boxplot` drew one per
category, both were covered, and nothing compared them. A rule that is meant to hold across a
family needs an assertion that spans the family. This file is that assertion for the shape of
the public signatures.

**The order is not a style preference.** ``layout/facet.py`` reads a chart's parameters by
*name* -- ``inspect.signature(plot_fn).parameters`` at ``layout/facet.py:235``, then a dict
keyed ``"xlim"``/``"ylim"``/``"bins"``/``"categories"`` handed back as keyword arguments. A
chart that spells one of those differently does not raise; it silently stops sharing that axis
when faceted. So the names in :data:`_FACET_READS` are load-bearing, and the rest of the
convention is what makes them findable.

Reordering *keyword-only* parameters cannot break a caller -- they can only ever be passed by
name -- and cannot move an output byte, since none of this reaches a renderer. That is why the
convention can be enforced rather than merely documented: adopting it costs nothing.

What is deliberately **not** checked here: whether a chart *has* a given parameter. ``pieplot``
has no ``xlim`` because it has no cartesian axis, and ``regplot`` has no ``hue`` on purpose.
Presence is a per-chart design question; this file only says that whatever a chart does take is
named and ordered like everybody else's.
"""

from __future__ import annotations

import ast
import inspect
from importlib import import_module
from pathlib import Path

import pytest

import svgplot as sp

_CHANNELS = ("data", "x", "y", "hue", "size", "values", "value", "labels")
"""Positional-or-keyword parameters: what the chart is drawn *from*.

Everything else is keyword-only in every chart, which is itself part of the convention and is
checked by :func:`test_everything_but_the_channels_is_keyword_only`.
"""

_UNIVERSAL = ("width", "height", "theme")
"""The block every chart ends its keyword block with, always in this order and always adjacent."""

_CROSS_CUTTING = ("info", "tooltip")
"""Flags shared across families, in the order they sit after a chart's own options.

``tooltip`` last of the two because it is the wider of them -- ten charts take it against
three for ``info`` -- so it sits closest to the universal block.
"""

_DOMAIN = ("categories", "xlim", "ylim", "xscale", "yscale")
"""What the axes span, after ``theme``.

**A new domain parameter goes here**, not into a chart's own options. ``layout/facet.py:31-33``
already names three that are waiting -- ``heatmap``'s value-to-colour scale, and the radial
extent of ``radarplot``/``gaugeplot``. Landing one as, say, ``rlim=`` in the usual place fails
:func:`test_every_chart_orders_its_keyword_block_the_same_way` with a message naming the
*chart*, which is the wrong place to look; this line is the right one.

That they come *after* ``theme`` looks wrong until you count: the six charts whose signature
ends at ``theme`` are exactly the six with no domain parameters at all. Nothing is out of
order; ``theme`` is simply not the last thing when there is something after it.
"""

_FACET_READS = ("xlim", "ylim", "bins", "categories")
"""The names ``layout.facet`` passes back as keyword arguments (``layout/facet.py:182-193``).

Spelling one of these differently costs a chart its axis sharing, without an error.
"""


def _parameters(name: str) -> dict[str, inspect.Parameter]:
    try:
        return dict(inspect.signature(getattr(sp, name)).parameters)
    except (TypeError, ValueError):  # pragma: no cover - every export is introspectable
        return {}


_CHARTS = sorted(
    name
    for name in sp.__all__
    if callable(getattr(sp, name))
    and not isinstance(getattr(sp, name), type)
    and next(iter(_parameters(name)), None) == "data"
)
"""The chart functions, found by taking ``data`` *first* rather than by a hand-kept list.

The "first" matters: ``facet`` also takes ``data``, but behind ``plot_fn``, and it is a
higher-order function rather than a chart -- it has no marks, no theme and no width of its own.
``apply_size``/``add_caption`` take a built ``Chart``/``Composition``, not data at all.
"""


def _expected(kwargs: list[str]) -> list[str]:
    """The order ``kwargs`` should be in, built from the names it actually holds.

    Derived rather than written down per chart, so the check cannot drift into a transcript of
    the current signatures -- it states the rule and lets each chart's own parameter set fill
    it in.
    """
    options = [name for name in kwargs if name not in _CROSS_CUTTING + _UNIVERSAL + _DOMAIN]
    return (
        options
        + [name for name in _CROSS_CUTTING if name in kwargs]
        + [name for name in _UNIVERSAL if name in kwargs]
        + [name for name in _DOMAIN if name in kwargs]
    )


def test_the_registry_holds_every_chart_and_nothing_else() -> None:
    """Two claims, and the name says both.

    Non-vacuity first: a change that broke the filter would turn every parametrized case below
    into zero cases and leave a file that asserts nothing while passing -- the shape
    ``test_gallery.py``'s ``<img>`` check once had, which needs only ``>= 1`` to catch. The
    exact count is the second claim and the stronger one: a seventeenth chart has to be
    acknowledged here, which is where somebody notices it must also be added to
    :data:`_CHART_OPTIONS`.
    """
    assert len(_CHARTS) == 16, _CHARTS


@pytest.mark.parametrize("name", _CHARTS)
def test_every_chart_orders_its_keyword_block_the_same_way(name: str) -> None:
    parameters = _parameters(name)
    kwargs = [parameter for parameter, spec in parameters.items() if spec.kind is inspect.Parameter.KEYWORD_ONLY]

    assert kwargs == _expected(kwargs), f"{name} orders its keyword block differently"


@pytest.mark.parametrize("name", _CHARTS)
def test_every_chart_ends_with_width_height_theme(name: str) -> None:
    """Adjacent and in this order, so the three that every chart shares read the same everywhere.

    Separate from the order check because it is the part a reader relies on most: whatever a
    chart's own options are, the tail is the same tail.
    """
    kwargs = [parameter for parameter, spec in _parameters(name).items() if spec.kind is inspect.Parameter.KEYWORD_ONLY]
    positions = [kwargs.index(name_) for name_ in _UNIVERSAL if name_ in kwargs]

    assert len(positions) == 3, f"{name} is missing one of {_UNIVERSAL}"
    assert positions == sorted(positions), f"{name} has {_UNIVERSAL} out of order"
    assert positions[-1] - positions[0] == 2, f"{name} has something wedged inside {_UNIVERSAL}"


@pytest.mark.parametrize("name", _CHARTS)
def test_everything_but_the_channels_is_keyword_only(name: str) -> None:
    """A chart's positional parameters are what it is drawn *from*; every option is named.

    This is what keeps the order check above cheap to satisfy: a keyword-only parameter can be
    reordered without breaking a caller, so the convention can be enforced rather than
    grandfathered.
    """
    positional = [
        parameter for parameter, spec in _parameters(name).items() if spec.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    ]

    assert positional, f"{name} takes nothing positionally, not even data"
    assert positional[0] == "data", f"{name} does not take data first"
    assert set(positional) <= set(_CHANNELS), f"{name} takes {sorted(set(positional) - set(_CHANNELS))} positionally"


_CHART_OPTIONS = {
    "areaplot": {"stacked", "estimator"},
    "barplot": {"orient", "stacked", "estimator"},
    "boxplot": {"mode"},
    "ecdfplot": {"stat", "complementary"},
    "gaugeplot": {"vmin", "vmax"},
    "heatmap": {"cmap", "center", "annot"},
    "histplot": {"bins"},
    "kdeplot": {"bandwidth", "fill"},
    "lineplot": {"interpolate", "estimator"},
    "pieplot": {"inner_radius"},
    "radarplot": {"fill"},
    "regplot": {"ci", "n_boot", "seed", "scatter"},
    "scatterplot": set(),
    "sparkline": set(),
    "treemap": set(),
    "violinplot": {"bandwidth", "inner"},
}
"""Each chart's own options — the keyword parameters that are not shared vocabulary.

A written-down list, and deliberately so. It is what makes
:func:`test_a_chart_uses_the_shared_vocabulary_or_declares_its_own` able to fail: without it,
an unrecognised name simply falls into the "options" bucket and sorts ahead of ``theme``, which
is exactly how a renamed ``xlim`` would pass every other check in this file. Adding a parameter
means adding it here, which is the point — a rename that was not meant to happen shows up as a
test edit somebody has to justify.
"""


@pytest.mark.parametrize("name", _CHARTS)
def test_a_chart_uses_the_shared_vocabulary_or_declares_its_own(name: str) -> None:
    """Every keyword parameter is either shared vocabulary or a declared chart option.

    This is the check with teeth about *names*, and it replaces one that had none. The first
    version listed eight plausible typos (``xlims``, ``x_lim``, ``nbins`` …) and asserted no
    chart used them; measured, ``wrong`` was empty for all sixteen, so all sixteen passed
    vacuously and it discriminated against nothing but those eight literals. Renaming
    ``histplot``'s ``xlim`` to ``x_range`` -- a rename that silently costs the chart its x-axis
    sharing under ``facet`` -- left the whole file green.

    Partitioning against a vocabulary catches that, because ``x_range`` belongs to no bucket.
    """
    kwargs = {parameter for parameter, spec in _parameters(name).items() if spec.kind is inspect.Parameter.KEYWORD_ONLY}
    # ``_CHANNELS`` too: a channel is shared vocabulary wherever it sits, and ``gaugeplot``
    # currently declares ``labels`` keyword-only where ``pieplot``/``treemap`` take it
    # positionally. That disagreement is real and has its own issue; it is not this check's
    # business, which is only whether the *word* is one the package already uses.
    shared = set(_CROSS_CUTTING) | set(_UNIVERSAL) | set(_DOMAIN) | set(_CHANNELS)

    unknown = kwargs - shared - _CHART_OPTIONS[name]

    assert not unknown, (
        f"{name} takes {sorted(unknown)}, which is neither shared vocabulary nor a declared "
        f"option — if it is a renamed shared name, facet will no longer find it"
    )


def test_every_declared_option_is_real() -> None:
    """The other direction, so the list above cannot rot into a wishlist.

    A declared option that no chart takes would quietly widen the partition for that chart,
    letting a future rename through under the name of a parameter that no longer exists.
    """
    stale = {
        name: sorted(options - set(_parameters(name)))
        for name, options in _CHART_OPTIONS.items()
        if options - set(_parameters(name))
    }

    assert _CHART_OPTIONS.keys() == set(_CHARTS), "the option table and the chart registry disagree"
    assert not stale, f"declared options that no longer exist: {stale}"


def test_facet_passes_only_names_this_file_pins() -> None:
    """The other half of the relationship above.

    Checking that charts spell ``xlim`` correctly says nothing unless ``facet`` is still the
    thing asking for ``xlim``. So the names come out of ``facet``'s **assignment sites** --
    every ``overrides[...] = ...`` in the module -- rather than out of one constant beside them.

    A first version read only ``_HORIZONTAL`` and claimed in its own docstring to catch "a fifth
    override added there". It did not: ``ylim`` is built at ``facet.py:189``, outside that
    tuple, and a sixth line inserted next to it left this file green. The assignments are where
    a new override has to appear, so that is what gets read.

    ``import_module``, not ``import svgplot.layout.facet``: ``layout/__init__.py`` re-exports
    the *function* under that name, so the dotted form binds the callable and the module is
    unreachable through it.
    """
    source = Path(import_module("svgplot.layout.facet").__file__).read_text()
    assigned = {
        node.slice.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "overrides"
        and isinstance(node.slice, ast.Constant)
        and isinstance(node.slice.value, str)
    }

    assert assigned, "no overrides[...] assignments found — the pattern is not matching"
    assert assigned == set(_FACET_READS), f"facet passes {sorted(assigned)}; this file pins {sorted(_FACET_READS)}"
