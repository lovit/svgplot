from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

import pytest

from svgplot.charts.line import lineplot
from svgplot.scales import TimeScale, make_ticks

SINGLE_SERIES = {"day": [1, 2, 3, 4, 5], "value": [10.0, 15.0, 7.0, 20.0, 12.0]}
HUE_SERIES = {
    "day": [1, 2, 3, 4, 5, 1, 2, 3, 4, 5],
    "value": [10.0, 15.0, 7.0, 20.0, 12.0, 5.0, 8.0, 3.0, 10.0, 6.0],
    "group": ["a", "a", "a", "a", "a", "b", "b", "b", "b", "b"],
}


# ---------------------------------------------------------------------------
# single series
# ---------------------------------------------------------------------------


def test_lineplot_renders_a_single_series_with_default_theme() -> None:
    chart = lineplot(SINGLE_SERIES, x="day", y="value")
    svg = chart.to_string()
    assert "<path" in svg
    assert "series-1" in svg
    assert "series-2" not in svg  # only one series was drawn


def test_lineplot_draws_no_legend_without_hue() -> None:
    chart = lineplot(SINGLE_SERIES, x="day", y="value")
    svg = chart.to_string()
    # theme.css always emits the shared ".legend-text { ... }" CSS rule regardless of
    # whether any legend is drawn -- what must be absent is an actual legend <text> element.
    assert 'class="legend-text"' not in svg


# ---------------------------------------------------------------------------
# hue= multi-series + legend
# ---------------------------------------------------------------------------


def test_lineplot_draws_one_series_per_hue_value() -> None:
    chart = lineplot(HUE_SERIES, x="day", y="value", hue="group")
    svg = chart.to_string()
    assert svg.count("<path") == 2
    assert "series-1" in svg
    assert "series-2" in svg


def test_lineplot_generates_a_legend_entry_per_hue_value() -> None:
    chart = lineplot(HUE_SERIES, x="day", y="value", hue="group")
    svg = chart.to_string()
    assert svg.count('class="legend-text"') == 2
    assert ">a<" in svg
    assert ">b<" in svg


def test_lineplot_colors_each_hue_series_distinctly_via_css() -> None:
    chart = lineplot(HUE_SERIES, x="day", y="value", hue="group")
    svg = chart.to_string()
    style = svg.split("<style>")[1].split("</style>")[0]
    assert ".series-1 { stroke: #E69F00;" in style  # first two colorblind-safe default palette entries
    assert ".series-2 { stroke: #56B4E9;" in style


def test_lineplot_raises_key_error_for_missing_hue_column() -> None:
    with pytest.raises(KeyError):
        lineplot(HUE_SERIES, x="day", y="value", hue="not_a_column")


# ---------------------------------------------------------------------------
# datetime x -> TimeScale
# ---------------------------------------------------------------------------


def test_lineplot_uses_a_time_axis_for_datetime_x_values() -> None:
    data = {"ts": [datetime(2024, 1, 1), datetime(2024, 1, 8), datetime(2024, 1, 15)], "v": [1.0, 5.0, 2.0]}
    chart = lineplot(data, x="ts", y="v")
    svg = chart.to_string()
    assert "2024-01" in svg  # a date-formatted tick label, not a raw numeric one


# ---------------------------------------------------------------------------
# interpolate=
# ---------------------------------------------------------------------------


def test_lineplot_linear_default_connects_raw_points_without_smoothing() -> None:
    chart = lineplot(SINGLE_SERIES, x="day", y="value")
    svg = chart.to_string()
    path_d = svg.split('d="')[1].split('"')[0]
    # "linear" (the default) draws exactly one segment per consecutive pair of raw points:
    # 5 points -> 1 "M" + 4 "L" commands, not a smoothed curve with far more points.
    assert path_d.count("M ") + path_d.count("L ") == 5


