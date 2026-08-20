from __future__ import annotations

import re
import warnings
from dataclasses import replace

import pytest

from _svg_probe import style_rules, tags as _tags, texts as _texts
from svgplot.charts._layout import DEFAULT_HEIGHT, DEFAULT_WIDTH, MARGIN_WITH_LEGEND, format_coord, plot_area
from svgplot.charts.heatmap import (
    _BYTES_FIXED,
    _BYTES_PER_CELL,
    _BYTES_PER_TICK,
    _WARN_CELL_COUNT,
    LEVELS,
    _composited,
    _readable_ink,
    heatmap,
)
from svgplot.palette._color import hex_to_rgb01
from svgplot.palette.diverging import DIVERGING_PALETTES
from svgplot.palette.normalize import Normalize
from svgplot.palette.sequential import SEQUENTIAL_PALETTES
from svgplot.theme import PRESETS
from svgplot.warnings import HeatmapSizeWarning

AREA = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=MARGIN_WITH_LEGEND)

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


def _annotations(svg: str) -> list[str]:
    """The text content of each annotation, in document order.

    Through the shared probe. The hand-written ``class="[^"]*heatmap-annotation[^"]*"`` also
    matched a ``heatmap-annotation-x``, which is the substring defect this file's own ``_tags``
    was consolidated to remove -- left behind in the same file it was removed from.
    """
    return _texts(svg, "text", "heatmap-annotation")


def _ramp() -> dict[str, list]:
    """One row per level plus the two saturating ends, so every ``level-N`` is present."""
    values = [float(index) for index in range(11)]
    return {"col": [f"c{index}" for index in range(11)], "row": ["p"] * 11, "v": values}


def _relative_luminance(hex_color: str) -> float:
    channels = [
        channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4 for channel in hex_to_rgb01(hex_color)
    ]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast(one: str, other: str) -> float:
    """WCAG contrast ratio. Written out here rather than imported, so a bug in the
    production luminance calculation cannot make its own output look correct."""
    dark, light = sorted((_relative_luminance(one), _relative_luminance(other)))
    return (light + 0.05) / (dark + 0.05)


def _cells(svg: str) -> list[dict[str, str]]:
    return _tags(svg, "rect", "heatmap-cell")


def _swatches(svg: str) -> list[dict[str, str]]:
    """Legend swatches -- level-classed rects that are not cells.

    ``level-1`` through ``level-N`` are whole class tokens, so this enumerates them rather
    than testing a prefix -- a prefix test against the *whole tag* counts any attribute that
    happens to contain those characters, which is the defect this file's own ``_tags`` was
    consolidated to remove. Enumerating also fixes the order to level number rather than
    document order; the two agree today.
    """
    return [
        tag
        for level in range(1, LEVELS + 1)
        for tag in _tags(svg, "rect", f"level-{level}")
        if "heatmap-cell" not in tag.get("class", "").split()
    ]


def _style_rules(svg: str) -> dict[str, str]:
    """Level rules by class name. Reads through the shared probe rather than a regex over the
    whole document: the document-scope prefix sits between ``<style>`` and the selector."""
    matches = (re.match(r"\.(level-\d+) \{", rule) for rule in style_rules(svg))
    return {match.group(1): match.string for match in matches if match}


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


def _diagonal(side: int) -> dict[str, list]:
    """A ``side x side`` grid holding only its diagonal -- the sparse case the two-term
    estimate exists for: ``side`` rects but ``2 * side`` axis ticks."""
    return {
        "col": [f"x{index}" for index in range(side)],
        "row": [f"y{index}" for index in range(side)],
        "v": [float(index) for index in range(side)],
    }


