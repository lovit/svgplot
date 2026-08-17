"""LabelSpec — field selection + format spec, ported from Bokeh's ``tooltips=[("label", "@field{format}")]``
mini-language (docs/research/17-static-hover-alternative.md). numeral/datetime/printf are the three
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
from dataclasses import dataclass

FORMAT_SCHEMES = ("numeral", "datetime", "printf")

# strftime directive letters this package understands (stdlib's common subset) — used to
# disambiguate a "%"-based format spec as datetime rather than printf.
_STRFTIME_DIRECTIVES = frozenset("aAbBcdfHIjmMpSUwWxXyYzZ%GguV")

# "d"/"s"/"x"/"f"/"%" are valid in BOTH strftime (day/microsecond/locale-date/literal-percent)
# and this module's printf whitelist (decimal/string/hex/float/literal-percent) — a format spec
# built only from these is ambiguous, so it must contain at least one *unambiguous* strftime
# directive (e.g. Y/m/H/M/S) to be classified as datetime; otherwise it falls through to printf.
_STRFTIME_UNAMBIGUOUS = _STRFTIME_DIRECTIVES - frozenset("dsxf%")

_FIELD_RE = re.compile(r"^@(?P<field>[A-Za-z_][A-Za-z0-9_]*)\{(?P<format_spec>.*)\}$")

# numeral scheme (Bokeh/numbro-style subset): optional "$" currency prefix, "0" or "0,0"
# integer part (comma = thousands grouping), optional ".0..0" decimal places, optional
# trailing "a" for SI-suffix abbreviation (k/M/B/T).
_NUMERAL_RE = re.compile(r"^(?P<currency>\$)?(?P<int_part>0(?:,0)?)(?:\.(?P<decimals>0+))?(?P<abbrev>a)?$")

# printf scheme: whitelist a single numeric/string conversion (plus literal "%%"), never
# delegate the raw user-supplied spec to `%`/`.format()` unvalidated — see module docstring.
_PRINTF_DIRECTIVE_RE = re.compile(r"%(?:%|\d*d|\d*s|\d*x|\.\d+f|\d*f)")


@dataclass(frozen=True)
class LabelField:
    """One parsed ``(label, "@field{format}")`` entry."""

    label: str
    field: str
    format_spec: str
    scheme: str


def _classify_scheme(format_spec: str) -> str:
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


def _parse_field(label: str, raw: str) -> LabelField:
    if not isinstance(label, str) or not isinstance(raw, str):
        raise ValueError(f"expected (str, str) pair, got ({label!r}, {raw!r})")
    match = _FIELD_RE.fullmatch(raw)
    if not match:
        raise ValueError(f"invalid label spec {raw!r} — expected '@field_name{{format}}'")
    field = match.group("field")
    format_spec = match.group("format_spec")
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

        Raises:
            ValueError: if ``spec`` is empty, or any entry doesn't parse cleanly
                (missing ``@``/braces, empty field name, or the intentionally
                unsupported ``{safe}`` scheme).
        """
        return cls(spec)

    def __len__(self) -> int:
        return len(self.fields)

    def __iter__(self):
        return iter(self.fields)


def render_value(field: LabelField, value: object) -> str:
    """Format ``value`` per ``field.scheme``/``field.format_spec``.

    Raises:
        ValueError: if the format spec (already validated at parse time to
            belong to this scheme) can't actually format ``value`` — e.g. a
            numeral/printf-numeric spec fed a non-finite or non-numeric value,
            or a datetime spec fed something that isn't a ``date``/``datetime``.
    """
    if field.scheme == "numeral":
        return _format_numeral(field.format_spec, value)
    if field.scheme == "datetime":
        return _format_datetime(field.format_spec, value)
    return _format_printf(field.format_spec, value)


def _require_finite_number(value: object, *, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{context} requires a real number, got {value!r}")
    if not math.isfinite(value):
        raise ValueError(f"{context} requires a finite number, got {value!r}")
    return float(value)


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
        payload: object = str(value)
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
