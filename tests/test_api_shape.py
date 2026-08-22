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

import inspect
from importlib import import_module

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


def test_the_registry_is_not_empty() -> None:
    """Without this, a change that broke the filter would turn every case below into zero cases
    and leave a file that asserts nothing while passing -- the shape ``test_gallery.py``'s
    ``<img>`` check once had."""
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


@pytest.mark.parametrize("name", _CHARTS)
def test_a_chart_spells_the_names_facet_looks_for(name: str) -> None:
    """``facet`` finds these by name, so a synonym loses axis sharing in silence.

    The assertion is one-sided on purpose: a chart may lack any of them -- ``pieplot`` has no
    cartesian axis to share -- but a chart that shares that *concept* must use that *word*. The
    counterpart, that ``facet`` only ever passes these four, is asserted below.
    """
    parameters = _parameters(name)
    near_misses = {
        "xlims": "xlim",
        "ylims": "ylim",
        "x_lim": "xlim",
        "y_lim": "ylim",
        "bin": "bins",
        "nbins": "bins",
        "category": "categories",
        "cats": "categories",
    }

    wrong = {found: want for found, want in near_misses.items() if found in parameters}

    assert not wrong, f"{name} spells {wrong} — facet reads these by name and would not find them"


def test_facet_passes_only_names_this_file_pins() -> None:
    """The other half of the relationship above.

    Checking that charts spell ``xlim`` correctly says nothing unless ``facet`` is still the
    thing asking for ``xlim``. Read out of ``facet``'s own source rather than restated, so a
    fifth override added there fails this until it is pinned here too.
    """
    # ``import_module``, not ``import svgplot.layout.facet as facet``: ``layout/__init__.py``
    # re-exports the *function* under that name, so the dotted form binds the callable and the
    # module's constants are unreachable through it.
    facet_module = import_module("svgplot.layout.facet")

    assert set(facet_module._HORIZONTAL) <= set(_FACET_READS), facet_module._HORIZONTAL
    assert set(_FACET_READS) - set(facet_module._HORIZONTAL) == {"ylim"}, "ylim is applied in the second pass"
