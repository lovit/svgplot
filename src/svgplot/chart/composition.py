"""Composition — the object every ``svgplot.layout`` function (row/column/grid) returns.

Holds multiple Chart objects arranged spatially but exposes the same
``.save()``/``.to_string()`` interface as a single Chart, so a composed
"도판" can be saved exactly like any other chart. See
docs-research/16-layout-vocabulary.md.

Composition strategy: each child ``Chart`` is a complete standalone ``<svg>``
document, so children are nested as ``<svg x= y= width= height=>`` elements
inside one outer ``<svg>``. A nested ``<svg>`` establishes its own coordinate
system via its ``viewBox``, so every child's internal coordinates keep working
unchanged (and a child placed into a cell larger/smaller than its natural size
simply scales).

**CSS class namespacing (the reason this module is more than a few lines).**
Each child carries its own ``<style>`` block, and CSS class selectors are
*document-global* — they do not respect nested-``<svg>`` boundaries. Since
``SvgDocument.semantic_class`` restarts its counter per document, every chart
independently emits ``.series-1``, ``.plot-background``, ``.grid-line``, ...
Nesting two charts unchanged would therefore let the second child's rules
restyle the first child's marks: compose a light-themed and a dark-themed
chart and both would render in whichever theme's ``<style>`` came last.

This module fixes that by rewriting each child into its own namespace before
nesting: every class on every element gains a per-child ``c{index}-`` prefix,
and the child's ``<style>`` selectors are rewritten to match. Prefixing (rather
than, say, wrapping rules in an ``#id`` descendant selector) keeps the output
hand-editable — ``c0-series-1`` still reads as "chart 0, series 1", preserving
the semantic-class principle of docs-research/14-scope-recommendation.md.

The rewrite covers *every* class selector in the child's ``<style>``, not only
the classes currently present on an element — ``theme/css.py`` emits some rules
speculatively (``.series-N-marker``), and a rule left un-prefixed would stay
document-global, inert only until some chart type starts using that class. This
is a token-level rewrite, not a general CSS parse, which is sound because
``theme/css.py`` is the only producer of these blocks and validates every value
it embeds (colors are strict ``#rrggbb``, font families exclude ``.``, numbers
come from ``format_coord`` so a decimal point is always followed by a digit), so
a class-name token cannot appear inside a declaration *value* — see that
module's docstring for the guarantees.
"""

from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from svgplot._svg import SvgDocument
from svgplot.accessibility import add_accessibility
from svgplot.chart.base import Chart
from svgplot.charts._layout import format_coord
from svgplot.output.jupyter import repr_svg
from svgplot.output.markdown import MARKDOWN_SUFFIXES, save_markdown, to_markdown
from svgplot.output.png import to_png
from svgplot.output.svg import save_svg, to_string

# A CSS class selector in a child's <style>. Matching every ".identifier" is sound
# only because theme/css.py is the sole producer of these blocks and validates every
# value it embeds: colors are strict "#rrggbb", numbers come from format_coord (so a
# decimal point is always followed by a digit, never a letter), and font families
# exclude "." outright. A class-name token therefore cannot appear inside a
# declaration value — see that module's docstring for the full guarantee.
_SELECTOR_RE = re.compile(r"\.([A-Za-z_][A-Za-z0-9_-]*)")

# Composition-level chrome (captions, per-cell titles) can't reuse a child's CSS
# rules — those are namespaced per child by design — so the composition emits its
# own small <style>. Every value here is a module constant with no interpolation
# from caller input, and each is validated before use anyway (see
# _render_composition_style), which is the same bar theme/css.py sets for the
# only other sanctioned <style> producer in the package.
_CAPTION_COLOR = "#111111"
_CAPTION_FONT_FAMILY = "sans-serif"
_CAPTION_FONT_SIZE = 14.0
_TITLE_FONT_SIZE = 13.0
_CAPTION_CLASS = "composition-caption"
_TITLE_CLASS = "composition-title"
_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_FONT_FAMILY_RE = re.compile(r"^[A-Za-z0-9 ,'-]+$")

