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
  values before they can reach CSS text.
"""

from __future__ import annotations

import re

from svgplot._svg import SvgDocument
from svgplot.charts._layout import format_coord
from svgplot.palette._color import HEX_COLOR_RE
from svgplot.theme.base import Theme

_FONT_FAMILY_RE = re.compile(r"^[A-Za-z0-9 ,'-]+$")
_CSS_CLASS_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


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


def _validate_css_class_name(value: str) -> str:
    """``series_classes`` entries are also caller-controlled data, not just Theme's
    fields — an unvalidated class name (e.g. ``"x{}body{background:red}.y"``) is just
    as much a CSS-breakout vector as an unvalidated color, so it needs the same
    up-front rejection rather than trusting ``_svg.py``'s XML-only class validation
    (which permits characters like ``{``/``}``/``;`` that are CSS-unsafe but XML-safe).
    """
    if not _CSS_CLASS_NAME_RE.fullmatch(value):
        raise ValueError(f"series class name must match {_CSS_CLASS_NAME_RE.pattern!r} for safe CSS embedding, got {value!r}")
    return value


def render_theme_style(document: SvgDocument, theme: Theme, series_classes: list[str], *, mark_style: str = "stroke") -> None:
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

    Meant to be called once per document, after all data marks/axes/legend have been
    added (order doesn't matter for correctness — CSS class rules apply regardless of
    where in the document the matching elements sit — but calling it last keeps a
    reader's mental model of "structure first, styling last" simple).

    Raises:
        ValueError: if any theme color isn't a strict ``#rrggbb`` hex string, if
            ``theme.font_family`` contains a character outside the safe allow-list,
            if any numeric style field isn't finite, or if ``mark_style`` isn't
            ``"stroke"`` or ``"fill"``.
    """
    if mark_style not in ("stroke", "fill"):
        raise ValueError(f"mark_style must be 'stroke' or 'fill', got {mark_style!r}")
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
        else:
            rules.append(f".{class_name} {{ fill: {color}; stroke: none; opacity: {opacity}; }}")

    document.add_text(None, "\n".join(rules), tag="style")