def _estimated_and_actual_kb(data: dict[str, list]) -> tuple[float, float]:
    """The formula's own answer and the real serialized size, both in KB.

    The formula is called directly rather than read out of the warning, because the 50x50
    point sits exactly *at* ``_WARN_CELL_COUNT`` and so emits no warning at all -- reading
    the warning would silently drop the one point that pins ``_BYTES_PER_CELL`` hardest.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", HeatmapSizeWarning)
        chart = heatmap(data, x="col", y="row", values="v")
    drawn = len(data["v"])
    ticks = len(set(data["col"])) + len(set(data["row"]))
    estimated = (drawn * _BYTES_PER_CELL + ticks * _BYTES_PER_TICK + _BYTES_FIXED) // 1024
    return estimated, len(chart.to_string()) / 1024


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("50x50 dense", _square(50)),
        ("100x100 dense", _square(100)),
        ("100x100 diagonal", _diagonal(100)),
        ("200x200 diagonal", _diagonal(200)),
    ],
)
def test_the_estimate_holds_at_every_point_the_docstring_cites(name: str, data: dict[str, list]) -> None:
    """``_BYTES_PER_TICK``'s docstring names four measured points and claims 5% on all of
    them. Pinning only two left the claim half-held: ``_BYTES_PER_CELL`` could drop from 88
    to 80 with the suite green, which puts the untested 50x50 point at -7.1%.

    Four points constrain the two constants to a band, not to a value -- 84 instead of 88
    is admitted here, and in fact fits slightly better (2.8% worst against 4.4%). That is
    the honest resolution of the measurement, not a gap: asserting harder would claim a
    precision these four points do not carry."""
    estimated, actual = _estimated_and_actual_kb(data)

    assert estimated == pytest.approx(actual, rel=0.05), f"{name}: {estimated} vs {actual:.1f} KB"


def test_the_warning_reports_the_same_number_the_formula_gives() -> None:
    """Otherwise the four points above could all hold while the text a reader actually sees
    said something else."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        chart = heatmap(_square(100), x="col", y="row", values="v")
    printed = int(re.search(r"~(\d+) KB", str(caught[0].message)).group(1))

    assert printed == _estimated_and_actual_kb(_square(100))[0]
    assert printed == pytest.approx(len(chart.to_string()) / 1024, rel=0.05)


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


# ---------------------------------------------------------------------------
# the legend names the values
# ---------------------------------------------------------------------------


def _legend_labels(svg: str) -> list[str]:
    return re.findall(r'class="legend-text">([^<]+)<', svg)


def _swatch_classes(svg: str) -> list[str]:
    return [next(name for name in swatch["class"].split() if name.startswith("level-")) for swatch in _swatches(svg)]


def test_each_swatch_is_labelled_with_the_value_its_colour_starts_at() -> None:
    """The legend is the only way a reader turns a cell's colour back into a number. It has
    no other test, and that is how the ``center=`` mislabelling below went unnoticed."""
    data = {"col": ["a", "b", "c"], "row": ["p", "p", "p"], "v": [0.0, 4.5, 9.0]}
    labels = _legend_labels(_render(data))

    assert labels == [format_coord(9.0 * index / LEVELS) for index in range(LEVELS)]


def test_the_legend_follows_a_centred_scale_too() -> None:
    """With ``center`` the normalisation is two straight lines, so undoing it by assuming
    one slope mislabels every step on the shorter side -- measured six of nine wrong, by up
    to two levels."""
    values = [0.0, 2.0, 10.0]
    data = {"col": ["a", "b", "c"], "row": ["p", "p", "p"], "v": values}
    normalize = Normalize.from_values(values, center=2.0)

    labels = _legend_labels(_render(data, cmap="coolwarm", center=2.0))

    assert labels == [format_coord(normalize.inverse(index / LEVELS)) for index in range(LEVELS)]

    # The centre falls inside the middle swatch rather than starting it: 0.5 sits between
    # 4/9 and 5/9 with nine levels. What matters is that the swatch the centre lands in is
    # the middle one, and that its own label brackets the centre.
    middle = LEVELS // 2
    assert float(labels[middle]) < 2.0 < float(labels[middle + 1])
    # A single-slope inverse would put this label at 4.444; the two-slope one at 1.778.
    assert labels[middle] == format_coord(normalize.inverse(middle / LEVELS))


