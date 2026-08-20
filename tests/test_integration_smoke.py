"""End-to-end smoke tests across the whole public API (issue #21).

Every other test file exercises one module in isolation. This one covers the
cross-cutting combinations nothing else does: every chart type under every
built-in preset, mixed-type compositions, faceting, both sizing modes, and a
real file round-trip. If a module-level refactor breaks how the pieces fit
together, this file is where it should surface.
"""

from __future__ import annotations

import inspect
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

import pytest

import svgplot as sp
from svgplot.chart.base import Chart
from svgplot.charts._layout import DEFAULT_WIDTH, SPARKLINE_WIDTH, format_coord
from svgplot.charts._legend import _SWATCH_HEIGHT, _SWATCH_WIDTH
from svgplot.theme.presets import PRESETS

_ROW_SPACING = 12.0
"""``layout.grid.row``'s default gap. A literal, so the width arithmetic below fails if the
default changes rather than following it."""

# One long-form frame every chart type can read, so the parametrized cases below
# differ only in which plotting function they call.
DATA = {
    "day": [1, 2, 3, 4, 1, 2, 3, 4],
    "value": [10.0, 15.0, 7.0, 20.0, 5.0, 8.0, 3.0, 12.0],
    "weight": [1.0, 4.0, 2.0, 5.0, 3.0, 1.0, 4.0, 2.0],
    "category": ["a", "b", "c", "d", "a", "b", "c", "d"],
    "group": ["x", "x", "x", "x", "y", "y", "y", "y"],
}

# (name, callable) per chart type — add a row here when a new chart type ships.
CHART_TYPES: list[tuple[str, Callable[..., Chart]]] = [
    ("lineplot", lambda **kw: sp.lineplot(DATA, x="day", y="value", **kw)),
    ("scatterplot", lambda **kw: sp.scatterplot(DATA, x="day", y="value", size="weight", **kw)),
    # estimator="mean": the shared fixture carries each category twice (it has to, for the
    # "group" channel), and barplot's default rule would discard one row of each pair and
    # say so with an AggregationWarning. The default rule is covered in test_charts_bar.py;
    # what this file is for is that every chart renders, which a warning only makes noisy.
    ("barplot", lambda **kw: sp.barplot(DATA, x="category", y="value", estimator="mean", **kw)),
    ("histplot", lambda **kw: sp.histplot(DATA, x="value", bins=4, **kw)),
    ("areaplot", lambda **kw: sp.areaplot(DATA, x="day", y="value", **kw)),
    ("pieplot", lambda **kw: sp.pieplot(DATA, values="value", labels="category", **kw)),
    ("boxplot", lambda **kw: sp.boxplot(DATA, x="group", y="value", **kw)),
    ("ecdfplot", lambda **kw: sp.ecdfplot(DATA, x="value", hue="group", **kw)),
    ("kdeplot", lambda **kw: sp.kdeplot(DATA, x="value", hue="group", **kw)),
    ("violinplot", lambda **kw: sp.violinplot(DATA, x="group", y="value", **kw)),
    ("regplot", lambda **kw: sp.regplot(DATA, x="day", y="value", **kw)),
    # y="group" rather than a second numeric column: heatmap needs one value per (x, y)
    # cell and refuses a duplicate, so the two channels have to partition the rows. 8 cells
    # is far under the size warning, which is deliberate -- a smoke test that warns would
    # make every other assertion here run under a filter.
    ("heatmap", lambda **kw: sp.heatmap(DATA, x="day", y="group", values="value", **kw)),
    ("radarplot", lambda **kw: sp.radarplot(DATA, x="category", y="value", hue="group", **kw)),
    ("treemap", lambda **kw: sp.treemap(DATA, values="value", labels="category", **kw)),
    ("sparkline", lambda **kw: sp.sparkline(DATA, y="value", **kw)),
    ("gaugeplot", lambda **kw: sp.gaugeplot(DATA, value="value", labels="category", **kw)),
]
CHART_IDS = [name for name, _ in CHART_TYPES]
CHART_FACTORIES = [factory for _, factory in CHART_TYPES]


def _themed_marks(svg: str) -> list[str]:
    """Elements carrying a themed data class, **excluding legend swatches**.

    ``render_legend`` gives a swatch the same class as the mark it stands for, so a plain
    substring check is satisfied by the legend alone: strip the class off every bar in the
    chart and the assertion still passes against a document whose only coloured thing is
    its key. Measured on four of the five shape charts before this was narrowed.
    """
    body = svg[: svg.index("<style>")] if "<style>" in svg else svg
    return [
        tag
        for tag in re.findall(r"<\w+\b[^>]*/?>", body)
        if (match := re.search(r'class="([^"]*)"', tag))
        and any(name.startswith(("series-", "level-")) for name in match.group(1).split())
        and "legend" not in match.group(1)
        and not _looks_like_a_swatch(tag)
    ]