CAPTION_HEIGHT = 28.0
"""Vertical space a caption reserves (text baseline sits inside this band)."""

TITLE_HEIGHT = 22.0
"""Vertical space a per-cell title reserves above its chart."""


@dataclass(frozen=True)
class Placement:
    """One chart placed at an absolute pixel rect inside the composed canvas.

    ``title`` renders as a heading immediately above the chart's rect (the
    "Tabs 대체" idiom of docs-research/16-layout-vocabulary.md); the rect is
    the chart's own area and already excludes the title band.
    """

    chart: Chart
    x: float
    y: float
    width: float
    height: float
    title: str | None = None


def chart_document(chart: Chart) -> SvgDocument:
    """Return the ``SvgDocument`` backing ``chart``.

    ``Chart`` deliberately keeps its document private (it exposes serialization,
    not its internals), but composing charts is fundamentally a document-level
    operation. This package-internal accessor keeps that coupling in one named,
    documented place rather than scattering ``chart._svg_document`` reads across
    the layout modules, and avoids widening ``Chart``'s public API for a need
    only ``svgplot.layout`` has.
    """
    return chart._svg_document


def chart_size(chart: Chart) -> tuple[float, float]:
    """Return ``(width, height)`` of a chart's own canvas."""
    document = chart_document(chart)
    return float(document.width), float(document.height)


def composition_document(composition: Composition) -> SvgDocument:
    """Return the ``SvgDocument`` backing ``composition`` — the :func:`chart_document`
    counterpart for an already-composed canvas, used by layout passes that adjust a
    composition after the fact (e.g. ``layout.caption.add_caption``).
    """
    return composition._svg_document


def composition_title(composition: Composition) -> str | None:
    """Return the accessible name a caller actually set on ``composition``, or ``None``.

    The :func:`composition_document` counterpart for the accessible name, and for the
    same reason: ``layout`` passes need to know whether a name is already set (see
    ``layout.caption.add_caption``, which only adopts its text when one isn't), and
    that read belongs in one named, documented place rather than as a bare
    ``composition._title`` in each layout module.

    Delegates to :meth:`Composition._resolved_title`, so "already set" means exactly
    what the render path means by it — a whitespace-only title reads as unset here
    just as it falls back to :attr:`Composition.DEFAULT_TITLE` there. Were the two to
    disagree, ``set_title("  ")`` followed by ``add_caption("Figure 3")`` would render
    the caption visibly while announcing the generic default.
    """
    return composition._resolved_title()


def _namespaced_child_root(chart: Chart, prefix: str) -> ET.Element:
    """Deep-copy ``chart``'s root element and rewrite its classes into ``prefix``'s namespace.

    Returns a detached ``<svg>`` element safe to nest into another document: the
    original chart is never mutated, so composing a chart doesn't disturb it (or
    any other composition it also appears in).
    """
    root = copy.deepcopy(chart_document(chart).root)

    for element in root.iter():
        class_attribute = element.get("class")
        if class_attribute is None:
            continue
        names = class_attribute.split()
        element.set("class", " ".join(f"{prefix}-{name}" for name in names))

    # Rewrite *every* class selector in the child's <style>, not only the classes
    # that happen to sit on an element today: theme/css.py emits some rules
    # speculatively (e.g. ".series-1-marker" for chart types that draw point
    # markers), and a rule left un-prefixed would stay document-global — inert
    # only until some chart type starts using that class, at which point two
    # children would silently collide again. Rewriting the whole block keeps the
    # namespace airtight regardless of which rules are currently exercised.
    for element in root.iter():
        if element.tag == "style" and element.text:
            element.text = _SELECTOR_RE.sub(lambda match: f".{prefix}-{match.group(1)}", element.text)

    return root


def _validate_constant_color(value: str, *, field: str) -> str:
    if not _HEX_COLOR_RE.fullmatch(value):
        raise ValueError(f"{field} must be a strict #rrggbb hex color for safe CSS embedding, got {value!r}")
    return value


