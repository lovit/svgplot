"""Theme -> CSS ``<style>`` block rendering, shared by every chart renderer.

Security (issue #12): ``_svg.py`` validates XML-structural safety for a
``<style>`` element's text content but explicitly does not vet CSS semantics
(see its module docstring's "Security note (issue #12)") — a value that's
individually XML-safe can still break out of a CSS *rule* via ``}``/``;``/
``@import``/``url(...)``. ``Theme`` is normally a trusted, developer-constructed
value object (see ``theme/base.py``'s own security note), but this module is
the first code to ever interpolate its string fields into CSS text, so every
value used here is independently validated before being embedded, regardless
of how trusted the caller believes ``Theme`` to be:

- Colors (``background``/``foreground``/``grid_color``/``spine_color``/
  ``tick_color``, and every ``palette`` entry actually used) must match a
  strict ``#rrggbb`` hex pattern (reusing ``palette._color.HEX_COLOR_RE``) —
  a 7-character string of that exact shape cannot contain any CSS-breaking
  character by construction, so this is sufficient without a general
  CSS-string escaper.
- ``font_family`` must match a conservative allow-listed character set
  (letters, digits, spaces, commas, hyphens, apostrophes — enough for real
  CSS font-family values like ``"Helvetica Neue", Arial, sans-serif``, not
  enough to contain ``{``/``}``/``;``/``:``/``/``).
- Numeric style fields (widths/sizes/opacity) are coerced through
  ``charts._layout.format_coord``, which rejects non-finite/non-numeric
  values before they can reach CSS text. That includes the derived
  ``opacity * fill_opacity`` product used by filled marks, so a bad factor
  can't reach the ``<style>`` block by arriving through the multiplication.
"""

from __future__ import annotations

import re

from svgplot._svg import SvgDocument
from svgplot.charts._layout import format_coord
from svgplot.palette._color import HEX_COLOR_RE
from svgplot.scope import CSS_CLASS_NAME_RE, validate_css_class_name
from svgplot.theme.base import Theme

_FONT_FAMILY_RE = re.compile(r"^[A-Za-z0-9 ,'-]+$")
_CSS_CLASS_NAME_RE = CSS_CLASS_NAME_RE


