from __future__ import annotations

import re
import warnings

import pytest

from svgplot.charts._layout import DEFAULT_HEIGHT, DEFAULT_WIDTH, MARGIN_WITH_LEGEND, plot_area
from svgplot.charts.heatmap import _WARN_CELL_COUNT, LEVELS, heatmap
from svgplot.warnings import HeatmapSizeWarning

AREA = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=MARGIN_WITH_LEGEND)

_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')

GRID = {
    "col": ["a", "a", "b", "b", "c", "c"],
    "row": ["p", "q", "p", "q", "p", "q"],
    "v": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
}


def _square(side: int) -> dict[str, list]:
    """A ``side x side`` heatmap, for the size-warning boundary."""
    columns = [f"x{index}" for index in range(side)]
    rows = [f"y{index}" for index in range(side)]
    return {
        "col": [column for column in columns for _ in rows],
        "row": [row for _ in columns for row in rows],
        "v": [float(index) for index in range(side * side)],
    }


def _tags(svg: str, element: str, css_class: str) -> list[dict[str, str]]:
    """Opening tags of ``element`` carrying ``css_class``. Matches both self-closing forms
    (``<rect …/>``) and ones with content (``<text …>…</text>``)."""
    return [dict(_ATTR_RE.findall(tag)) for tag in re.findall(rf"<{element}\b[^>]*?/?>", svg) if css_class in tag]


def _cells(svg: str) -> list[dict[str, str]]:
    return _tags(svg, "rect", "heatmap-cell")


def _swatches(svg: str) -> list[dict[str, str]]:
    """Legend swatches -- level-classed rects that are not cells."""
    return [
        dict(_ATTR_RE.findall(tag))
        for tag in re.findall(r"<rect\b[^>]*/>", svg)
        if "level-" in tag and "heatmap-cell" not in tag
    ]


def _style_rules(svg: str) -> dict[str, str]:
    return {match.group(1): match.group(0).strip() for match in re.finditer(r"\.(level-\d+) \{[^}]*\}", svg)}


def _render(data: dict[str, list], **kwargs: object) -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", HeatmapSizeWarning)
        return heatmap(data, x="col", y="row", values="v", **kwargs).to_string()  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# cells and legend
# ---------------------------------------------------------------------------


def test_one_rect_per_cell_and_one_swatch_per_level() -> None:
    svg = _render(GRID)

    assert len(_cells(svg)) == 6
    assert len(_swatches(svg)) == LEVELS


def test_a_missing_pair_leaves_a_hole_rather_than_a_zero() -> None:
    """A hole and a zero look nothing alike to a reader; drawing one for the other invents
    data that was never in the frame."""
    holey = {"col": ["a", "a", "b"], "row": ["p", "q", "p"], "v": [1.0, 2.0, 3.0]}
    svg = _render(holey)

    assert len(_cells(svg)) == 3


def test_cells_tile_the_plot_area_without_gaps() -> None:
    svg = _render(GRID)
    cells = _cells(svg)
    widths = {float(cell["width"]) for cell in cells}
    heights = {float(cell["height"]) for cell in cells}

    assert len(widths) == len(heights) == 1
    assert widths.pop() == pytest.approx((AREA.right - AREA.left) / 3)
    assert heights.pop() == pytest.approx((AREA.bottom - AREA.top) / 2)


def test_the_grid_spans_the_whole_plot_area() -> None:
    cells = _cells(_render(GRID))
    lefts = [float(cell["x"]) for cell in cells]
    tops = [float(cell["y"]) for cell in cells]

    assert min(lefts) == pytest.approx(AREA.left)
    assert max(lefts) + float(cells[0]["width"]) == pytest.approx(AREA.right)
    assert min(tops) == pytest.approx(AREA.top)
    assert max(tops) + float(cells[0]["height"]) == pytest.approx(AREA.bottom)


def test_categories_keep_their_first_seen_order() -> None:
    reordered = {"col": ["z", "a"], "row": ["p", "p"], "v": [1.0, 2.0]}
    cells = _cells(_render(reordered))

    assert float(cells[0]["x"]) < float(cells[1]["x"])