def test_the_swatches_carry_one_level_class_each_in_order() -> None:
    assert _swatch_classes(_render(GRID)) == [f"level-{index + 1}" for index in range(LEVELS)]


def test_the_legend_reads_from_low_to_high() -> None:
    labels = _legend_labels(_render(GRID))

    assert [float(label) for label in labels] == sorted(float(label) for label in labels)


# ---------------------------------------------------------------------------
# the quantiser
# ---------------------------------------------------------------------------


def test_the_quantiser_maps_evenly_spaced_values_to_every_level() -> None:
    """``GRID``'s six values skip levels 3, 5 and 7, so an off-by-one lands on the same two
    ends and goes unnoticed. Nine values are no better -- with exactly ``LEVELS`` evenly
    spaced values ``t * LEVELS`` and ``t * (LEVELS - 1)`` happen to agree everywhere, and
    ``int`` and ``round`` agree too because every product is a whole number. Eleven values
    separate all three: ``* (LEVELS - 1)`` doubles up in the middle instead of at the ends,
    and ``round`` shifts the whole scale one step early."""
    count = 11
    values = [float(index) for index in range(count)]
    data = {"col": [f"c{index}" for index in range(count)], "row": ["p"] * count, "v": values}
    cells = _cells(_render(data))
    levels = [next(name for name in cell["class"].split() if name.startswith("level-")) for cell in cells]

    # A level spans 1/9 of the range while a step is 1/10 of it, so the two ends each take
    # two values and the middle nine land one apiece.
    assert levels == [f"level-{min(max(index, 1), LEVELS)}" for index in range(count)]


# ---------------------------------------------------------------------------
# annotations carry the values, and are themed
# ---------------------------------------------------------------------------


def test_an_annotation_shows_its_cell_s_value() -> None:
    """Only the count and position were checked, so writing the level number -- or a
    constant -- into every cell passed."""
    data = {"col": ["a", "b"], "row": ["p", "p"], "v": [1.5, 12.0]}
    svg = _render(data, annot=True)

    assert _annotations(svg) == ["1.5", "12"]


def test_annotations_take_the_font_from_a_class_the_theme_styles() -> None:
    """A class of its own has no CSS rule at all, so the text falls back to the browser
    default -- a serif face at the browser's own size, next to the theme's sans everywhere
    else on the chart."""
    svg = _render(GRID, annot=True, theme="dark")
    annotation = _tags(svg, "text", "heatmap-annotation")[0]

    assert "tick-label" in annotation["class"].split()
    assert ".tick-label {" in svg


@pytest.mark.parametrize("cmap", sorted(SEQUENTIAL_PALETTES))
def test_annotation_ink_is_readable_on_every_level_of_every_sequential_map(cmap: str) -> None:
    """The fix for the class above was first to borrow ``.tick-label``'s ``fill`` as well as
    its font -- and that made things worse, not better. Cell colours come from the colormap
    and are byte-identical under every preset, so the theme foreground is a colour picked to
    read against the *canvas*, applied over a *cell*. Measured on the dark preset it left 5
    of 9 levels below 3:1, worst 1.04:1 -- less legible than the browser default it
    replaced. Ink now comes from the cell's own luminance instead.

    Parametrised on the **colormap**, not on the theme preset: the preset is exactly the
    axis along which these colours do not vary, so looping over presets would run the same
    assertion five times. Sweeping the maps instead is what makes a mutation that inks every
    cell the same mid-grey fail."""
    _assert_ink_is_readable(_render(_ramp(), annot=True, cmap=cmap))


@pytest.mark.parametrize("cmap", sorted(DIVERGING_PALETTES))
def test_annotation_ink_is_readable_on_a_centred_diverging_map(cmap: str) -> None:
    """``center=`` swaps in a different palette entirely, so it is a second set of nine cell
    colours and needs its own check -- and it is the harder one, since a diverging map runs
    pale through the middle where a sequential map only starts there."""
    _assert_ink_is_readable(_render(_ramp(), annot=True, cmap=cmap, center=5.0))


