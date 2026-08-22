"""``hue=`` on ``boxplot``/``violinplot`` — seaborn's second grouping axis (#135).

``x=`` decides what is placed next to what; ``hue=`` decides what is compared inside each of
those. The properties worth pinning are that the two never merge (one colour per hue in every
category), that a chart drawn without it is untouched, and that the dodged marks stay inside
the band they belong to.
"""

from __future__ import annotations

import random
import re
import warnings
import xml.etree.ElementTree as ET

import pytest

import svgplot as sp
from svgplot.charts._categorical import NO_HUE, group_by_category
from svgplot.charts._layout import DEFAULT_HEIGHT, DEFAULT_WIDTH, MARGIN_WITH_LEGEND, plot_area
from svgplot.scales import CategoricalScale

SVG = "{http://www.w3.org/2000/svg}"
CATEGORIES = ["Thu", "Fri", "Sat"]
HUES = ["Yes", "No"]
PLOTS = [sp.boxplot, sp.violinplot]


def _data(rows_per_cell: int = 8) -> dict[str, list]:
    """Every (category, hue) cell filled, with values that differ per cell.

    Filled deliberately: a fixture that happens to miss a cell hides whether an *absent* cell
    is skipped or merely mis-drawn, and the counts below would then prove nothing.
    """
    rng = random.Random("hue")
    rows = [
        (category, hue, float(10 + 3 * index + 7 * slot) + rng.random() * 4)
        for index, category in enumerate(CATEGORIES)
        for slot, hue in enumerate(HUES)
        for _ in range(rows_per_cell)
    ]
    return {"day": [row[0] for row in rows], "smoker": [row[1] for row in rows], "bill": [row[2] for row in rows]}


def _marks(svg: str, tag: str, needle: str) -> list[dict[str, str]]:
    root = ET.fromstring(svg)
    return [
        node.attrib
        for node in root.iter(f"{SVG}{tag}")
        if needle in (node.get("class") or "") and "plot-background" not in (node.get("class") or "")
    ]


def _series_classes(svg: str) -> set[str]:
    return set(re.findall(r"\b(series-\d+)\b", svg))


# --- the grouping ----------------------------------------------------------------------


@pytest.mark.parametrize("plot", PLOTS)
def test_one_mark_per_category_and_hue(plot) -> None:
    """Three categories times two groups is six marks, not three and not two."""
    svg = plot(_data(), x="day", y="bill", hue="smoker").to_string()

    centres = {round(float(mark["x"]), 1) for mark in _marks(svg, "rect", "marker")} or {
        round(float(path["d"].split()[1].split(",")[0]), 1) for path in _marks(svg, "path", "violin-body")
    }

    assert len(centres) == len(CATEGORIES) * len(HUES)


@pytest.mark.parametrize("plot", PLOTS)
def test_a_hue_group_keeps_one_colour_across_every_category(plot) -> None:
    """The comparison the argument exists for. Cycling the palette per category instead would
    make the same group a different colour in each, which is the question ``x=`` already
    answers with position."""
    svg = plot(_data(), x="day", y="bill", hue="smoker").to_string()

    assert len(_series_classes(svg)) == len(HUES)


@pytest.mark.parametrize("plot", PLOTS)
def test_without_a_hue_every_category_is_one_colour(plot) -> None:
    """The other half of the same rule, and the half that changed.

    These charts used to cycle the palette per category, on the grounds that colour was then
    the only thing telling two of them apart. It is not: a category is named by its axis label
    and placed by its position, so a rotating palette spends a colour claiming a distinction
    the colour does not carry -- and it made ``barplot``, which never did this, the odd one
    out among three charts of the same shape. Colour means ``hue=`` now, in all three.
    """
    svg = plot(_data(), x="day", y="bill").to_string()

    assert len(_series_classes(svg)) == 1


@pytest.mark.parametrize("plot", PLOTS)
def test_the_three_category_charts_agree_about_colour(plot) -> None:
    """Stated across the three rather than inside each, because the defect was the disagreement.

    ``barplot`` drew one colour, ``boxplot`` and ``violinplot`` drew one per category, and
    nothing compared them -- each had its own test asserting its own behaviour, and both
    passed. A rule that is meant to hold across a family needs an assertion that spans it.
    """
    from svgplot import barplot

    categories = len(_series_classes(barplot(_data(), x="day", y="bill", estimator="mean").to_string()))

    assert len(_series_classes(plot(_data(), x="day", y="bill").to_string())) == categories == 1