# ---------------------------------------------------------------------------
# quantised colours
# ---------------------------------------------------------------------------


def test_every_level_gets_exactly_one_css_rule() -> None:
    """The whole point of quantising: nine rules a reader can edit by hand to recolour the
    chart. One rule per cell would be unmaintainable and would break the package's
    hand-editable-output principle."""
    rules = _style_rules(_render(GRID))

    assert len(rules) == LEVELS
    assert sorted(rules) == sorted(f"level-{index + 1}" for index in range(LEVELS))


def test_level_classes_are_valid_names() -> None:
    svg = _render(GRID)
    classes = {match for cell in _cells(svg) for match in cell["class"].split() if match.startswith("level-")}

    assert classes
    assert all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", name) for name in classes)


def test_level_rules_carry_theme_opacity_only() -> None:
    """A heatmap's colour *is* its data, so blending every cell with 25% background would
    misreport every value. ``fill_opacity`` must not reach these rules."""
    rules = _style_rules(_render(GRID))

    for rule in rules.values():
        assert "opacity: 1;" in rule
        assert "fill-opacity" not in rule
        assert "stroke: none" in rule


def test_the_extremes_land_on_the_end_levels() -> None:
    svg = _render(GRID)
    cells = _cells(svg)
    levels = [next(name for name in cell["class"].split() if name.startswith("level-")) for cell in cells]

    # GRID's values run 1..6 over the full range, so the smallest is level-1 and the
    # largest level-9 -- an off-by-one in the quantiser shows up at exactly these ends.
    assert levels[0] == "level-1"
    assert levels[-1] == f"level-{LEVELS}"


def test_a_center_switches_to_a_diverging_scale_with_a_neutral_middle() -> None:
    """``center=`` means the middle level reads as "at the centre", not "halfway between
    the extremes" -- which is only true if the palette is diverging and the normalisation
    is two-sided."""
    plain = _style_rules(_render(GRID))
    centred = _style_rules(_render(GRID, cmap="coolwarm", center=3.5))
    middle = centred[f"level-{LEVELS // 2 + 1}"]

    assert centred != plain
    # A diverging map's midpoint is near-neutral; a sequential one's middle is not.
    fill = re.search(r"fill: (#[0-9a-f]{6})", middle).group(1)
    red, green, blue = (int(fill[index : index + 2], 16) for index in (1, 3, 5))
    assert max(red, green, blue) - min(red, green, blue) < 16


def test_the_centre_value_lands_on_the_middle_level() -> None:
    """The centre has to be *off* the range's midpoint for this to mean anything: with
    symmetric data a two-sided normalisation and a plain one agree, and forgetting to pass
    ``center`` through to ``Normalize`` goes unnoticed. Here 2.0 sits a fifth of the way up
    [0, 10], so a plain normalisation puts it on level 2 and a centred one on level 5."""
    data = {"col": ["a", "b", "c"], "row": ["p", "p", "p"], "v": [0.0, 2.0, 10.0]}
    cells = _cells(_render(data, cmap="coolwarm", center=2.0))
    levels = [next(name for name in cell["class"].split() if name.startswith("level-")) for cell in cells]

    assert levels == ["level-1", f"level-{LEVELS // 2 + 1}", f"level-{LEVELS}"]


# ---------------------------------------------------------------------------
# the size warning
# ---------------------------------------------------------------------------


def test_a_small_heatmap_warns_about_nothing() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        heatmap(_square(10), x="col", y="row", values="v")


def test_a_large_heatmap_warns_exactly_once() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        heatmap(_square(100), x="col", y="row", values="v")

    sized = [entry for entry in caught if issubclass(entry.category, HeatmapSizeWarning)]
    assert len(sized) == 1


