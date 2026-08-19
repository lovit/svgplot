from __future__ import annotations

import pytest

from svgplot._svg import SvgDocument
from svgplot.charts._legend import render_legend


def test_render_legend_stroke_mark_style_draws_line_swatches() -> None:
    document = SvgDocument()
    render_legend(document, [("A", "series-1"), ("B", "series-2")], x=10.0, y=20.0, font_size=11.0)

    swatches = document.root.findall(".//line[@class='series-1']") + document.root.findall(".//line[@class='series-2']")
    assert len(swatches) == 2
    assert not document.root.findall(".//rect[@class='series-1']")


def test_render_legend_fill_mark_style_draws_rect_swatches() -> None:
    document = SvgDocument()
    render_legend(document, [("A", "series-1")], x=10.0, y=20.0, mark_style="fill", font_size=11.0)

    assert document.root.findall(".//rect[@class='series-1']")
    assert not document.root.findall(".//line[@class='series-1']")


def test_render_legend_rejects_unknown_mark_style() -> None:
    document = SvgDocument()
    with pytest.raises(ValueError, match="mark_style"):
        render_legend(document, [("A", "series-1")], x=0.0, y=0.0, mark_style="bogus", font_size=11.0)


def test_render_legend_labels_each_entry() -> None:
    document = SvgDocument()
    render_legend(document, [("A", "series-1"), ("B", "series-2")], x=10.0, y=20.0, font_size=11.0)

    labels = [node.text for node in document.root.findall(".//text[@class='legend-text']")]
    assert labels == ["A", "B"]


def test_render_legend_rows_do_not_overlap() -> None:
    document = SvgDocument()
    render_legend(
        document,
        [("A", "series-1"), ("B", "series-2"), ("C", "series-3")],
        x=10.0,
        y=20.0,
        font_size=11.0,
    )

    labels = document.root.findall(".//text[@class='legend-text']")
    y_positions = [float(label.get("y")) for label in labels]
    assert y_positions == sorted(y_positions)
    assert len(set(y_positions)) == len(y_positions)


# ---------------------------------------------------------------------------
# labels that do not fit (issue #112)
# ---------------------------------------------------------------------------

import re  # noqa: E402

import svgplot as sp  # noqa: E402
from svgplot.charts._layout import DEFAULT_WIDTH  # noqa: E402
from svgplot.charts._textwidth import text_width  # noqa: E402

_LONG_KO = "매우 긴 카테고리 이름입니다 정말로 깁니다"


def _legend_labels(svg: str) -> list[tuple[float, str]]:
    return [(float(x), text) for x, text in re.findall(r'<text x="(-?[\d.]+)"[^>]*class="legend-text"[^>]*>([^<]*)<', svg)]


def test_a_long_label_stays_inside_the_canvas() -> None:
    """It used to run past the ``viewBox``, where nothing renders it -- 118px of room on the
    default canvas is about 11 CJK characters, an ordinary Korean label length."""
    svg = sp.barplot({"x": ["a", "b"], "y": [1.0, 2.0], "g": [_LONG_KO, "짧음"]}, x="x", y="y", hue="g").to_string()

    for start, text in _legend_labels(svg):
        assert start + text_width(text, 11.0) <= DEFAULT_WIDTH


def test_the_full_text_survives_in_a_title() -> None:
    """Shortening must cost presentation, not information. Without this the cut characters
    are simply gone -- worse than the overflow, which at least kept them in the file."""
    svg = sp.barplot({"x": ["a", "b"], "y": [1.0, 2.0], "g": [_LONG_KO, "짧음"]}, x="x", y="y", hue="g").to_string()

    assert _LONG_KO not in [text for _, text in _legend_labels(svg)], "expected the shown label to be cut"
    assert f"<title>{_LONG_KO}</title>" in svg


def test_a_label_that_fits_gets_no_title_and_no_ellipsis() -> None:
    """Every existing chart's legend has to come out exactly as before. A ``<title>`` on
    each row would also double the legend's markup in a file meant to be hand-editable."""
    svg = sp.barplot({"x": ["a", "b"], "y": [1.0, 2.0], "g": ["짧음", "b"]}, x="x", y="y", hue="g").to_string()

    assert [text for _, text in _legend_labels(svg)] == ["b", "짧음"]
    assert "<title>짧음</title>" not in svg


def test_a_korean_label_is_cut_sooner_than_a_latin_one() -> None:
    """The two are charged differently, and this is the case that motivated the fix: the
    same budget holds about twice as many Latin characters."""

    def shown(label: str) -> str:
        svg = sp.barplot({"x": ["a", "b"], "y": [1.0, 2.0], "g": [label, "z"]}, x="x", y="y", hue="g").to_string()
        return next(text for _, text in _legend_labels(svg) if text != "z")

    assert len(shown("가" * 40)) < len(shown("a" * 40))