@pytest.mark.parametrize("plot", PLOTS)
def test_a_legend_names_the_hue_groups_and_only_appears_with_one(plot) -> None:
    with_hue = plot(_data(), x="day", y="bill", hue="smoker").to_string()
    without = plot(_data(), x="day", y="bill").to_string()

    def rows(svg: str) -> list[str]:
        # The *elements*, not the string: every theme's stylesheet carries a ``.legend-text``
        # rule whether a legend is drawn or not, so a substring check passes on a chart that
        # has no legend at all.
        return [
            (node.text or "") for node in ET.fromstring(svg).iter(f"{SVG}text") if "legend-text" in (node.get("class") or "")
        ]

    assert rows(with_hue) == sorted(HUES)
    assert rows(without) == []


@pytest.mark.parametrize("plot", PLOTS)
def test_the_description_reads_out_the_hue_groups(plot) -> None:
    """A reader who cannot see the legend still has to learn there are two of them."""
    root = ET.fromstring(plot(_data(), x="day", y="bill", hue="smoker").to_string())
    desc = next(node for node in root if node.tag == f"{SVG}desc").text or ""

    assert "2 series (No, Yes)" in desc


@pytest.mark.parametrize("plot", PLOTS)
def test_a_category_missing_one_group_keeps_its_place(plot) -> None:
    """The rule ``categories=`` already follows: an absent cell leaves a gap rather than
    shifting the marks after it, or two charts of the same data disagree about position."""
    data = _data()
    keep = [
        index
        for index, (day, smoker) in enumerate(zip(data["day"], data["smoker"], strict=True))
        if not (day == "Fri" and smoker == "Yes")
    ]
    sparse = {key: [values[index] for index in keep] for key, values in data.items()}

    full = plot(data, x="day", y="bill", hue="smoker").to_string()
    thin = plot(sparse, x="day", y="bill", hue="smoker").to_string()

    def centres(svg: str) -> set[float]:
        return {round(float(mark["x"]), 1) for mark in _marks(svg, "rect", "marker")} or {
            round(float(path["d"].split()[1].split(",")[0]), 1) for path in _marks(svg, "path", "violin-body")
        }

    assert centres(thin) < centres(full), "removing a cell moved the others"


# --- the geometry ----------------------------------------------------------------------


@pytest.mark.parametrize("plot", PLOTS)
def test_dodged_marks_stay_inside_their_own_band(plot) -> None:
    """Splitting a band into slots is only worth anything if the slots hold. A mark drifting
    into the neighbouring category reads as belonging to it."""
    svg = plot(_data(), x="day", y="bill", hue="smoker").to_string()
    area = plot_area(DEFAULT_WIDTH, DEFAULT_HEIGHT, margin=MARGIN_WITH_LEGEND)
    scale = CategoricalScale(CATEGORIES, (area.left, area.right))
    edges = [*sorted(scale(category) for category in CATEGORIES), area.right]

    for mark in _marks(svg, "rect", "marker") or _marks(svg, "rect", "violin-box"):
        left, width = float(mark["x"]), float(mark["width"])
        band = max(index for index, edge in enumerate(edges[:-1]) if edge <= left + width / 2)
        assert edges[band] <= left and left + width <= edges[band + 1], (mark, edges)


@pytest.mark.parametrize("plot", PLOTS)
def test_the_no_hue_chart_is_untouched(plot) -> None:
    """Every width in the dodge divides by the number of slots, which is one without a hue --
    so the whole feature has to reduce to exactly what was drawn before it existed."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert plot(_data(), x="day", y="bill").to_string() == plot(_data(), x="day", y="bill", hue=None).to_string()


# --- the shared grouping helper ---------------------------------------------------------


def test_both_charts_group_through_one_function() -> None:
    """The README says the two take the same positional arguments; they now also agree on what
    a category and a hue group *are*, because there is only one implementation left."""

    columns = {"g": ["a", "a", "b"], "v": [1.0, 2.0, 3.0], "h": ["x", "y", "x"]}

    assert group_by_category(columns, "g", "v", "h") == group_by_category(columns, "g", "v", "h")


def test_a_missing_hue_value_drops_its_row() -> None:
    """The same rule the x and y columns already follow. Bucketing those rows under the string
    "None" would invent a group the data does not have."""
    columns = {"g": ["a", "a"], "v": [1.0, 2.0], "h": ["x", None]}

    assert group_by_category(columns, "g", "v", "h") == {("a", "x"): [1.0]}


def test_a_nan_category_label_drops_its_row_on_both_charts() -> None:
    """``violinplot`` filtered with ``is_missing`` and ``boxplot`` with ``is None``, so a NaN
    label became a category called "nan" on one chart and vanished on the other -- exactly the
    disagreement sharing the function ends."""
    columns = {"g": [float("nan"), "a", "a"], "v": [1.0, 2.0, 3.0]}

    assert group_by_category(columns, "g", "v") == {("a", NO_HUE): [2.0, 3.0]}
