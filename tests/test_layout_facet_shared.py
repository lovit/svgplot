"""Faceted panels share their axes, so they can actually be compared.

The failure this file exists around is silent: two panels draw a line to the same height,
one means 3 and the other 300, and nothing on the page says so. So the assertions here are
about **tick labels and mark coordinates**, not about panel counts -- a chart that faceted
correctly and scaled wrongly passes every structural check.
"""

from __future__ import annotations

import re

import pytest

import svgplot as sp
from svgplot.chart._domain import Domains, union

# Two groups whose y ranges do not overlap at all, so an unshared axis is unmistakable.
SPLIT = {
    "x": [1, 2, 3, 4, 5, 6],
    "y": [1.0, 2.0, 3.0, 100.0, 200.0, 300.0],
    "g": ["a", "a", "a", "b", "b", "b"],
}


def _widths(svg: str) -> list[set[str]]:
    """Bar widths per panel -- the shape of the division, independent of how many bars filled."""
    return [set(re.findall(r'<rect[^>]*width="([\d.]+)"[^>]*class="c\d+-series', panel)) for panel in _panels(svg)]


def _panels(svg: str) -> list[str]:
    return re.split(r"(?=<svg x=)", svg)[1:]


def _ticks(panel: str) -> list[str]:
    """Composition namespaces every class (``tick-label`` becomes ``c0-tick-label``), so a
    pattern anchored on the bare name matches nothing and two panels compare equal by both
    being empty. Asserted non-empty at each call site for the same reason."""
    return re.findall(r'class="c?\d*-?tick-label"[^>]*>([^<]+)</text>', panel)


def _numbers(panel: str) -> list[float]:
    return [float(tick) for tick in _ticks(panel) if re.fullmatch(r"-?\d+(\.\d+)?", tick)]


def _axis_numbers(panel: str) -> tuple[list[float], list[float]]:
    """Numeric tick labels split into (x, y) by where they sit.

    ``render_x_axis`` writes below the plot area and ``render_y_axis`` to its left, so the
    two are separable by position. Reading them as one list mixes the axes and lets a test
    about x pass because y happened to agree."""
    labelled = re.findall(r'<text x="(-?[\d.]+)" y="(-?[\d.]+)"[^>]*class="c?\d*-?tick-label"[^>]*>([^<]+)<', panel)
    numeric = [(float(x), float(y), tick) for x, y, tick in labelled if re.fullmatch(r"-?\d+(\.\d+)?", tick)]
    if not numeric:
        return [], []
    left_edge = min(x for x, _, _ in numeric)
    y_axis = [float(tick) for x, _, tick in numeric if x == left_edge]
    x_axis = [float(tick) for x, _, tick in numeric if x != left_edge]
    return x_axis, y_axis


def _axis_labels(panel: str) -> tuple[list[str], list[str]]:
    """All tick labels split into (left-edge, elsewhere) by position, numeric or not."""
    labelled = re.findall(r'<text x="(-?[\d.]+)" y="-?[\d.]+"[^>]*class="c?\d*-?tick-label"[^>]*>([^<]+)<', panel)
    if not labelled:
        return [], []
    left_edge = min(float(x) for x, _ in labelled)
    return (
        [text for x, text in labelled if float(x) == left_edge],
        [text for x, text in labelled if float(x) != left_edge],
    )


def test_panels_share_their_axes_by_default() -> None:
    """The whole point. Without this the two panels' tick sets are disjoint -- 1..3 against
    100..300 -- while their lines reach the same height."""
    panels = _panels(sp.facet(sp.lineplot, SPLIT, col="g", x="x", y="y").to_string())

    assert len(panels) == 2
    assert _ticks(panels[0]), "no tick labels found — the pattern is not matching"
    assert _ticks(panels[0]) == _ticks(panels[1])


def test_the_shared_axis_spans_every_panel_s_data() -> None:
    """Equal tick sets are not enough on their own: two panels both clipped to the same
    wrong window would also be equal. The span has to cover the union of the data.

    Read per axis. An earlier version pooled both axes into one list, and the y ticks (up
    to 300) satisfied the x assertion (>= 6) on their own -- removing x sharing entirely
    left this test green."""
    panels = _panels(sp.facet(sp.lineplot, SPLIT, col="g", x="x", y="y").to_string())
    x_ticks, y_ticks = _axis_numbers(panels[0])

    assert x_ticks and y_ticks
    # ``make_ticks`` rounds to nice values, so the ticks bracket the domain rather than
    # landing on it. What matters is that the left panel's axis reaches into the right
    # panel's data -- 300 is nowhere near its own maximum of 3.
    assert max(x_ticks) >= 6.0
    assert max(y_ticks) >= 300.0


def test_turning_sharing_off_restores_per_panel_scaling() -> None:
    """The previous behaviour is still reachable, and is what ``sharex=False`` means."""
    panels = _panels(sp.facet(sp.lineplot, SPLIT, col="g", x="x", y="y", sharex=False, sharey=False).to_string())

    assert _ticks(panels[0]) != _ticks(panels[1])
    assert max(_numbers(panels[0])) < min(_numbers(panels[1]))


