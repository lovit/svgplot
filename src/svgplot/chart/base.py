"""Chart — the object every ``*plot()`` function returns.

Wraps a single ``svgplot._svg.SvgDocument`` and exposes the imperative
escape-hatch methods recommended in docs/research/11-api-syntax.md
(권고안 B, 근거 5): the primary API is functional (``lineplot(data=...)``),
but the returned Chart can still be customized and always composes with
``svgplot.layout``.
"""

from __future__ import annotations


class Chart:
    """A single rendered chart, backed by one SVG document."""

    def __init__(self, svg_document: object) -> None:
        raise NotImplementedError

    def set_title(self, title: str) -> Chart:
        """Set the chart title. Returns self for chaining."""
        raise NotImplementedError

    def palette(self, spec: str | list[str]) -> Chart:
        """Override the color palette. Returns self for chaining."""
        raise NotImplementedError

    def to_string(self, *, pretty: bool = True) -> str:
        """Serialize to an SVG string. See svgplot.output.svg."""
        raise NotImplementedError

    def save(self, path: str) -> None:
        """Write the chart to a file. See svgplot.output.svg/png."""
        raise NotImplementedError

    def _repr_svg_(self) -> str:
        """Jupyter rich display hook. See svgplot.output.jupyter."""
        raise NotImplementedError
