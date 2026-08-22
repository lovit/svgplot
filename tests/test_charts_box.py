from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from svgplot.chart.base import Chart
from svgplot.charts._layout import plot_area
from svgplot.charts.box import boxplot
from svgplot.scales import LinearScale
from svgplot.stats.box import MODES, BoxStats, box_stats

NO_OUTLIER_DATA = {
    "group": ["a", "a", "a", "a", "a", "b", "b", "b", "b", "b"],
    "value": [1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 12.0, 14.0, 16.0, 18.0],
}
WITH_OUTLIER_DATA = {
    "group": ["a", "a", "a", "a", "a"],
    "value": [1.0, 2.0, 3.0, 4.0, 100.0],
}

# Mirrors boxplot()'s own canvas/margin constants, so a test can recompute the
# pixel coordinates a given stat *should* map to instead of just asserting an
# element exists.
_AREA = plot_area(800.0, 600.0, margin=(30.0, 40.0, 50.0, 60.0))


def _elements(chart: Chart, tag: str, class_prefix: str = "") -> list[dict[str, str]]:
    """Attributes of every ``tag`` element whose class starts with ``class_prefix``.

    Re-parsing the serialized SVG namespaces the tags, hence the ``}``-strip.
    """
    root = ET.fromstring(chart.to_string(pretty=False))
    return [
        element.attrib
        for element in root.iter()
        if element.tag.split("}")[-1] == tag and (element.get("class") or "").startswith(class_prefix)
    ]


def _boxes(chart: Chart) -> list[dict[str, str]]:
    """Every line a box is drawn with, for a chart that draws no legend.

    A legend swatch is a ``<line>`` carrying the same ``series-N`` class as the marks it
    stands for, and structurally it is indistinguishable from a whisker cap -- same tag, same
    class, same zero height. Only its position tells them apart, and a test that filtered on
    the plot area's right edge would be asserting a layout constant to answer a question about
    marks.

    So the case is refused rather than guessed at. Every caller here draws without ``hue=``,
    which is the configuration these tests are about; a legend appears only with ``hue=``, and
    left unchecked it would arrive as a phantom sixth "box" of one element -- a wrong answer
    that looks like a real one.
    """
    assert not _elements(
        chart, "text", "legend-text"
    ), "this chart has a legend, whose swatch is indistinguishable from a whisker cap"
    return _elements(chart, "line", "series-1")


def _by_category(elements: list[dict[str, str]]) -> list[list[dict[str, str]]]:
    """``elements`` grouped into one list per box, left to right.

    Selecting on ``series-N`` used to do this, back when a box's palette slot was its
    category. Colour now comes from ``hue=`` and nothing else, so every box without a hue
    carries ``series-1`` and the class no longer says which category a mark belongs to --
    which is the point of the change, and a reason to group by something that still does.

    Grouped on the mark's centre, within a tolerance, and the tolerance is measured rather
    than picked. Every line in one box -- the median across the full width, the two caps at
    60% of it, the two stems at zero width -- is drawn symmetrically about the same centre, so
    in exact arithmetic their centres are equal. The *emitted* coordinates are not: each end is
    rounded to six decimals independently, so a centre recovered from two ends can be off by
    half of that. Measured across 1 - 20 categories at six canvas widths, the worst spread
    inside one box is 5e-7px and the smallest gap between two boxes is 7px -- seven orders of
    magnitude apart, so ``_SAME_BOX`` can sit anywhere in between without being tuned to a
    fixture.

    Two earlier versions of this got it wrong in opposite ways, and both are worth recording.
    The first clustered on ``x1`` with a 40px threshold whose docstring claimed the within-box
    spread was under 30px; it was 105px, a number taken from the fixture. The second claimed
    the centres were *exact* and used equality -- which passes on this file's two-category
    fixture, where every coordinate lands integral, and splits a box in two at six categories
    and in three at eleven. Three is the ceiling, not a measurement: a box emits exactly three
    distinct x-pairs -- the median across the full width, the two caps, the two zero-width
    stems -- so equality can separate it into at most three. Nor is it monotonic; seven, eight,
    ten and twelve categories do not split at all. Neither ``Decimal`` nor rounding to the emitted precision rescues equality,
    because the two ends are rounded independently and their errors do not cancel.
    """
    ordered = sorted(elements, key=_centre)
    groups: list[list[dict[str, str]]] = []
    for attributes in ordered:
        if not groups or _centre(attributes) - _centre(groups[-1][-1]) > _SAME_BOX:
            groups.append([])
        groups[-1].append(attributes)
    return groups


def _centre(attributes: dict[str, str]) -> float:
    return (float(attributes["x1"]) + float(attributes["x2"])) / 2