@pytest.mark.parametrize(("sharex", "sharey"), [(True, False), (False, True)])
def test_the_two_axes_are_shared_independently(sharex: bool, sharey: bool) -> None:
    """One flag must not quietly do the other's work."""
    panels = _panels(sp.facet(sp.lineplot, SPLIT, col="g", x="x", y="y", sharex=sharex, sharey=sharey).to_string())
    (left_x, left_y), (right_x, right_y) = (_axis_numbers(panel) for panel in panels)

    assert left_x and left_y, "no ticks found on one of the axes"
    # SPLIT's x and y both differ per group, so each axis agrees across panels exactly when
    # its own flag is on.
    assert (left_x == right_x) is sharex
    assert (left_y == right_y) is sharey


def test_a_panel_s_marks_move_with_the_shared_axis() -> None:
    """Ticks could agree while the marks were drawn against the old scale. The line for
    group 'a' (values 1..3) must sit near the bottom of a 1..300 axis, not span the panel."""
    shared = _panels(sp.facet(sp.lineplot, SPLIT, col="g", x="x", y="y").to_string())[0]
    alone = _panels(sp.facet(sp.lineplot, SPLIT, col="g", x="x", y="y", sharey=False).to_string())[0]

    def height_span(panel: str) -> float:
        ys = [float(y) for _, y in re.findall(r"[ML] (-?[\d.]+),(-?[\d.]+)", panel)]
        return max(ys) - min(ys)

    assert height_span(shared) < height_span(alone) / 10


# ---------------------------------------------------------------------------
# categorical axes
# ---------------------------------------------------------------------------

CATEGORIES = {
    "cat": ["a", "b", "b", "c"],
    "v": [1.0, 2.0, 3.0, 4.0],
    "g": ["left", "left", "right", "right"],
}


@pytest.mark.parametrize("factory", [sp.barplot, sp.boxplot], ids=["barplot", "boxplot"])
def test_a_categorical_axis_shares_the_union_of_its_categories(factory: object) -> None:
    """Panel 'left' has categories a, b and panel 'right' has b, c. Sharing means both show
    a, b, c -- a union, not a min/max -- so the same tick means the same thing in both."""
    panels = _panels(sp.facet(factory, CATEGORIES, col="g", x="cat", y="v").to_string())  # type: ignore[arg-type]
    labels = [[tick for tick in _ticks(panel) if tick in "abc"] for panel in panels]

    assert labels[0] == labels[1] == ["a", "b", "c"]


def test_a_category_with_no_rows_keeps_its_band_but_draws_no_mark() -> None:
    """The band has to exist or the shared axis would not line up; the mark must not, or the
    chart would invent a value the caller never gave.

    Both halves, and the first is the one that needs sharing: ``bars == [2, 2]`` alone is
    true without sharing too, since each panel simply draws its own two categories. What
    only sharing produces is **three ticks against two bars**."""
    panels = _panels(sp.facet(sp.barplot, CATEGORIES, col="g", x="cat", y="v").to_string())

    for panel in panels:
        ticks = [tick for tick in _ticks(panel) if tick in {"a", "b", "c"}]
        bars = re.findall(r'<rect[^>]*class="c?\d*-?series-\d+"', panel)
        assert len(ticks) == 3, "the empty category lost its band"
        assert len(bars) == 2, "a bar was drawn for a category with no rows"


def test_panels_assign_hue_colours_independently() -> None:
    """The limit this file used to hide behind a per-category invariant, now stated outright.

    ``boxplot`` minted a palette class per category, and a panel skipping an empty category
    would shift every later colour -- so a shared ``categories=`` list was what kept two panels
    agreeing. Categories no longer take colour, and it is worth being exact about what that
    did and did not move: **nothing replaced the sharing.** ``hue_values`` comes from each
    panel's own rows, and ``facet`` shares ``xlim``/``ylim``/``bins``/``categories`` but not
    hue values, so a group absent from one panel takes a different palette slot in the other.

    ``layout/facet.py`` records this as an open limit. Nothing executed it. The first version
    of this test claimed the opposite -- "the same hue is the same colour in both panels" --
    and passed, because its fixture named the hues ``L`` and ``R``: sorted, the shared one came
    first in both panels and landed on slot 1 either way. Renaming them ``Z`` and ``A`` leaves
    every assertion in that version identical and the property violated.
    """
    sparse = {
        "cat": ["a", "a", "b", "b"] * 2,
        "v": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
        "g": ["left"] * 4 + ["right"] * 4,
        # "Z" is in both panels; "A" only in the right one, and sorts before it.
        "h": ["Z", "Z", "Z", "Z", "Z", "Z", "A", "A"],
    }
    svg = sp.facet(sp.boxplot, sparse, col="g", x="cat", y="v", hue="h").to_string()
    colour_of_class = dict(re.findall(r"\.(c\d+-series-\d+) \{ stroke: (#[0-9A-Fa-f]{6})", svg))
    # Read through the *legend*, so the assertion is about which hue got which colour rather
    # than about which class did. Asserting ``c1-series-2 == "#56B4E9"`` says nothing: the
    # classes take the palette in order whatever the hues are, so reversing the hue order
    # leaves every such assertion true and the property under test reversed. That is the flaw
    # this test was rewritten to remove, and the first rewrite still had it.
    panels = [
        {
            label: colour_of_class[class_name]
            for class_name, label in re.findall(
                r'class="(c\d+-series-\d+)"[^>]*/>\s*<text[^>]*class="c\d+-legend-text">([^<]*)<', panel
            )
        }
        for panel in _panels(svg)
    ]

    assert panels[0] == {"Z": "#E69F00"}, "the left panel holds only Z, which takes the first slot"
    assert panels[1] == {"A": "#E69F00", "Z": "#56B4E9"}, "the right panel sorts A first, pushing Z to the second"
    assert panels[0]["Z"] != panels[1]["Z"], "so Z is two different colours — the known limit"


