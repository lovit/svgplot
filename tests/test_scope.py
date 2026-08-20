"""Tests for svgplot.scope — confining a chart's CSS to that chart."""

from __future__ import annotations

import re
import subprocess
import sys
import textwrap
import warnings

import pytest

import svgplot as sp
from svgplot._svg import SvgDocument
from svgplot.layout.sizing import apply_size
from svgplot.scope import RESPONSIVE_CSS, apply_scope, scope_token, validate_css_class_name

DATA = {"x": [1, 2, 3], "y": [1.0, 2.0, 3.0]}
CATEGORIES = {"c": ["a", "b"], "v": [1.0, 2.0]}
SPREAD = {"c": ["a"] * 6, "v": [1.0, 2, 3, 4, 5, 6]}
SAMPLE = {"v": [1.0, 2, 2, 3, 3, 3, 4, 4, 5]}
CATEGORIES3 = {"c": ["a", "b", "c"], "v": [3.0, 1.0, 2.0]}
GAUGE = {"n": ["a"], "v": [50.0]}
GRID = {"c": ["a", "b", "a", "b"], "r": ["p", "p", "q", "q"], "v": [1.0, 2.0, 3.0, 4.0]}
FACETED = {"x": [1, 2, 1, 2], "y": [1.0, 2.0, 3.0, 4.0], "g": ["a", "a", "b", "b"]}

_SCOPED_SELECTOR = re.compile(r":where\(\.[\w-]+\) (\.[\w-]+)")


def _selectors(svg: str) -> set[str]:
    """The fully-qualified selectors a document defines, scope included."""
    return set(re.findall(r":where\(\.[\w-]+\) \.[\w-]+", svg))


# --------------------------------------------------------------------------- the collision


def test_two_charts_in_one_document_no_longer_define_the_same_selector() -> None:
    """The whole point. A line chart's ``.series-1`` sets ``fill: none`` and a bar chart's
    sets a fill; inlined together, whichever came last used to repaint the other."""
    line = sp.lineplot(DATA, x="x", y="y").to_string()
    bar = sp.barplot(CATEGORIES, x="c", y="v").to_string()

    assert _selectors(line), "the line chart defines no scoped selector at all"
    assert not _selectors(line) & _selectors(bar)


def test_the_element_classes_are_untouched() -> None:
    """Only the selector moves. A reader's stylesheet, and every other test in this suite,
    reads the class off the element -- keeping it is what makes the change affordable."""
    svg = sp.lineplot(DATA, x="x", y="y", hue=None).to_string()

    assert 'class="series-1 line-series"' in svg
    assert 'class="plot-background"' in svg


def test_a_scoped_rule_keeps_the_specificity_it_had() -> None:
    """``:where()`` contributes nothing, so the rule still weighs (0,1,0) and a host page's
    own ``.series-1`` competes on source order exactly as before. A bare prefix would make it
    (0,2,0) and silently beat the overrides this package exists to accept."""
    rule = next(line for line in sp.lineplot(DATA, x="x", y="y").to_string().splitlines() if ".series-1 {" in line)
    selector = rule.split("{")[0]

    assert selector.startswith(":where(.")
    assert len(_SCOPED_SELECTOR.findall(selector)) == 1
    assert ">" not in selector and "#" not in selector


def test_every_selector_in_a_comma_list_is_scoped() -> None:
    """``a, b { … }`` prefixed once leaves ``b`` document-global -- a leak in the one shape
    that still looks scoped."""
    document = SvgDocument(width=100, height=100)
    document.add_text(None, ".a, .b { fill: red; }", tag="style")

    token = apply_scope(document)

    assert f":where(.{token}) .a, :where(.{token}) .b {{ fill: red; }}" in document.to_string()


