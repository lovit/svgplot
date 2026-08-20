"""LabelSpec — field selection + format spec, ported from Bokeh's ``tooltips=[("label", "@field{format}")]``
mini-language (docs-research/17-static-hover-alternative.md). numeral/datetime/printf are the three
format schemes; ``{safe}``-style raw HTML is deliberately not supported.

Security note (PR #23 security review): the "printf" scheme's format string
comes from user input. Do not pass it to ``str.format()``/``%`` directly —
that allows attribute access injection (e.g. ``{0.__class__.__init__.__globals__}``).
Implementers: parse only a whitelisted set of printf-style conversion
specifiers instead of delegating to Python's general string formatting.
"""

from __future__ import annotations

import datetime
import math
import re
from collections.abc import Iterator
from dataclasses import dataclass

FORMAT_SCHEMES = ("plain", "numeral", "datetime", "printf")
"""The four ways a field's value can be turned into label text.

``plain`` is what a bare ``@field`` gets: render the value as it is. It exists because the
other three all require a *number* or a *date*, which left no way to put a text column in a
label at all -- ``@name`` and ``@name{}`` were both refused and ``@name{s}`` was read as a
numeral spec, so the only working spelling was ``@name{%s}`` and nothing pointed at it. Bokeh,
which this mini-language is taken from, renders a bare ``@field`` exactly this way.
"""

# Defense in depth against a pathological format spec (e.g. width/precision digits
# many characters long) — no legitimate spec in this mini-language needs to be long.
_MAX_FORMAT_SPEC_LENGTH = 128

# strftime directive letters this package understands (stdlib's common subset) — used to
# disambiguate a "%"-based format spec as datetime rather than printf.
_STRFTIME_DIRECTIVES = frozenset("aAbBcdfHIjmMpSUwWxXyYzZ%GguV")

# "d"/"s"/"x"/"f"/"%" are valid in BOTH strftime (day/microsecond/locale-date/literal-percent)
# and this module's printf whitelist (decimal/string/hex/float/literal-percent) — a format spec
# built only from these is ambiguous, so it must contain at least one *unambiguous* strftime
# directive (e.g. Y/m/H/M/S) to be classified as datetime; otherwise it falls through to printf.
_STRFTIME_UNAMBIGUOUS = _STRFTIME_DIRECTIVES - frozenset("dsxf%")

_FIELD_PREFIX = "@"
_FIELD_OPEN = "{"
_FIELD_CLOSE = "}"

# numeral scheme (Bokeh/numbro-style subset): optional "$" currency prefix, "0" or "0,0"
# integer part (comma = thousands grouping), optional ".0..0" decimal places, optional
# trailing "a" for SI-suffix abbreviation (k/M/B/T).
_NUMERAL_RE = re.compile(r"^(?P<currency>\$)?(?P<int_part>0(?:,0)?)(?:\.(?P<decimals>0+))?(?P<abbrev>a)?$")

# printf scheme: whitelist a single numeric/string conversion (plus literal "%%"), never
# delegate the raw user-supplied spec to `%`/`.format()` unvalidated — see module docstring.
# Width/precision digit counts are capped at 3 (i.e. up to 999) — uncapped `\d*`/`\d+` would
# let a spec like "%99999999d" pass the whitelist and then have Python's `%` operator build a
# 100MB+ string from a single value, amplified further per table row (round-2 security review).
_PRINTF_DIRECTIVE_RE = re.compile(r"%(?:%|\d{0,3}d|\d{0,3}s|\d{0,3}x|\.\d{1,3}f|\d{0,3}f)")


@dataclass(frozen=True)
class LabelField:
    """One parsed ``(label, "@field{format}")`` entry."""

    label: str
    field: str
    format_spec: str
    scheme: str


def _classify_scheme(format_spec: str) -> str:
    """Classify a "@field{format_spec}"'s inner spec as numeral/datetime/printf.

    Not ``%``-prefixed -> numeral. ``%``-prefixed -> datetime only if it contains
    at least one *unambiguous* strftime directive (e.g. ``Y``/``m``/``H``); ``d``/
    ``s``/``x``/``f``/``%`` are valid in both strftime and this module's printf
    whitelist, so a spec built only from those (e.g. bare ``%d``) is treated as
    printf rather than datetime.
    """
    if len(format_spec) > _MAX_FORMAT_SPEC_LENGTH:
        raise ValueError(f"format spec is too long ({len(format_spec)} chars, max {_MAX_FORMAT_SPEC_LENGTH})")
    if format_spec == "safe":
        raise ValueError("'{safe}' (raw HTML escape bypass) is intentionally not supported")
    if not format_spec:
        raise ValueError("format spec must not be empty")
    if format_spec.startswith("%"):
        directives = set(re.findall(r"%(.)", format_spec))
        if directives <= _STRFTIME_DIRECTIVES and directives & _STRFTIME_UNAMBIGUOUS:
            return "datetime"
        return "printf"
    return "numeral"