def test_a_category_takes_no_colour_of_its_own_in_any_panel() -> None:
    """The rule the change above installed, checked where a panel-shaped bug would show.

    Every panel draws its categories in one colour, so no panel's palette can depend on which
    categories it happens to hold -- which is what the per-category version had to work to
    guarantee, and now gets by construction.
    """
    panels = _panels(sp.facet(sp.boxplot, CATEGORIES, col="g", x="cat", y="v").to_string())
    classes = [sorted(set(re.findall(r"series-(\d+)", panel))) for panel in panels]

    assert classes[0] == classes[1] == ["1"]


# ---------------------------------------------------------------------------
# charts whose domains cannot be predicted, and charts that have none
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("factory", [sp.histplot, sp.kdeplot, sp.ecdfplot], ids=["histplot", "kdeplot", "ecdfplot"])
def test_a_derived_y_domain_is_shared_too(factory: object) -> None:
    """These are why sharing renders twice. A bin count, a density and a proportion are
    none of them columns in the input, so no caller could have computed the union up
    front -- the panels have to be drawn once to find out what they used."""
    data = {"v": [1.0, 1.1, 1.2, 1.3, 50.0, 90.0, 91.0, 92.0], "g": ["a"] * 4 + ["b"] * 4}
    panels = _panels(sp.facet(factory, data, col="g", x="v").to_string())  # type: ignore[arg-type]

    assert _ticks(panels[0])
    assert _ticks(panels[0]) == _ticks(panels[1])


@pytest.mark.parametrize(
    ("factory", "kwargs"),
    [
        pytest.param(sp.pieplot, {"values": "v", "labels": "cat"}, id="pieplot"),
        pytest.param(sp.treemap, {"values": "v", "labels": "cat"}, id="treemap"),
        pytest.param(sp.gaugeplot, {"value": "v", "labels": "cat"}, id="gaugeplot"),
        pytest.param(sp.sparkline, {"y": "v"}, id="sparkline"),
    ],
)
def test_a_chart_with_no_cartesian_axes_facets_unchanged(factory: object, kwargs: dict[str, str]) -> None:
    """Sharing must be a no-op for them rather than an error: they record no domains, so
    there is nothing to union and the second render is skipped."""
    shared = sp.facet(factory, CATEGORIES, col="g", **kwargs).to_string()  # type: ignore[arg-type]
    unshared = sp.facet(factory, CATEGORIES, col="g", sharex=False, sharey=False, **kwargs).to_string()  # type: ignore[arg-type]

    assert shared == unshared


def test_a_grid_facet_shares_across_both_dimensions() -> None:
    """``col=`` and ``row=`` together take a different code path from either alone."""
    data = {
        "x": [1, 2, 3, 4],
        "y": [1.0, 2.0, 300.0, 400.0],
        "c": ["p", "p", "q", "q"],
        "r": ["s", "t", "s", "t"],
    }
    panels = _panels(sp.facet(sp.lineplot, data, col="c", row="r", x="x", y="y").to_string())

    assert all(_ticks(panel) for panel in panels)
    assert len({tuple(_ticks(panel)) for panel in panels}) == 1


def test_a_single_panel_is_not_rendered_twice() -> None:
    """With one panel the union is that panel's own domain, so the second pass would
    reproduce the first exactly. Skipping it is what keeps the common case free."""
    one_group = {"x": [1, 2], "y": [1.0, 2.0], "g": ["only", "only"]}
    calls: list[dict[str, object]] = []

    def counting_lineplot(data: object, **kwargs: object) -> object:
        calls.append(kwargs)
        return sp.lineplot(data, **kwargs)  # type: ignore[arg-type]

    sp.facet(counting_lineplot, one_group, col="g", x="x", y="y")

    assert len(calls) == 1
    assert "ylim" not in calls[0]


def test_sharing_settles_the_horizontal_axis_before_the_vertical_one() -> None:
    """Pins both the cost and the order.

    Three passes, not two, and the order is the point: a binned chart's y domain is a
    *consequence* of its x division, so fixing both at once takes the height from a division
    that the same call is about to change underneath it. Measured, that drew a bar 57.8px
    above the plot area. The middle pass carries ``xlim`` and no ``ylim``."""
    calls: list[dict[str, object]] = []

    def counting_lineplot(data: object, **kwargs: object) -> object:
        calls.append(kwargs)
        return sp.lineplot(data, **kwargs)  # type: ignore[arg-type]

    sp.facet(counting_lineplot, SPLIT, col="g", x="x", y="y")

    assert len(calls) == 6, "two panels, three passes"
    assert all("xlim" not in call and "ylim" not in call for call in calls[:2]), "the first pass measures"
    assert all("xlim" in call and "ylim" not in call for call in calls[2:4]), "the second settles x"
    assert all("xlim" in call and "ylim" in call for call in calls[4:]), "the third settles y"


