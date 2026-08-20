"""Chart — the object every ``*plot()`` function returns.

Wraps a single ``svgplot._svg.SvgDocument`` and exposes the imperative
escape-hatch methods recommended in docs-research/11-api-syntax.md
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

from svgplot._svg import SvgDocument, validate_element_id
from svgplot.accessibility import add_accessibility
from svgplot.chart._domain import Domains
from svgplot.labels._source import LabelData
from svgplot.labels.table import MISSING_TEXT, render_table
from svgplot.output.jupyter import repr_svg
from svgplot.output.markdown import MARKDOWN_SUFFIXES, save_markdown, to_markdown
from svgplot.output.png import to_png
from svgplot.output.svg import save_svg, to_string
from svgplot.scope import apply_scope, validate_css_class_name


class Chart:
    """A single rendered chart, backed by one SVG document."""

    DEFAULT_TITLE = "Chart"
    """Accessible name used when the caller hasn't set one. An empty ``aria-label``
    is worse than a generic one — assistive tech would announce ``role="img"`` with
    no usable name at all (see ``accessibility.add_accessibility``)."""

    DEFAULT_TABLE_ID = "svgplot-data-table"
    """The id an ``info=`` table is referenced by. One page holding two charts with
    ``info=`` needs two distinct ids — see :meth:`set_table_id`."""

    def __init__(
        self,
        svg_document: SvgDocument,
        labels: LabelData | None = None,
        domains: Domains | None = None,
        *,
        description: str | None = None,
    ) -> None:
        self._svg_document = svg_document
        self._title: str | None = None
        self._palette: str | list[str] | None = None
        self._labels = labels
        self._description = description
        self._table_id = self.DEFAULT_TABLE_ID
        self._scope: str | None = None
        self._domains = domains or Domains()

    @property
    def domains(self) -> Domains:
        """What this chart's axes actually spanned.

        Empty for a chart with no cartesian axes (a pie, a treemap). Read by
        :func:`~svgplot.layout.facet.facet` to make several panels agree; see
        ``charts/_domain.py`` for why this is recorded rather than recomputed from the
        data. Not part of the public API surface yet -- it is a chart's report about
        itself, and the shape of that report is still settling.
        """
        return self._domains

    def set_title(self, title: str) -> Chart:
        """Set the chart title. Returns self for chaining."""
        self._title = title
        return self

    def set_table_id(self, table_id: str) -> Chart:
        """Set the element id the ``info=`` table is published and referenced under.

        The default, :attr:`DEFAULT_TABLE_ID`, is fine for one chart on a page. Two charts
        with ``info=`` on the same page must not share it: duplicate ids make
        ``aria-describedby`` resolve to whichever came first, so the second chart would be
        described by the first chart's data. Returns self for chaining.

        Has no effect on a chart built without ``info=``: there is no table to publish, so
        :attr:`table_id` stays ``None`` and no ``aria-describedby`` is written. The id is
        still remembered, so setting it before adding ``info=`` is not a trap either.

        Raises:
            ValueError: if ``table_id`` is empty, contains whitespace, or contains a
                character XML 1.0 forbids — see ``_svg.validate_element_id`` for why the
                stricter of the two documents' rules applies to both.
        """
        validate_element_id(table_id, parameter="table_id")
        self._table_id = table_id
        return self

    def set_scope(self, scope: str) -> Chart:
        """Set the CSS class this chart's own rules are confined to.

        Unset, a deterministic one is derived from the document -- see
        :func:`svgplot.scope.apply_scope`. Name it yourself when you want to target the
        chart from a host stylesheet (``set_scope("sales")`` makes ``.sales .series-1`` yours
        to override), or when two byte-identical charts on a page must be styled apart:
        the derived token is a hash of the picture, so identical pictures share one.

        Returns self for chaining.

        Raises:
            ValueError: if ``scope`` is not a valid CSS class name. The rule is
                ``theme.css``'s, because that is where the name has to survive as a selector.
        """
        self._scope = validate_css_class_name(scope, kind="scope")
        return self

    @property
    def scope(self) -> str | None:
        """The scope class set by :meth:`set_scope`, or ``None`` while it is derived."""
        return self._scope

    @property
    def table_id(self) -> str | None:
        """The id this chart's ``aria-describedby`` points at, or ``None`` when the chart
        was built without ``info=`` and so has no table to point at."""
        return self._table_id if self._labels is not None else None

    def to_html_table(self) -> str | None:
        """The ``info=`` table as an HTML ``<table>`` carrying :attr:`table_id`, or
        ``None`` when the chart has no ``info=``.

        This is the other half of ``aria-describedby``: the attribute is a reference into
        the host document, so it resolves only where an element with that id exists. Emit
        this next to :meth:`to_string`'s output in an HTML page and the reference holds;
        emit the SVG alone and it is ignored, leaving the ``<desc>`` to describe the chart.

        Not what ``.md`` output uses. A GitHub-flavored markdown table cannot carry an id,
        so :meth:`to_markdown` keeps rendering one — and suppresses ``aria-describedby``
        rather than emitting a reference that has nothing to resolve to.
        """
        if self._labels is None:
            return None
        return render_table(
            self._labels.columns, self._labels.spec, format="html", missing=MISSING_TEXT, table_id=self._table_id
        )

    def palette(self, spec: str | list[str]) -> Chart:
        """Override the color palette. Returns self for chaining."""
        self._palette = spec
        return self

    def _accessible_document(self, *, describedby: bool = True) -> SvgDocument:
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

        ``describedby=False`` is for the markdown path, whose table is GitHub-flavored and
        so cannot carry the id the attribute would name — see :meth:`to_html_table`.
        """
        document = copy.deepcopy(self._svg_document)
        # Before add_accessibility, so the derived token is a hash of the picture rather than
        # of the picture plus its title -- otherwise set_title() would rewrite every CSS line.
        apply_scope(document, self._scope)
        add_accessibility(
            document,
            title=(self._title or "").strip() or self.DEFAULT_TITLE,
            desc=self._description,
            describedby=self.table_id if describedby else None,
        )
        return document

    def to_string(self, *, pretty: bool = True, declaration: bool = True) -> str:
        """Serialize to an SVG string. See svgplot.output.svg.

        ``declaration=False`` drops the ``<?xml …?>`` prolog. That is what inlining into an
        HTML document needs: a prolog is only legal at the very start of an entity, so one
        sitting mid-document renders as text and refuses to parse. Passed through rather
        than stripped by the caller so serialization stays in one place --
        :meth:`svgplot._svg.SvgDocument.to_string` gives the reasoning.
        """
        return to_string(self._accessible_document(), pretty=pretty, declaration=declaration)

    def to_markdown(self) -> str:
        """Serialize to inline markdown. See svgplot.output.markdown.

        Raises:
            ValueError: if the serialized SVG contains a blank line (see
                ``svgplot.output.markdown``), or if an ``info=`` value cannot be rendered
                by the format spec it was given. The latter is deferred to here rather
                than caught at plot time: a *missing* value is substituted with
                :data:`~svgplot.labels.table.MISSING_TEXT`, but a present-yet-unformattable
                one (``inf`` under a numeral spec, a float under a datetime spec) has no
                sensible substitute, and validating every row at plot time would make
                ``info=`` cost a full pass over the data whether or not markdown is ever
                asked for.
        """
        return to_markdown(self._accessible_document(describedby=False), self._label_table())

    def _label_table(self) -> str | None:
        """The footnote table to place under the chart, or ``None`` when the chart was
        built without ``info=`` — the normal case, not an error: markdown is a format, not
        a feature flag.

        Rendered at serialization time rather than at plot time, so building a chart stays
        cheap and a chart that is never saved as markdown never pays for the table.

        ``missing=MISSING_TEXT`` rather than ``render_table``'s default refusal: these rows
        already passed the chart's own channel filter, so a hole can only be in a column
        the chart never consulted, and dropping the row would silently shrink the table.
        """
        if self._labels is None:
            return None
        return render_table(self._labels.columns, self._labels.spec, missing=MISSING_TEXT)

    def save(self, path: str) -> None:
        """Write the chart to a file. Dispatches on ``path``'s extension: ``.svg`` (see
        svgplot.output.svg), ``.png`` (see svgplot.output.png, requires the ``png`` extra),
        or ``.md``/``.markdown`` (see svgplot.output.markdown).

        ``path`` is a filesystem path chosen by the caller — this is a library
        function, not a web endpoint. Callers embedding user-supplied filenames
        (e.g. in a web service) are responsible for validating/resolving them.

        Raises:
            ValueError: if ``path``'s extension isn't one of the above, or — for markdown
                output — for anything :meth:`to_markdown` rejects.
            ImportError: if the extension is ``.png`` and the ``png`` extra isn't installed.
        """
        suffix = Path(path).suffix.lower()
        # describedby only where the reference can resolve — the markdown path's table is
        # GFM and cannot carry the id, so it gets a document without the attribute. Built
        # before the suffix is dispatched on, as it always was, so an unrenderable title
        # still reports itself ahead of an unsupported extension.
        document = self._accessible_document(describedby=suffix not in MARKDOWN_SUFFIXES)
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
        """Jupyter rich display hook. See svgplot.output.jupyter.

        No ``aria-describedby``: this hook returns the SVG alone, and a notebook renders
        it into a cell with no table beside it, so the reference would have nothing to
        resolve to. A user who wants both writes :meth:`to_html_table` into its own cell.
        """
        return repr_svg(self._accessible_document(describedby=False))