_SAME_BOX = 0.001
"""How far two marks' centres may differ and still belong to one box.

Two thousand times the worst rounding error and seven thousand times below the smallest gap
between boxes -- see :func:`_by_category` for both measurements.
"""


def _y_scale(stats_by_category: list[BoxStats]) -> LinearScale:
    """Rebuild the y scale boxplot() derives from the rendered stats — the domain
    spans every whisker *and* every outlier, which is what keeps outliers on-canvas.
    """
    lows = [s.whisker_low for s in stats_by_category] + [o for s in stats_by_category for o in s.outliers]
    highs = [s.whisker_high for s in stats_by_category] + [o for s in stats_by_category for o in s.outliers]
    return LinearScale((min(lows), max(highs)), (_AREA.bottom, _AREA.top))


@pytest.mark.parametrize("mode", MODES)
def test_boxplot_renders_for_every_mode(mode: str) -> None:
    chart = boxplot(NO_OUTLIER_DATA, x="group", y="value", mode=mode)
    svg = chart.to_string()
    assert svg.count("<rect") >= 2  # plot-background + at least one box per category (2 categories)


def test_boxplot_draws_one_box_per_distinct_x_category() -> None:
    """Counted as box bodies, not as palette classes.

    Two categories used to mean ``series-1`` and ``series-2``, so the class count was the box
    count. Colour follows ``hue=`` alone now, so both boxes are ``series-1`` and the rects are
    what has to be counted -- which is what the test was ever about.
    """
    chart = boxplot(NO_OUTLIER_DATA, x="group", y="value")

    assert len(_elements(chart, "rect", "series-1-marker")) == 2
    assert "series-2" not in chart.to_string(), "a category took a palette slot of its own"


def test_boxplot_box_spans_exactly_q1_to_q3_in_pixels() -> None:
    """Pins the rect against the pixel positions q1/q3 map to, so swapping the two
    (or scaling either wrongly) fails — asserting only that a rect exists would not.
    """
    stats = box_stats(WITH_OUTLIER_DATA["value"], mode="1.5IQR")
    assert stats.q1 != stats.q3  # sanity: this dataset has a non-degenerate box
    chart = boxplot(WITH_OUTLIER_DATA, x="group", y="value", mode="1.5IQR")

    y_scale = _y_scale([stats])
    (box,) = _elements(chart, "rect", "series-1-marker")
    assert float(box["y"]) == pytest.approx(y_scale(stats.q3))  # q3 is the *top* edge (y grows downward)
    assert float(box["y"]) + float(box["height"]) == pytest.approx(y_scale(stats.q1))


def test_boxplot_shows_outlier_as_a_marker_when_present() -> None:
    chart = boxplot(WITH_OUTLIER_DATA, x="group", y="value", mode="1.5IQR")
    svg = chart.to_string()
    assert "<circle" in svg


def test_boxplot_shows_no_outlier_marker_when_none_present() -> None:
    chart = boxplot(NO_OUTLIER_DATA, x="group", y="value", mode="1.5IQR")
    svg = chart.to_string()
    assert "<circle" not in svg


def test_boxplot_median_line_sits_between_box_edges() -> None:
    """Renders and inspects the actual median <line> — the previous version only
    re-checked a box_stats invariant, so it passed without drawing anything.
    """
    stats = box_stats(WITH_OUTLIER_DATA["value"], mode="1.5IQR")
    chart = boxplot(WITH_OUTLIER_DATA, x="group", y="value", mode="1.5IQR")

    (box,) = _elements(chart, "rect", "series-1-marker")
    median_line = _elements(chart, "line", "series-1")[0]  # median is drawn before the whiskers
    top, bottom = float(box["y"]), float(box["y"]) + float(box["height"])
    assert top <= float(median_line["y1"]) <= bottom
    assert float(median_line["y1"]) == pytest.approx(_y_scale([stats])(stats.median))


def test_boxplot_draws_exactly_five_series_lines_per_category() -> None:
    """Median + 2 whisker stems + 2 caps, per category. Counting *all* <line>
    elements would not catch a missing box: the axes alone emit 12 of them.
    """
    chart = boxplot(NO_OUTLIER_DATA, x="group", y="value")

    assert [len(category) for category in _by_category(_boxes(chart))] == [5, 5]