@pytest.mark.parametrize("factory", [sp.barplot, sp.boxplot, sp.violinplot], ids=["barplot", "boxplot", "violinplot"])
def test_a_categorical_chart_shares_its_value_axis_too(factory: object) -> None:
    """The category list is only half of what these charts draw. Every test above reads the
    category ticks, so a chart that shared them and kept its own value scale passed -- which
    is the original defect wearing a different hat."""
    data = {
        "cat": ["a", "a", "a", "b", "b", "b"] * 2,
        "v": [1.0, 2.0, 3.0, 2.0, 3.0, 4.0, 300.0, 305.0, 310.0, 320.0, 325.0, 330.0],
        "g": ["L"] * 6 + ["R"] * 6,
    }
    panels = _panels(sp.facet(factory, data, col="g", x="cat", y="v").to_string())  # type: ignore[arg-type]
    values = [_axis_numbers(panel)[1] for panel in panels]

    assert values[0], "no value-axis ticks found"
    assert values[0] == values[1]
    # The left panel's own data tops out at 4; a shared axis has to reach the right panel's.
    assert max(values[0]) >= 300.0


@pytest.mark.parametrize("factory", [sp.boxplot, sp.violinplot], ids=["boxplot", "violinplot"])
def test_every_panel_colours_its_categories_the_same_way(factory: object) -> None:
    """``violinplot`` was left out of the original version of this check, so the issue's
    "bar/box/violin" criterion was two thirds met. It needs at least two values per category
    to estimate a density, which is why this fixture is richer than ``CATEGORIES``.

    One class per panel now, not three: a category no longer takes a palette slot, so the
    thing this used to guard -- a skipped category shifting every later colour -- cannot
    arise. What is left worth pinning is that both panels agree, which they do trivially and
    would stop doing if one of the two charts drifted back.
    """
    data = {
        "cat": ["a", "a", "b", "b", "b", "b", "c", "c"],
        "v": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
        "g": ["L", "L", "L", "L", "R", "R", "R", "R"],
    }
    panels = _panels(sp.facet(factory, data, col="g", x="cat", y="v").to_string())  # type: ignore[arg-type]
    classes = [sorted(set(re.findall(r"series-(\d+)", panel))) for panel in panels]

    assert classes[0] == classes[1] == ["1"]


@pytest.mark.parametrize("orient", ["v", "h"])
def test_the_share_flags_name_the_axis_on_screen_not_the_data_role(orient: str) -> None:
    """``sharex`` lines up the horizontal axis whichever data happens to run along it.

    ``barplot(orient="h")`` puts its values on x and its categories up the left edge. Filing
    the categories under ``sharex`` regardless meant ``sharex=True`` lined up the *vertical*
    axis on a horizontal chart -- the opposite of what the flag's name says. Both
    orientations are checked because that is the invariant: the answer must not depend on
    which data role landed where."""
    data = {"cat": ["a", "b", "b", "c"], "v": [1.0, 2.0, 300.0, 400.0], "g": ["L", "L", "R", "R"]}
    panels = _panels(sp.facet(sp.barplot, data, col="g", x="cat", y="v", orient=orient, sharex=True, sharey=False).to_string())

    left = [_axis_labels(panel)[0] for panel in panels]
    bottom = [_axis_labels(panel)[1] for panel in panels]
    assert bottom[0] == bottom[1], "sharex did not line up the horizontal axis"
    assert left[0] != left[1], "sharey=False should have left the vertical axis alone"


def test_an_all_constant_axis_still_renders() -> None:
    """The union of panels that all show one value is a zero-width span. ``apply_limit``
    rightly refuses that from a *caller* -- it maps every value to one pixel -- but a chart
    given no override handles its own constant data fine, so forwarding the degenerate union
    turned a chart that rendered into a ValueError."""
    constant = {"x": [1, 2, 3, 4], "y": [5.0] * 4, "g": ["a", "a", "b", "b"]}

    assert sp.facet(sp.lineplot, constant, col="g", x="x", y="y").to_string().count("<svg") == 3


def test_an_explicit_limit_wins_over_the_computed_union() -> None:
    """Passing ``ylim=`` through ``facet`` used to be ``TypeError: lineplot() got an
    unexpected keyword argument 'ylim'`` -- the parameter this feature added could not be
    used with the feature."""
    svg = sp.facet(sp.lineplot, SPLIT, col="g", x="x", y="y", ylim=(0.0, 500.0)).to_string()
    panels = _panels(svg)

    assert max(_axis_numbers(panels[0])[1]) == 500.0
    assert _ticks(panels[0]) == _ticks(panels[1])


def test_panels_that_already_agree_are_not_rendered_twice() -> None:
    """The docstring claims the second pass runs only when it would change something."""
    same = {"x": [1, 2, 1, 2], "y": [1.0, 2.0, 1.0, 2.0], "g": ["a", "a", "b", "b"]}
    calls: list[dict[str, object]] = []

    def counting(data: object, **kwargs: object) -> object:
        calls.append(kwargs)
        return sp.lineplot(data, **kwargs)  # type: ignore[arg-type]

    sp.facet(counting, same, col="g", x="x", y="y")

    assert len(calls) == 2, "identical panels do not need a second pass"


def test_histogram_panels_share_their_bin_boundaries_not_just_their_axis() -> None:
    """A shared axis with unshared bins is the original defect in disguise: the bars come
    out different widths and a count of 3 covers a different amount of data in each panel,
    while the aligned axis says they are comparable. Measured 5.77px against 3.85px."""
    data = {"v": [1.0, 2.0, 3.0, 4.0, 90.0, 90.5, 91.0, 92.0], "g": ["a"] * 4 + ["b"] * 4}
    panels = _panels(sp.facet(sp.histplot, data, col="g", x="v", bins=4).to_string())
    widths = [
        {width for _, width in re.findall(r'<rect x="([\d.]+)"[^>]*width="([\d.]+)"[^>]*class="c\d+-series', panel)}
        for panel in panels
    ]

    # Equal widths alone prove nothing: with *neither* axis nor bins shared, each panel
    # spans its own narrow range over the full plot area and the widths coincide anyway.
    # The defect only exists when the axis is shared, so that has to be asserted here too.
    assert _ticks(panels[0]) == _ticks(panels[1]), "the axis was not shared, so this proves nothing"
    assert widths[0] and widths[0] == widths[1]