def test_the_warning_carries_the_count_the_size_and_the_way_out() -> None:
    """A bare "this is big" tells the caller nothing they can act on."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        heatmap(_square(100), x="col", y="row", values="v")
    message = str(caught[0].message)

    assert "10000 cells" in message
    assert "KB" in message
    assert ".png" in message


def test_the_estimated_size_is_close_to_the_real_one() -> None:
    """The number in the warning has to be worth reading. Measured 863 KB against an
    estimate of 859 KB at 10,000 cells."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        chart = heatmap(_square(100), x="col", y="row", values="v")
    estimated = int(re.search(r"~(\d+) KB", str(caught[0].message)).group(1))
    actual = len(chart.to_string()) / 1024

    assert estimated == pytest.approx(actual, rel=0.15)


def test_a_large_heatmap_still_renders() -> None:
    """There is deliberately no hard cap -- the warning is advice, not a refusal."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", HeatmapSizeWarning)
        svg = heatmap(_square(60), x="col", y="row", values="v").to_string()

    assert len(_cells(svg)) == 3600


def test_the_threshold_itself_stays_silent() -> None:
    """The bound is inclusive, so exactly ``_WARN_CELL_COUNT`` cells must not warn."""
    side = 50
    assert side * side == _WARN_CELL_COUNT

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        heatmap(_square(side), x="col", y="row", values="v")


# ---------------------------------------------------------------------------
# annotations
# ---------------------------------------------------------------------------


def test_annotations_are_off_by_default() -> None:
    assert "heatmap-annotation" not in _render(GRID)


def test_one_annotation_per_drawn_cell() -> None:
    svg = _render(GRID, annot=True)

    assert len(_tags(svg, "text", "heatmap-annotation")) == len(_cells(svg))


def test_an_annotation_sits_at_its_cell_s_centre() -> None:
    """Placement uses the cell's own geometry -- this package has no font metrics, so the
    label is centred on the rect rather than fitted to it."""
    svg = _render(GRID, annot=True)
    cell = _cells(svg)[0]
    annotation = _tags(svg, "text", "heatmap-annotation")[0]

    assert float(annotation["x"]) == pytest.approx(float(cell["x"]) + float(cell["width"]) / 2)
    assert float(annotation["y"]) == pytest.approx(float(cell["y"]) + float(cell["height"]) / 2)


def test_a_hole_gets_no_annotation() -> None:
    holey = {"col": ["a", "a", "b"], "row": ["p", "q", "p"], "v": [1.0, 2.0, 3.0]}
    svg = _render(holey, annot=True)

    assert len(_tags(svg, "text", "heatmap-annotation")) == 3


# ---------------------------------------------------------------------------
# rejected input
# ---------------------------------------------------------------------------


def test_a_duplicate_cell_is_refused() -> None:
    """Last-one-wins would hide half the data behind a rect that looks like every other
    rect -- there is no visual cue that a cell was overwritten."""
    data = {"col": ["a", "a"], "row": ["p", "p"], "v": [1.0, 2.0]}

    with pytest.raises(ValueError, match="duplicate cell"):
        heatmap(data, x="col", y="row", values="v")


@pytest.mark.parametrize(
    ("data", "kwargs", "error", "match"),
    [
        ({"col": [], "row": [], "v": []}, {}, ValueError, "at least one row"),
        ({"col": [None], "row": ["p"], "v": [1.0]}, {}, ValueError, "after dropping missing"),
        (None, {"x": "nope"}, KeyError, "x column not found"),
        (None, {"values": "nope"}, KeyError, "values column not found"),
        (None, {"theme": "not-a-preset"}, KeyError, "unknown theme preset"),
        (None, {"cmap": "not-a-cmap"}, KeyError, "unknown"),
    ],
)
def test_heatmap_rejects_unusable_input(data: dict | None, kwargs: dict, error: type[Exception], match: str) -> None:
    payload = GRID if data is None else data
    call_kwargs = {"x": "col", "y": "row", "values": "v", **kwargs}
    with pytest.raises(error, match=match):
        heatmap(payload, **call_kwargs)


def test_rows_missing_any_channel_are_dropped() -> None:
    data = {"col": ["a", "b", None], "row": ["p", None, "p"], "v": [1.0, 2.0, 3.0]}

    assert len(_cells(_render(data))) == 1


def test_heatmap_is_deterministic() -> None:
    assert _render(GRID) == _render(GRID)
