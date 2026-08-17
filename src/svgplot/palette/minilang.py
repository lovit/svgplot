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

# Value accepts "123", "123.45", and the leading-zero-less shorthand ".45" (the
# research doc's own example is "ch:s=.25,r=-.5") — but not a bare "." or "-".
_CH_PARAM_RE = re.compile(r"^(?:(?P<key>[a-z]+)=)?(?P<value>-?(?:\d+\.?\d*|\.\d+))$")
_CH_PARAM_ALIASES = {"s": "start", "start": "start", "r": "rot", "rot": "rot"}
_CH_POSITIONAL_PARAM_ORDER = ("start", "rot")


def parse_palette_spec(spec: str) -> list[str]:
    """Parse a palette mini-language string into a concrete color list.

    Recognized forms: ``"light:#rrggbb"``, ``"dark:#rrggbb"``,
    ``"blend:#rrggbb,#rrggbb"``, ``"ch:start=<float>,rot=<float>"`` (or the
    positional form ``"ch:<float>,<float>"``). Anything without one of those
    prefixes is treated as a named qualitative palette (``qualitative(spec, ...)``).

    Raises:
        ValueError: if a recognized prefix's argument doesn't match its expected
            grammar (with a message naming the expected form), or (via
            ``qualitative``) if a bare name is blocked.
        KeyError: if a bare name isn't a registered qualitative palette.
    """
    prefix, _, rest = spec.partition(":")
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
    positional_index = 0
    for token in rest.split(","):
        token = token.strip()
        match = _CH_PARAM_RE.fullmatch(token)
        if not match:
            raise ValueError(f"invalid ch: parameter {token!r} in {spec!r} — expected 'key=value' or a bare number")
        raw_key = match.group("key")
        if raw_key is None:
            if positional_index >= len(_CH_POSITIONAL_PARAM_ORDER):
                raise ValueError(f"too many positional ch: parameters in {spec!r} (at most 2: start, rot)")
            key = _CH_POSITIONAL_PARAM_ORDER[positional_index]
            positional_index += 1
        elif raw_key in _CH_PARAM_ALIASES:
            key = _CH_PARAM_ALIASES[raw_key]
        else:
            raise ValueError(f"unknown ch: parameter {raw_key!r} in {spec!r} — expected 'start'/'s' or 'rot'/'r'")
        params[key] = float(match.group("value"))
    return cubehelix_sequence(_DEFAULT_SPEC_COLOR_COUNT, start=params.get("start", 0.5), rot=params.get("rot", -1.5))