def _looks_like_a_swatch(tag: str) -> bool:
    """A legend swatch is a ``_SWATCH_WIDTH`` x ``_SWATCH_HEIGHT`` rect, or a line of that
    width. Matched by shape rather than by class, because the whole problem is that it
    shares the mark's class -- and by **importing** the constants rather than repeating
    them, because a hardcoded 16 silently stops matching if ``_legend.py`` ever changes its
    swatch size, which puts every swatch back in the count and reverts this narrowing."""
    size = re.search(rf'width="{format_coord(_SWATCH_WIDTH)}" height="{format_coord(_SWATCH_HEIGHT)}"', tag)
    span = re.search(r'<line x1="(-?[\d.]+)"[^>]*x2="(-?[\d.]+)"', tag)
    return bool(size) or bool(span and float(span.group(2)) - float(span.group(1)) == _SWATCH_WIDTH)


def assert_renders_a_real_chart(svg: str) -> None:
    """A rendered chart must be a well-formed standalone SVG document that actually
    carries chart content — not merely a non-empty string.
    """
    assert svg.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert svg.rstrip().endswith("</svg>")
    assert "<style" in svg, "expected a theme <style> block"
    # Either a series-coloured mark or a value-coloured one. They are alternatives rather
    # than a weakened check: heatmap's colour comes from the datum, not from a position in
    # the palette, so it carries `level-N` and deliberately passes no series classes at all.
    assert _themed_marks(svg), "expected at least one themed data mark outside the legend"
    ET.fromstring(svg)  # parses => structurally valid XML, not just plausible text


# ---------------------------------------------------------------------------
# every chart type x every built-in theme
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("factory", CHART_FACTORIES, ids=CHART_IDS)
def test_every_chart_type_renders_with_the_default_theme(factory: Callable[..., Chart]) -> None:
    assert_renders_a_real_chart(factory().to_string())


@pytest.mark.parametrize("preset", sorted(PRESETS), ids=sorted(PRESETS))
@pytest.mark.parametrize("factory", CHART_FACTORIES, ids=CHART_IDS)
def test_every_chart_type_renders_with_every_built_in_preset(factory: Callable[..., Chart], preset: str) -> None:
    """Themes are cross-cutting: a chart type that only ever gets exercised against
    the default theme can still break on a preset that zeroes a width or swaps a
    color (``minimal`` sets ``tick_size=0``, for instance).
    """
    svg = factory(theme=preset).to_string()
    assert_renders_a_real_chart(svg)
    assert PRESETS[preset].background in svg, "the preset's own background color should reach the CSS"


def test_a_theme_object_and_a_preset_name_are_interchangeable() -> None:
    from_name = sp.lineplot(DATA, x="day", y="value", theme="dark").to_string()
    from_object = sp.lineplot(DATA, x="day", y="value", theme=PRESETS["dark"]).to_string()
    assert from_name == from_object


def test_derived_themes_flow_through_a_render() -> None:
    """``apply_context``/``parametric_theme`` produce Themes like any other, so a
    chart rendered with one must still be a valid chart carrying that theme's colors.
    """
    scaled = sp.apply_context(sp.Theme(), "poster")
    assert_renders_a_real_chart(sp.lineplot(DATA, x="day", y="value", theme=scaled).to_string())

    branded = sp.parametric_theme("#3366cc")
    svg = sp.lineplot(DATA, x="day", y="value", theme=branded).to_string()
    assert_renders_a_real_chart(svg)
    assert branded.palette[0] in svg


# ---------------------------------------------------------------------------
# composition across chart types
# ---------------------------------------------------------------------------


def test_a_composition_of_different_chart_types_serializes_as_one_document() -> None:
    """The composition layer namespaces each child's CSS classes; charts of different
    types are the case most likely to expose a collision, since each brings its own
    class vocabulary.
    """
    composed = sp.row(
        [
            sp.lineplot(DATA, x="day", y="value"),
            sp.barplot(DATA, x="category", y="value", estimator="mean"),
            sp.pieplot(DATA, values="value", labels="category"),
        ]
    )
    svg = composed.to_string()
    ET.fromstring(svg)
    assert svg.rstrip().endswith("</svg>")
    # Each child keeps its own namespaced classes rather than sharing one global set.
    for index in range(3):
        assert f"c{index}-series-1" in svg