def test_a_facet_of_compositions_does_not_try_to_share() -> None:
    """``plot_fn`` may return a ``Composition`` -- a nested facet, or ``add_caption`` around
    a chart. Those carry no domains, and asking for the union of an empty list raises."""

    def nested(data: object, **kwargs: object) -> object:
        return sp.facet(sp.lineplot, data, col="g2", **kwargs)  # type: ignore[arg-type]

    data = {"x": [1, 2, 3, 4], "y": [1.0, 2.0, 3.0, 4.0], "g": ["a", "a", "b", "b"], "g2": ["p", "q", "p", "q"]}

    assert sp.facet(nested, data, col="g", x="x", y="y").to_string().count("<svg") > 1


def test_a_facet_whose_panels_mix_chart_kinds_shares_what_it_can() -> None:
    """``plot_fn`` is a caller's callable, so nothing stops it returning a pie for one panel
    and a line for another. Requiring *every* panel to have recorded a domain would skip
    sharing for the ones that did; requiring *any* is the rule that matches "share what can
    be shared"."""
    data = {"x": [1, 2, 3, 4], "y": [1.0, 2.0, 300.0, 400.0], "g": ["a", "a", "b", "b"]}
    calls: list[dict[str, object]] = []

    def mixed(group: object, **kwargs: object) -> object:
        calls.append(kwargs)
        if len(calls) % 2:
            return sp.pieplot(group, values="y")
        return sp.lineplot(group, x="x", y="y")

    sp.facet(mixed, data, col="g")

    assert len(calls) == 6, "a panel that recorded a domain should still get the later passes"


@pytest.mark.parametrize("bins", [None, "auto", "sturges"])
def test_histogram_bins_are_shared_on_the_strategies_not_only_on_a_fixed_count(bins: object) -> None:
    """The default path, which the first fix missed entirely.

    ``bin_range=`` only tells numpy which *range* to cover; ``bins="auto"`` still derives the
    bin **width** from each panel's own values and lays that width across the range, so the
    boundaries still disagree. On this fixture the panels choose widths of 0.650000 and
    0.216667 for the same shared span -- a three-to-one difference in what one bar means,
    under an axis whose ticks matched exactly.

    ``bins=4`` -- the only case the first regression test covered -- can never catch this: a
    fixed count is shared by construction, whatever the range. Every case here goes through
    a strategy instead, including the one where the caller names it themselves.
    """
    values = [float(n % 7) for n in range(300)] + [50.0 + (n % 3) for n in range(300)]
    data = {"v": values, "g": ["a"] * 300 + ["b"] * 300}
    kwargs = {} if bins is None else {"bins": bins}
    panels = _panels(sp.facet(sp.histplot, data, col="g", x="v", **kwargs).to_string())  # type: ignore[arg-type]
    widths = [
        {width for _, width in re.findall(r'<rect x="([\d.]+)"[^>]*width="([\d.]+)"[^>]*class="c\d+-series', panel)}
        for panel in panels
    ]

    assert _ticks(panels[0]) == _ticks(panels[1]), "the axis was not shared, so this proves nothing"
    assert widths[0] and widths[0] == widths[1], f"bin widths still disagree: {widths}"


@pytest.mark.parametrize("count", [3, 6, 20])
def test_an_explicit_bin_count_is_the_number_of_bins_the_panels_get(count: int) -> None:
    """The count the caller wrote, not one re-derived from it.

    The union carries a bin *width*, and turning that back into a count across the whole
    shared span made ``bins=6`` mean 156 and ``bins=3`` mean 78 -- both a surprise and a
    change from what the same call drew before panels shared anything. An integer needs no
    help: once ``xlim`` is shared, every panel divides the same range into the same number,
    so the edges line up on their own.

    Counting bars would not show this, because most of these bins are empty. The edges are
    what the caller asked about, so the edges are what is checked."""
    values = [float(n % 7) for n in range(300)] + [50.0 + (n % 3) for n in range(300)]
    data = {"v": values, "g": ["a"] * 300 + ["b"] * 300}
    panels = _panels(sp.facet(sp.histplot, data, col="g", x="v", bins=count).to_string())
    plot_width = 700.0
    widths = {width for panel in panels for width in re.findall(r'<rect[^>]*width="([\d.]+)"[^>]*class="c\d+-series', panel)}

    assert _ticks(panels[0]) == _ticks(panels[1])
    assert len(widths) == 1, f"panels drew bars of different widths: {widths}"
    # One bin's width in pixels is the plot area divided by the number of bins across it.
    assert float(next(iter(widths))) == pytest.approx(plot_width / count, rel=0.02)


