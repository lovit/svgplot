from __future__ import annotations

import re

import pytest

from svgplot.charts.treemap import treemap

DATA = {"label": ["a", "b", "c", "d", "e", "f", "g"], "value": [6.0, 6.0, 4.0, 3.0, 2.0, 2.0, 1.0]}

# Geometry treemap derives from its fixed canvas/margins (800x600, margin
# top/right/bottom/left = 30/180/30/30).
_AREA_LEFT, _AREA_TOP = 30.0, 30.0
_AREA_WIDTH, _AREA_HEIGHT = 590.0, 540.0
_PLOT_PIXELS = _AREA_WIDTH * _AREA_HEIGHT

# The legend draws its own swatch <rect>s at a fixed 16x10; tiles are everything else.
_LEGEND_SWATCH_WIDTH = 16.0

_RECT_RE = re.compile(r'<rect x="([-\d.]+)" y="([-\d.]+)" width="([-\d.]+)" height="([-\d.]+)" class="(series-\d+)"')


def _tiles(svg: str) -> list[tuple[float, float, float, float]]:
    """(x, y, width, height) of every tile rect, legend swatches excluded."""
    return [
        (float(x), float(y), float(w), float(h))
        for x, y, w, h, _cls in _RECT_RE.findall(svg)
        if float(w) != _LEGEND_SWATCH_WIDTH
    ]


