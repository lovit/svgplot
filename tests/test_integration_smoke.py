"""End-to-end smoke tests across the whole public API (issue #21).

Every other test file exercises one module in isolation. This one covers the
cross-cutting combinations nothing else does: every chart type under every
built-in preset, mixed-type compositions, faceting, both sizing modes, and a
real file round-trip. If a module-level refactor breaks how the pieces fit
together, this file is where it should surface.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

import pytest

import svgplot as sp
from svgplot.chart.base import Chart
from svgplot.theme.presets import PRESETS

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
    ("barplot", lambda **kw: sp.barplot(DATA, x="category", y="value", **kw)),
    ("histplot", lambda **kw: sp.histplot(DATA, x="value", bins=4, **kw)),
    ("areaplot", lambda **kw: sp.areaplot(DATA, x="day", y="value", **kw)),
    ("pieplot", lambda **kw: sp.pieplot(DATA, values="value", labels="category", **kw)),
    ("boxplot", lambda **kw: sp.boxplot(DATA, x="group", y="value", **kw)),
    ("ecdfplot", lambda **kw: sp.ecdfplot(DATA, x="value", **kw)),
    ("kdeplot", lambda **kw: sp.kdeplot(DATA, x="value", hue="group", **kw)),
    ("violinplot", lambda **kw: sp.violinplot(DATA, x="group", y="value", **kw)),
    ("regplot", lambda **kw: sp.regplot(DATA, x="day", y="value", **kw)),
]
CHART_IDS = [name for name, _ in CHART_TYPES]
CHART_FACTORIES = [factory for _, factory in CHART_TYPES]


def assert_renders_a_real_chart(svg: str) -> None:
    """A rendered chart must be a well-formed standalone SVG document that actually
    carries chart content — not merely a non-empty string.
    """
    assert svg.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert svg.rstrip().endswith("</svg>")
    assert "<style" in svg, "expected a theme <style> block"
    assert 'class="series-1' in svg or 'class="series-1"' in svg, "expected at least one series-classed mark"
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
            sp.barplot(DATA, x="category", y="value"),
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
    sp.column([sp.lineplot(DATA, x="day", y="value"), sp.barplot(DATA, x="category", y="value")]).save(str(destination))
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

    assert series_rules
    assert all(re.match(r"^c\d+-", rule) for rule in series_rules)


@pytest.mark.parametrize(
    ("factory", "kwargs"),
    [
        pytest.param(sp.ecdfplot, {"x": "value"}, id="ecdfplot"),
        pytest.param(sp.kdeplot, {"x": "value"}, id="kdeplot"),
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