def test_composed_children_keep_their_own_theme_colors() -> None:
    """CSS class selectors are document-global, so nesting two charts is exactly the
    situation where one child's ``<style>`` could restyle the other's marks.
    """
    svg = sp.row(
        [
            sp.lineplot(DATA, x="day", y="value", theme="light"),
            sp.lineplot(DATA, x="day", y="value", theme="dark"),
        ]
    ).to_string()
    assert f".c0-plot-background {{ fill: {PRESETS['light'].background}; }}" in svg
    assert f".c1-plot-background {{ fill: {PRESETS['dark'].background}; }}" in svg


def test_grid_and_column_and_caption_compose_together() -> None:
    composed = sp.grid(
        [[sp.lineplot(DATA, x="day", y="value"), None], [None, sp.boxplot(DATA, x="group", y="value")]],
        titles=["왼쪽 위", None, None, "오른쪽 아래"],
    )
    sp.add_caption(composed, "Figure 1. 통합 스모크")
    svg = composed.to_string()
    ET.fromstring(svg)
    assert "Figure 1. 통합 스모크" in svg
    assert "왼쪽 위" in svg


def test_facet_produces_one_panel_per_group() -> None:
    svg = sp.facet(sp.lineplot, DATA, col="group", x="day", y="value").to_string()
    ET.fromstring(svg)
    assert "group = x" in svg
    assert "group = y" in svg


# ---------------------------------------------------------------------------
# sizing, output, import surface
# ---------------------------------------------------------------------------


def test_both_sizing_modes_produce_different_documents() -> None:
    responsive = sp.apply_size(sp.lineplot(DATA, x="day", y="value"), "responsive").to_string()
    fixed = sp.apply_size(sp.lineplot(DATA, x="day", y="value"), "fixed").to_string()

    assert "viewBox" in responsive
    assert "max-width" in responsive
    assert "viewBox" not in fixed
    assert "max-width" not in fixed


@pytest.mark.parametrize("factory", CHART_FACTORIES, ids=CHART_IDS)
def test_saving_a_chart_writes_parseable_svg_to_disk(factory: Callable[..., Chart], tmp_path: Path) -> None:
    """ "Human-readable, hand-editable SVG" is this package's core promise, so the
    file that lands on disk has to parse — asserting on the in-memory string alone
    would not prove the write path produces a usable document.
    """
    destination = tmp_path / "chart.svg"
    factory().save(str(destination))

    written = destination.read_text(encoding="utf-8")
    assert written.strip(), "save() wrote an empty file"
    ET.fromstring(written)
    assert "\n" in written, "saved output should be pretty-printed, not a single line"


def test_saving_a_composition_writes_parseable_svg_to_disk(tmp_path: Path) -> None:
    destination = tmp_path / "composition.svg"
    sp.column([sp.lineplot(DATA, x="day", y="value"), sp.barplot(DATA, x="category", y="value", estimator="mean")]).save(
        str(destination)
    )
    ET.fromstring(destination.read_text(encoding="utf-8"))


def test_every_exported_name_is_importable() -> None:
    missing = [name for name in sp.__all__ if not hasattr(sp, name)]
    assert not missing, f"names in __all__ that aren't actually exported: {missing}"
    assert sp.__version__ == "0.1.0"


def test_a_mixed_composition_of_distribution_charts_keeps_its_namespaces() -> None:
    """The cross-drift an individual chart PR cannot catch: four chart types that each
    mint ``series-N`` classes, placed in one document. Without per-cell prefixes the
    second chart's palette would silently repaint the first."""
    composition = sp.grid(
        [
            [sp.kdeplot(DATA, x="value", hue="group"), sp.violinplot(DATA, x="group", y="value")],
            [sp.regplot(DATA, x="day", y="value"), sp.ecdfplot(DATA, x="value")],
        ]
    )
    svg = composition.to_string()
    series_rules = sorted(set(re.findall(r"\.([a-z0-9-]*series[a-z0-9-]*)\s*\{", svg)))
    prefixes = {rule.split("-")[0] for rule in series_rules}

    assert series_rules
    assert all(re.match(r"^c\d+-", rule) for rule in series_rules)
    # Distinct per cell, not merely present: one shared prefix is exactly the collision
    # this guards against, and it satisfies "every rule is prefixed" just as well.
    assert len(prefixes) == 4


