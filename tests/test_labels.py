"""Tests for svgplot.labels.{spec,table}."""

from __future__ import annotations

import datetime

import pytest

from svgplot.labels import LabelSpec, render_table
from svgplot.labels.spec import render_value
from svgplot.labels.table import TABLE_FORMATS

# ---------------------------------------------------------------------------
# LabelSpec.parse — parsing "@field{format}" entries
# ---------------------------------------------------------------------------


def test_parse_extracts_field_and_format_spec() -> None:
    spec = LabelSpec.parse([("날짜", "@date{%Y-%m-%d}"), ("종가", "@close{$0.00}")])
    assert len(spec) == 2
    date_field, close_field = spec
    assert date_field.label == "날짜"
    assert date_field.field == "date"
    assert date_field.format_spec == "%Y-%m-%d"
    assert close_field.field == "close"
    assert close_field.format_spec == "$0.00"


def test_parse_classifies_numeral_datetime_printf_schemes() -> None:
    spec = LabelSpec.parse(
        [
            ("a", "@x{0,0.000}"),
            ("b", "@y{%Y-%m-%d}"),
            ("c", "@z{%.2f}"),
        ]
    )
    numeral, datetime_field, printf_field = spec
    assert numeral.scheme == "numeral"
    assert datetime_field.scheme == "datetime"
    assert printf_field.scheme == "printf"


def test_classify_scheme_mixed_unambiguous_and_ambiguous_directives_is_datetime() -> None:
    """ "%Y%d" mixes an unambiguous strftime-only directive (Y) with an ambiguous one
    (d, which also looks like printf's %d) — the presence of Y should be enough to
    classify the whole spec as datetime.
    """
    (field,) = LabelSpec.parse([("x", "@x{%Y%d}")])
    assert field.scheme == "datetime"


def test_classify_scheme_only_ambiguous_directives_is_printf() -> None:
    """ "%d%x" combines two letters that are BOTH valid strftime directives (day,
    locale-date) AND valid printf conversions (decimal, hex) — with no unambiguous
    strftime directive present, this must fall through to printf, not datetime.
    """
    (field,) = LabelSpec.parse([("x", "@x{%d%x}")])
    assert field.scheme == "printf"


def test_parse_rejects_implausibly_long_format_spec() -> None:
    with pytest.raises(ValueError, match="too long"):
        LabelSpec.parse([("x", "@x{" + "0" * 200 + "}")])


def test_parse_rejects_empty_spec() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        LabelSpec.parse([])


def test_parse_rejects_safe_scheme() -> None:
    with pytest.raises(ValueError, match="safe"):
        LabelSpec.parse([("raw", "@html{safe}")])


@pytest.mark.parametrize(
    "raw",
    [
        "date{%Y-%m-%d}",  # missing "@"
        "@date%Y-%m-%d",  # missing braces
        "@date{}",  # empty format spec
        "@{%Y-%m-%d}",  # empty field name
        "@date{",  # unbalanced
    ],
)
def test_parse_rejects_malformed_entries(raw: str) -> None:
    with pytest.raises(ValueError):
        LabelSpec.parse([("label", raw)])


def test_parse_rejects_non_tuple_entry_types() -> None:
    with pytest.raises(ValueError):
        LabelSpec.parse([(123, "@x{0,0}")])  # type: ignore[list-item]


def test_gadget_like_format_spec_is_rejected_not_evaluated() -> None:
    """A format spec shaped like a str.format() attribute-access gadget must be rejected
    as an invalid numeral spec, never passed to str.format()/%% for evaluation.
    """
    spec = LabelSpec.parse([("x", "@x{{0.__class__}}")])
    (field,) = spec
    assert field.scheme == "numeral"
    with pytest.raises(ValueError, match="numeral"):
        render_value(field, 1)


# ---------------------------------------------------------------------------
# render_value — numeral scheme
# ---------------------------------------------------------------------------