def test_lineplot_interpolate_cubic_produces_a_smoothed_curve_with_more_points() -> None:
    chart = lineplot(SINGLE_SERIES, x="day", y="value", interpolate="cubic")
    svg = chart.to_string()
    path_d = svg.split('d="')[1].split('"')[0]
    assert path_d.count("L ") > 4  # smoothing densifies the path well beyond the 5 raw points


def test_lineplot_rejects_unknown_interpolate_method() -> None:
    with pytest.raises(ValueError, match="interpolation method"):
        lineplot(SINGLE_SERIES, x="day", y="value", interpolate="not-a-real-method")


def test_lineplot_propagates_stats_interpolate_error_for_too_few_points() -> None:
    """stats.interpolate.interpolate itself rejects fewer than 2 points for a
    non-linear method — that error must surface cleanly through lineplot, not be
    swallowed or replaced by a different exception.
    """
    with pytest.raises(ValueError):
        lineplot({"day": [1], "value": [10.0]}, x="day", y="value", interpolate="cubic")


# ---------------------------------------------------------------------------
# .save() produces human-readable (pretty-printed, semantically classed) SVG
# ---------------------------------------------------------------------------


def test_lineplot_save_produces_pretty_printed_svg_with_semantic_classes(tmp_path) -> None:
    chart = lineplot(HUE_SERIES, x="day", y="value", hue="group")
    path = tmp_path / "chart.svg"
    chart.save(str(path))
    content = path.read_text()
    assert content.startswith('<?xml version="1.0"')
    assert "\n  " in content  # indented, i.e. genuinely pretty-printed, not one compact line
    assert 'class="series-1' in content
    assert 'class="series-2' in content


# ---------------------------------------------------------------------------
# theme=
# ---------------------------------------------------------------------------


def test_lineplot_accepts_a_built_in_theme_preset_by_name() -> None:
    chart = lineplot(SINGLE_SERIES, x="day", y="value", theme="dark")
    svg = chart.to_string()
    assert "#1e1e1e" in svg  # theme.presets.PRESETS["dark"].background


def test_lineplot_accepts_an_explicit_theme_instance() -> None:
    from svgplot.theme.base import Theme

    chart = lineplot(SINGLE_SERIES, x="day", y="value", theme=Theme(background="#abcdef"))
    svg = chart.to_string()
    assert "#abcdef" in svg


def test_lineplot_rejects_unknown_theme_preset_name() -> None:
    with pytest.raises(KeyError, match="unknown theme preset"):
        lineplot(SINGLE_SERIES, x="day", y="value", theme="not-a-real-preset")


