"""Tests for svgplot.labels.{spec,table}."""

from __future__ import annotations

import datetime
import html
import re

import pytest

from svgplot.labels import LabelSpec, render_table
from svgplot.labels.spec import render_value
from svgplot.labels.table import _MARKDOWN_ESCAPED, TABLE_FORMATS, _collapse_newlines, _escape_markdown_cell

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


@pytest.mark.parametrize("raw", ["line1\nline2", "line1\rline2", "line1\r\nline2"])
def test_render_table_collapses_newline_in_markdown_cell(raw: str) -> None:
    """A raw line ending in a cell value would otherwise terminate the GFM table row early,
    desynchronizing every row after it — must not appear literally in output.

    All three forms, not just ``\\n``: a lone ``\\r`` splits the row in cmark-gfm just as a
    ``\\n`` does, and testing only ``\\n`` left removing its handling undetected."""
    spec = LabelSpec.parse([("Name", "@name{%s}")])
    result = render_table({"name": [raw]}, spec, format="markdown")
    lines = result.splitlines()

    assert len(lines) == 3
    assert lines[2] == "| line1 line2 |"


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
        "",
    ],
)
def test_a_field_name_that_is_not_an_identifier_is_still_rejected(raw: str) -> None:
    """Widening to Unicode must not widen to *anything*: a name with a space or a hyphen
    is not a column reference, and letting it through would defer the failure to a
    confusing lookup error later.

    ``@xyz}`` is the case the brace handling has to get right from the other side now that a
    bare ``@field`` is legal: with no ``{`` the whole tail is the name, and ``xyz}`` is not an
    identifier. ``@x`` was in this list until a bare field became meaningful -- see the test
    below, which pins that it parses rather than leaving its absence here to imply it."""
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


# ---------------------------------------------------------------------------
# markdown inline syntax in a cell (issue #97)
# ---------------------------------------------------------------------------


def _markdown_cell(value: str) -> str:
    spec = LabelSpec.parse([("Name", "@name{%s}")])
    return render_table({"name": [value]}, spec, format="markdown").splitlines()[2]


@pytest.mark.parametrize(
    ("value", "cell"),
    [
        ("[click](https://evil.example/pwn)", r"| \[click\](https://evil.example/pwn) |"),
        ("![px](https://evil.example/p.gif)", r"| !\[px\](https://evil.example/p.gif) |"),
        ("`code`", r"| \`code\` |"),
        ("**bold**", r"| \*\*bold\*\* |"),
        ("_em_", r"| \_em\_ |"),
    ],
)
def test_markdown_inline_syntax_in_a_cell_renders_literally(value: str, cell: str) -> None:
    """A cell holds data, not markup. Unescaped, the first two are the ones that matter:
    a live link is a phishing target and a remote image is an IP beacon for whoever opens
    the document. Neither is XSS -- ``html.escape`` still stops ``<`` -- but both are
    active content injected from caller data, and the representative use of ``info=`` is a
    user-submitted CSV."""
    assert _markdown_cell(value) == cell


@pytest.mark.parametrize("value", ["~~strike~~", "a~b"])
def test_a_tilde_is_left_alone(value: str) -> None:
    """The one character where escaping costs more than it buys. Python-Markdown's escape
    list has no ``~``, so ``\\~`` reaches its readers as a visible backslash in every cell
    containing one -- while the GFM strikethrough that escaping would suppress is already
    inert in that flavour. A styling change in one flavour is a smaller harm than corrupted
    text in another."""
    assert _markdown_cell(value) == f"| {value} |"


def test_the_escapes_round_trip_back_to_the_original_value() -> None:
    """Escaping is only correct if a renderer reading it back produces what the caller
    gave. Asserting the escaped form alone would pass for an escaper that mangled the
    value as long as it did so consistently."""
    value = r"""a|b [x](y) `c` **d** _e_ ~f~ \g\ 100% 5*6 & <tag> "q" 'p'"""
    cell = _markdown_cell(value).removeprefix("| ").removesuffix(" |")

    # Both passes reversed, in the order a renderer applies them: backslash escapes first,
    # then HTML entities. Reversing only the backslashes would pass for a value that
    # happened to contain no entity-escaped character, which is how the earlier version of
    # this test stayed green while checking half the round trip.
    unescaped = html.unescape(re.sub(r"\\(.)", r"\1", cell))
    assert unescaped == value


def test_the_html_escape_and_inline_escape_passes_do_not_interact() -> None:
    """``_escape_markdown_cell`` runs ``html.escape`` before the inline escapes, and that
    order is free rather than load-bearing -- but only while the two passes stay disjoint.
    If ``html.escape`` ever emitted one of the escaped characters, or learned to touch a
    backslash, the placement would silently start to matter."""

    def alternate_order(text: str) -> str:
        text = _collapse_newlines(text).replace("\\", "\\\\")
        for character in _MARKDOWN_ESCAPED:
            text = text.replace(character, f"\\{character}")
        return html.escape(text, quote=True)

    values = ["a&b", "<x>", '"q"', "'p'", "a|b [x] `c` *d* _e_", "\\&\\[", "&amp;", "&#124;"]
    assert [_escape_markdown_cell(value) for value in values] == [alternate_order(value) for value in values]
    # ...and the reason it holds: the two passes touch disjoint characters.
    assert not set(html.escape("&<>\"'", quote=True)) & set(_MARKDOWN_ESCAPED)