def test_numeral_grouping_and_decimals() -> None:
    (field,) = LabelSpec.parse([("x", "@x{0,0.000}")])
    assert render_value(field, 1234.5678) == "1,234.568"


def test_numeral_currency_prefix() -> None:
    (field,) = LabelSpec.parse([("x", "@x{$0.00}")])
    assert render_value(field, 42) == "$42.00"


def test_numeral_negative_currency_keeps_sign_before_symbol() -> None:
    (field,) = LabelSpec.parse([("x", "@x{$0.00}")])
    assert render_value(field, -5) == "-$5.00"


def test_numeral_si_abbreviation() -> None:
    (field,) = LabelSpec.parse([("x", "@x{0.0a}")])
    assert render_value(field, 1234) == "1.2k"
    assert render_value(field, 3_400_000) == "3.4M"


def test_numeral_si_abbreviation_negative_puts_sign_before_magnitude() -> None:
    (field,) = LabelSpec.parse([("x", "@x{0.0a}")])
    assert render_value(field, -1234) == "-1.2k"


def test_numeral_si_abbreviation_below_threshold_has_no_suffix() -> None:
    (field,) = LabelSpec.parse([("x", "@x{0.0a}")])
    assert render_value(field, 0) == "0.0"
    assert render_value(field, 42) == "42.0"


def test_numeral_rejects_non_finite_value() -> None:
    (field,) = LabelSpec.parse([("x", "@x{0.00}")])
    with pytest.raises(ValueError, match="finite"):
        render_value(field, float("nan"))
    with pytest.raises(ValueError, match="finite"):
        render_value(field, float("inf"))


def test_numeral_rejects_non_numeric_value() -> None:
    (field,) = LabelSpec.parse([("x", "@x{0.00}")])
    with pytest.raises(ValueError, match="real number"):
        render_value(field, "not a number")


def test_numeral_rejects_int_too_large_to_convert_to_float() -> None:
    """An int with no float representation makes math.isfinite/float() raise
    OverflowError, not return False — post-merge security review: this leaked
    as a raw OverflowError instead of the ValueError render_value's docstring
    promises, which could crash an unsuspecting caller on untrusted data.
    """
    (field,) = LabelSpec.parse([("x", "@x{0.00}")])
    with pytest.raises(ValueError, match="finite"):
        render_value(field, 10**400)


# ---------------------------------------------------------------------------
# render_value — datetime scheme
# ---------------------------------------------------------------------------


def test_datetime_strftime() -> None:
    (field,) = LabelSpec.parse([("x", "@x{%Y-%m-%d}")])
    assert render_value(field, datetime.date(2026, 8, 18)) == "2026-08-18"


def test_datetime_accepts_datetime_instance() -> None:
    (field,) = LabelSpec.parse([("x", "@x{%Y-%m-%d %H:%M}")])
    assert render_value(field, datetime.datetime(2026, 8, 18, 9, 30)) == "2026-08-18 09:30"


def test_datetime_rejects_non_date_value() -> None:
    (field,) = LabelSpec.parse([("x", "@x{%Y-%m-%d}")])
    with pytest.raises(ValueError, match="date"):
        render_value(field, "2026-08-18")


# ---------------------------------------------------------------------------
# render_value — printf scheme
# ---------------------------------------------------------------------------


def test_printf_float_precision() -> None:
    (field,) = LabelSpec.parse([("x", "@x{%.2f}")])
    assert render_value(field, 3.14159) == "3.14"


def test_printf_int_and_string_and_hex() -> None:
    (int_field,) = LabelSpec.parse([("x", "@x{%d}")])
    (str_field,) = LabelSpec.parse([("x", "@x{%s}")])
    (hex_field,) = LabelSpec.parse([("x", "@x{%x}")])
    assert render_value(int_field, 42) == "42"
    assert render_value(str_field, "hello") == "hello"
    assert render_value(hex_field, 255) == "ff"


def test_printf_literal_percent() -> None:
    (field,) = LabelSpec.parse([("x", "@x{%d%%}")])
    assert render_value(field, 50) == "50%"