def _validate_constant_font_family(value: str, *, field: str) -> str:
    if not _FONT_FAMILY_RE.fullmatch(value) or value.count("'") % 2 != 0:
        raise ValueError(f"{field} is not a safely embeddable CSS font-family, got {value!r}")
    return value


def _render_composition_style(document: SvgDocument) -> None:
    """Emit the composition's own ``<style>`` block (caption/title text only).

    Mirrors ``theme/css.py``'s contract: every embedded value is validated before
    it reaches CSS text, even though all of them are module constants here.
    """
    color = _validate_constant_color(_CAPTION_COLOR, field="caption color")
    font_family = _validate_constant_font_family(_CAPTION_FONT_FAMILY, field="caption font family")
    caption_size = format_coord(_CAPTION_FONT_SIZE)
    title_size = format_coord(_TITLE_FONT_SIZE)
    rules = [
        f".{_CAPTION_CLASS} {{ fill: {color}; font-family: {font_family}; font-size: {caption_size}px; }}",
        f".{_TITLE_CLASS} {{ fill: {color}; font-family: {font_family}; font-size: {title_size}px; font-weight: bold; }}",
    ]
    document.add_text(None, "\n".join(rules), tag="style")


def compose(placements: list[Placement], width: float, height: float) -> SvgDocument:
    """Build the composed ``SvgDocument`` for already-positioned ``placements``."""
    document = SvgDocument(width=width, height=height)
    for index, placement in enumerate(placements):
        if placement.title is not None:
            document.add_text(
                None,
                placement.title,
                tag="text",
                attrib={"x": format_coord(placement.x), "y": format_coord(placement.y - TITLE_HEIGHT / 3)},
                classes=[_TITLE_CLASS],
            )
        child_root = _namespaced_child_root(placement.chart, f"c{index}")
        nested = document.add_node(
            None,
            "svg",
            attrib={
                "x": format_coord(placement.x),
                "y": format_coord(placement.y),
                "width": format_coord(placement.width),
                "height": format_coord(placement.height),
            },
        )
        for key, value in child_root.attrib.items():
            if key in ("x", "y", "width", "height", "xmlns"):
                continue  # the outer placement owns position/size; xmlns is inherited
            document.set_attribute(nested, key, value)
        if "viewBox" not in nested.attrib:
            # Nesting scales a child to its cell only via viewBox — without one, the
            # child keeps its intrinsic coordinates and is clipped whenever the cell
            # is smaller than it. apply_size(chart, "fixed") deliberately strips
            # viewBox, so restore it here from the child's own size rather than
            # forbidding fixed-then-compose: composition owns cell fitting, and a
            # caller shouldn't have to know the two features interact.
            child_document = chart_document(placement.chart)
            viewbox = f"0 0 {format_coord(child_document.width)} {format_coord(child_document.height)}"
            document.set_attribute(nested, "viewBox", viewbox)
        nested.extend(list(child_root))
    _render_composition_style(document)
    return document