@pytest.mark.parametrize(
    ("factory", "kwargs"),
    [
        pytest.param(sp.ecdfplot, {"x": "value"}, id="ecdfplot"),
        pytest.param(sp.kdeplot, {"x": "value"}, id="kdeplot"),
        # One category per panel here, because faceting by "group" and splitting on
        # "category" too leaves a single value per violin and KDE needs two. The
        # shared y domain that a multi-category panel would exercise is covered in the
        # violin's own tests; what this row checks is that facet forwards the signature.
        pytest.param(sp.violinplot, {"x": "group", "y": "value"}, id="violinplot"),
        pytest.param(sp.regplot, {"x": "day", "y": "value"}, id="regplot"),
    ],
)
def test_the_distribution_charts_facet(factory: Callable[..., Chart], kwargs: dict[str, str]) -> None:
    """``facet`` forwards ``**kwargs`` untouched, so a chart whose signature drifts breaks
    here and nowhere else."""
    composition = sp.facet(factory, DATA, col="group", **kwargs)

    assert len(composition.charts) == 2
    assert composition.to_string().startswith("<?xml")


def test_violinplot_takes_boxplot_s_positional_arguments() -> None:
    """The README tells readers the two share ``(data, x, y)``, so that has to stay true.
    Every other test here calls by keyword, which cannot notice a positional shape drifting
    -- making ``y`` keyword-only breaks the documented swap and nothing else fails."""
    assert sp.violinplot(DATA, "group", "value").to_string()
    assert sp.boxplot(DATA, "group", "value").to_string()

    violin = [
        name
        for name, parameter in inspect.signature(sp.violinplot).parameters.items()
        if parameter.kind is parameter.POSITIONAL_OR_KEYWORD
    ]
    box = [
        name
        for name, parameter in inspect.signature(sp.boxplot).parameters.items()
        if parameter.kind is parameter.POSITIONAL_OR_KEYWORD
    ]

    assert violin == box == ["data", "x", "y"]


# ---------------------------------------------------------------------------
# the shape charts (M8)
# ---------------------------------------------------------------------------


def _classed(svg: str, css_class: str) -> int:
    """How many *elements* carry ``css_class``, ignoring the ``<style>`` block.

    Searching the whole document would count the CSS rule itself, and every chart emits
    every static rule -- so a naive substring check reports a cartesian axis on a pie."""
    body = svg[: svg.index("<style>")] if "<style>" in svg else svg
    return sum(1 for classes in re.findall(r'<\w+\b[^>]*class="([^"]*)"', body) if css_class in classes.split())


@pytest.mark.parametrize(
    ("name", "spines", "has_ticks"),
    [
        ("lineplot", 2, True),
        ("heatmap", 2, True),
        ("radarplot", 0, True),
        ("gaugeplot", 8, True),
        ("treemap", 0, False),
        ("sparkline", 0, False),
        ("pieplot", 0, False),
    ],
)
def test_each_chart_draws_the_frame_its_shape_calls_for(name: str, spines: int, has_ticks: bool) -> None:
    """Whether a chart has a cartesian axis is a design decision per chart, not an accident,
    and the M8 shapes are where it stops being uniform. ``heatmap`` keeps both spines because
    its cells sit on categorical axes; ``radarplot`` replaces them with spokes and rings but
    still labels categories; ``gaugeplot``'s ``spine``-classed paths are its arc
    tracks -- an outlined region rather than an axis, one per row, so the count here is the
    fixture's row count and not a frame at all (its tick ring uses ``tick-line``);
    ``treemap``/``sparkline``/``pieplot`` have no frame at all. A chart silently gaining or losing one would change how
    it reads, and nothing else here would notice."""
    svg = dict(CHART_TYPES)[name]().to_string()

    assert _classed(svg, "spine") == spines
    assert (_classed(svg, "tick-label") > 0) is has_ticks


def test_sparkline_keeps_its_own_canvas_while_every_other_chart_shares_one() -> None:
    """It is the one chart sized to sit inside a sentence, so the shared 800x600 default
    would defeat its entire purpose."""
    sizes = {
        name: re.search(r'width="([\d.]+)" height="([\d.]+)"', factory().to_string()).groups() for name, factory in CHART_TYPES
    }

    assert sizes["sparkline"] == ("120", "24")
    assert {size for name, size in sizes.items() if name != "sparkline"} == {("800", "600")}


