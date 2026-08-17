"""Palette mini-language parser (``"ch:..."``, ``"light:X"``, ``"dark:X"``, ``"blend:a,b"``).

Ported from seaborn's ``color_palette()`` grammar but reimplemented with an
explicit parser instead of ad-hoc ``split(":")``/``startswith`` checks, for
better error messages (docs/research/12-aesthetics.md §2). Parsing only —
the actual color generation for each spec form is ``sequential.py``'s (this
module dispatches into it); a bare name with no recognized prefix falls back
to :func:`svgplot.palette.qualitative.qualitative`.
"""

from __future__ import annotations

import re

from svgplot.palette._color import HEX_COLOR_RE
from svgplot.palette.qualitative import qualitative
from svgplot.palette.sequential import blend_sequence, cubehelix_sequence, light_dark_sequence

_DEFAULT_SPEC_COLOR_COUNT = 6
"""How many colors a spec produces when the spec itself doesn't name a count
(this mini-language, unlike ``qualitative()``/``sequential()``, takes no ``n``)."""

_MAX_SPEC_LENGTH = 256
"""Sane upper bound on a mini-language spec string — this exists purely to reject
pathological input early (megabyte-scale specs) with a clear message, before any
parsing work happens on it, not because a legitimate spec would ever be this long.
"""

# Value accepts "123", "123.45", and the leading-zero-less shorthand ".45" (the
# research doc's own example is "ch:s=.25,r=-.5") — but not a bare "." or "-".
# The dot lives *inside* the alternation (not as a trailing `\.?` after `\d+`) and
# digits are pinned to ASCII 0-9 (not `\d`, which is Unicode-aware and matches e.g.
# Arabic-Indic/fullwidth digits) — both deliberate: an optional-dot-after-\d+\d*
# shape is ambiguous over how many digits `\d+` vs `\d*` each consume, and a regex
# engine backtracks through every such split on a failed match, which is O(n^2) on
# a long run of digits (a `"ch:s=" + "9"*100_000 + "x"` spec took ~21s to reject
# with the ambiguous form; this form is linear — same input rejects in ~17ms).
_CH_PARAM_RE = re.compile(r"^(?:(?P<key>[a-z]+)=)?(?P<value>-?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))$")
_CH_PARAM_ALIASES = {"s": "start", "start": "start", "r": "rot", "rot": "rot"}
_CH_POSITIONAL_PARAM_ORDER = ("start", "rot")


def parse_palette_spec(spec: str) -> list[str]:
    """Parse a palette mini-language string into a concrete color list.

    Recognized forms: ``"light:#rrggbb"``, ``"dark:#rrggbb"``,
    ``"blend:#rrggbb,#rrggbb"``, ``"ch:start=<float>,rot=<float>"`` (or the
    positional form ``"ch:<float>,<float>"``). Anything without one of those
    prefixes is treated as a named qualitative palette (``qualitative(spec, ...)``).

    Raises:
        ValueError: if ``spec`` isn't a string, is implausibly long, or a
            recognized prefix's argument doesn't match its expected grammar
            (with a message naming the expected form), or (via ``qualitative``)
            if a bare name is blocked.
        KeyError: if a bare name isn't a registered qualitative palette.
    """
    if not isinstance(spec, str):
        raise ValueError(f"palette spec must be a string, got {spec!r}")
    if len(spec) > _MAX_SPEC_LENGTH:
        raise ValueError(f"palette spec is too long ({len(spec)} chars, max {_MAX_SPEC_LENGTH})")
    prefix, separator, rest = spec.partition(":")
    if separator == ":":
        # Only a genuine "prefix:..." form is special — a bare name that happens to
        # equal "light"/"dark"/"blend"/"ch" (all four are also, or could become,
        # registered qualitative palette names) must still reach the bare-name
        # fallback below, since str.partition on a colon-less string returns the
        # whole string as `prefix` with an empty `separator`, which this check
        # distinguishes from an actual "prefix:" split.
        if prefix == "light" or prefix == "dark":
            return _parse_light_dark_spec(spec, prefix, rest)
        if prefix == "blend":
            return _parse_blend_spec(spec, rest)
        if prefix == "ch":
            return _parse_cubehelix_spec(spec, rest)
    return qualitative(spec, _DEFAULT_SPEC_COLOR_COUNT)


def _parse_light_dark_spec(spec: str, prefix: str, rest: str) -> list[str]:
    if not HEX_COLOR_RE.fullmatch(rest):
        raise ValueError(f"invalid {prefix}: spec {spec!r} — expected '{prefix}:#rrggbb'")
    return light_dark_sequence(rest, _DEFAULT_SPEC_COLOR_COUNT, dark=(prefix == "dark"))


def _parse_blend_spec(spec: str, rest: str) -> list[str]:
    parts = rest.split(",")
    if len(parts) != 2 or not all(HEX_COLOR_RE.fullmatch(part) for part in parts):
        raise ValueError(f"invalid blend: spec {spec!r} — expected 'blend:#rrggbb,#rrggbb'")
    return blend_sequence(parts[0], parts[1], _DEFAULT_SPEC_COLOR_COUNT)


def _parse_cubehelix_spec(spec: str, rest: str) -> list[str]:
    if not rest:
        raise ValueError(f"invalid ch: spec {spec!r} — expected e.g. 'ch:s=.25,r=-.5' or 'ch:0.25,-0.5'")
    params: dict[str, float] = {}
    # Names not yet claimed by either form, in the order a positional token should
    # fill them — mirrors Python's own call-argument binding: a keyword token removes
    # its name from here, so a later positional token can't silently collide with it,
    # and re-claiming an already-set name (by either form) is rejected outright rather
    # than overwriting it.
    unclaimed_positional_names = list(_CH_POSITIONAL_PARAM_ORDER)
    for token in rest.split(","):
        token = token.strip()
        match = _CH_PARAM_RE.fullmatch(token)
        if not match:
            raise ValueError(f"invalid ch: parameter {token!r} in {spec!r} — expected 'key=value' or a bare number")
        raw_key = match.group("key")
        if raw_key is None:
            if not unclaimed_positional_names:
                raise ValueError(f"too many positional ch: parameters in {spec!r} (at most 2: start, rot)")
            key = unclaimed_positional_names.pop(0)
        elif raw_key in _CH_PARAM_ALIASES:
            key = _CH_PARAM_ALIASES[raw_key]
            if key in unclaimed_positional_names:
                unclaimed_positional_names.remove(key)
        else:
            raise ValueError(f"unknown ch: parameter {raw_key!r} in {spec!r} — expected 'start'/'s' or 'rot'/'r'")
        if key in params:
            raise ValueError(f"ch: parameter {key!r} given more than once in {spec!r}")
        params[key] = float(match.group("value"))
    return cubehelix_sequence(_DEFAULT_SPEC_COLOR_COUNT, start=params.get("start", 0.5), rot=params.get("rot", -1.5))