def _validate_css_color(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not HEX_COLOR_RE.fullmatch(value):
        raise ValueError(f"{field} must be a strict #rrggbb hex color for safe CSS embedding, got {value!r}")
    return value


def _validate_css_font_family(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _FONT_FAMILY_RE.fullmatch(value):
        raise ValueError(
            f"{field} must contain only letters/digits/spaces/commas/hyphens/apostrophes "
            f"for safe CSS embedding, got {value!r}"
        )
    # An odd number of "'" can't inject a new rule (no "{"/"}"/";"/":" allowed by the
    # regex above), but it does leave a CSS string literal unterminated, which silently
    # corrupts every rule after it in the <style> block — not an injection, but still
    # a real breakage this validator should catch (post-merge security review).
    if value.count("'") % 2 != 0:
        raise ValueError(f'{field} has an unterminated quote (odd number of "\'"), got {value!r}')
    return value


_validate_css_class_name = validate_css_class_name


def render_theme_style(
    document: SvgDocument,
    theme: Theme,
    series_classes: list[str],
    *,
    mark_style: str = "stroke",
    level_colors: dict[str, str] | None = None,
    ink_colors: dict[str, str] | None = None,
    transparent_to_pointer: tuple[str, ...] = (),
) -> None:
    """Emit one ``<style>`` element (child of ``document``'s root) with CSS rules for
    the shared static chart elements (background/grid/spine/tick/tick-label/legend-text)
    plus one rule per entry in ``series_classes``, colored by cycling through
    ``theme.palette`` — the same convention ``document.semantic_class("series")``-style
    incrementing class names are meant to pair with.

    ``mark_style`` picks which CSS properties color a series: ``"stroke"`` (the
    default — outlined marks like lines, e.g. ``lineplot``) sets ``stroke``/leaves
    ``fill: none`` and also emits a paired ``.{class}-marker`` rule (``fill: color``)
    for chart types that draw point markers alongside a stroked line/path (e.g. a
    future scatter/line-with-markers chart); ``"fill"`` (solid marks like bars/areas/
    pie slices) sets ``fill``/leaves ``stroke: none`` and emits no separate marker
    rule, since a fill-based mark has no meaningful separate "marker" companion.
    ``"outlined"`` sets *both* — a visible ``stroke`` outline plus a translucent
    ``fill`` (via ``fill-opacity``) — for shapes that are simultaneously bounded and
    filled (violin bodies, filled KDE curves, treemap tiles, radar polygons, gauge
    arcs). That shape is inexpressible with the other two, which force ``fill: none``
    and ``stroke: none`` respectively, and it can't borrow the ``-marker`` rule
    either: that rule carries no opacity, so overlapping hue groups would fully
    occlude, and adding opacity to it would silently change ``boxplot``'s already
    shipped rendering.

    Filled marks are emitted at ``theme.opacity * theme.fill_opacity`` rather than
    ``theme.opacity`` alone, so overlapping fills stay mutually visible by default —
    see :attr:`Theme.fill_opacity <svgplot.theme.base.Theme>` for why fills need that
    and strokes don't. ``"outlined"`` keeps the two factors separate instead of
    pre-multiplying them: its stroke is the shape's boundary and must stay as opaque
    as ``theme.opacity`` says, while only the interior is softened, so the fill
    factor rides on ``fill-opacity`` and the whole-mark factor on ``opacity``.

    ``ink_colors`` maps a CSS class name to an explicit ``#rrggbb`` for **text drawn on top
    of one of those marks** — a heatmap's ``annot=`` labels. It is separate from
    ``level_colors`` rather than folded into it because the two want opposite things from
    opacity: a level colour carries ``theme.opacity`` like every other mark, while ink is
    picked for contrast against the mark underneath it and any opacity blends it back
    toward that mark. It emits ``fill`` alone, so the caller pairs it with a class that
    supplies the font (``tick-label``), and later emission order lets it win the ``fill``
    at equal specificity.

    ``level_colors`` maps a CSS class name to an explicit ``#rrggbb``, for marks whose
    color encodes a *value* rather than a series identity — a heatmap cell's color
    comes from its datum, not from its position in ``theme.palette``. There is no other
    legal way to express that: ``_svg.py`` rejects ``style=`` attributes outright, and a
    ``fill=`` presentation attribute would both regress the CSS-class-only styling
    contract (docs-research/12-aesthetics.md §4) and be invisible to
    ``chart.composition``'s selector-namespacing rewrite, so composing two
    value-colored charts would silently cross-theme them.

    Level rules are **``mark_style``-independent by design**: they always emit
    ``fill``/``stroke: none``, whatever ``mark_style`` the series marks use. A
    value-encoding mark is a filled region — an outline would read as a second visual
    channel carrying no data. So a caller passing ``mark_style="outlined"`` alongside
    ``level_colors`` gets outlined *series* marks and flat-filled *level* marks, which
    is intended rather than an oversight. Duplicate handling differs between the two
    for the same kind of reason: a class repeated inside ``series_classes`` is skipped
    (it would re-emit an identical rule), while a class in both ``series_classes`` and
    ``level_colors`` raises, because those two rules would disagree about the color.

    Meant to be called once per document, after all data marks/axes/legend have been
    added (order doesn't matter for correctness — CSS class rules apply regardless of
    where in the document the matching elements sit — but calling it last keeps a
    reader's mental model of "structure first, styling last" simple).

    ``transparent_to_pointer`` names classes that must not intercept the pointer:
    ``pointer-events: none``, one rule per class. It is a *behaviour* rather than a colour and
    it is here rather than in a caller-written ``<style>`` because this function owns the
    document's only stylesheet -- a second one would be a second place to look. Deliberately a
    list of class names rather than an escape hatch for arbitrary CSS: each name goes through
    the same validation ``series_classes`` does, so nothing can be interpolated into a selector.

    It exists for text drawn *on top of* a mark that has something to say. A ``treemap`` tile's
    label sits inside the tile and takes the pointer, so the tile's own ``<title>`` is
    unreachable exactly where the reader is looking. Empty by default, so a chart that does not
    ask for it emits the stylesheet it emitted before this argument existed.

    Raises:
        ValueError: if any theme color isn't a strict ``#rrggbb`` hex string, if
            ``theme.font_family`` contains a character outside the safe allow-list,
            if any numeric style field isn't finite, if ``mark_style`` isn't
            ``"stroke"``/``"fill"``/``"outlined"``, if a ``level_colors`` key or value
            fails the same validation ``series_classes``/theme colors get, or if a
            class name appears in more than one of ``series_classes``/``level_colors``/
            ``ink_colors``.
    """
    if mark_style not in ("stroke", "fill", "outlined"):
        raise ValueError(f"mark_style must be 'stroke', 'fill', or 'outlined', got {mark_style!r}")
    background = _validate_css_color(theme.background, field="theme.background")
    foreground = _validate_css_color(theme.foreground, field="theme.foreground")
    grid_color = _validate_css_color(theme.grid_color, field="theme.grid_color")
    spine_color = _validate_css_color(theme.spine_color, field="theme.spine_color")
    tick_color = _validate_css_color(theme.tick_color, field="theme.tick_color")
    font_family = _validate_css_font_family(theme.font_family, field="theme.font_family")

    grid_width = format_coord(theme.grid_width)
    spine_width = format_coord(theme.spine_width)
    line_width = format_coord(theme.line_width)
    opacity = format_coord(theme.opacity)
    # Filled marks occlude each other, so they carry an extra factor (see Theme.fill_opacity).
    # Multiplied, not substituted, so theme.opacity still dims every mark type uniformly.
    fill_opacity = format_coord(theme.opacity * theme.fill_opacity)
    # "outlined" keeps the factors on separate properties rather than pre-multiplying:
    # its stroke is the shape's boundary and stays at theme.opacity, while fill-opacity
    # softens only the interior. CSS multiplies them for the fill anyway, so the rendered
    # interior alpha still matches the "fill" branch's product.
    mark_fill_opacity = format_coord(theme.fill_opacity)
    tick_label_size = format_coord(theme.tick_label_font_size)
    legend_size = format_coord(theme.legend_font_size)

    rules = [
        f".plot-background {{ fill: {background}; }}",
        f".grid-line {{ stroke: {grid_color}; stroke-width: {grid_width}; }}",
        f".spine {{ stroke: {spine_color}; stroke-width: {spine_width}; fill: none; }}",
        f".tick-line {{ stroke: {tick_color}; }}",
        f".tick-label {{ fill: {foreground}; font-family: {font_family}; font-size: {tick_label_size}px; }}",
        f".legend-text {{ fill: {foreground}; font-family: {font_family}; font-size: {legend_size}px; }}",
    ]

    palette = theme.palette
    if not palette:
        raise ValueError("theme.palette must not be empty")  # Theme.__post_init__ already enforces this; defense in depth
    seen_classes: set[str] = set()
    for index, class_name in enumerate(series_classes):
        _validate_css_class_name(class_name)
        if class_name in seen_classes:
            continue  # a caller passing the same class twice shouldn't emit a duplicate CSS rule
        seen_classes.add(class_name)
        color = _validate_css_color(palette[index % len(palette)], field=f"theme.palette[{index % len(palette)}]")
        if mark_style == "stroke":
            rules.append(f".{class_name} {{ stroke: {color}; fill: none; stroke-width: {line_width}; opacity: {opacity}; }}")
            rules.append(f".{class_name}-marker {{ fill: {color}; stroke: none; }}")
        elif mark_style == "outlined":
            rules.append(
                f".{class_name} {{ stroke: {color}; stroke-width: {line_width}; "
                f"fill: {color}; fill-opacity: {mark_fill_opacity}; opacity: {opacity}; }}"
            )
        else:
            rules.append(f".{class_name} {{ fill: {color}; stroke: none; opacity: {fill_opacity}; }}")

    for class_name, raw_color in (level_colors or {}).items():
        _validate_css_class_name(class_name, kind="level")
        if class_name in seen_classes:
            # Two rules for one class would leave the winner decided by emission order —
            # a silent, position-dependent override. A caller mixing a palette-colored
            # series with a value-colored level under one name is confused, not clever.
            raise ValueError(f"class name {class_name!r} appears in both series_classes and level_colors")
        seen_classes.add(class_name)
        color = _validate_css_color(raw_color, field=f"level_colors[{class_name!r}]")
        # theme.opacity only — deliberately NOT multiplied by theme.fill_opacity, unlike
        # every other filled mark above. A level color *is* the data encoding: the reader
        # decodes the cell's value from its hue, so blending 25% of the background into it
        # doesn't merely soften the look, it reports a different value for every cell, and
        # uniformly enough that the distortion is invisible. fill_opacity exists to stop
        # overlapping marks from occluding one another (issue #45); level-colored marks
        # tile rather than overlap, so they never had that problem to solve.
        rules.append(f".{class_name} {{ fill: {color}; stroke: none; opacity: {opacity}; }}")

    for class_name, raw_color in (ink_colors or {}).items():
        _validate_css_class_name(class_name, kind="ink")
        if class_name in seen_classes:
            raise ValueError(f"class name {class_name!r} appears in both ink_colors and another color mapping")
        seen_classes.add(class_name)
        color = _validate_css_color(raw_color, field=f"ink_colors[{class_name!r}]")
        # Colour only: no opacity, and no stroke. An ink colour is chosen *against* the mark
        # it sits on, so any opacity blends it back toward that mark and undoes the choice —
        # measured, theme.opacity=0.8 alone drops a heatmap annotation from 4.9:1 to 3.3:1,
        # below WCAG AA. Text is not a tiling mark either, so it never had the occlusion
        # problem theme.opacity and theme.fill_opacity exist to solve.
        rules.append(f".{class_name} {{ fill: {color}; }}")

    for class_name in transparent_to_pointer:
        _validate_css_class_name(class_name, kind="pointer")
        rules.append(f".{class_name} {{ pointer-events: none; }}")

    document.add_text(None, "\n".join(rules), tag="style")