@pytest.mark.parametrize(
    ("factory", "kwargs"),
    [
        pytest.param(sp.heatmap, {"x": "day", "y": "category", "values": "value"}, id="heatmap"),
        pytest.param(sp.radarplot, {"x": "category", "y": "value"}, id="radarplot"),
        pytest.param(sp.treemap, {"values": "value", "labels": "category"}, id="treemap"),
        pytest.param(sp.sparkline, {"y": "value"}, id="sparkline"),
        pytest.param(sp.gaugeplot, {"value": "value", "labels": "category"}, id="gaugeplot"),
    ],
)
def test_the_shape_charts_facet(factory: Callable[..., Chart], kwargs: dict[str, str]) -> None:
    """``facet`` forwards ``**kwargs`` untouched, so a chart whose signature drifts breaks
    here and nowhere else. All five work -- they were missing from this file because nobody
    added the rows, not because faceting a shape chart is meaningless."""
    composition = sp.facet(factory, DATA, col="group", **kwargs)
    svg = composition.to_string()

    assert svg.count("<svg") == 3, "expected one root plus two panels"
    ET.fromstring(svg)


def _mixed_size_row() -> str:
    """The **narrow** child first. With the wide one leading, its own width and the widest
    width are the same number, so advancing by ``max(col_widths)`` instead of by each
    column's own puts the second child in exactly the right place anyway -- the two
    formulas coincide and the offset assertion below checks nothing."""
    return sp.row([sp.sparkline(DATA, y="value"), sp.treemap(DATA, values="value", labels="category")]).to_string()


def test_a_composition_gives_each_child_its_own_width() -> None:
    """``sparkline`` is the one chart with its own canvas, which makes it the likeliest
    thing to break a layout that assumes every child is the same size -- so this has to
    assert the *sizes*, not just that the two children were namespaced apart. Sizing every
    column to the widest blows the 120px sparkline's column up to 800 and the sheet from
    932 to 1612, and the version of this test that only checked namespacing stayed green."""
    svg = _mixed_size_row()
    widths = [float(width) for width, _ in re.findall(r'<svg[^>]*width="([\d.]+)" height="([\d.]+)"', svg)]

    root, sparkline_width, treemap_width = widths
    assert (sparkline_width, treemap_width) == (SPARKLINE_WIDTH, DEFAULT_WIDTH)
    assert root == sparkline_width + treemap_width + _ROW_SPACING


def test_a_composition_places_a_narrow_child_right_after_its_neighbour() -> None:
    """The width arithmetic above is satisfied by a sheet that is the right size but leaves
    a gap inside it: advancing by the widest column rather than by each column's own moves
    the second child without changing the total, so the offsets need their own assertion --
    and the narrow child has to lead, or the two formulas agree (see ``_mixed_size_row``)."""
    svg = _mixed_size_row()
    offsets = [float(x) for x in re.findall(r'<svg x="(-?[\d.]+)" y="-?[\d.]+"', svg)]

    assert offsets == [0.0, SPARKLINE_WIDTH + _ROW_SPACING]


def test_a_composition_of_differently_sized_children_keeps_its_namespaces() -> None:
    """The other half, kept separate so neither assertion can stand in for the other."""
    svg = _mixed_size_row()
    rules = [
        rule for block in re.findall(r"<style>(.*?)</style>", svg, re.S) for rule in re.findall(r"^\.([\w-]+)", block, re.M)
    ]

    assert {match.group(1) for rule in rules if (match := re.match(r"(c\d+)-", rule))} == {"c0", "c1"}
    assert not [rule for rule in rules if rule.startswith(("level-", "series-"))]
    ET.fromstring(svg)


def test_a_mixed_composition_of_shape_charts_keeps_its_namespaces() -> None:
    """The shape charts bring two class families the earlier compositions never exercised --
    heatmap's value-coloured ``level-N`` and its annotation ink -- and composition rewrites
    selectors by prefix, so a family it does not know about would cross-theme silently."""
    composition = sp.row(
        [
            sp.heatmap(DATA, x="day", y="group", values="value", annot=True),
            sp.radarplot(DATA, x="category", y="value", hue="group"),
            sp.gaugeplot(DATA, value="value", labels="category"),
        ]
    )
    svg = composition.to_string()
    # One <style> per child plus the composition's own, so the rules have to be gathered
    # from all of them -- reading only the first would report the first child's namespace
    # as the only one and pass against a document that never namespaced the others.
    rules = [
        rule for block in re.findall(r"<style>(.*?)</style>", svg, re.S) for rule in re.findall(r"^\.([\w-]+)", block, re.M)
    ]

    assert {match.group(1) for rule in rules if (match := re.match(r"(c\d+)-", rule))} == {"c0", "c1", "c2"}
    # Nothing escaped the rewrite: no data-mark rule survives without a namespace, which
    # is what would let the second chart's palette repaint the first.
    assert not [rule for rule in rules if rule.startswith(("level-", "series-"))]
    # ...and heatmap's two families both made it through, not just the one composition
    # already knew about.
    assert any(rule.startswith("c0-level-") and rule.endswith("-annotation") for rule in rules)
    ET.fromstring(svg)