def test_lineplot_rejects_wrong_type_for_theme() -> None:
    with pytest.raises(TypeError):
        lineplot(SINGLE_SERIES, x="day", y="value", theme=123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# edge cases
# ---------------------------------------------------------------------------


def test_lineplot_rejects_empty_data() -> None:
    with pytest.raises(ValueError, match="at least one row"):
        lineplot({"day": [], "value": []}, x="day", y="value")


def test_lineplot_raises_key_error_for_missing_x_or_y_column() -> None:
    with pytest.raises(KeyError):
        lineplot(SINGLE_SERIES, x="not_a_column", y="value")
    with pytest.raises(KeyError):
        lineplot(SINGLE_SERIES, x="day", y="not_a_column")


def test_lineplot_drops_rows_with_missing_x_or_y() -> None:
    data = {"day": [1, 2, None, 4, 5], "value": [10.0, 15.0, 7.0, None, 12.0]}
    chart = lineplot(data, x="day", y="value")
    svg = chart.to_string()
    path_d = svg.split('d="')[1].split('"')[0]
    # only day=1, day=5 survive (day=2's y is fine but day=3's x is missing and day=4's y is
    # missing) -- wait: day=2/value=15 is fully present, so 3 points survive: 1, 2, 5.
    assert path_d.count("L ") == 2


def test_lineplot_handles_a_single_point_series_without_crashing() -> None:
    chart = lineplot({"day": [1], "value": [10.0]}, x="day", y="value")
    svg = chart.to_string()
    assert "<path" in svg


def test_lineplot_rejects_data_where_every_row_is_missing() -> None:
    with pytest.raises(ValueError, match="no rows with both x and y"):
        lineplot({"day": [None, None], "value": [None, None]}, x="day", y="value")


# ---------------------------------------------------------------------------
# time axis: accepted types and tick resolution (issue #113)
# ---------------------------------------------------------------------------


def _x_tick_labels(svg: str) -> list[str]:
    """Bottom-axis labels only. Pooling both axes lets a y-axis label satisfy an assertion
    about x -- which is how an earlier version of a test like this passed while the x axis
    was empty."""
    return re.findall(r'<text x="[\d.]+" y="[\d.]+"[^>]*text-anchor="middle"[^>]*class="tick-label"[^>]*>([^<]+)<', svg)


def _time_chart(start: datetime, step: timedelta, count: int = 4) -> str:
    values = [start + step * index for index in range(count)]
    return lineplot({"t": values, "y": [float(index) for index in range(count)]}, x="t", y="y").to_string()


@pytest.mark.parametrize(
    ("step", "expected"),
    [
        (timedelta(seconds=10), r"^\d{2}:\d{2}:\d{2}$"),
        (timedelta(hours=1), r"^\d{2}:\d{2}$"),
        (timedelta(days=1), r"^\d{4}-\d{2}-\d{2}$"),
        (timedelta(days=30), r"^\d{4}-\d{2}$"),
        (timedelta(days=365 * 4), r"^\d{4}$"),
    ],
    ids=["seconds", "hours", "days", "months", "years"],
)
def test_a_time_axis_labels_at_the_resolution_its_domain_needs(step: timedelta, expected: str) -> None:
    """A fixed ``"%Y-%m-%d"`` is right for a domain of months and wrong on both sides of it.

    Measured before this: a three-hour domain labelled all five ticks ``2024-01-01``, so the
    only thing distinguishing the ticks -- their position -- was contradicted by the only
    thing naming them. A three-year domain spent eleven characters on a day nobody chose."""
    labels = _x_tick_labels(_time_chart(datetime(2024, 1, 1, 1, 0), step))

    assert labels, "the x axis drew no labels"
    assert all(re.match(expected, label) for label in labels), labels


@pytest.mark.parametrize(
    "step",
    [
        timedelta(seconds=1),
        timedelta(seconds=10),
        timedelta(minutes=7),
        timedelta(hours=1),
        timedelta(hours=8),
        timedelta(days=1),
        timedelta(days=3),
        timedelta(days=30),
        timedelta(days=200),
        timedelta(days=365 * 4),
    ],
    ids=["1s", "10s", "7m", "1h", "8h", "1d", "3d", "30d", "200d", "4y"],
)
def test_no_two_time_ticks_carry_the_same_label(step: timedelta) -> None:
    """The property the resolution rule exists for, checked across every span it switches on.

    Two ticks at different positions with the same text is the failure that has no visible
    symptom: the axis looks fine and reads wrong. A start of 01:23:45 rather than midnight is
    deliberate -- ticks aligned to the domain's own start hide exactly this."""
    labels = _x_tick_labels(_time_chart(datetime(2024, 1, 1, 1, 23, 45), step))

    assert labels, "the x axis drew no labels"
    assert len(labels) == len(set(labels)), labels


def test_ticks_that_span_two_dates_keep_the_date_on_the_label() -> None:
    """``12:00, 18:00, 00:00, 06:00`` covers eighteen hours and two dates. Dropping the date
    because the span is under a day leaves a reader to guess which midnight ``00:00`` is --
    and the labels stay distinct either way, so the no-duplicates test cannot catch it."""
    labels = _x_tick_labels(_time_chart(datetime(2024, 1, 1, 7, 23), timedelta(hours=8)))

    assert labels, "the x axis drew no labels"
    assert any(label.startswith("2024-01-02") for label in labels), labels


def test_time_ticks_land_on_boundaries_a_reader_recognises() -> None:
    """Nice numbers are not nice times. Stepping the underlying timestamp by a nice number
    gave 50,000-second steps, landing ticks at 04:13 and 18:06 -- positions no reader asked
    for, and the reason a few-day domain could not use date-only labels at all."""
    labels = _x_tick_labels(_time_chart(datetime(2024, 1, 1, 7, 23), timedelta(hours=1)))

    assert labels, "the x axis drew no labels"
    assert all(label.endswith(":00") for label in labels), labels


def test_monthly_ticks_land_on_the_first_of_the_month_not_every_thirty_days() -> None:
    """A month is 28 to 31 days, so a fixed 30-day step drifts and turns a year of monthly
    ticks into twelve different days of the month. Stepping by the field instead is what
    ``_calendar_ticks`` is for, and the label resolution hides the drift -- ``%Y-%m`` reads
    the same whether the tick is the 1st or the 27th."""
    values = [datetime(2024, 1, 15) + timedelta(days=45 * index) for index in range(6)]
    svg = lineplot({"t": values, "y": [float(index) for index in range(6)]}, x="t", y="y").to_string()
    positions = make_ticks(TimeScale((values[0], values[-1]), (0.0, 700.0)))

    assert _x_tick_labels(svg), "the x axis drew no labels"
    assert all(moment.day == 1 for moment in positions), positions
    assert all(moment.hour == 0 and moment.minute == 0 for moment in positions), positions


def test_a_date_column_plots_exactly_as_a_datetime_column_does() -> None:
    """``datetime`` is a subclass of ``date``, so ``isinstance(value, datetime)`` was False
    for every plain ``date`` -- the commonest thing a CSV or a pandas column holds -- and the
    column fell through to the numeric path and died in ``float()``.

    Comparing the two SVGs rather than checking that ``date`` merely renders is the point:
    promoting to midnight has to be lossless, not approximately right."""
    days = [date(2024, 1, 1), date(2024, 1, 5), date(2024, 1, 9)]
    moments = [datetime(2024, 1, 1), datetime(2024, 1, 5), datetime(2024, 1, 9)]

    assert (
        lineplot({"t": days, "y": [1.0, 2.0, 3.0]}, x="t", y="y").to_string()
        == lineplot({"t": moments, "y": [1.0, 2.0, 3.0]}, x="t", y="y").to_string()
    )


def test_a_column_mixing_dates_and_datetimes_is_promoted_rather_than_refused() -> None:
    """The documented answer to "what if both". Promoting is lossless and a column of dates
    with one timestamp in it is a real shape -- pandas produces it from a CSV where one row
    carried a time."""
    mixed = [date(2024, 1, 1), datetime(2024, 1, 5), date(2024, 1, 9)]
    labels = _x_tick_labels(lineplot({"t": mixed, "y": [1.0, 2.0, 3.0]}, x="t", y="y").to_string())

    assert labels == _x_tick_labels(
        lineplot(
            {"t": [datetime(2024, 1, 1), datetime(2024, 1, 5), datetime(2024, 1, 9)], "y": [1.0, 2.0, 3.0]}, x="t", y="y"
        ).to_string()
    )


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ([time(1), time(2), time(3)], "holds time"),
        (["a", "b", "c"], "holds str"),
        ([date(2024, 1, 1), 5.0, date(2024, 1, 9)], "mixes dates with float"),
    ],
    ids=["time-of-day", "strings", "dates-and-numbers"],
)
def test_a_column_with_no_place_on_an_x_axis_names_the_column(values: list, message: str) -> None:
    """``datetime.time`` is the one worth naming: it is a time of day with no day, so two
    values a week apart are the same point and there is no domain to draw.

    Every message names the column, because the failure it replaces did not -- it came out of
    a ``sorted`` key as ``TypeError: float() argument must be a string or a real number, not
    'datetime.time'``, which tells a caller with twelve columns nothing about which one."""
    with pytest.raises(ValueError, match=message) as raised:
        lineplot({"t": values, "y": [1.0, 2.0, 3.0]}, x="t", y="y")

    assert "'t'" in str(raised.value)
