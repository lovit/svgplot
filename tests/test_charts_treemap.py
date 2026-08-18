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
