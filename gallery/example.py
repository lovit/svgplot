"""What a gallery example file declares, and how its code is turned into a picture.

The contract is deliberately small: a module in ``examples/`` sets a handful of module-level
names and nothing else. It defines no functions and imports nothing from this package, so a
chart's page is written by someone who only has to know their own chart.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from types import ModuleType

REQUIRED = ("TITLE", "SUMMARY", "REQUIRES", "SETUP", "EXAMPLES")


@dataclass(frozen=True)
class Example:
    """One captioned figure on a chart's page: the code, and the SVG that code produced."""

    caption: str
    code: str
    svg: str


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

    ``SETUP`` runs once and is shown once at the top of the page, which is what makes each
    page self-contained: setup plus any one example is a complete script.

    Raises:
        ValueError: if a required name is missing, if an example does not end in an
            expression, or if an example evaluates to something with no ``to_string``.
    """
    missing = [field for field in REQUIRED if not hasattr(module, field)]
    if missing:
        raise ValueError(f"{name}: example module is missing {', '.join(missing)}")

    import svgplot as sp

    namespace: dict = {"sp": sp}
    exec(compile(module.SETUP, f"<{name} setup>", "exec"), namespace)

    examples = []
    for caption, code in module.EXAMPLES:
        chart = _run(code, dict(namespace))
        if not hasattr(chart, "to_string"):
            raise ValueError(f"{name}: example {caption!r} evaluated to {type(chart).__name__}, not a chart")
        examples.append(Example(caption=caption, code=code.strip(), svg=chart.to_string()))

    return Page(
        name=name,
        title=module.TITLE,
        summary=module.SUMMARY,
        requires=module.REQUIRES,
        setup=module.SETUP.strip(),
        examples=examples,
        notes=list(getattr(module, "NOTES", [])),
    )