def test_boxplot_whisker_caps_sit_at_the_whisker_ends() -> None:
    stats = box_stats(NO_OUTLIER_DATA["value"][:5], mode="1.5IQR")
    chart = boxplot(NO_OUTLIER_DATA, x="group", y="value")
    y_scale = _y_scale([stats, box_stats(NO_OUTLIER_DATA["value"][5:], mode="1.5IQR")])

    first_category, _second = _by_category(_boxes(chart))
    _median, _upper_stem, upper_cap, _lower_stem, lower_cap = first_category
    for cap, whisker in ((upper_cap, stats.whisker_high), (lower_cap, stats.whisker_low)):
        assert float(cap["y1"]) == float(cap["y2"]) == pytest.approx(y_scale(whisker))  # horizontal, at the whisker end
        assert float(cap["x1"]) < float(cap["x2"])  # non-zero width


def test_boxplot_y_domain_includes_outliers() -> None:
    """An outlier outside the whisker range must still land inside the *plot area*
    (top=30..bottom=550), not merely the canvas — the looser canvas bound (0..600)
    would still pass even if the outlier were drawn over the axis margin.
    """
    stats = box_stats(WITH_OUTLIER_DATA["value"], mode="1.5IQR")
    assert stats.outliers  # sanity: this dataset actually produces an outlier
    chart = boxplot(WITH_OUTLIER_DATA, x="group", y="value", mode="1.5IQR")

    (outlier_marker,) = _elements(chart, "circle", "series-1-marker")
    cy = float(outlier_marker["cy"])
    assert _AREA.top <= cy <= _AREA.bottom
    assert cy == pytest.approx(_y_scale([stats])(stats.outliers[0]))


@pytest.mark.parametrize(
    "values",
    [[5.0], [7.0, 7.0, 7.0, 7.0]],
    ids=["single value", "all identical"],
)
def test_boxplot_degenerate_group_renders_a_zero_height_box(values: list[float]) -> None:
    """Pins today's behavior: when every quartile collapses to one value the box has
    height 0, so it is effectively invisible. Recorded so a future minimum-height
    change is a deliberate decision rather than an unnoticed regression.
    """
    data = {"group": ["a"] * len(values), "value": values}
    chart = boxplot(data, x="group", y="value")

    (box,) = _elements(chart, "rect", "series-1-marker")
    assert float(box["height"]) == 0.0
    assert float(box["width"]) > 0.0  # the box still spans the category band horizontally


def test_boxplot_modes_produce_different_whiskers_for_the_same_data() -> None:
    """ "각 mode별 렌더" is only meaningful if the mode actually changes the output:
    "extremes" stretches the whisker to the max and reports no outlier, while
    "1.5IQR" fences it off and reports the same point as an outlier.
    """
    extremes = box_stats(WITH_OUTLIER_DATA["value"], mode="extremes")
    iqr = box_stats(WITH_OUTLIER_DATA["value"], mode="1.5IQR")
    assert extremes.whisker_high != iqr.whisker_high
    assert extremes.outliers == [] and iqr.outliers == [100.0]

    extremes_chart = boxplot(WITH_OUTLIER_DATA, x="group", y="value", mode="extremes")
    iqr_chart = boxplot(WITH_OUTLIER_DATA, x="group", y="value", mode="1.5IQR")
    assert _elements(extremes_chart, "circle", "series-1-marker") == []
    assert len(_elements(iqr_chart, "circle", "series-1-marker")) == 1


def test_boxplot_drops_rows_with_missing_x_or_y() -> None:
    data = {"group": ["a", "a", None, "a"], "value": [1.0, 2.0, 3.0, None]}
    chart = boxplot(data, x="group", y="value")
    svg = chart.to_string()
    assert "series-1" in svg
    assert "series-2" not in svg


def test_boxplot_raises_value_error_for_empty_data() -> None:
    with pytest.raises(ValueError, match="at least one row"):
        boxplot({"group": [], "value": []}, x="group", y="value")


def test_boxplot_raises_value_error_when_all_rows_missing() -> None:
    with pytest.raises(ValueError, match="no rows"):
        boxplot({"group": [None, None], "value": [1.0, 2.0]}, x="group", y="value")


def test_boxplot_raises_key_error_for_missing_column() -> None:
    with pytest.raises(KeyError):
        boxplot(NO_OUTLIER_DATA, x="not_a_column", y="value")


def test_boxplot_raises_key_error_for_unknown_theme_preset() -> None:
    with pytest.raises(KeyError):
        boxplot(NO_OUTLIER_DATA, x="group", y="value", theme="not_a_preset")


def test_boxplot_propagates_box_stats_error_for_unknown_mode() -> None:
    with pytest.raises(ValueError, match="unknown box mode"):
        boxplot(NO_OUTLIER_DATA, x="group", y="value", mode="not_a_mode")