# Every chart that draws a legend. An earlier version listed seven and the commit message
# claimed "all of them", which was wrong by five.
_LEGEND_CHARTS = {
    "barplot": lambda data, label: sp.barplot(data, x="x", y="y", hue="g"),
    "lineplot": lambda data, label: sp.lineplot(data, x="d", y="y", hue="g"),
    "scatterplot": lambda data, label: sp.scatterplot(data, x="d", y="y", hue="g"),
    "areaplot": lambda data, label: sp.areaplot(data, x="d", y="y", hue="g"),
    "pieplot": lambda data, label: sp.pieplot(data, values="v", labels="g"),
    "treemap": lambda data, label: sp.treemap(data, values="v", labels="g"),
    "gaugeplot": lambda data, label: sp.gaugeplot(data, value="v", labels="g"),
    "histplot": lambda data, label: sp.histplot(data, x="y", hue="g", bins=2),
    "ecdfplot": lambda data, label: sp.ecdfplot(data, x="y", hue="g"),
    "heatmap": lambda data, label: sp.heatmap(data, x="x", y="g", values="v"),
    "radarplot": lambda data, label: sp.radarplot(
        {"c": ["a", "b", "c"] * 2, "v": [1.0, 2.0, 3.0] * 2, "g": [label] * 3 + ["짧음"] * 3}, x="c", y="v", hue="g"
    ),
    "kdeplot": lambda data, label: sp.kdeplot(
        {"y": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0], "g": [label] * 3 + ["짧음"] * 3}, x="y", hue="g"
    ),
}


@pytest.mark.parametrize("name", sorted(_LEGEND_CHARTS), ids=sorted(_LEGEND_CHARTS))
@pytest.mark.parametrize("label", [_LONG_KO, "W" * 40, "0123456789" * 4, "M" * 40], ids=["ko", "W", "digits", "M"])
def test_every_chart_that_draws_a_legend_keeps_its_labels_inside(name: str, label: str) -> None:
    """Not one representative chart but all twelve, and not one label but the character
    classes the width model treats differently. ``render_legend`` derives the room itself
    now, but each chart still chooses where the legend starts."""
    data = {"x": ["a", "b"], "y": [1.0, 2.0], "v": [1.0, 2.0], "g": [label, "짧음"], "d": [1, 2]}
    svg = _LEGEND_CHARTS[name](data, label).to_string()
    labels = _legend_labels(svg)

    assert labels, f"{name} drew no legend"
    for start, text in labels:
        assert start + text_width(text, 11.0) <= DEFAULT_WIDTH, f"{name}: {text!r} overflows"


def test_the_room_is_read_from_the_document_not_a_constant() -> None:
    """``render_legend`` derives the room from ``document.width``. A hardcoded 800 is right
    for every chart today and wrong for all of them the moment one can be given a size --
    which is open issue #120."""
    from svgplot._svg import SvgDocument
    from svgplot.charts._legend import render_legend

    narrow = SvgDocument(width=300.0, height=200.0)
    render_legend(narrow, [("가" * 30, "series-1")], x=200.0, y=20.0, font_size=11.0)
    shown = re.findall(r'class="legend-text"[^>]*>([^<]*)<', narrow.to_string())

    assert shown and shown[0].endswith("…")
    assert text_width(shown[0], 11.0) <= 300.0 - 222.0


@pytest.mark.parametrize("label", ["W" * 40, "0123456789" * 4], ids=["W", "digits"])
def test_a_treemap_tile_label_is_cut_to_its_tile(label: str) -> None:
    """Tile labels are centred in their tile and reuse ``legend-text``, so they were not
    covered by the legend fix at all -- measured, a 40-character label ran 137px past the
    canvas edge while the legend beside it was correctly cut."""
    svg = sp.treemap({"v": [1.0, 2.0], "g": [label, "짧음"]}, values="v", labels="g").to_string()
    centred = re.findall(r'<text x="([\d.]+)"[^>]*text-anchor="middle"[^>]*class="legend-text"[^>]*>([^<]*)<', svg)

    assert centred, "no tile labels found"
    for centre, text in centred:
        assert float(centre) + text_width(text, 11.0) / 2 <= DEFAULT_WIDTH


_LABEL_CHARTS = sorted(set(_LEGEND_CHARTS) - {"heatmap"})
"""Every legend chart except ``heatmap``, whose legend lists the colour scale's numeric
levels rather than the series label -- there is no label of the caller's on that path to
keep."""


