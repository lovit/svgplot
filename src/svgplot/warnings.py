"""Warning categories this package raises at runtime.

**Policy: a warning means the output is valid but degraded — anything invalid
raises instead.** A chart that renders correctly yet is too large to embed
comfortably warns; a chart whose input can't produce a correct rendering raises
``ValueError``. Keeping that line sharp is what makes these warnings safe to
silence: a caller who filters them away never loses correctness, only advice.

Every category descends from :class:`SvgplotWarning` so a caller can silence
this package specifically without touching other libraries' warnings::

    warnings.filterwarnings("ignore", category=svgplot.SvgplotWarning)

They descend from ``UserWarning`` rather than ``DeprecationWarning`` because
they describe the *current* call's output, not a future API change — and so
they are shown by default rather than hidden outside ``__main__``.

Despite the module name, this never shadows the standard library's ``warnings``
for any caller: absolute imports mean ``import warnings`` inside this package
still resolves to the stdlib module, and callers reach these names through
``svgplot`` (or ``svgplot.warnings``), never as a bare top-level ``warnings``.
"""

from __future__ import annotations


class SvgplotWarning(UserWarning):
    """Base class for every warning this package emits."""


class HeatmapSizeWarning(SvgplotWarning):
    """A heatmap has enough cells that the SVG is large and its cells are small.

    The chart still renders correctly; the warning carries the cell count and an
    estimated size so the caller can decide whether to aggregate the data or
    export to PNG instead (docs/research/13-svg-opportunity.md).
    """
