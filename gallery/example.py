"""What a gallery example file declares, and how its code is turned into a picture.

The contract is deliberately small: a module in ``examples/`` sets a handful of module-level
names and nothing else. It defines no functions and imports nothing from this package, so a
chart's page is written by someone who only has to know their own chart.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from types import ModuleType

from gallery.interaction import Controls, resolve

REQUIRED = ("TITLE", "SUMMARY", "REQUIRES", "SETUP", "EXAMPLES")


@dataclass(frozen=True)
class Example:
    """One captioned figure on a chart's page: the code, and the SVG that code produced."""

    caption: str
    code: str
    svg: str
    table: str | None
    controls: Controls | None = None


@dataclass(frozen=True)
class Page:
    """Everything one chart's page needs, after its examples have been run."""

    name: str
    title: str
    summary: str
    requires: str
    setup: str
    examples: list[Example]
    notes: list[str]


def _run(code: str, namespace: dict) -> object:
    """Execute ``code`` in ``namespace`` and return the value of its last expression.

    Split rather than a bare ``eval`` so an example may build a value over several lines and
    still end in the call being demonstrated. The last statement must be an expression --
    an example whose final line is an assignment has produced nothing to draw, and saying so
    here is better than writing an empty file and finding out in a browser.
    """
    body = ast.parse(code, mode="exec").body
    if not body or not isinstance(body[-1], ast.Expr):
        raise ValueError("an example's last line must be an expression that evaluates to a chart")
    exec(compile(ast.Module(body=body[:-1], type_ignores=[]), "<example>", "exec"), namespace)
    return eval(compile(ast.Expression(body[-1].value), "<example>", "eval"), namespace)


def load(module: ModuleType, name: str) -> Page:
    """Run every example in ``module`` and collect the page it describes.

    The *same string* is executed and printed, so the code a reader copies is by construction
    the code that made the picture above it. Verifying documentation by re-implementing its
    examples has already hidden two that referenced names the document never defined.

    That guarantee now has three named exceptions, listed rather than glossed. The builder
    calls ``set_title`` (the caption becomes the chart's accessible name), ``set_scope`` (a
    page-unique CSS scope, so two charts inlined together stop repainting each other) and
    ``set_table_id`` where there is an ``info=`` table (so two tables on one page keep their
    own ids). All three are about the *document the picture sits in* rather than the picture,
    all three are things the embedding tutorial tells a reader to do themselves, and none
    moves a pixel: the drawing is what the printed code drew.

    ``SETUP`` runs once and is shown once at the top of the page, which is what makes each
    page self-contained: setup plus any one example is a complete script.

    An optional ``INTERACTIONS`` maps an example's 1-based number to the kind of control that
    figure should carry (``gallery.interaction.KINDS``). It is read with ``getattr`` rather
    than added to ``REQUIRED``, the same way ``NOTES`` is: sixteen pages will end up declaring
    it and several will deliberately not. What each control *is* -- which series exist, what
    they are called, which classes they carry -- is read back out of the rendered SVG rather
    than declared here, so it cannot disagree with the picture.

    Raises:
        ValueError: if a required name is missing, if an example does not end in an
            expression, if an example evaluates to something with no ``to_string``, if
            ``INTERACTIONS`` names an example number that does not exist, or if a named
            figure cannot carry the control it asks for.
    """
    missing = [field for field in REQUIRED if not hasattr(module, field)]
    if missing:
        raise ValueError(f"{name}: example module is missing {', '.join(missing)}")

    import svgplot as sp

    namespace: dict = {"sp": sp}
    exec(compile(module.SETUP, f"<{name} setup>", "exec"), namespace)

    interactions = dict(getattr(module, "INTERACTIONS", {}))
    unknown = sorted(set(interactions) - set(range(1, len(module.EXAMPLES) + 1)))
    if unknown:
        raise ValueError(f"{name}: INTERACTIONS names example(s) {unknown}, but there are {len(module.EXAMPLES)}")

    examples = []
    for index, (caption, code) in enumerate(module.EXAMPLES, start=1):
        chart = _run(code, dict(namespace))
        if not hasattr(chart, "to_string"):
            raise ValueError(f"{name}: example {caption!r} evaluated to {type(chart).__name__}, not a chart")
        figure = f"svgplot-{name}-{index}"
        chart.set_title(caption).set_scope(figure)
        if getattr(chart, "table_id", None) is not None:
            chart.set_table_id(f"{figure}-table")
        svg = chart.to_string(declaration=False)
        examples.append(
            Example(
                caption=caption,
                code=code.strip(),
                svg=svg,
                table=chart.to_html_table() if chart.table_id else None,
                controls=resolve(figure, interactions[index], svg) if index in interactions else None,
            )
        )

    return Page(
        name=name,
        title=module.TITLE,
        summary=module.SUMMARY,
        requires=module.REQUIRES,
        setup=module.SETUP.strip(),
        examples=examples,
        notes=list(getattr(module, "NOTES", [])),
    )