class Composition:
    """A spatial arrangement of one or more Chart objects.

    Exposes the same serialization surface as :class:`~svgplot.chart.base.Chart`
    (``to_string``/``save``/``_repr_svg_``) so a composed figure is saved exactly
    like a single chart.
    """

    DEFAULT_TITLE = "Chart composition"
    """Accessible name used when neither :meth:`set_title` nor a caption supplied one.
    Deliberately distinct from ``Chart.DEFAULT_TITLE`` so a screen-reader user can tell
    a multi-panel figure from a single chart without exploring it."""

    def __init__(self, document: SvgDocument, charts: list[Chart]) -> None:
        """``document`` is the composed canvas built by a ``svgplot.layout`` function;
        ``charts`` are the children it was built from, kept so a composition can be
        re-laid-out (e.g. by :func:`svgplot.layout.caption.add_caption`) without the
        caller having to hold onto them separately.
        """
        self._svg_document = document
        self._charts = list(charts)
        self._title: str | None = None

    def set_title(self, title: str) -> Composition:
        """Set the composition's accessible name. Returns self for chaining.

        Mirrors :meth:`svgplot.chart.base.Chart.set_title`. ``layout.add_caption`` also
        sets this when it isn't already set, since a caption *is* the figure's name —
        announcing a generic default while a visible caption reads "Figure 3. Quarterly
        revenue" would be strictly worse for a screen-reader user.

        ``grid(titles=...)`` deliberately does *not* feed this. Those are per-cell
        headings, so there is no single one of them to name the whole figure by, and
        concatenating them would announce the panel list before the reader learns what
        the figure even is. They stay visible chrome; the figure's name comes from
        ``set_title``, a caption, or :attr:`DEFAULT_TITLE`.
        """
        self._title = title
        return self

    def _resolved_title(self) -> str | None:
        """The accessible name a caller actually set, or ``None`` if none is in effect.

        The single definition of "unset" for this class: both the render path below and
        ``layout.caption.add_caption`` (via :func:`composition_title`) ask this, so a
        whitespace-only title can't count as set in one and unset in the other.
        """
        return (self._title or "").strip() or None

    def _accessible_document(self) -> SvgDocument:
        """Return a copy of the composed document with role/aria/title/desc applied.

        Same copy-based approach as :meth:`svgplot.chart.base.Chart._accessible_document`
        and for the same reasons — ``add_accessibility`` appends and is once-per-document,
        while every serialization path is repeatedly callable.

        Only the *outer* document gets these: children were nested from
        ``chart_document()`` (the charts' raw documents, before ``Chart``'s own
        accessibility pass), so a composed figure announces one name rather than one
        per panel. ``test_composition_children_do_not_carry_their_own_accessibility``
        pins that.

        The panel count is ``len(self._charts)``, which is the number of charts actually
        placed — ``layout.grid`` drops ``None`` blank cells before building the
        ``Composition``, so a blank never inflates the count a screen reader announces.
        """
        document = copy.deepcopy(self._svg_document)
        count = len(self._charts)
        add_accessibility(
            document,
            title=self._resolved_title() or self.DEFAULT_TITLE,
            desc=f"A figure composed of {count} chart{'' if count == 1 else 's'}.",
        )
        return document

    @property
    def charts(self) -> list[Chart]:
        """The child charts, in placement order (a copy — mutating it changes nothing)."""
        return list(self._charts)

    def to_string(self, *, pretty: bool = True, declaration: bool = True) -> str:
        """Serialize to an SVG string. See svgplot.output.svg.

        ``declaration=False`` drops the ``<?xml …?>`` prolog, for inlining into an HTML
        document. Same contract as :meth:`svgplot.chart.base.Chart.to_string`.
        """
        return to_string(self._accessible_document(), pretty=pretty, declaration=declaration)

    def to_markdown(self) -> str:
        """Serialize to inline markdown. See svgplot.output.markdown.

        A composition carries no table of its own: gathering the children's is a follow-up
        (which child gets a heading? what if only some have ``info=``? is a facet grid one
        table or N?). The format is supported here regardless, because this class promises
        the same serialization surface as :class:`~svgplot.chart.base.Chart` and supporting
        markdown on only one of them would break that documented invariant.
        """
        return to_markdown(self._accessible_document())

    def save(self, path: str) -> None:
        """Write the composition to a file, dispatching on ``path``'s extension
        (``.svg``/``.png``/``.md``/``.markdown``) exactly as
        :meth:`svgplot.chart.base.Chart.save` does.

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
            save_markdown(document, None, path)
        else:
            raise ValueError(
                f"unsupported file extension for Composition.save: {suffix!r} "
                f"(expected .svg, .png or one of {MARKDOWN_SUFFIXES})"
            )

    def _repr_svg_(self) -> str:
        """Jupyter rich display hook. See svgplot.output.jupyter."""
        return repr_svg(self._accessible_document())