def test_printf_rejects_non_whitelisted_directive() -> None:
    (field,) = LabelSpec.parse([("x", "@x{%(__class__)s}")])
    assert field.scheme == "printf"
    with pytest.raises(ValueError, match="printf"):
        render_value(field, "anything")


def test_printf_rejects_multiple_conversions() -> None:
    (field,) = LabelSpec.parse([("x", "@x{%d%d}")])
    assert field.scheme == "printf"
    with pytest.raises(ValueError, match="exactly one"):
        render_value(field, 1)


def test_printf_rejects_non_finite_numeric_value() -> None:
    (field,) = LabelSpec.parse([("x", "@x{%.2f}")])
    with pytest.raises(ValueError, match="finite"):
        render_value(field, float("inf"))


def test_printf_rejects_oversized_width_precision() -> None:
    """A short-but-huge width/precision digit string (e.g. 8 digits) would otherwise
    pass an uncapped whitelist and let Python's % operator build a 100MB+ string from
    a single value — the digit-count cap must reject it before that ever happens.
    """
    (width_field,) = LabelSpec.parse([("x", "@x{%99999999d}")])
    (precision_field,) = LabelSpec.parse([("x", "@x{%.99999999f}")])
    with pytest.raises(ValueError, match="printf"):
        render_value(width_field, 1)
    with pytest.raises(ValueError, match="printf"):
        render_value(precision_field, 1.0)


def test_render_value_rejects_none_for_every_scheme() -> None:
    numeral, datetime_field, printf_field = LabelSpec.parse([("a", "@a{0.00}"), ("b", "@b{%Y-%m-%d}"), ("c", "@c{%s}")])
    for field in (numeral, datetime_field, printf_field):
        with pytest.raises(ValueError, match="missing"):
            render_value(field, None)


# ---------------------------------------------------------------------------
# render_table
# ---------------------------------------------------------------------------


_SPEC = LabelSpec.parse([("Name", "@name{%s}"), ("Score", "@score{0.0}")])


class _FakeDataFrame:
    """Duck-types the pandas.DataFrame surface (``.columns`` + ``__getitem__``) that
    ``data._columns.extract_columns`` relies on — mirrors ``tests/test_data.py``'s fixture.
    """

    def __init__(self, data: dict[str, list]) -> None:
        self._data = data

    @property
    def columns(self) -> list[str]:
        return list(self._data.keys())

    def __getitem__(self, key: str) -> list:
        return self._data[key]


def test_render_table_from_dataframe_like_object() -> None:
    data = _FakeDataFrame({"name": ["Ann", "Bo"], "score": [91.2, 77.5]})
    result = render_table(data, _SPEC, format="markdown")
    lines = result.splitlines()
    assert lines[2] == "| Ann | 91.2 |"
    assert lines[3] == "| Bo | 77.5 |"


def test_render_table_raises_on_missing_value() -> None:
    """render_table propagates render_value's ValueError for a None cell rather than
    silently rendering "None" or crashing with an unrelated error.
    """
    data = {"name": ["Ann", None], "score": [91.2, 77.5]}
    with pytest.raises(ValueError, match="missing"):
        render_table(data, _SPEC, format="markdown")


def test_render_table_markdown_from_dict_of_columns() -> None:
    data = {"name": ["Ann", "Bo"], "score": [91.2, 77.5]}
    result = render_table(data, _SPEC, format="markdown")
    lines = result.splitlines()
    assert lines[0] == "| Name | Score |"
    assert lines[1] == "| --- | --- |"
    assert lines[2] == "| Ann | 91.2 |"
    assert lines[3] == "| Bo | 77.5 |"


def test_render_table_html_from_list_of_records() -> None:
    data = [{"name": "Ann", "score": 91.2}, {"name": "Bo", "score": 77.5}]
    result = render_table(data, _SPEC, format="html")
    assert "<table>" in result
    assert "<th>Name</th>" in result
    assert "<td>Ann</td>" in result
    assert "<td>91.2</td>" in result