def test_the_ink_does_not_take_the_theme_s_opacity() -> None:
    """Ink reaches the ``<style>`` block through the same call the cells do, and the cell
    rules carry ``theme.opacity``. Inheriting it would blend the ink back toward the cell it
    was chosen to contrast with: at ``opacity=0.8`` the measured ratio falls from 4.9:1 to
    3.3:1, below AA, and at 0.5 to 1.8:1."""
    faded = replace(PRESETS["light"], opacity=0.5)
    style = _style_of(_render(_ramp(), annot=True, theme=faded))

    ink_rules = [line for line in style.splitlines() if "-annotation {" in line]
    assert len(ink_rules) == LEVELS
    for rule in ink_rules:
        assert "opacity" not in rule, rule


@pytest.mark.parametrize("opacity", [1.0, 0.8, 0.5, 0.3])
def test_the_ink_is_readable_against_what_the_reader_actually_sees(opacity: float) -> None:
    """Dropping ``opacity`` from the ink rule was necessary but not sufficient: the *cell*
    still carries it, so the colour on screen is the colormap blended toward the plot
    background, and ink chosen against the unblended colour is chosen for a cell nobody
    sees. Asserting "the ink rule has no opacity" passed at ``opacity=0.5`` while the
    rendered contrast was 2.23:1 -- a green test for an unreadable chart. Measuring the
    composite is what makes this test mean something."""
    theme = replace(PRESETS["light"], opacity=opacity)
    style = _style_of(_render(_ramp(), annot=True, theme=theme))
    fills = dict(re.findall(r"\.(level-\d+(?:-annotation)?) \{ fill: (#[0-9a-f]{6})", style))

    for index in range(1, LEVELS + 1):
        seen = _composited(fills[f"level-{index}"], over=theme.background, opacity=opacity)
        ratio = _contrast(seen, fills[f"level-{index}-annotation"])
        assert ratio >= 4.5, f"opacity={opacity} level-{index}: {ratio:.2f}:1"


def test_the_theme_s_opacity_still_reaches_the_cells() -> None:
    """The exemption above is for text only -- removing opacity from the level rules too
    would be a different change, and this keeps the two apart."""
    faded = replace(PRESETS["light"], opacity=0.5)
    style = _style_of(_render(_ramp(), annot=True, theme=faded))

    cell_rules = [line for line in style.splitlines() if re.match(r"\.level-\d+ \{", line)]
    assert len(cell_rules) == LEVELS
    assert all("opacity: 0.5" in rule for rule in cell_rules)


def _style_of(svg: str) -> str:
    """The chart's CSS rules, one per line, with the document scope stripped.

    Its callers match rules by line prefix (``re.match(r"\\.level-\\d+ \\{", line)``), which
    ``svgplot.scope`` pushed out of reach by wrapping each selector in ``:where(...)``.
    Stripping here rather than in each caller keeps the readers from drifting apart."""
    return "\n".join(style_rules(svg))


def _assert_ink_is_readable(svg: str) -> None:
    style = _style_of(svg)
    fills = dict(re.findall(r"\.(level-\d+(?:-annotation)?) \{ fill: (#[0-9a-f]{6})", style))

    assert len(fills) == 2 * LEVELS, sorted(fills)
    for index in range(1, LEVELS + 1):
        ratio = _contrast(fills[f"level-{index}"], fills[f"level-{index}-annotation"])
        assert ratio >= 4.5, f"level-{index}: {ratio:.2f}:1"


def test_each_annotation_takes_the_ink_of_the_cell_it_sits_on() -> None:
    """The nine ink rules are worthless if the text does not carry the matching class, and
    a ``<style>``-only assertion cannot tell: dropping the class entirely, or giving every
    annotation ``level-1``'s ink, both leave the emitted CSS byte-identical."""
    svg = _render(_ramp(), annot=True, theme="dark")
    cells = _cells(svg)
    annotations = _tags(svg, "text", "heatmap-annotation")

    assert len(annotations) == len(cells) == 11
    for cell, annotation in zip(cells, annotations, strict=True):
        level = next(name for name in cell["class"].split() if name.startswith("level-"))
        assert f"{level}-annotation" in annotation["class"].split()
    # ...and the classes really do differ across levels, so "all of them say level-1" fails.
    inks = {name for annotation in annotations for name in annotation["class"].split() if name.startswith("level-")}
    assert len(inks) == LEVELS