_CHARTS = {
    "lineplot": lambda theme: sp.lineplot(DATA, x="x", y="y", theme=theme),
    "scatterplot": lambda theme: sp.scatterplot(DATA, x="x", y="y", theme=theme),
    "barplot": lambda theme: sp.barplot(CATEGORIES, x="c", y="v", theme=theme),
    "areaplot": lambda theme: sp.areaplot(DATA, x="x", y="y", theme=theme),
    "histplot": lambda theme: sp.histplot(SAMPLE, x="v", theme=theme),
    "pieplot": lambda theme: sp.pieplot(CATEGORIES, values="v", labels="c", theme=theme),
    "boxplot": lambda theme: sp.boxplot(SPREAD, x="c", y="v", theme=theme),
    "violinplot": lambda theme: sp.violinplot(SPREAD, x="c", y="v", theme=theme),
    "kdeplot": lambda theme: sp.kdeplot(SAMPLE, x="v", theme=theme),
    "ecdfplot": lambda theme: sp.ecdfplot(SAMPLE, x="v", theme=theme),
    "regplot": lambda theme: sp.regplot(DATA, x="x", y="y", theme=theme),
    "heatmap": lambda theme: sp.heatmap(GRID, x="c", y="r", values="v", theme=theme),
    "radarplot": lambda theme: sp.radarplot(CATEGORIES3, x="c", y="v", theme=theme),
    "treemap": lambda theme: sp.treemap(CATEGORIES, values="v", labels="c", theme=theme),
    "gaugeplot": lambda theme: sp.gaugeplot(GAUGE, value="v", labels="n", theme=theme),
    "sparkline": lambda theme: sp.sparkline({"y": [1.0, 2, 3]}, y="y", theme=theme),
    "row": lambda theme: sp.row([sp.lineplot(DATA, x="x", y="y", theme=theme), sp.barplot(CATEGORIES, x="c", y="v")]),
    "facet": lambda theme: sp.facet(sp.lineplot, FACETED, col="g", x="x", y="y", theme=theme),
}


