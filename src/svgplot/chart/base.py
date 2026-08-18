"""Chart — the object every ``*plot()`` function returns.

Wraps a single ``svgplot._svg.SvgDocument`` and exposes the imperative
escape-hatch methods recommended in docs/research/11-api-syntax.md
(권고안 B, 근거 5): the primary API is functional (``lineplot(data=...)``),
but the returned Chart can still be customized and always composes with
``svgplot.layout``.

``set_title`` is applied at render time, not when it's called: every
serialization path runs the stored document through ``accessibility.py`` first
(see :meth:`Chart._accessible_document`). ``palette`` still only records state —
resolving a spec into actual colors is ``theme``/``palette``'s job, landing in a
later issue.
"""

from __future__ import annotations

import copy
from pathlib import Path

from svgplot._svg import SvgDocument
from svgplot.accessibility import add_accessibility
from svgplot.output.jupyter import repr_svg
from svgplot.output.markdown import MARKDOWN_SUFFIXES, save_markdown, to_markdown
from svgplot.output.png import to_png
from svgplot.output.svg import save_svg, to_string


class Chart:
    """A single rendered chart, backed by one SVG document."""

    DEFAULT_TITLE = "Chart"
    """Accessible name used when the caller hasn't set one. An empty ``aria-label``
    is worse than a generic one — assistive tech would announce ``role="img"`` with
    no usable name at all (see ``accessibility.add_accessibility``)."""

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

    def _accessible_document(self) -> SvgDocument:
        """Return a copy of the document with role/aria/title/desc applied.

        A *copy*, because ``add_accessibility`` appends ``<title>``/``<desc>`` and is
        documented as once-per-document — but ``to_string``/``save``/``_repr_svg_``
        are all callable repeatedly, so mutating the stored document would stack a
        fresh pair on every render. Applying to a throwaway copy also means a
        ``set_title()`` after an earlier render still takes effect, since the title
        is read at serialization time rather than baked in once.

        A whitespace-only title falls back to :attr:`DEFAULT_TITLE` just like an empty
        one. Without the ``strip()`` the two diverge — ``""`` falls back quietly while
        ``"   "`` reaches ``add_accessibility``'s empty-title ``ValueError``, which
        would then surface at ``save()`` time rather than at the ``set_title()`` call
        that caused it.
        """
        document = copy.deepcopy(self._svg_document)
        add_accessibility(document, title=(self._title or "").strip() or self.DEFAULT_TITLE)
        return document

    def to_string(self, *, pretty: bool = True) -> str:
        """Serialize to an SVG string. See svgplot.output.svg."""
        return to_string(self._accessible_document(), pretty=pretty)

    def to_markdown(self) -> str:
        """Serialize to inline markdown. See svgplot.output.markdown."""
        return to_markdown(self._accessible_document(), self._label_table())

    def _label_table(self) -> str | None:
        """The footnote table to place under the chart, or ``None`` for none.

        Always ``None`` here: wiring ``info=`` through to a rendered table is issue #69.
        Markdown output does not wait on it — the format is useful for a chart with no
        labels at all, and returning ``None`` is what makes that the normal case rather
        than an error.
        """
        return None

    def save(self, path: str) -> None:
        """Write the chart to a file. Dispatches on ``path``'s extension: ``.svg`` (see
        svgplot.output.svg), ``.png`` (see svgplot.output.png, requires the ``png`` extra),
        or ``.md``/``.markdown`` (see svgplot.output.markdown).

        ``path`` is a filesystem path chosen by the caller — this is a library
        function, not a web endpoint. Callers embedding user-supplied filenames
        (e.g. in a web service) are responsible for validating/resolving them.

        Raises:
            ValueError: if ``path``'s extension isn't one of the above, or if markdown
                output is requested and the serialized SVG contains a blank line.
            ImportError: if the extension is ``.png`` and the ``png`` extra isn't installed.
        """
        suffix = Path(path).suffix.lower()
        document = self._accessible_document()
        if suffix == ".svg":
            save_svg(document, path)
        elif suffix == ".png":
            to_png(document, path)
        elif suffix in MARKDOWN_SUFFIXES:
            save_markdown(document, self._label_table(), path)
        else:
            raise ValueError(
                f"unsupported file extension for Chart.save: {suffix!r} "
                f"(expected .svg, .png or one of {MARKDOWN_SUFFIXES})"
            )

    def _repr_svg_(self) -> str:
        """Jupyter rich display hook. See svgplot.output.jupyter."""
        return repr_svg(self._accessible_document())