def _split_field(raw: str) -> tuple[str, str | None]:
    """Split ``"@field{format}"`` into its two parts.

    The field name is validated with ``str.isidentifier()`` rather than a character-class
    regex. The original ``[A-Za-z_][A-Za-z0-9_]*`` rejected every non-ASCII column name --
    ``@매출{0,0}`` and ``@売上{%d}`` both failed -- even though Python considers those
    perfectly good identifiers. Writing the Unicode rule out as a regex means restating
    XID_Start/XID_Continue by hand and keeping it in step with the Unicode database, so
    the check defers to the interpreter's own answer instead.

    The name is *not* normalised: it has to match a column key in the caller's data
    exactly, and NFKC-folding it here would make ``@ﬁeld`` silently look up ``field``.

    Raises:
        ValueError: if ``raw`` is neither ``@name`` nor ``@name{...}`` with a name that is an
            identifier. The format spec is optional; an *empty* one is not.
    """
    invalid = ValueError(f"invalid label spec {raw!r} — expected '@field_name' or '@field_name{{format}}'")
    if not raw.startswith(_FIELD_PREFIX):
        raise invalid
    open_at = raw.find(_FIELD_OPEN)
    if open_at == -1:
        # No braces at all: render the value as it is. ``None`` rather than ``""`` because the
        # two mean different things and only one of them is allowed -- ``@name{}`` is someone
        # who started writing a format and stopped, which is the safer thing to refuse.
        field = raw[len(_FIELD_PREFIX) :]
        if not field.isidentifier():
            raise invalid
        return field, None
    if not raw.endswith(_FIELD_CLOSE):
        raise invalid
    # The format spec may itself contain braces, so the split is at the *first* opening
    # brace and the *last* closing one -- what the previous greedy regex also did.
    field = raw[len(_FIELD_PREFIX) : open_at]
    if not field.isidentifier():
        raise invalid
    return field, raw[open_at + 1 : -1]


def _parse_field(label: str, raw: str) -> LabelField:
    if not isinstance(label, str) or not isinstance(raw, str):
        raise ValueError(f"expected (str, str) pair, got ({label!r}, {raw!r})")
    field, format_spec = _split_field(raw)
    if format_spec is None:
        return LabelField(label=label, field=field, format_spec="", scheme="plain")
    scheme = _classify_scheme(format_spec)
    return LabelField(label=label, field=field, format_spec=format_spec, scheme=scheme)


class LabelSpec:
    """A field+format specification shared by every static label renderer (table/inline/panel)."""

    def __init__(self, fields: list[tuple[str, str]]) -> None:
        if not isinstance(fields, list) or not fields:
            raise ValueError("fields must be a non-empty list of (label, '@field{format}') tuples")
        self.fields: tuple[LabelField, ...] = tuple(_parse_field(label, raw) for label, raw in fields)

    @classmethod
    def parse(cls, spec: list[tuple[str, str]]) -> LabelSpec:
        """Parse ``[("label", "@field{format}"), ...]`` into a :class:`LabelSpec`.

        Only this list-of-tuples form is supported — issue #11's Acceptance
        Criteria only calls for this shape, so a single-string mini-language
        alternative is intentionally out of scope rather than half-implemented.

        Raises:
            ValueError: if ``spec`` is empty, or any entry doesn't parse cleanly
                (missing ``@``/braces, empty field name, an implausibly long
                format spec, or the intentionally unsupported ``{safe}`` scheme).
        """
        return cls(spec)

    def __len__(self) -> int:
        return len(self.fields)

    def __iter__(self) -> Iterator[LabelField]:
        return iter(self.fields)