def test_boxplot_corner_radius_produces_rx_attribute() -> None:
    chart = boxplot(NO_OUTLIER_DATA, x="group", y="value", theme="minimal")
    svg_default = chart.to_string()
    assert 'rx="' not in svg_default  # "minimal" preset doesn't set corner_radius

    from svgplot.theme.base import Theme

    chart = boxplot(NO_OUTLIER_DATA, x="group", y="value", theme=Theme(corner_radius=4.0))
    svg = chart.to_string()
    assert 'rx="4"' in svg


# --------------------------------------------------------------------------------- tooltips


def _marks(chart: Chart) -> list[tuple[str, str | None]]:
    """Every drawn mark as ``(class, its <title> text or None)``, in document order.

    Through the parsed tree rather than a regex, so a mark that lost its ``<title>`` shows up
    as ``None`` rather than disappearing from the list -- the whole question here is which
    marks *have* one. The chart's own ``<title>`` is a child of the root ``<svg>``, which
    carries no ``series`` class, so it is excluded by the filter rather than by position.
    """
    root = ET.fromstring(chart.to_string(pretty=False))
    marks = []
    for element in root.iter():
        classes = (element.get("class") or "").split()
        if not any(name.startswith("series-") for name in classes):
            continue
        title = element.find("{http://www.w3.org/2000/svg}title")
        marks.append((classes[0], None if title is None else title.text))
    return marks


# Two categories, different quartiles, and *different outlier counts* -- one and two. Every
# assertion below compares the whole set of sentences, so a box that named the other box's
# category or the other box's stats has nowhere to hide. On a one-category fixture six separate
# wrong-attribution mutations were green in this file: naming ``drawn_categories[0]``, swapping
# the two boxes' stats, and four more on the outliers. And with one outlier per box,
# ``plural(len(outliers))`` and a hard-coded ``plural(1)`` agree.
TWO_CATEGORIES_WITH_OUTLIERS = {
    "group": ["a"] * 5 + ["b"] * 10,
    "value": [1.0, 2.0, 3.0, 4.0, 100.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 200.0, 300.0],
}


def test_a_box_tooltip_names_its_quartiles_whiskers_and_outlier_count() -> None:
    chart = boxplot(WITH_OUTLIER_DATA, x="group", y="value", tooltip=True)
    said = {title for _, title in _marks(chart) if title and not title.endswith(" · outlier")}

    assert said == {"group: a · value: Q1 2 · median 3 · Q3 4 · whiskers: [1, 4] · 1 outlier"}


def test_each_box_says_its_own_category_and_its_own_numbers() -> None:
    """The set of sentences, on a fixture where the two boxes differ in every clause. Asserting
    "two distinct sentences" or "each starts with ``group:``" instead lets a box name the other
    box's category, or the two swap their stats wholesale, with nothing in this file noticing --
    only the committed gallery, whose failure message says to regenerate the file."""
    chart = boxplot(TWO_CATEGORIES_WITH_OUTLIERS, x="group", y="value", tooltip=True)
    summaries = {title for _, title in _marks(chart) if title and not title.endswith(" · outlier")}

    assert summaries == {
        "group: a · value: Q1 2 · median 3 · Q3 4 · whiskers: [1, 4] · 1 outlier",
        "group: b · value: Q1 12.25 · median 14.5 · Q3 16.75 · whiskers: [10, 17] · 2 outliers",
    }


def test_each_outlier_says_its_own_category_group_and_value() -> None:
    """Same shape for the circles, and the reason is the same: with one outlier in one category
    a tooltip naming ``outliers[0]``'s value, or ``drawn_categories[0]``, or ``hue_values[0]``,
    is indistinguishable from the right answer."""
    chart = boxplot(TWO_CATEGORIES_WITH_OUTLIERS, x="group", y="value", tooltip=True)
    circles = {title for _, title in _marks(chart) if title and title.endswith(" · outlier")}

    assert circles == {
        "group: a · value: 100 · outlier",
        "group: b · value: 200 · outlier",
        "group: b · value: 300 · outlier",
    }


def test_every_mark_of_a_box_says_the_same_thing_and_none_is_left_silent() -> None:
    """The pointer stops at the topmost element under it, so a mark with no ``<title>`` is a
    hole in the glyph -- an untitled median line reads as a dead stripe across a box that
    otherwise responds. Six marks per box: body, median, two stems, two caps.

    "Every mark has one, and each box's are all equal" is the part that survives a box growing
    a seventh mark. The count below does not, and it is here on purpose: a seventh mark is a
    change somebody should have to look at, and this is where they find out."""
    marks = _marks(boxplot(NO_OUTLIER_DATA, x="group", y="value", tooltip=True))

    assert marks, "the fixture stopped drawing anything"
    assert all(title is not None for _, title in marks), "a mark was left without a tooltip"
    assert len({title for _, title in marks}) == 2, "two boxes, two sentences, repeated across their marks"
    assert len(marks) == 12, "and each box is six marks"


