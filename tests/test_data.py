"""Tests for svgplot.data.{ingest,semantic,metadata}."""

from __future__ import annotations

import math

import pytest

from svgplot.data import LongFormData, attach_metadata, extract_channels, ingest_longform


class _FakeDataFrame:
    """Duck-types the pandas.DataFrame surface ingest.py relies on (``.columns`` +
    ``__getitem__``), so these tests exercise the DataFrame branch without a pandas
    dependency.
    """

    def __init__(self, data: dict[str, list]) -> None:
        self._data = data

    @property
    def columns(self) -> list[str]:
        return list(self._data.keys())

    def __getitem__(self, key: str) -> list:
        return self._data[key]


# ---------------------------------------------------------------------------
# ingest_longform
# ---------------------------------------------------------------------------


def test_ingest_longform_accepts_dict_of_columns() -> None:
    data = ingest_longform({"x": [1, 2, 3], "y": [4, 5, 6]}, x="x", y="y")

    assert isinstance(data, LongFormData)
    assert data.columns == {"x": [1, 2, 3], "y": [4, 5, 6]}
    assert data.x == "x"
    assert data.y == "y"
    assert len(data) == 3


def test_ingest_longform_accepts_list_of_dict_records() -> None:
    records = [{"x": 1, "y": 4}, {"x": 2, "y": 5}, {"x": 3, "y": 6}]

    data = ingest_longform(records, x="x", y="y")

    assert data.columns == {"x": [1, 2, 3], "y": [4, 5, 6]}


def test_ingest_longform_accepts_dataframe_like_input() -> None:
    frame = _FakeDataFrame({"x": [1, 2], "y": [3, 4]})

    data = ingest_longform(frame, x="x", y="y")

    assert data.columns == {"x": [1, 2], "y": [3, 4]}


def test_ingest_longform_y_is_optional() -> None:
    data = ingest_longform({"x": [1, 2, 3]}, x="x")

    assert data.y is None


def test_ingest_longform_raises_for_missing_x_column() -> None:
    with pytest.raises(KeyError, match="x"):
        ingest_longform({"y": [1, 2, 3]}, x="x")


def test_ingest_longform_raises_for_missing_y_column() -> None:
    with pytest.raises(KeyError, match="y"):
        ingest_longform({"x": [1, 2, 3]}, x="x", y="y")


def test_ingest_longform_raises_for_unsupported_type() -> None:
    with pytest.raises(TypeError, match="unsupported data type"):
        ingest_longform(42, x="x")


def test_ingest_longform_raises_for_mismatched_column_lengths() -> None:
    with pytest.raises(ValueError, match="mismatched lengths"):
        ingest_longform({"x": [1, 2, 3], "y": [1, 2]}, x="x", y="y")


def test_ingest_longform_preserves_missing_values_without_dropping_rows() -> None:
    data = ingest_longform({"x": [1, None, 3], "y": [4, 5, math.nan]}, x="x", y="y")

    assert data.columns["x"] == [1, None, 3]
    assert data.columns["y"][2] != data.columns["y"][2]  # NaN preserved, not dropped
    assert len(data) == 3


def test_ingest_longform_raises_for_empty_dict() -> None:
    with pytest.raises(KeyError, match="x"):
        ingest_longform({}, x="x")


def test_ingest_longform_raises_for_empty_list() -> None:
    with pytest.raises(KeyError, match="x"):
        ingest_longform([], x="x")


def test_ingest_longform_x_and_y_may_be_the_same_column() -> None:
    data = ingest_longform({"x": [1, 2, 3]}, x="x", y="x")

    assert data.x == data.y == "x"


def test_ingest_longform_list_of_records_uses_first_records_keys_as_schema() -> None:
    """A key missing from the first record is dropped even if later records have it;
    a key present in the first record but missing later becomes None — documented
    asymmetric behavior of data._columns.extract_columns, not a crash.
    """
    key_added_later = ingest_longform([{"x": 1}, {"x": 2, "y": 5}], x="x")
    assert key_added_later.columns == {"x": [1, 2]}

    key_missing_later = ingest_longform([{"x": 1, "y": 3}, {"x": 2}], x="x", y="y")
    assert key_missing_later.columns == {"x": [1, 2], "y": [3, None]}