def test_a_shared_span_far_wider_than_a_panels_own_does_not_overflow() -> None:
    """``round`` before ``min`` meant the cap could not do its job: a panel whose own span is
    a e-308 fraction of the shared one produces a ratio past the integer range, and rounding
    it first raises ``OverflowError: cannot convert float infinity to integer`` on input that
    rendered before sharing existed."""
    data = {"v": [0.0, 5e-324, 1e-323, 0.0, 1.0], "g": ["a"] * 3 + ["b"] * 2}
    panels = _panels(sp.facet(sp.histplot, data, col="g", x="v").to_string())

    assert len(panels) == 2
    assert all(re.search(r'class="c\d+-series', panel) for panel in panels), "a panel drew no bars"


def test_a_degenerate_x_union_is_left_for_each_panel_to_handle() -> None:
    """Every panel showing one constant unions to a zero-width span, which ``apply_limit``
    rightly refuses from a caller -- so forwarding it turns a facet that rendered into a
    ``ValueError: axis limits must be increasing``. The y-side guard was covered and the
    x-side was not."""
    data = {"x": [5.0] * 4, "y": [1.0, 2.0, 3.0, 4.0], "g": ["a", "a", "b", "b"]}

    assert sp.facet(sp.lineplot, data, col="g", x="x", y="y").to_string().count("<svg") > 1


def test_the_shared_division_is_the_finest_a_panel_chose_and_survives_the_wider_span() -> None:
    """``min`` on widths rather than ``max`` on counts, and the difference is visible.

    Sharing the largest *count* re-spreads it over the union: two panels at 1..3 and
    100..102 each chose the same handful of bins for their own two-unit span, and that many
    bins across 1..102 collapses each panel to a single bar. Both panels agree either way, so the panels-agree
    assertions elsewhere cannot see it -- only counting the bars can.

    No explicit ``bins=`` here on purpose. An integer is the caller's decision and is left
    alone (see ``_may_override``), so it would take this test through a different branch and
    prove nothing about the union."""
    data = {"v": [1.0, 2.0, 3.0, 100.0, 101.0, 102.0], "g": ["a"] * 3 + ["b"] * 3}
    panels = _panels(sp.facet(sp.histplot, data, col="g", x="v").to_string())
    bars = [len(re.findall(r'<rect[^>]*class="c\d+-series', panel)) for panel in panels]
    widths = {width for panel in panels for width in re.findall(r'<rect[^>]*width="([\d.]+)"[^>]*class="c\d+-series', panel)}

    assert _ticks(panels[0]) == _ticks(panels[1]), "the axis was not shared, so this proves nothing"
    assert len(widths) == 1, f"panels drew bars of different widths: {widths}"
    assert bars == [3, 3], f"sharing collapsed the panels to {bars}"


def test_a_strategy_that_chose_more_bins_than_a_caller_may_ask_for_still_renders() -> None:
    """``histogram_bins`` caps an integer ``bins`` at ``MAX_BINS`` because a caller asking
    for a million wants something a chart cannot show. A *strategy* has no such ceiling, so
    a panel is free to choose 15,885 -- and ``main`` renders it.

    Re-deriving that as an integer put it back through the caller's gate: measured, this
    exact input raised ``ValueError: bins must be at most 10000, got 16032``, naming a number
    the caller never wrote, on a facet that rendered on ``main``."""
    spike = [n / 500.0 for n in range(500)] + [2000.0]
    data = {"v": spike + [n / 500.0 for n in range(500)], "g": ["a"] * 501 + ["b"] * 500}

    assert sp.histplot({"v": spike}, x="v", bins="fd").domains.x_step is not None
    panels = _panels(sp.facet(sp.histplot, data, col="g", x="v", bins="fd").to_string())

    assert _ticks(panels[0]) == _ticks(panels[1])
    assert all(re.search(r'class="c\d+-series', panel) for panel in panels), "a panel drew no bars"


def test_both_share_flags_off_skips_the_second_pass_entirely() -> None:
    """The guard is not only an optimisation. ``union`` refuses panels that disagree about
    which axis holds their categories, and with both flags off there is nothing to union --
    so a facet whose ``plot_fn`` varies ``orient`` per panel renders instead of raising."""

    def mixed(data: object, **kwargs: object) -> object:
        rows = data["cat"]  # type: ignore[index]
        return sp.barplot(data, orient="h" if rows[0] == "a" else "v", **kwargs)  # type: ignore[arg-type]

    data = {"cat": ["a", "a", "b", "b"], "v": [1.0, 2.0, 3.0, 4.0], "g": ["L", "L", "R", "R"]}

    assert sp.facet(mixed, data, col="g", x="cat", y="v", sharex=False, sharey=False).to_string().count("<svg") > 1


@pytest.mark.parametrize("name", ["xlim", "ylim"])
def test_passing_an_override_as_none_does_not_switch_sharing_off(name: str) -> None:
    """``ylim=None`` is what a wrapper forwards when it has nothing to say, and every chart
    reads it as "no override". Keying the caller-wins rule off the *name* alone let it turn
    sharing off while ``sharey`` still read ``True`` -- and nothing in the output said so."""
    data = {"x": [1, 2, 3, 4], "y": [1.0, 2.0, 300.0, 400.0], "g": ["a", "a", "b", "b"]}
    shared = _panels(sp.facet(sp.lineplot, data, col="g", x="x", y="y").to_string())
    with_none = _panels(sp.facet(sp.lineplot, data, col="g", x="x", y="y", **{name: None}).to_string())  # type: ignore[arg-type]

    assert _ticks(with_none[0]) == _ticks(with_none[1])
    assert [_ticks(panel) for panel in with_none] == [_ticks(panel) for panel in shared]