def test_escaping_does_not_touch_the_html_renderer() -> None:
    """``<td>`` content is not markdown, so a backslash there would be a literal backslash
    shown to the reader -- the escaping has to be specific to the markdown path."""
    spec = LabelSpec.parse([("Name", "@name{%s}")])
    result = render_table({"name": ["[x](y) `c` *d*"]}, spec, format="html")

    assert "<td>[x](y) `c` *d*</td>" in result
    assert "\\" not in result


def test_a_backslash_already_in_the_value_survives_the_new_escapes() -> None:
    """The doubling has to happen before the inline escapes go in, or a user-supplied
    ``\\`` pairs with an inserted one and the character after it comes back live."""
    cell = _markdown_cell(r"\[not a link](x)")

    assert cell == r"| \\\[not a link\](x) |"
    assert re.sub(r"\\(.)", r"\1", cell.removeprefix("| ").removesuffix(" |")) == r"\[not a link](x)"


def test_an_escaped_cell_still_holds_one_column() -> None:
    """The point of all of it: whatever the value contains, the row keeps its shape."""
    spec = LabelSpec.parse([("A", "@a{%s}"), ("B", "@b{%s}")])
    result = render_table({"a": ["x|y [z](w)"], "b": ["ok"]}, spec, format="markdown")
    rows = result.splitlines()

    assert len(rows) == 3
    assert rows[2].count(" | ") == 1  # one separator => two cells


def test_a_label_gets_the_same_treatment_as_a_cell() -> None:
    """A header is caller data too, and an unescaped link there renders just as live."""
    spec = LabelSpec.parse([("[hdr](https://evil.example)", "@name{%s}")])
    result = render_table({"name": ["ok"]}, spec, format="markdown")

    assert result.splitlines()[0] == r"| \[hdr\](https://evil.example) |"


@pytest.mark.parametrize(
    "value",
    ["https://bare.example/beacon", "www.bare.example/beacon", "victim@bare.example"],
)
def test_gfm_autolink_is_documented_as_out_of_reach(value: str) -> None:
    """GFM's autolink extension links text carrying no markup at all, so no backslash escape
    reaches it -- and it is three forms, not one: a bare URL, a ``www.`` prefix, and an email
    address. The email is the one that matters most, since the representative ``info=`` input
    is a user-submitted CSV. Killing them would mean rewriting the value, so this pins the
    limit rather than pretending it away."""
    assert _markdown_cell(value) == f"| {value} |"


# --- a bare @field ---------------------------------------------------------------------


def test_a_bare_field_renders_the_value_as_it_is() -> None:
    """The whole point: the three formatting schemes all demand a number or a date, so before
    this there was no way to put a text column in a label. ``@name`` and ``@name{}`` were both
    refused and ``@name{s}`` was read as a numeral spec — only ``@name{%s}`` worked, and
    nothing in the mini-language pointed at it. Bokeh, where this syntax comes from, renders a
    bare ``@field`` exactly this way."""
    spec = LabelSpec.parse([("city", "@name")])

    (field,) = spec.fields
    assert field.scheme == "plain"
    assert render_value(field, "서울") == "서울"


def test_a_bare_field_spells_numbers_the_way_the_axes_do() -> None:
    """A value should not change spelling depending on whether the reader met it on an axis or
    in a footnote, so this shares ``format_value_label`` rather than falling back to ``str``."""
    (field,) = LabelSpec.parse([("v", "@v")]).fields

    assert render_value(field, 30.0) == "30"
    assert render_value(field, 3.25) == "3.25"
    assert render_value(field, 3000) == "3000"


def test_a_bare_field_leaves_a_bool_alone() -> None:
    """``True`` is not ``1`` to a reader, so the number rule deliberately skips it."""
    (field,) = LabelSpec.parse([("ok", "@ok")]).fields

    assert render_value(field, True) == "True"


def test_an_empty_format_is_still_refused() -> None:
    """Optional and empty are different. ``@name{}`` reads as someone who started writing a
    format and stopped, which is the safer of the two to refuse."""
    with pytest.raises(ValueError, match="format spec must not be empty"):
        LabelSpec.parse([("v", "@v{}")])


def test_a_bare_field_may_be_named_in_any_script() -> None:
    """The identifier rule is unchanged — it just now applies to the whole tail."""
    (field,) = LabelSpec.parse([("매출", "@매출")]).fields

    assert field.field == "매출"
    assert field.scheme == "plain"
