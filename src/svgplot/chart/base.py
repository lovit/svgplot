"""Chart — the object every ``*plot()`` function returns.

Wraps a single ``svgplot._svg.SvgDocument`` and exposes the imperative
escape-hatch methods recommended in docs/research/11-api-syntax.md
(권고안 B, 근거 5): the primary API is functional (``lineplot(data=...)``),
but the returned Chart can still be customized and always composes with
``svgplot.layout``.

``set_title``/``palette`` only record state on the Chart for now — applying a
title to the document (``<title>``/``aria-label``) is ``accessibility.py``'s
job, and resolving a palette spec into actual colors is ``theme``/``palette``'s
job. Both land in later issues and will read this stored state when a chart is
actually rendered.
"""

from __future__ import annotations

from pathlib import Path

from svgplot._svg import SvgDocument
from svgplot.output.jupyter import repr_svg
from svgplot.output.png import to_png
from svgplot.output.svg import save_svg, to_string


class Chart:
    """A single rendered chart, backed by one SVG document."""

    def __init__(self, svg_document: SvgDocument) -> None:
        self._svg_document = svg_document
        self._title: str | None = None
        self._palette: str | list[str] | None = None

    def set_title(self, title: str) -> Chart:
        """Set the chart title. Returns self for chaining."""
        self._title = title
        return self

    def palette(self, spec: str | list[str]) -> Chart:
        """Override the color palette. Returns self for chaining."""
        self._palette = spec
        return self

    def to_string(self, *, pretty: bool = True) -> str:
        """Serialize to an SVG string. See svgplot.output.svg."""
        return to_string(self._svg_document, pretty=pretty)

    def save(self, path: str) -> None:
        """Write the chart to a file. Dispatches on ``path``'s extension: ``.svg`` (see
        svgplot.output.svg) or ``.png`` (see svgplot.output.png, requires the ``png`` extra).

        ``path`` is a filesystem path chosen by the caller — this is a library
        function, not a web endpoint. Callers embedding user-supplied filenames
        (e.g. in a web service) are responsible for validating/resolving them.

        Raises:
            ValueError: if ``path``'s extension is neither ``.svg`` nor ``.png``.
            ImportError: if the extension is ``.png`` and the ``png`` extra isn't installed.
        """
        suffix = Path(path).suffix.lower()
        if suffix == ".svg":
            save_svg(self._svg_document, path)
        elif suffix == ".png":
            to_png(self._svg_document, path)
        else:
            raise ValueError(f"unsupported file extension for Chart.save: {suffix!r} (expected .svg or .png)")

    def _repr_svg_(self) -> str:
        """Jupyter rich display hook. See svgplot.output.jupyter."""
        return repr_svg(self._svg_document)
