"""Every ``Theme`` field is documented, and the ones documented as dead really are.

``Theme`` is the widest surface in the package -- ``theme=`` is a parameter of all sixteen
charts -- and until now it was the one public class whose fields were described in ``#``
comments, which no ``help()``, no IDE hover and no doc build ever shows. Promoting them to
attribute docstrings is only half the job: nine of the 26 fields **change no output byte**,
and a docstring that describes what a field would do reads exactly like one describing what it
does.

So the split is measured here rather than asserted in prose. Each field is rendered twice --
once with the default theme, once with that one field changed -- across sixteen charts. A
field whose renders differ is live; one whose renders match is inert. Both halves are pinned,
which is what makes the fact durable in both directions: wiring up ``grid_style`` fails this
file until its docstring stops saying nothing consumes it, and quietly *unwiring* a live field
fails it too.

The alternative -- grepping ``src/`` for the attribute name -- is what the docstrings would
have been checked against if this file did not exist, and it is wrong in a way that matters:
``apply_context`` reads six of the dead fields to scale them, so a grep calls them live while
no pixel moves.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import textwrap

import pytest

import svgplot as sp
from svgplot.theme.base import Theme

_CATEGORICAL = {
    "x": [1.0, 2.0, 3.0, 4.0],
    "y": [1.0, 4.0, 9.0, 16.0],
    "g": ["a", "a", "b", "b"],
    "cat": ["가", "나", "다", "라"],
    "v": [3.0, 1.0, 4.0, 2.0],
}
_GRID = {"r": ["a", "a", "b", "b"], "c": ["x", "y", "x", "y"], "v": [1.0, 2.0, 3.0, 4.0]}

# One value per field, chosen to be visibly unlike the default. A field that reached the
# output only for *some* values would look inert here, so nothing subtle: a different colour,
# several times the size, the other end of an enumeration.
_UNLIKE_THE_DEFAULT: dict[str, object] = {
    "background": "#eeeeee",
    "foreground": "#222222",
    "palette": ("#111111", "#222222", "#333333"),
    "grid_color": "#dddddd",
    "grid_width": 3.0,
    "grid_style": "dashed",
    "spine_color": "#444444",
    "spine_width": 3.0,
    "tick_color": "#555555",
    "tick_size": 9.0,
    "tick_direction": "in",
    "line_width": 7.0,
    "marker_size": 9.0,
    "opacity": 0.5,
    "fill_opacity": 0.5,
    "corner_radius": 4.0,
    "font_family": "serif",
    "title_font_size": 40.0,
    "subtitle_font_size": 40.0,
    "axis_label_font_size": 40.0,
    "tick_label_font_size": 40.0,
    "legend_font_size": 40.0,
    "annotation_font_size": 40.0,
    "tooltip_font_size": 40.0,
    "caption_font_size": 40.0,
    "legend_position": "left",
}

# Documented as changing nothing. Not a list of fields to skip -- a claim, checked below in
# both directions.
_INERT = frozenset(
    {
        "grid_style",
        "tick_direction",
        "legend_position",
        "title_font_size",
        "subtitle_font_size",
        "axis_label_font_size",
        "annotation_font_size",
        "tooltip_font_size",
        "caption_font_size",
    }
)

_FIELDS = [field.name for field in dataclasses.fields(Theme)]

_DENIAL = "Changes no output byte today"
"""The one sentence an inert field's docstring must contain. A single fixed phrase rather than
a list of near-synonyms: the list was three entries long and growing, and each new spelling was
a way for a field to be documented as dead without this file noticing."""


def _render_every_chart(theme: Theme | None) -> list[str]:
    """One SVG per chart type, so a field live in only one of them still counts as live.

    ``set_title`` is on the line chart on purpose: it is the only way a caller asks for a
    title at all, and without it ``title_font_size`` would be called inert for the trivial
    reason that no title was requested.
    """
    return [
        chart.to_string()
        for chart in (
            sp.lineplot(_CATEGORICAL, x="x", y="y", theme=theme).set_title("제목"),
            sp.scatterplot(_CATEGORICAL, x="x", y="y", hue="g", size="v", theme=theme),
            sp.barplot(_CATEGORICAL, x="cat", y="v", theme=theme),
            sp.pieplot(_CATEGORICAL, values="v", labels="cat", theme=theme),
            sp.boxplot(_CATEGORICAL, x="g", y="y", theme=theme),
            sp.heatmap(_GRID, x="c", y="r", values="v", theme=theme),
            sp.treemap(_CATEGORICAL, values="v", labels="cat", theme=theme),
            sp.gaugeplot(_CATEGORICAL, values="v", labels="cat", theme=theme),
            sp.radarplot(_CATEGORICAL, x="cat", y="v", theme=theme),
            sp.sparkline(_CATEGORICAL, y="v", theme=theme),
            sp.areaplot(_CATEGORICAL, x="x", y="y", hue="g", theme=theme),
            sp.histplot(_CATEGORICAL, x="y", theme=theme),
            sp.violinplot(_CATEGORICAL, x="g", y="y", theme=theme),
            sp.ecdfplot(_CATEGORICAL, x="y", theme=theme),
            sp.kdeplot(_CATEGORICAL, x="y", theme=theme),
            sp.regplot(_CATEGORICAL, x="x", y="y", ci=None, theme=theme),
        )
    ]


_DEFAULT_RENDER = _render_every_chart(None)


def test_the_field_list_is_not_empty() -> None:
    """Without this, a change that emptied ``fields(Theme)`` would turn every case below into
    zero cases and leave a file that asserts nothing while passing."""
    assert len(_FIELDS) == 26, _FIELDS
    assert _UNLIKE_THE_DEFAULT.keys() == set(_FIELDS), "a field has no value to change it to"
    # The class docstring counts the fields in prose. A reader trusts that number and nothing
    # else recomputes it, so a field added without touching the sentence would leave the one
    # description of Theme's size wrong.
    assert f"{len(_FIELDS)} fields ordered by concern" in (Theme.__doc__ or "")


@pytest.mark.parametrize("field", _FIELDS)
def test_every_field_says_what_it_is(field: str) -> None:
    """An attribute docstring, not a ``#`` comment. The difference is whether ``help(Theme)``,
    an IDE hover or a doc build can show it -- a comment is discarded by the parser.

    Only presence is checked, not length. A floor on words was tried and removed: it failed
    ``grid_color``, whose "Guide-line colour." is the whole of what there is to say, and the
    only way to pass it would have been to pad. What a docstring *claims* is checked by the
    test below, which is the half a word count cannot reach anyway.
    """
    assert field in getattr(Theme, "__annotations__", {}), f"{field} is not an annotated field"
    assert _ATTRIBUTE_DOCS.get(field), f"{field} has no attribute docstring"


@pytest.mark.parametrize("field", _FIELDS)
def test_a_field_is_live_exactly_when_its_docstring_does_not_deny_it(field: str) -> None:
    """The measurement the module docstring describes, one field at a time."""
    changed = _render_every_chart(dataclasses.replace(Theme(), **{field: _UNLIKE_THE_DEFAULT[field]}))
    reaches_the_output = changed != _DEFAULT_RENDER
    # Both sides must be bools. Comparing a bool with anything else makes ``!=`` true whatever
    # the two say, and an assertion that cannot fail is not one. That is not hypothetical here:
    # it was written against a ``str | None`` first, and hardcoding a live field's colour in
    # ``theme/css.py`` went unnoticed until a mutation asked this test to prove itself.
    denies_it = _denies_being_consumed(_ATTRIBUTE_DOCS.get(field, ""))

    assert reaches_the_output != denies_it, (
        f"{field} changes the output" if reaches_the_output else f"{field} changes no output byte"
    ) + " — its docstring says the opposite"


def test_the_inert_set_is_the_one_the_docstrings_claim() -> None:
    """Stated once as a set, so the count in ``Theme``'s own docstring has something to fail
    against. Nine is a number a reader will trust; nothing else checks it."""
    assert {field for field in _FIELDS if _denies_being_consumed(_ATTRIBUTE_DOCS.get(field, ""))} == _INERT
    assert "Nine of the 26" in (Theme.__doc__ or "")


def test_a_field_that_is_documented_as_dead_is_dead_for_every_chart() -> None:
    """Not "dead on the chart I happened to try". The per-field test already renders all
    sixteen; this says out loud that the set is what makes that true, because an inert field
    that woke up on one chart type is exactly the drift this file exists to catch."""
    for field in sorted(_INERT):
        changed = _render_every_chart(dataclasses.replace(Theme(), **{field: _UNLIKE_THE_DEFAULT[field]}))
        assert changed == _DEFAULT_RENDER, f"{field} reaches the output of some chart"


def _attribute_docs() -> dict[str, str]:
    """``Theme``'s attribute docstrings, read out of its source.

    Read from the source rather than from an attribute, because Python keeps no runtime record
    of an attribute docstring -- it is a bare string expression the compiler evaluates and
    discards. Every tool that displays one (Sphinx, IDEs, ``dataclasses`` doc generators)
    reads the source too, so this is the same thing a reader would see.

    Parsed rather than matched with a regular expression: the fields' docstrings run to several
    paragraphs and quote code, and an expression told about each way one of them can be spelled
    is an expression that will be wrong about the next one.
    """
    body = ast.parse(textwrap.dedent(inspect.getsource(Theme))).body[0]
    assert isinstance(body, ast.ClassDef)
    docs: dict[str, str] = {}
    pending: str | None = None
    for node in body.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            pending = node.target.id
        elif pending is not None and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                docs[pending] = inspect.cleandoc(node.value.value)
            pending = None
        else:
            pending = None
    return docs


_ATTRIBUTE_DOCS = _attribute_docs()


def _denies_being_consumed(doc: str) -> bool:
    """Whether a docstring claims the field reaches no output.

    One fixed sentence, and deliberately the *same proposition this file measures*: rendering
    twice and comparing bytes can only ever confirm or refute "changes no output byte", so a
    docstring that claimed something adjacent -- "nothing draws one" -- would be checked by a
    test that cannot see it. Two of them were wrong that way: captions and grid headings *are*
    drawn, at a hardcoded size, and the measurement had no opinion either way because the
    field is inert regardless.

    Matched on the fixed phrase rather than on keywords like "not" or "yet", so that describing
    what a live field does *not* do -- ``tick_color``'s "the tick label takes foreground, not
    this" -- cannot be read as a denial.
    """
    return _DENIAL in doc