def render_value(field: LabelField, value: object) -> str:
    """Format ``value`` per ``field.scheme``/``field.format_spec``.

    Raises:
        ValueError: if ``value`` is ``None`` (this package never silently
            renders a missing value as e.g. the string ``"None"`` — substitute
            or skip missing values upstream before calling this), or if the
            format spec (already validated at parse time to belong to this
            scheme) can't actually format ``value`` — e.g. a numeral/printf-
            numeric spec fed a non-finite or non-numeric value, or a datetime
            spec fed something that isn't a ``date``/``datetime``.
    """
    if value is None:
        raise ValueError(f"cannot render a missing value for field {field.field!r} — substitute or skip it upstream")
    if field.scheme == "plain":
        return _format_plain(value)
    if field.scheme == "numeral":
        return _format_numeral(field.format_spec, value)
    if field.scheme == "datetime":
        return _format_datetime(field.format_spec, value)
    return _format_printf(field.format_spec, value)


def _format_plain(value: object) -> str:
    """A bare ``@field``: the value as it is, with this package's own number spelling.

    ``format_value_label`` rather than ``str`` so a float column reads ``30`` and not ``30.0``
    -- the same rule the axes already apply to the same numbers, so a value does not change
    spelling depending on whether the reader met it on an axis or in a footnote. ``bool`` is
    excluded from that on purpose: ``True`` is not ``1`` to a reader.
    """
    # Imported here, not at module scope: ``charts`` imports ``chart.base``, which imports
    # this package, so a top-level import closes a cycle. Sharing the rule still beats copying
    # its two lines -- a value should not change spelling depending on whether the reader met
    # it on an axis or in a footnote.
    from svgplot.charts._layout import format_value_label

    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int | float) and math.isfinite(value):
        return format_value_label(float(value))
    return str(value)


def _require_finite_number(value: object, *, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{context} requires a real number, got {value!r}")
    try:
        # An int too large to represent as a float (e.g. 10**400) makes
        # math.isfinite/float() itself raise OverflowError rather than
        # returning False — the docstring only promises ValueError, so
        # this must be caught and re-raised as one, not left to leak.
        if not math.isfinite(value):
            raise ValueError(f"{context} requires a finite number, got {value!r}")
        return float(value)
    except OverflowError as e:
        raise ValueError(f"{context} requires a finite number, got {value!r}") from e


def _format_numeral(format_spec: str, value: object) -> str:
    number = _require_finite_number(value, context="numeral format")
    match = _NUMERAL_RE.fullmatch(format_spec)
    if not match:
        raise ValueError(f"unsupported numeral format spec: {format_spec!r}")
    grouping = "," in match.group("int_part")
    decimals = len(match.group("decimals") or "")
    abbreviate = match.group("abbrev") is not None
    currency = match.group("currency") is not None

    sign = "-" if number < 0 else ""
    magnitude = abs(number)
    suffix = ""
    if abbreviate:
        for threshold, label in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "k")):
            if magnitude >= threshold:
                magnitude /= threshold
                suffix = label
                break
    text = f"{magnitude:,.{decimals}f}" if grouping else f"{magnitude:.{decimals}f}"
    return f"{sign}{'$' if currency else ''}{text}{suffix}"


def _format_datetime(format_spec: str, value: object) -> str:
    if not isinstance(value, datetime.date):  # datetime.datetime is a subclass of date
        raise ValueError(f"datetime format requires a datetime.date/datetime.datetime, got {type(value).__name__}")
    try:
        return value.strftime(format_spec)
    except ValueError as error:
        raise ValueError(f"invalid datetime format spec {format_spec!r}: {error}") from error


def _format_printf(format_spec: str, value: object) -> str:
    directives = _PRINTF_DIRECTIVE_RE.findall(format_spec)
    real_directives = [d for d in directives if d != "%%"]
    if len(real_directives) != 1:
        raise ValueError(f"printf format spec must contain exactly one conversion, got {format_spec!r}")
    if "%" in _PRINTF_DIRECTIVE_RE.sub("", format_spec):
        raise ValueError(f"unsupported printf format spec: {format_spec!r}")

    conversion = real_directives[0]
    kind = conversion[-1]
    if kind == "s":
        # "".join(...) forces a genuine plain str even if `value` is a str subclass
        # with a custom __rmod__/__str__ — str(value) alone can preserve the subclass,
        # which would let a hijacked __rmod__ intercept the `%` formatting below.
        payload: object = "".join(str(value))
    elif kind == "f":
        payload = _require_finite_number(value, context="printf numeric format")
    else:
        # %d/%x require an actual int — unlike %f, Python's %-operator doesn't
        # accept a float for these (%x especially: TypeError, not truncation).
        payload = int(_require_finite_number(value, context="printf numeric format"))
    try:
        return format_spec % payload
    except (TypeError, ValueError) as error:
        raise ValueError(f"failed to format value with printf spec {format_spec!r}: {error}") from error
