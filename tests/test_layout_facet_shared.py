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

# Two groups whose y ranges do not overlap at all, so an unshared axis is unmistakable.
SPLIT = {
    "x": [1, 2, 3, 4, 5, 6],
    "y": [1.0, 2.0, 3.0, 100.0, 200.0, 300.0],
    "g": ["a", "a", "a", "b", "b", "b"],
}


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


def test_a_shared_category_keeps_one_colour_across_panels() -> None:
    """``boxplot`` mints a palette class per category. Skipping the categories a panel has
    no data for would shift every later one, and 'b' would be a different colour on each
    side -- the exact confusion sharing the axis was meant to remove."""
    panels = _panels(sp.facet(sp.boxplot, CATEGORIES, col="g", x="cat", y="v").to_string())
    classes = [sorted(set(re.findall(r"series-(\d+)", panel))) for panel in panels]
    assert classes[0], "no series classes found — the pattern is not matching"

    assert classes[0] == classes[1] == ["1", "2", "3"]


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


def test_sharing_renders_each_panel_exactly_twice() -> None:
    """Pins the cost so a future change cannot quietly make it three passes."""
    calls: list[dict[str, object]] = []

    def counting_lineplot(data: object, **kwargs: object) -> object:
        calls.append(kwargs)
        return sp.lineplot(data, **kwargs)  # type: ignore[arg-type]

    sp.facet(counting_lineplot, SPLIT, col="g", x="x", y="y")

    assert len(calls) == 4, "two panels, two passes"
    assert all("ylim" not in call for call in calls[:2])
    assert all("ylim" in call and "xlim" in call for call in calls[2:])


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
def test_a_shared_category_keeps_one_colour_across_panels_everywhere(factory: object) -> None:
    """``violinplot`` was left out of the original version of this check, so the issue's
    "bar/box/violin" criterion was two thirds met. It needs at least two values per category
    to estimate a density, which is why this fixture is richer than ``CATEGORIES``."""
    data = {
        "cat": ["a", "a", "b", "b", "b", "b", "c", "c"],
        "v": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
        "g": ["L", "L", "L", "L", "R", "R", "R", "R"],
    }
    panels = _panels(sp.facet(factory, data, col="g", x="cat", y="v").to_string())  # type: ignore[arg-type]
    classes = [sorted(set(re.findall(r"series-(\d+)", panel))) for panel in panels]

    assert classes[0] == classes[1] == ["1", "2", "3"]


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
    """Passing ``ylim=`` through ``facet`` used to be a ``TypeError`` for a duplicate
    keyword -- the parameter this feature added could not be used with the feature."""
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

    assert len(calls) == 4, "a panel that recorded a domain should still get a second pass"