def test_render_table_rejects_unknown_format() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        render_table({"name": ["Ann"], "score": [1.0]}, _SPEC, format="pdf")


def test_render_table_rejects_missing_field() -> None:
    with pytest.raises(KeyError):
        render_table({"name": ["Ann"]}, _SPEC, format="markdown")


def test_render_table_handles_empty_data() -> None:
    result = render_table({"name": [], "score": []}, _SPEC, format="markdown")
    lines = result.splitlines()
    assert lines[0] == "| Name | Score |"
    assert lines[1] == "| --- | --- |"
    assert len(lines) == 2


def test_render_table_escapes_html_in_markdown_output() -> None:
    spec = LabelSpec.parse([("Name", "@name{%s}")])
    data = {"name": ["<script>alert(1)</script>"]}
    result = render_table(data, spec, format="markdown")
    assert "<script>" not in result
    assert "&lt;script&gt;" in result


def test_render_table_escapes_html_in_html_output() -> None:
    spec = LabelSpec.parse([("Name", "@name{%s}")])
    data = {"name": ["<script>alert(1)</script>"]}
    result = render_table(data, spec, format="html")
    assert "<script>" not in result
    assert "&lt;script&gt;" in result


def test_render_table_escapes_html_in_markdown_label() -> None:
    """The display label is just as much user input as a cell value — a label
    containing HTML metacharacters must come out escaped in the header row too,
    not just data cells (post-merge security review: this was untested).
    """
    spec = LabelSpec.parse([("<script>alert(1)</script>", "@name{%s}")])
    data = {"name": ["ok"]}
    result = render_table(data, spec, format="markdown")
    assert "<script>" not in result
    assert "&lt;script&gt;" in result


def test_render_table_escapes_html_in_html_label() -> None:
    spec = LabelSpec.parse([("<script>alert(1)</script>", "@name{%s}")])
    data = {"name": ["ok"]}
    result = render_table(data, spec, format="html")
    assert "<script>" not in result
    assert "&lt;script&gt;" in result


def test_render_table_escapes_pipe_in_markdown_label() -> None:
    spec = LabelSpec.parse([("a|b", "@name{%s}")])
    data = {"name": ["ok"]}
    result = render_table(data, spec, format="markdown")
    lines = result.splitlines()
    assert lines[0] == "| a\\|b |"


def test_render_table_escapes_pipe_in_markdown_cell() -> None:
    spec = LabelSpec.parse([("Name", "@name{%s}")])
    data = {"name": ["a|b"]}
    result = render_table(data, spec, format="markdown")
    lines = result.splitlines()
    assert lines[2] == "| a\\|b |"


def _gfm_unescape_backslash_and_pipe(text: str) -> str:
    """Reverse GFM's backslash-escaping for "\\" and "|" only, to check a round-trip
    (mirrors what a markdown renderer does: "\\\\" -> one "\\", "\\|" -> one "|").
    """
    placeholder = "\0"
    return text.replace("\\|", placeholder).replace("\\\\", "\\").replace(placeholder, "|")


def test_render_table_escapes_backslash_before_pipe_in_markdown_cell() -> None:
    """A value already containing "\\|" must not let its backslash combine with the
    escaping this function inserts to produce a literal "|" that splits the cell —
    round-2 security review: the naive fix (escape "|" alone) is exploitable this way.
    A correct renderer must round-trip back to the original value.
    """
    spec = LabelSpec.parse([("Name", "@name{%s}")])
    data = {"name": ["a\\|b"]}
    result = render_table(data, spec, format="markdown")
    lines = result.splitlines()
    assert len(lines) == 3  # the embedded "|" didn't split the row into extra cells
    cell = lines[2].removeprefix("| ").removesuffix(" |")
    assert _gfm_unescape_backslash_and_pipe(cell) == "a\\|b"