@pytest.mark.parametrize("name", sorted(_CHARTS), ids=sorted(_CHARTS))
@pytest.mark.parametrize("theme", sorted(sp.PRESETS), ids=sorted(sp.PRESETS))
def test_no_rule_escapes_its_document(name: str, theme: str) -> None:
    """The guarantee this module exists to give, asserted directly rather than inferred.

    Every other test here reads rules through a ``:where(...)`` pattern, so a rule that escaped
    the rewrite is invisible to them *by construction* -- they would find one fewer match and
    pass. Only the committed-gallery byte diff notices, and that fires for any output change at
    all, which makes it useless for saying *what* broke. Verified by injecting a leaking rule
    (``".legend-swatch,"`` on its own line) into ``theme.css``: this test fails and the rest of
    the file still passes.

    ``RESPONSIVE_CSS`` is the one rule allowed to stay global -- see :func:`apply_scope`.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        svg = _CHARTS[name](theme).to_string()

    rules = [line for block in re.findall(r"<style>(.*?)</style>", svg, re.S) for line in block.splitlines() if line.strip()]
    escaped = [rule for rule in rules if not rule.startswith(":where(.") and rule.strip() != RESPONSIVE_CSS]

    assert rules, f"{name} emitted no CSS at all"
    assert not escaped, f"{name} leaks {len(escaped)} document-global rule(s): {escaped[:3]}"


def test_the_chart_style_block_stays_flat() -> None:
    """The invariant the rewriter rests on: one rule per line, no at-rules. It is a token
    substitution, not a CSS parser, so a ``@media`` block would put a line starting with ``@``
    and a bare closing brace through it, and a selector list split across two lines would leave
    the second selector document-global."""
    svg = sp.lineplot(DATA, x="x", y="y").to_string()

    for block in re.findall(r"<style>(.*?)</style>", svg, re.S):
        for line in block.splitlines():
            if not line.strip():
                continue
            assert line.count("{") == 1 and line.rstrip().endswith("}"), f"not one flat rule: {line!r}"
            assert not line.lstrip().startswith("@"), f"at-rule reaches the rewriter: {line!r}"


# --------------------------------------------------------------------------- the token


def test_the_token_is_stable_across_processes() -> None:
    """A salted hash would satisfy every other test here and break "same input, same SVG" --
    which only shows up as a churning diff in whoever regenerates the gallery next."""
    program = textwrap.dedent(
        """
        import svgplot as sp
        print(sp.lineplot({"x": [1, 2, 3], "y": [1.0, 2.0, 3.0]}, x="x", y="y").to_string())
        """
    )
    runs = {
        subprocess.run(
            [sys.executable, "-c", program],
            capture_output=True,
            text=True,
            check=True,
            env={"PYTHONHASHSEED": "random", "PATH": ""},
        ).stdout
        for _ in range(3)
    }

    assert len(runs) == 1


def test_the_token_follows_the_picture_not_the_title() -> None:
    """The token is computed before the accessibility pass, so naming a chart does not rewrite
    every CSS line in it."""
    plain = sp.lineplot(DATA, x="x", y="y")
    titled = sp.lineplot(DATA, x="x", y="y").set_title("Quarterly sales")

    assert _selectors(plain.to_string()) == _selectors(titled.to_string())


def test_different_pictures_get_different_tokens() -> None:
    tokens = {
        next(iter(_selectors(chart.to_string()))).split(")")[0]
        for chart in (
            sp.lineplot(DATA, x="x", y="y"),
            sp.barplot(CATEGORIES, x="c", y="v"),
            sp.lineplot(DATA, x="x", y="y", theme="dark"),
        )
    }

    assert len(tokens) == 3


def test_identical_pictures_share_a_token_and_that_is_harmless() -> None:
    """Two byte-identical charts collide by construction. Recorded rather than guarded: their
    rules are identical too, so sharing changes nothing -- and it is why ``set_scope`` exists,
    for the caller who needs to style one of them apart."""
    first = sp.lineplot(DATA, x="x", y="y").to_string()
    second = sp.lineplot(DATA, x="x", y="y").to_string()

    assert first == second


# --------------------------------------------------------------------------- what is skipped


def test_the_responsive_rule_is_left_global() -> None:
    """Its class sits on the *root*, and a descendant combinator cannot match the element
    carrying the scope. Scoping it would leave the class in place and the rule syntactically
    fine while responsive sizing quietly stopped working -- a failure with no symptom."""
    svg = apply_size(sp.lineplot(DATA, x="x", y="y"), "responsive").to_string()

    assert RESPONSIVE_CSS in svg
    assert ":where(.svgplot-f" not in svg.split(RESPONSIVE_CSS)[0].rsplit("<style>", 1)[-1]


def test_scoping_does_not_change_what_the_chart_looks_like() -> None:
    """Rendered through cairosvg the scoped and unscoped documents are the same picture. The
    ``png`` extra and libcairo are both optional here, so this skips rather than fails."""
    cairosvg = pytest.importorskip("cairosvg")
    scoped = sp.lineplot(DATA, x="x", y="y").to_string()
    plain = re.sub(r'\sclass="svgplot-f[0-9a-f]+"', "", re.sub(r":where\(\.[\w-]+\)\s*", "", scoped))

    try:
        rendered = (cairosvg.svg2png(bytestring=scoped.encode()), cairosvg.svg2png(bytestring=plain.encode()))
    except OSError as missing_libcairo:  # pragma: no cover - depends on the machine
        pytest.skip(f"cairosvg cannot rasterize here: {missing_libcairo}")

    assert rendered[0] == rendered[1]


# --------------------------------------------------------------------------- set_scope


def test_set_scope_names_the_class_and_chains() -> None:
    chart = sp.lineplot(DATA, x="x", y="y")

    assert chart.set_scope("sales") is chart
    assert chart.scope == "sales"
    assert ":where(.sales) .series-1" in chart.to_string()


def test_set_scope_is_available_on_a_composition_too() -> None:
    """Two *figures* on a page collide the same way two charts do: both emit ``.c0-series-1``
    and ``.composition-caption``."""
    figure = sp.row([sp.lineplot(DATA, x="x", y="y"), sp.lineplot(DATA, x="x", y="y")])

    assert figure.set_scope("panel") is figure
    assert ":where(.panel) .c0-series-1" in figure.to_string()


@pytest.mark.parametrize("bad", ["", "3-leading-digit", "has space", "semi;colon", "brace{}", "dot.dot"])
def test_set_scope_rejects_a_name_that_would_not_survive_a_selector(bad: str) -> None:
    """Stricter than the element-id rule on purpose: XML 1.0 permits ``{``/``}``/``;``, which
    are CSS-breakout characters once the name is written into a selector."""
    with pytest.raises(ValueError, match="class name must match"):
        sp.lineplot(DATA, x="x", y="y").set_scope(bad)


def test_validate_css_class_name_returns_the_name_it_accepted() -> None:
    assert validate_css_class_name("figure-1") == "figure-1"


def test_scope_token_is_a_valid_class_name() -> None:
    """A digit-leading token would be rejected by the very validator that guards ``set_scope``,
    so the prefix is load-bearing rather than decorative."""
    document = SvgDocument(width=10, height=10)

    assert validate_css_class_name(scope_token(document))