def _overlap_area(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    dx = min(ax + aw, bx + bw) - max(ax, bx)
    dy = min(ay + ah, by + bh) - max(ay, by)
    return dx * dy if dx > 0 and dy > 0 else 0.0


def _worst_ratio(tiles: list[tuple[float, float, float, float]]) -> float:
    return max(max(w / h, h / w) for _x, _y, w, h in tiles if w > 0 and h > 0)


# ---------------------------------------------------------------------------
# exact tiling
# ---------------------------------------------------------------------------


def test_treemap_renders_one_rect_per_tile() -> None:
    svg = treemap(DATA, values="value", labels="label").to_string()
    assert len(_tiles(svg)) == len(DATA["value"])


def test_treemap_tiles_cover_the_whole_plot_area() -> None:
    """Union of tile areas equals the plot area. Paired with the overlap test below:
    a layout bug can satisfy coverage while double-covering part of the rect, so
    neither assertion alone proves an exact partition."""
    tiles = _tiles(treemap(DATA, values="value", labels="label").to_string())
    covered = sum(w * h for _x, _y, w, h in tiles)
    assert covered == pytest.approx(_PLOT_PIXELS, abs=1e-6)


def test_treemap_tiles_do_not_overlap() -> None:
    tiles = _tiles(treemap(DATA, values="value", labels="label").to_string())
    for index, tile in enumerate(tiles):
        for other in tiles[index + 1 :]:
            assert _overlap_area(tile, other) == pytest.approx(0.0, abs=1e-9)


def test_treemap_tiles_stay_inside_the_plot_area() -> None:
    tiles = _tiles(treemap(DATA, values="value", labels="label").to_string())
    for x, y, w, h in tiles:
        assert x >= _AREA_LEFT - 1e-9
        assert y >= _AREA_TOP - 1e-9
        assert x + w <= _AREA_LEFT + _AREA_WIDTH + 1e-9
        assert y + h <= _AREA_TOP + _AREA_HEIGHT + 1e-9


def test_treemap_tile_area_is_proportional_to_value() -> None:
    svg = treemap(DATA, values="value", labels="label").to_string()
    tiles = _tiles(svg)
    total_value = sum(DATA["value"])
    # Tiles are emitted in descending-value order (squarified's precondition), so
    # comparing against the sorted values pairs each tile with its own value.
    for (_x, _y, w, h), value in zip(tiles, sorted(DATA["value"], reverse=True), strict=True):
        # rel=1e-6, not tighter: coordinates are serialized through format_coord, which
        # rounds to 6 decimals, so an exact-area assertion would be testing the
        # serializer's precision rather than the layout's correctness.
        assert w * h == pytest.approx(value / total_value * _PLOT_PIXELS, rel=1e-6)


# ---------------------------------------------------------------------------
# squarified quality
# ---------------------------------------------------------------------------


def test_treemap_aspect_ratios_beat_naive_slice_and_dice() -> None:
    """The whole point of squarified. Slice-and-dice gives every tile the full height
    and a width proportional to its value, which turns small values into slivers —
    on this fixture its worst ratio is ~22 against squarified's ~2."""
    tiles = _tiles(treemap(DATA, values="value", labels="label").to_string())
    total_value = sum(DATA["value"])
    naive = [(0.0, 0.0, value / total_value * _AREA_WIDTH, _AREA_HEIGHT) for value in sorted(DATA["value"], reverse=True)]
    assert _worst_ratio(tiles) < _worst_ratio(naive) / 4


def test_treemap_keeps_tiles_near_square_on_a_uniform_fixture() -> None:
    """Four equal values tile a rectangle as a 2x2 grid, so no tile should be far
    from the plot area's own aspect ratio."""
    data = {"label": ["a", "b", "c", "d"], "value": [1.0, 1.0, 1.0, 1.0]}
    tiles = _tiles(treemap(data, values="value", labels="label").to_string())
    assert len(tiles) == 4
    assert _worst_ratio(tiles) < 1.5


# ---------------------------------------------------------------------------
# labels
# ---------------------------------------------------------------------------


def test_treemap_labels_large_tiles() -> None:
    svg = treemap(DATA, values="value", labels="label").to_string()
    assert ">a<" in svg
    assert ">b<" in svg


def test_treemap_omits_labels_on_tiles_too_small_to_hold_them() -> None:
    """A geometry threshold, not a text measurement — this package has no font
    metrics by design, so tile size is the only signal available."""
    data = {"label": ["huge", "sliver"], "value": [100000.0, 1.0]}
    svg = treemap(data, values="value", labels="label").to_string()
    tiles = _tiles(svg)
    smallest = min(tiles, key=lambda tile: tile[2] * tile[3])
    assert smallest[2] < 40.0 or smallest[3] < 16.0  # below the labelling threshold
    # The legend still names it; only the on-tile label is suppressed.
    on_tile_labels = re.findall(r'text-anchor="middle"[^>]*>([^<]+)<', svg)
    assert "sliver" not in on_tile_labels


def test_treemap_defaults_labels_to_1_based_position_when_omitted() -> None:
    svg = treemap({"value": [5.0, 3.0]}, values="value").to_string()
    assert ">1<" in svg
    assert ">2<" in svg


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


def test_treemap_rejects_negative_value() -> None:
    data = {"label": ["a", "b"], "value": [10.0, -5.0]}
    with pytest.raises(ValueError, match="non-negative"):
        treemap(data, values="value", labels="label")


@pytest.mark.parametrize("bad_value", [float("inf"), float("-inf")])
def test_treemap_rejects_non_finite_value(bad_value: float) -> None:
    """Without an explicit check an inf survives the negative check, becomes nan once
    divided into a proportion, and only then fails — with a message about a coordinate,
    naming neither the offending value nor its row."""
    data = {"label": ["a", "b"], "value": [10.0, bad_value]}
    with pytest.raises(ValueError, match="finite"):
        treemap(data, values="value", labels="label")


def test_treemap_rejects_all_zero_values() -> None:
    data = {"label": ["a", "b"], "value": [0.0, 0.0]}
    with pytest.raises(ValueError, match="zero"):
        treemap(data, values="value", labels="label")


def test_treemap_handles_a_zero_value_among_positives() -> None:
    """A zero-valued tile is legal — it just has no area. It must still emit its rect
    so the tile count matches the row count."""
    data = {"label": ["a", "b"], "value": [10.0, 0.0]}
    tiles = _tiles(treemap(data, values="value", labels="label").to_string())
    assert len(tiles) == 2
    assert min(w * h for _x, _y, w, h in tiles) == pytest.approx(0.0)


def test_treemap_single_tile_fills_the_plot_area() -> None:
    tiles = _tiles(treemap({"label": ["only"], "value": [7.0]}, values="value", labels="label").to_string())
    assert len(tiles) == 1
    (_x, _y, w, h) = tiles[0]
    assert w * h == pytest.approx(_PLOT_PIXELS, abs=1e-6)


def test_treemap_drops_rows_with_missing_value_or_label() -> None:
    data = {"label": ["a", None, "c"], "value": [10.0, 20.0, None]}
    tiles = _tiles(treemap(data, values="value", labels="label").to_string())
    assert len(tiles) == 1


def test_treemap_raises_when_all_rows_missing() -> None:
    data = {"label": [None, None], "value": [None, None]}
    with pytest.raises(ValueError, match="missing"):
        treemap(data, values="value", labels="label")


def test_treemap_raises_on_empty_data() -> None:
    with pytest.raises(ValueError, match="at least one row"):
        treemap({"label": [], "value": []}, values="value", labels="label")


def test_treemap_raises_keyerror_for_unknown_values_column() -> None:
    with pytest.raises(KeyError):
        treemap(DATA, values="nope", labels="label")


def test_treemap_raises_keyerror_for_unknown_labels_column() -> None:
    with pytest.raises(KeyError):
        treemap(DATA, values="value", labels="nope")


def test_treemap_raises_keyerror_for_unknown_theme_preset() -> None:
    with pytest.raises(KeyError):
        treemap(DATA, values="value", labels="label", theme="not-a-real-preset")


def test_treemap_raises_typeerror_for_bad_theme_type() -> None:
    with pytest.raises(TypeError):
        treemap(DATA, values="value", labels="label", theme=123)  # type: ignore[arg-type]


# --------------------------------------------------------------------------------- tooltips


def _tile_titles(svg: str) -> list[str]:
    """The ``<title>`` that is a tile ``<rect>``'s first child, in document order.

    Matched through the mark: this file's other ``<title>`` elements are the chart's own and a
    *label*'s, the one holding the full name when the drawn text had to be shortened. Taking
    every title and dropping the last would count those labels as tiles.
    """
    return re.findall(r'<rect\b[^>]*\bclass="series-\d+"[^>]*(?<!/)>\s*<title>([^<]*)</title>', svg)


def test_a_tile_tooltip_names_it_gives_its_value_and_its_share() -> None:
    """The share is a reading of the picture rather than an extra fact: a treemap encodes value
    as area, so "40.0%" is what the tile's size means."""
    data = {"label": ["alpha", "beta", "gamma", "delta"], "value": [40.0, 30.0, 20.0, 10.0]}
    svg = treemap(data, values="value", labels="label", tooltip=True).to_string()

    assert _tile_titles(svg) == [
        "alpha · value: 40 · 40.0%",
        "beta · value: 30 · 30.0%",
        "gamma · value: 20 · 20.0%",
        "delta · value: 10 · 10.0%",
    ]


def test_a_tile_too_small_for_a_label_still_says_its_name() -> None:
    """The point of the feature. A tile draws its label only at 40x16 px or larger, so the
    smallest tiles -- the ones a reader actually has to look up -- are anonymous rectangles.
    The legend names them, but matching a legend row to a tile in a squarified layout means
    hunting by colour."""
    lopsided = {"label": ["big", "tiny"], "value": [3200.0, 1.0]}
    svg = treemap(lopsided, values="value", labels="label", tooltip=True).to_string()
    drawn = re.findall(r'class="treemap-label legend-text">([^<]*)<', svg)

    assert "tiny" not in drawn, "the fixture stopped being the unlabelled case"
    assert any(title.startswith("tiny · ") for title in _tile_titles(svg))


def test_the_label_stops_taking_the_pointer_when_the_tile_has_something_to_say() -> None:
    """A label sits *inside* its tile, so it intercepts the pointer exactly where the reader is
    looking -- today the tile's ``<title>`` is unreachable there and the label's own truncation
    ``<title>`` comes up instead. The rule is emitted only with ``tooltip=True``: with it off
    that label ``<title>`` is the only thing under the pointer, and taking the label out of the
    way would delete the one way to read the full name."""
    data = {"label": ["alpha", "beta"], "value": [60.0, 40.0]}

    assert (
        ".treemap-label { pointer-events: none; }" in treemap(data, values="value", labels="label", tooltip=True).to_string()
    )
    assert "pointer-events" not in treemap(data, values="value", labels="label").to_string()


def test_a_label_too_long_to_read_is_left_out_of_the_tooltip() -> None:
    """The name is written once per tile. Dropped rather than truncated -- half a name is a
    different name -- and the tile still says its value and its share. The label element keeps
    the full text in its own ``<title>``, which is where a reader recovers it."""
    long_name = "면" * 5000
    data = {"label": [long_name, "b"], "value": [60.0, 40.0]}
    svg = treemap(data, values="value", labels="label", tooltip=True).to_string()

    assert _tile_titles(svg) == ["value: 60 · 60.0%", "b · value: 40 · 40.0%"]
    assert svg.count(long_name) == 2, "the name is repeated beyond its label and its legend row"


def test_the_default_draws_no_tooltip_and_saying_so_changes_nothing() -> None:
    """What this can check is that ``tooltip=False`` is the same call as not writing it, and
    that neither titles a tile. It is deliberately not named for byte-identity with the version
    before ``tooltip=`` existed, which it cannot see -- both sides are this branch's code.
    ``docs/gallery/*.html`` holds those bytes."""
    omitted = treemap(DATA, values="value", labels="label").to_string()
    explicit = treemap(DATA, values="value", labels="label", tooltip=False).to_string()

    assert omitted == explicit
    assert _tile_titles(omitted) == []


def test_every_tile_gets_exactly_one_tooltip() -> None:
    svg = treemap(DATA, values="value", labels="label", tooltip=True).to_string()

    assert len(_tile_titles(svg)) == len(DATA["value"])


def test_the_share_is_rounded_where_the_value_is_not() -> None:
    """A share is a proportion of a total the reader can also see, not a measurement, so one
    decimal is the whole of it. Full precision puts ``33.33333333333333%`` in a tooltip whose
    longest clause would then be the least informative one -- while the *value* beside it is
    spelled exactly, because that one is a number out of somebody's file."""
    thirds = {"label": ["a", "b", "c"], "value": [1.0, 1.0, 1.0]}
    uneven = {"label": ["a", "b"], "value": [1.0, 2.0]}

    assert _tile_titles(treemap(thirds, values="value", labels="label", tooltip=True).to_string()) == [
        "a · value: 1 · 33.3%",
        "b · value: 1 · 33.3%",
        "c · value: 1 · 33.3%",
    ]
    assert _tile_titles(treemap(uneven, values="value", labels="label", tooltip=True).to_string()) == [
        "b · value: 2 · 66.7%",
        "a · value: 1 · 33.3%",
    ]