def _room_for_the_label(name: str) -> float:
    """The pixels a chart actually leaves its legend labels, measured from its own output.

    A fixed-length label cannot serve every chart: ``pieplot`` and ``treemap`` start their
    legend far left of ``barplot``'s, so 15 characters is near the budget for one and half
    of it for another. Rendering once with a short label and reading back where it landed is
    what makes the near-budget case mean the same thing for all of them."""
    data = {"x": ["a", "b"], "y": [1.0, 2.0], "v": [1.0, 2.0], "g": ["짧음", "짧다"], "d": [1, 2]}
    svg = _LEGEND_CHARTS[name](data, "짧음").to_string()
    starts = [float(start) for start, _ in _legend_labels(svg)]

    assert starts, f"{name} drew no legend"
    return DEFAULT_WIDTH - max(starts)


def _label_filling(fraction: float, room: float, char: str) -> str:
    """``char`` repeated until it is estimated at ``fraction`` of ``room``."""
    return char * max(1, int(room * fraction / text_width(char, 11.0)))


@pytest.mark.parametrize("name", _LABEL_CHARTS, ids=_LABEL_CHARTS)
def test_a_label_the_estimate_calls_a_fit_still_keeps_its_text(name: str) -> None:
    """The other half of the contract, and the half with no visible symptom.

    A label that overflows *and* was truncated is at worst ugly -- the text is in the file.
    A label the estimate wrongly called a fit is cut by the ``viewBox`` with nothing left to
    recover it, and that is the case ``needs_full_text`` exists for. Asserting it per chart
    rather than on the function is deliberate: the function was right and its call sites
    could be deleted without a single test noticing -- measured, ``Љ`` x14 then rendered
    44.8px past the canvas edge with its text nowhere in the file."""
    label = _label_filling(0.9, _room_for_the_label(name), "a")
    data = {"x": ["a", "b"], "y": [1.0, 2.0], "v": [1.0, 2.0], "g": [label, "짧음"], "d": [1, 2]}
    svg = _LEGEND_CHARTS[name](data, label).to_string()
    carrying = [entry for entry in re.findall(r"<text[^>]*>(?:(?!</text>).)*?</text>", svg, re.S) if label in entry]

    assert carrying, f"{name} truncated a label that was supposed to fit"
    assert any("<title>" in entry for entry in carrying), f"{name}: full text kept nowhere"


@pytest.mark.parametrize("name", _LABEL_CHARTS, ids=_LABEL_CHARTS)
def test_a_label_in_an_unmeasured_script_keeps_its_text_well_before_the_budget(name: str) -> None:
    """Half the budget is comfortable for a Latin label and past the canvas edge for a
    Cyrillic one, because ``Љ`` is charged 0.73 against a measured 1.057. Nothing about the
    *chart* changes that -- which is why it is checked on all of them."""
    label = _label_filling(0.5, _room_for_the_label(name), "\u0409")
    data = {"x": ["a", "b"], "y": [1.0, 2.0], "v": [1.0, 2.0], "g": [label, "짧음"], "d": [1, 2]}
    svg = _LEGEND_CHARTS[name](data, label).to_string()
    carrying = [entry for entry in re.findall(r"<text[^>]*>(?:(?!</text>).)*?</text>", svg, re.S) if label in entry]

    assert carrying, f"{name} truncated a label that was supposed to fit"
    assert any("<title>" in entry for entry in carrying), f"{name}: full text kept nowhere"


def test_a_treemap_tile_label_the_estimate_calls_a_fit_keeps_its_text() -> None:
    """Same gap on the tile-label path, which reuses ``legend-text`` but not
    ``render_legend``: its ``needs_full_text`` call could be deleted with the suite green."""
    svg = sp.treemap({"v": [90.0, 10.0], "g": ["\u0409" * 20, "짧음"]}, values="v", labels="g").to_string()
    tiles = [entry for entry in re.findall(r"<text[^>]*>(?:(?!</text>).)*?</text>", svg, re.S) if "\u0409" in entry]

    assert tiles, "the tile label was not drawn"
    assert any("<title>" in tile for tile in tiles), "full text kept nowhere"


def test_a_comfortably_short_label_still_gets_no_title() -> None:
    """The guard on the tests above: a rule that titled everything would pass them and bury
    every ordinary chart in markup nobody can hand-edit (핵심 원칙 1)."""
    svg = sp.barplot({"x": ["a", "b"], "y": [1.0, 2.0], "g": ["매출", "비용"]}, x="x", y="y", hue="g").to_string()
    entries = re.findall(r'<text[^>]*class="legend-text"[^>]*>(?:(?!</text>).)*?</text>', svg, re.S)

    assert entries, "no legend labels found"
    assert not any("<title>" in entry for entry in entries)