def test_the_ink_rules_are_absent_when_nothing_is_annotated() -> None:
    """Nine rules no element matches are nine more lines to read past in a file whose whole
    point is that a person can hand-edit it."""
    assert "-annotation {" not in _render(GRID)


def test_the_ink_flips_to_black_on_a_pale_cell_and_white_on_a_dark_one() -> None:
    """Pinned against the WCAG threshold rather than a midpoint: splitting at 0.5 luminance
    would send white ink onto cells where black reads up to 1.7x better."""
    assert _readable_ink("#ffffff") == "#000000"
    assert _readable_ink("#000000") == "#ffffff"
    # One step either side of the threshold, so a moved constant fails rather than rounds.
    assert _readable_ink("#767676") == "#000000"  # luminance 0.18116, just above 0.17913
    assert _readable_ink("#757575") == "#ffffff"  # luminance 0.17789, just below it
    # A mid-grey a 0.5 split would hand to white ink. Black wins here by 1.7x, which is the
    # whole reason the threshold is derived rather than picked.
    assert _readable_ink("#8a8a8a") == "#000000"
    assert _contrast("#8a8a8a", "#000000") / _contrast("#8a8a8a", "#ffffff") == pytest.approx(1.7, abs=0.1)


# ---------------------------------------------------------------------------
# ordering and missing values
# ---------------------------------------------------------------------------


def test_columns_keep_their_first_seen_order() -> None:
    """Asserted through the tick labels: cells are emitted in column order either way, so
    comparing their x coordinates is true whatever order the categories are in."""
    data = {"col": ["z", "a"], "row": ["p", "p"], "v": [1.0, 2.0]}
    svg = _render(data)

    assert re.findall(r'class="tick-label"[^>]*>([^<]+)<', svg)[:2] == ["z", "a"]


def test_a_row_with_a_missing_value_is_dropped() -> None:
    """The existing drop test holes ``col``/``row`` only, so removing the check on
    ``values`` itself passed."""
    data = {"col": ["a", "b", "c"], "row": ["p", "p", "p"], "v": [1.0, None, float("nan")]}

    assert len(_cells(_render(data))) == 1


# ---------------------------------------------------------------------------
# the size estimate
# ---------------------------------------------------------------------------


def test_the_estimate_tracks_a_sparse_grid_too() -> None:
    """A 100x100 grid holding a diagonal draws 100 rects but still labels 200 ticks.
    Estimating from grid cells alone put it at 859 KB against a real 51 KB."""
    side = 100
    sparse = {
        "col": [f"x{index}" for index in range(side)],
        "row": [f"y{index}" for index in range(side)],
        "v": [float(index) for index in range(side)],
    }
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        chart = heatmap(sparse, x="col", y="row", values="v")

    estimated = int(re.search(r"~(\d+) KB", str(caught[0].message)).group(1))
    actual = len(chart.to_string()) / 1024

    assert len(_cells(chart.to_string())) == side
    assert estimated == pytest.approx(actual, rel=0.05)


def test_the_warning_still_fires_on_a_sparse_grid() -> None:
    """The *grid* is what makes each cell too small to read, however few are filled."""
    side = 100
    sparse = {
        "col": [f"x{index}" for index in range(side)],
        "row": [f"y{index}" for index in range(side)],
        "v": [float(index) for index in range(side)],
    }
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        heatmap(sparse, x="col", y="row", values="v")

    assert len(caught) == 1
    assert "10000 cells" in str(caught[0].message)