def test_an_outlier_names_its_own_value_because_it_is_one_observation() -> None:
    """The box is a summary of many rows and cannot name one of them. An outlier circle is a
    single value, and it repeats the category rather than leaning on the box behind it: the
    circle is drawn on top and usually outside the box entirely."""
    marks = _marks(boxplot(WITH_OUTLIER_DATA, x="group", y="value", tooltip=True))
    circles = [title for _, title in marks if title and title.endswith(" · outlier")]

    assert circles == ["group: a · value: 100 · outlier"]


def test_a_box_with_no_outliers_says_nothing_about_outliers() -> None:
    """``plural(0, "outlier")`` would read "0 outliers", which is a sentence about something
    that is not on screen. The clause is left out instead."""
    marks = _marks(boxplot(NO_OUTLIER_DATA, x="group", y="value", tooltip=True))

    assert all(title and "outlier" not in title for _, title in marks)


def test_a_hued_box_names_its_group_as_well_as_its_category() -> None:
    data = {
        "group": ["a", "a", "a", "b", "b", "b"],
        "value": [1.0, 2.0, 3.0, 10.0, 12.0, 14.0],
        "side": ["left", "right", "left", "right", "left", "right"],
    }
    # ``if title`` drops the legend swatches, which carry a series class and no tooltip -- the
    # legend already names the group in text beside them.
    said = {title for _, title in _marks(boxplot(data, x="group", y="value", hue="side", tooltip=True)) if title}

    assert said, "the fixture stopped drawing boxes"
    assert all(title.startswith("group: ") and " · side: " in title for title in said)
    assert {title.split(" · ")[1] for title in said} == {"side: left", "side: right"}


def test_a_hued_outlier_names_its_own_group() -> None:
    """The circle has to carry the hue clause itself. With one group having outliers, naming
    ``hue_values[0]`` for every circle is indistinguishable from the right answer -- so both
    groups get one, and they are different values."""
    data = {
        "group": ["a"] * 10,
        "value": [1.0, 2.0, 3.0, 4.0, 50.0, 10.0, 11.0, 12.0, 13.0, 500.0],
        "side": ["left"] * 5 + ["right"] * 5,
    }
    circles = {
        title
        for _, title in _marks(boxplot(data, x="group", y="value", hue="side", tooltip=True))
        if title and title.endswith(" · outlier")
    }

    assert circles == {
        "group: a · side: left · value: 50 · outlier",
        "group: a · side: right · value: 500 · outlier",
    }


def test_the_default_draws_no_tooltip_and_saying_so_changes_nothing() -> None:
    """What this can check is that ``tooltip=False`` is the same call as not writing it, and
    that neither titles a mark. It is deliberately not named for byte-identity with the version
    before ``tooltip=`` existed, which it cannot see -- both sides are this branch's code.
    ``docs/gallery/*.html`` holds those bytes, and
    ``test_gallery.py::test_the_committed_gallery_is_what_a_fresh_build_produces`` compares
    them."""
    omitted = boxplot(WITH_OUTLIER_DATA, x="group", y="value")
    explicit = boxplot(WITH_OUTLIER_DATA, x="group", y="value", tooltip=False)

    assert omitted.to_string() == explicit.to_string()
    assert all(title is None for _, title in _marks(omitted))


def test_a_category_too_long_or_too_blank_to_read_is_left_out_of_the_tooltip() -> None:
    """The category is a string out of the data and it is written once per mark -- six times
    per box, plus once per outlier, where ``barplot`` writes it once. Uncapped, the two boxes
    below took the file from 18,345 bytes to 109,479, with seven ``<title>`` elements over
    4,000 characters and the longest at 5,062. The axis tick showing the same category is
    already shortened, and so are the column names.

    A category of one tab goes for the other reason: ``"group:  · value: …"`` names the box
    with a label that is not on screen."""
    data = {"group": ["면" * 5000] * 3 + ["\t"] * 3, "value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]}
    chart = boxplot(data, x="group", y="value", tooltip=True)
    said = {title for _, title in _marks(chart) if title}

    assert len(chart.to_string().encode()) < 25_000, "the unreadable category was written into the file anyway"
    assert said == {
        "value: Q1 1.5 · median 2 · Q3 2.5 · whiskers: [1, 3]",
        "value: Q1 4.5 · median 5 · Q3 5.5 · whiskers: [4, 6]",
    }