# ---------------------------------------------------------------------------
# extract_channels
# ---------------------------------------------------------------------------


def test_extract_channels_splits_hue_into_three_groups() -> None:
    data = {"x": [1, 2, 3, 4, 5, 6], "group": ["a", "a", "b", "b", "c", "c"]}

    groups = extract_channels(data, hue="group")

    assert set(groups.keys()) == {"a", "b", "c"}
    assert groups["a"]["x"] == [1, 2]
    assert groups["b"]["x"] == [3, 4]
    assert groups["c"]["x"] == [5, 6]


def test_extract_channels_col_and_row_combination_uses_tuple_keys() -> None:
    data = {
        "x": [1, 2, 3, 4],
        "col": ["left", "left", "right", "right"],
        "row": ["top", "bottom", "top", "bottom"],
    }

    groups = extract_channels(data, col="col", row="row")

    assert set(groups.keys()) == {("left", "top"), ("left", "bottom"), ("right", "top"), ("right", "bottom")}
    assert groups[("left", "top")]["x"] == [1]
    assert groups[("right", "bottom")]["x"] == [4]


def test_extract_channels_group_contains_all_original_columns() -> None:
    data = {"x": [1, 2], "y": [10, 20], "group": ["a", "b"]}

    groups = extract_channels(data, hue="group")

    assert groups["a"] == {"x": [1], "y": [10], "group": ["a"]}


def test_extract_channels_drops_rows_with_missing_channel_value() -> None:
    data = {"x": [1, 2, 3], "group": ["a", None, math.nan]}

    groups = extract_channels(data, hue="group")

    assert set(groups.keys()) == {"a"}
    assert groups["a"]["x"] == [1]


def test_extract_channels_hue_col_row_combination_uses_three_tuple_keys() -> None:
    data = {
        "x": [1, 2, 3, 4],
        "group": ["a", "a", "b", "b"],
        "col": ["left", "right", "left", "right"],
        "row": ["top", "top", "bottom", "bottom"],
    }

    groups = extract_channels(data, hue="group", col="col", row="row")

    assert set(groups.keys()) == {
        ("a", "left", "top"),
        ("a", "right", "top"),
        ("b", "left", "bottom"),
        ("b", "right", "bottom"),
    }
    assert groups[("a", "left", "top")]["x"] == [1]


def test_extract_channels_requires_at_least_one_channel() -> None:
    with pytest.raises(ValueError, match="at least one"):
        extract_channels({"x": [1, 2]})


def test_extract_channels_raises_for_unknown_channel_column() -> None:
    with pytest.raises(KeyError, match="hue"):
        extract_channels({"x": [1, 2]}, hue="missing")


def test_extract_channels_raises_for_unsupported_data_type() -> None:
    with pytest.raises(TypeError, match="unsupported data type"):
        extract_channels(42, hue="group")


def test_extract_channels_on_empty_data_raises_for_missing_channel_column() -> None:
    with pytest.raises(KeyError, match="hue"):
        extract_channels([], hue="group")


# ---------------------------------------------------------------------------
# attach_metadata
# ---------------------------------------------------------------------------


def test_attach_metadata_pairs_each_value_with_its_metadata() -> None:
    result = attach_metadata([10, 20], [{"label": "Q1"}, {"label": "Q2"}])

    assert result == [
        {"value": 10, "metadata": {"label": "Q1"}},
        {"value": 20, "metadata": {"label": "Q2"}},
    ]


def test_attach_metadata_none_gives_every_point_none_metadata() -> None:
    result = attach_metadata([1, 2, 3], None)

    assert result == [{"value": 1, "metadata": None}, {"value": 2, "metadata": None}, {"value": 3, "metadata": None}]


def test_attach_metadata_allows_individual_none_entries() -> None:
    result = attach_metadata([1, 2], [{"label": "only first"}, None])

    assert result[1] == {"value": 2, "metadata": None}


def test_attach_metadata_raises_for_length_mismatch() -> None:
    with pytest.raises(ValueError, match="length"):
        attach_metadata([1, 2, 3], [{"label": "only one"}])


def test_attach_metadata_empty_values_returns_empty_list() -> None:
    assert attach_metadata([], None) == []
    assert attach_metadata([], []) == []