def test_a_chart_with_no_categories_does_not_vote_on_which_axis_holds_them() -> None:
    """``categories_axis`` defaults to ``"x"``, and a chart that recorded no categories
    carries that default. Letting it into the vote makes a facet mixing ``barplot(orient="h")``
    with anything cartesian raise "charts disagree", which is a claim about data neither
    chart holds."""
    horizontal = Domains(x=(0.0, 1.0), categories=("a",), categories_axis="y")
    plain = Domains(y=(0.0, 1.0))

    assert union([horizontal, plain]).categories_axis == "y"
    assert union([plain, horizontal]).categories_axis == "y"


def test_charts_that_disagree_about_the_category_axis_say_so() -> None:
    """Without the check, ``axes.pop()`` picks one at random from a set -- so the same input
    lines the categories up along x on one run and y on the next."""
    with pytest.raises(ValueError, match="disagree"):
        union([Domains(categories=("a",), categories_axis="x"), Domains(categories=("b",), categories_axis="y")])


@pytest.mark.parametrize("plot_fn", [sp.boxplot, sp.violinplot])
def test_a_distribution_chart_files_its_categories_under_sharex(plot_fn: object) -> None:
    """``boxplot``/``violinplot`` pass ``Domains(y=..., categories=...)`` and lean on the
    ``"x"`` default for the axis. Nothing checked that, so flipping the default would have
    quietly filed their categories under ``sharey`` -- where ``sharex=False`` stops lining up
    the axis the categories are actually drawn on."""
    data = {
        "cat": ["a", "a", "b", "b", "c", "c", "c", "d", "d"],
        "v": [1.0, 2.0, 3.0, 5.0, 4.0, 6.0, 9.0, 7.0, 8.0],
        "g": ["L"] * 4 + ["R"] * 5,
    }
    kept = _panels(sp.facet(plot_fn, data, col="g", x="cat", y="v", sharex=True, sharey=False).to_string())  # type: ignore[arg-type]
    dropped = _panels(sp.facet(plot_fn, data, col="g", x="cat", y="v", sharex=False, sharey=True).to_string())  # type: ignore[arg-type]

    assert _axis_labels(kept[0])[1] == _axis_labels(kept[1])[1], "sharex should line up the categories"
    assert _axis_labels(dropped[0])[1] != _axis_labels(dropped[1])[1], "sharex=False should have left them alone"


@pytest.mark.parametrize("plot_fn", [sp.barplot, sp.boxplot, sp.violinplot], ids=["barplot", "boxplot", "violinplot"])
@pytest.mark.parametrize(
    ("bad", "message"),
    [((), "at least one"), ("ab", "single string"), ((1, 2), "sequence of names"), (5, "sequence of names")],
    ids=["empty", "string", "numbers", "scalar"],
)
def test_every_chart_taking_categories_validates_it(plot_fn: object, bad: object, message: str) -> None:
    """The validator had tests and the wiring had none, so replacing
    ``require_categories(categories)`` with ``list(categories)`` in any of the three charts
    left the whole suite green -- and ``categories="ab"`` went back to silently drawing bars
    for ``a`` and ``b`` that nobody asked for.

    Testing a helper is not testing the code that calls it. This is the same gap that let
    ``histplot(xlim=)``'s validation be deleted unnoticed a round earlier."""
    data = {"cat": ["a", "a", "b", "b", "c", "c"], "v": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]}

    with pytest.raises(ValueError, match=message):
        plot_fn(data, x="cat", y="v", categories=bad)  # type: ignore[operator]


@pytest.mark.parametrize("plot_fn", [sp.barplot, sp.boxplot, sp.violinplot], ids=["barplot", "boxplot", "violinplot"])
def test_categories_naming_one_a_panel_has_no_rows_for_still_draws(plot_fn: object) -> None:
    """The guard on the test above. This is what the parameter exists for -- a facet panel is
    handed every category any panel drew -- so a validator that refused unknown names would
    pass the rejection tests and break the feature."""
    data = {"cat": ["a", "a", "b", "b"], "v": [1.0, 2.0, 3.0, 4.0]}
    svg = plot_fn(data, x="cat", y="v", categories=("a", "b", "z")).to_string()  # type: ignore[operator]

    assert "z" in svg, "the absent category should still take a band on the axis"


def test_the_derived_bin_count_rounds_rather_than_truncates() -> None:
    """``round`` versus ``int`` on the ratio, which differ by one bin whenever the shared span
    is not a whole multiple of the width. Truncating loses the last division, so the panel
    that chose the finest width does not quite get it back -- and no assertion about the
    panels agreeing can see that, because they agree on either number."""
    from svgplot.layout.facet import _bins_covering

    assert _bins_covering((1.0, 102.0), 2.0 / 3) == 152
    assert _bins_covering((0.0, 10.0), 3.0) == 3
    assert _bins_covering((0.0, 1.0), 5e-311) == 10_000, "the cap has to apply before rounding"