def test_render_table_collapses_newline_in_markdown_cell() -> None:
    """A raw newline in a cell value would otherwise terminate the GFM table row
    early, desynchronizing every row after it — must not appear literally in output.
    """
    spec = LabelSpec.parse([("Name", "@name{%s}")])
    data = {"name": ["line1\nline2"]}
    result = render_table(data, spec, format="markdown")
    lines = result.splitlines()
    assert len(lines) == 3
    assert "line1" in lines[2] and "line2" in lines[2]


def test_table_formats_constant() -> None:
    assert set(TABLE_FORMATS) == {"markdown", "html"}


# ---------------------------------------------------------------------------
# non-ASCII field names (issue #57)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "field"),
    [
        ("@매출{0,0}", "매출"),
        ("@売上{%d}", "売上"),
        ("@café{%s}", "café"),
        ("@Привет{%s}", "Привет"),
        ("@x{%s}", "x"),
        ("@_x{%s}", "_x"),
        ("@x2{%s}", "x2"),
    ],
)
def test_a_field_name_may_be_any_python_identifier(raw: str, field: str) -> None:
    """The original character class was ``[A-Za-z_][A-Za-z0-9_]*``, which rejected every
    non-ASCII column name — in a Korean-first project, the first thing a user tries."""
    assert LabelSpec.parse([("L", raw)]).fields[0].field == field


@pytest.mark.parametrize(
    "raw",
    [
        "@1field{%s}",
        "@my-field{%s}",
        "@{%s}",
        "@x y{%s}",
        "@매출 합계{%s}",
        "@x.y{%s}",
        "x{%s}",
        "@x{%s",
        "@x%s}",
        "@xyz}",
        "@매출}",
        "@x",
        "",
    ],
)
def test_a_field_name_that_is_not_an_identifier_is_still_rejected(raw: str) -> None:
    """Widening to Unicode must not widen to *anything*: a name with a space or a hyphen
    is not a column reference, and letting it through would defer the failure to a
    confusing lookup error later.

    @xyz} is the case that only the explicit opening-brace check catches: with no
    { at all the name still looks like an identifier, so it would parse with the
    whole string as its own format spec."""
    with pytest.raises(ValueError, match="invalid label spec"):
        LabelSpec.parse([("L", raw)])


@pytest.mark.parametrize("name", ["매출", "売上", "café", "x", "_", "x1", "1x", "my-field", "", "class", "αβγ", "🎉"])
def test_acceptance_agrees_with_str_isidentifier(name: str) -> None:
    """The point of deferring to the interpreter rather than restating XID_Start/
    XID_Continue as a regex: the two answers cannot drift apart as Unicode grows.

    ``class`` is accepted on purpose — it is a keyword in Python source, but a perfectly
    ordinary column name in someone's data."""
    accepted = True
    try:
        LabelSpec.parse([("L", f"@{name}{{%s}}")])
    except ValueError:
        accepted = False

    assert accepted == name.isidentifier()


def test_a_field_name_is_not_unicode_normalised() -> None:
    """The name has to match a column key exactly. NFKC-folding it here would make
    ``@ﬁeld`` silently look up ``field`` — and then fail on data that really does have a
    ``ﬁeld`` column."""
    assert LabelSpec.parse([("L", "@ﬁeld{%s}")]).fields[0].field == "ﬁeld"


def test_braces_inside_the_format_spec_still_belong_to_the_format() -> None:
    """The split is at the first ``{`` and the last ``}``, matching what the greedy regex
    did — a format spec containing braces must not be truncated."""
    assert LabelSpec.parse([("L", "@x{%s}}")]).fields[0].format_spec == "%s}"


def test_a_korean_field_name_renders_through_to_the_table() -> None:
    """End-to-end: parsing was only the first gate, and the value still has to survive
    formatting and escaping."""
    table = render_table({"매출": [1200.0, 3400.0]}, LabelSpec.parse([("매출", "@매출{0,0}")]))

    assert table.splitlines() == ["| 매출 |", "| --- |", "| 1,200 |", "| 3,400 |"]