# ---------------------------------------------------------------------------
# cmap and center have to agree (issue #109)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cmap", sorted(SEQUENTIAL_PALETTES))
def test_a_sequential_cmap_with_center_names_the_pairing_not_the_key(cmap: str) -> None:
    """The two registries are disjoint, so the likeliest mistake here is the *pair*, and the
    palette functions cannot report it: each sees only its own half. ``center=1.0`` with the
    default ``cmap="blues"`` used to raise ``KeyError: unknown diverging palette: 'blues'``,
    which is wrong twice -- ``blues`` is not unknown, and the key is not what went wrong."""
    with pytest.raises(ValueError, match=r"center= needs a diverging colormap"):
        _render(GRID, cmap=cmap, center=5.0)


@pytest.mark.parametrize("cmap", sorted(DIVERGING_PALETTES))
def test_a_diverging_cmap_without_center_is_refused_too(cmap: str) -> None:
    """The other direction, and it is not symmetric decoration: a diverging map drawn as a
    sequential one puts its pale midpoint at the middle of the *data range* instead of at a
    value the caller chose, which reads as a centre that is not there."""
    with pytest.raises(ValueError, match=r"is a diverging colormap, which needs a center="):
        _render(GRID, cmap=cmap)


@pytest.mark.parametrize(
    ("cmap", "center", "usable", "wrong"),
    [
        ("blues", 5.0, DIVERGING_PALETTES, SEQUENTIAL_PALETTES),
        ("coolwarm", None, SEQUENTIAL_PALETTES, DIVERGING_PALETTES),
    ],
)
def test_the_message_names_the_offending_cmap_and_the_ones_that_would_work(
    cmap: str, center: float | None, usable: dict[str, object], wrong: dict[str, object]
) -> None:
    """Both directions, symmetrically. Checking only one left the other's message free to
    drop its suggestions entirely, or -- worse -- to list the very colormap it just
    rejected, which walks the caller in a circle. Both mutations passed the whole suite.

    The offending name has to appear too: this project's other rejections quote the value
    that broke the rule (``got vmin=...``), and that was the argument for replacing the
    original ``KeyError`` in the first place."""
    with pytest.raises(ValueError) as caught:
        _render(GRID, cmap=cmap, center=center)
    message = str(caught.value)
    suggested = set(re.findall(r"[a-z]+", message.split("(")[-1] if "(" in message else message.split("one of")[-1]))

    assert repr(cmap) in message, "the rejection does not name the colormap that broke the rule"
    assert set(usable) <= suggested, f"{sorted(set(usable) - suggested)} missing from the suggestions"
    assert not (set(wrong) & suggested), f"{sorted(set(wrong) & suggested)} suggested but would be rejected too"


@pytest.mark.parametrize(
    ("cmap", "center"),
    [("blues", None), ("greens", None), ("coolwarm", 5.0), ("purplegreen", 5.0)],
)
def test_the_valid_pairings_still_render(cmap: str, center: float | None) -> None:
    """Otherwise the two refusals above would pass for a check that rejected everything."""
    assert len(_style_rules(_render(GRID, cmap=cmap, center=center))) == LEVELS


def test_an_unregistered_cmap_still_raises_keyerror_from_the_palette() -> None:
    """The new check is about the pairing only. A name in neither registry is a different
    mistake and keeps its own error, so widening this to catch everything would hide it."""
    with pytest.raises(KeyError, match="unknown sequential palette"):
        _render(GRID, cmap="nope")
    with pytest.raises(KeyError, match="unknown diverging palette"):
        _render(GRID, cmap="nope", center=5.0)


def test_the_fixed_term_reproduces_the_chart_it_is_anchored_to() -> None:
    """``_BYTES_FIXED``'s whole justification is that the model is exact on a one-cell heatmap,
    and nothing executed that. The four grid points do not pin it -- a free 3800, which
    overpredicts this chart by 28%, passes them at 2.40%.

    Single-character labels: two-character ones make the chart 3,286 bytes, so the anchor is
    a property of this fixture as much as of the model.
    """
    one_cell = heatmap({"col": ["a"], "row": ["p"], "v": [1.0]}, x="col", y="row", values="v")

    assert len(one_cell.to_string()) == 1 * _BYTES_PER_CELL + 2 * _BYTES_PER_TICK + _BYTES_FIXED