def test_a_bar_never_lands_above_the_plot_area_it_was_scaled_into() -> None:
    """The failure the pass order exists to prevent, and one with no symptom in the file.

    The shared ``ylim`` comes from bin counts, and re-dividing the x axis can merge two bins
    the first division kept apart -- these panels peak at 9 and 8, and one bar of the redrawn
    left panel holds 10. Scaled into a ``ylim`` of 9 it starts at y=-27.8, 57.8px above the
    plot area, where the ``viewBox`` clips it: the axis says 9 and the bar means 10.

    Nothing downstream can catch it. A chart handed a ``ylim`` records the ``ylim`` rather
    than what it drew, so unioning the panels again reports no growth."""
    left = [
        0.296,
        0.929,
        0.894,
        0.085,
        0.507,
        0.17,
        0.905,
        0.842,
        0.203,
        0.159,
        0.915,
        0.192,
        0.389,
        0.601,
        0.379,
        0.852,
        0.922,
        0.982,
        0.842,
        0.536,
        0.472,
        0.531,
        0.006,
        0.027,
        0.956,
        0.234,
        0.885,
        0.789,
        0.392,
        0.585,
        0.565,
        0.172,
        0.033,
        0.112,
        0.622,
        0.162,
    ]
    right = [
        58.644,
        42.044,
        1.852,
        8.304,
        38.613,
        2.559,
        4.07,
        2.801,
        51.39,
        45.706,
        11.959,
        57.274,
        32.034,
        39.85,
        52.783,
        45.346,
        42.675,
        23.031,
        14.795,
        12.19,
        2.032,
        56.955,
        54.667,
        45.225,
        5.248,
        45.086,
        37.936,
        28.627,
        7.959,
        47.518,
        38.779,
        17.668,
        20.191,
        15.67,
        21.054,
        55.806,
    ]
    data = {"v": left + right, "g": ["a"] * len(left) + ["b"] * len(right)}
    svg = sp.facet(sp.histplot, data, col="g", x="v").to_string()
    tops = [float(y) for y in re.findall(r'<rect[^>]*y="([\d.-]+)"[^>]*class="c\d+-series', svg)]

    assert tops, "no bars were drawn"
    assert min(tops) >= 30.0, f"a bar starts {30.0 - min(tops):.1f}px above the plot area"


def test_a_panel_function_that_names_no_keywords_is_still_called() -> None:
    """``facet``'s contract is that any function taking its data positionally works. Sharing
    broke that on the *default* path -- both flags default to ``True``, so the second pass
    added ``xlim`` to a hand-written panel function that never named it and raised
    ``TypeError: got an unexpected keyword argument 'xlim'``. Every panel function in this
    file takes ``**kwargs``, so none of them reached it."""

    def plain(group: object) -> object:
        return sp.lineplot(group, x="x", y="y")  # type: ignore[arg-type]

    assert sp.facet(plain, SPLIT, col="g").to_string().count("<svg") > 1


def test_a_division_is_shared_only_when_every_panel_has_one() -> None:
    """``bins`` means nothing to a chart that does not bin. Sharing it from whichever panel
    reported one handed ``lineplot`` the histogram's division, and a caller whose panel
    function forwards its keywords got ``TypeError: unexpected keyword argument 'bins'``."""
    data = {"x": [1, 2, 3, 4], "y": [1.0, 2.0, 300.0, 400.0], "g": ["a", "a", "b", "b"]}

    def mixed(group: object, **kwargs: object) -> object:
        if group["g"][0] == "a":  # type: ignore[index]
            return sp.histplot(group, x="y", **kwargs)  # type: ignore[arg-type]
        return sp.lineplot(group, x="x", y="y", **kwargs)  # type: ignore[arg-type]

    assert sp.facet(mixed, data, col="g").to_string().count("<svg") > 1


def test_a_keyword_bound_to_the_panel_function_counts_as_the_callers_own() -> None:
    """``functools.partial(histplot, bins=4)`` states ``bins`` exactly as firmly as
    ``facet(..., bins=4)``. Reading only the latter let the shared bin *width* be re-derived
    into 182 divisions -- the substitution ``_may_override``'s own docstring calls "both a
    surprise and a regression", reached by writing the same intent a different way."""
    import functools

    data = {"v": [1.0, 2.0, 3.0, 4.0, 90.0, 90.5, 91.0, 92.0], "g": ["a"] * 4 + ["b"] * 4}
    through_partial = sp.facet(functools.partial(sp.histplot, x="v", bins=4), data, col="g").to_string()
    through_facet = sp.facet(sp.histplot, data, col="g", x="v", bins=4).to_string()

    assert _widths(through_partial) == _widths(through_facet)


def test_a_panel_function_with_positional_only_parameters_is_still_called() -> None:
    """Naming a positional-only parameter is ``TypeError: got some positional-only arguments
    passed as keyword``, which is the same failure filtering by signature exists to prevent --
    so the filter has to look at the *kind* and not only at the name."""

    def positional_only(group: object, xlim: object = None, ylim: object = None, /) -> object:
        return sp.lineplot(group, x="x", y="y")  # type: ignore[arg-type]

    assert sp.facet(positional_only, SPLIT, col="g").to_string().count("<svg") > 1


def test_a_panel_function_wrapped_without_functools_wraps_is_still_called() -> None:
    """A decorator that forwards ``*args, **kwargs`` reports a signature of ``**kwargs``, so
    everything is passed through -- and the strict function underneath rejects it. Charts are
    commonly wrapped this way for theming."""

    def adapter(fn: object) -> object:
        def inner(*args: object, **kwargs: object) -> object:
            return fn(*args, **kwargs)  # type: ignore[operator]

        return inner

    @adapter
    def strict(group: object) -> object:
        return sp.lineplot(group, x="x", y="y")  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="unexpected keyword"):
        sp.facet(strict, SPLIT, col="g")
