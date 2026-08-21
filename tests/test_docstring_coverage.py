"""Every public parameter is named where a reader would look for it.

Coverage as a gate rather than a habit. The holes this closes were not exotic: ``info=`` was
undocumented on two of the three charts that take it, ``violinplot`` never mentioned the
``hue=`` a whole CHANGELOG section argues for, and ``row`` documented neither of its two
keyword arguments. Each was invisible because nothing looked.

The check is "the name appears in the docstring", not "there is an ``Args:`` block". This
package explains parameters in running prose -- ``Args:`` appears three times in all of
``src/`` -- and mandating a block would put every parameter in two places, one of which
would go stale. Prose that names the parameter is what a reader can actually find.

The name has to appear as a *word*. A plain substring made short names unfalsifiable --
``x`` was satisfied by "pixels", ``ci`` by "reproducible", ``bins`` by "histogram_bins".
Measured, that change closes nothing today (every parameter that appears, appears whole),
which is the point: it costs nothing and removes a way to pass without meaning to.

**The name has to appear outside ``Raises:``.** A parameter mentioned only there -- "if
``bins`` isn't a recognized spec" -- tells a reader the parameter exists and nothing about what
it does. When that limit was written down it failed 15 functions on 29 parameters; the count
had drifted to 27 by the time it was closed, because other work documented two of them in
passing. Most were ``theme=`` and ``data``, and ``theme=`` now carries one shared paragraph
across the thirteen charts that were missing it -- duplicated in full rather than assembled by
a decorator, matching how ``width``/``height`` are already handled, because a docstring that is
composed at import time is not what a reader sees in the source. :func:`test_the_shared_theme_paragraph_is_one_paragraph`
is what keeps the copies from drifting.

**Classes are in the gate too**, which is what makes this module's title true rather than
nearly true. They were excluded by an ``isinstance(obj, type)`` filter, and behind it sat
``Theme``'s 26 constructor parameters, ``Chart``'s four, and nineteen public methods and
properties. Three
allowances make the check fit what a class actually is, each narrow enough to name:

* a dataclass field may be documented by its **attribute docstring** rather than in the class
  docstring. Requiring the latter would mean writing ``Theme``'s 26 fields out twice, and the
  second copy is the one that goes stale. ``tests/test_theme_fields.py`` checks those.
* a constructor parameter may be documented in ``__init__``'s own docstring, which is where
  ``Composition`` already puts it and where ``help()`` shows it.
* ``Raises:`` is required of a method only when it can actually refuse something -- a
  ``raise`` in its own body, or in a function of this package that it calls. The rule for
  functions is unconditional because every public function here validates its arguments;
  ``Chart.set_title`` does not, and demanding a ``Raises:`` block from it would be asking for
  an invented one. One call level is the right depth, and both neighbouring depths were tried:
  zero skipped ``set_scope``, which raises through ``validate_scope`` and said nothing about
  it, and following the whole graph reaches something that raises from every serializer, which
  would make the rule "every method, always" by another name.

There is deliberately no allowlist. ``tests/test_gallery.py`` already recorded why: an empty
escape hatch is one somebody widens later without anyone deciding to.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
import re
import textwrap

import pytest

import svgplot as sp

_PUBLIC = sorted(
    name
    for name in sp.__all__
    if callable(getattr(sp, name)) and not isinstance(getattr(sp, name), type) and not name.startswith("_")
)

_CLASSES = sorted(
    name
    for name in sp.__all__
    if isinstance(getattr(sp, name), type) and not issubclass(getattr(sp, name), Warning) and not name.startswith("_")
)


def _public_callables(cls: type) -> list[str]:
    """Every public method a caller can reach, however it is declared.

    ``inspect.isfunction`` alone finds plain methods and misses the rest: a ``classmethod``
    is a bound method, a ``property`` is a descriptor, and both are things a caller calls.
    ``LabelSpec.parse`` and ``Chart.domains`` are exactly those two cases, and a gate that
    quietly skipped them would be smaller than it reads.
    """
    names = []
    for name, member in vars(cls).items():
        if name.startswith("_"):
            continue
        if isinstance(member, property | classmethod | staticmethod) or inspect.isfunction(member):
            names.append(name)
    return names


def _resolve(class_name: str, method_name: str) -> object:
    """The underlying function, unwrapped from whatever descriptor declares it."""
    member = vars(getattr(sp, class_name))[method_name]
    if isinstance(member, property):
        return member.fget
    if isinstance(member, classmethod | staticmethod):
        return member.__func__
    return member


_METHODS = sorted(
    (class_name, method_name) for class_name in _CLASSES for method_name in _public_callables(getattr(sp, class_name))
)

_THEME_PARAGRAPH = """``theme=`` takes a :class:`~svgplot.theme.base.Theme`, the name of a preset
    (``"light"``, ``"dark"``, ``"minimal"``, ``"high_contrast"``, ``"print"``), or ``None``
    for the default theme. Fonts, line widths, opacities and the grid/spine/tick colours come
    from it, along with every colour this chart's own arguments do not set. No render reads or
    writes global style state, so two charts given the same ``Theme`` are styled alike no
    matter what was drawn in between."""
"""The paragraph in full, not its opening. The first version stopped after the preset names,
which left the two sentences carrying the substantive claims outside the guard -- one copy
could be rewritten to say the opposite and nothing failed."""


def _names(prose: str, parameter: str) -> bool:
    """Whether ``prose`` names ``parameter`` as a word rather than inside a longer one."""
    return re.search(rf"(?<![\w-]){re.escape(parameter)}(?![\w-])", prose) is not None


def _prose(doc: str | None) -> str:
    """The part of a docstring a reader learns from: everything before ``Raises:``.

    Splitting rather than stripping the block: what follows ``Raises:`` in this package is
    always the last section, so everything before it is the explanation.
    """
    return (doc or "").split("Raises:")[0]


def _signature(name: str) -> inspect.Signature | None:
    try:
        return inspect.signature(getattr(sp, name))
    except (TypeError, ValueError):  # pragma: no cover - no builtin is exported today
        return None


def _attribute_docs(cls: type) -> set[str]:
    """Which of ``cls``'s annotated fields carry an attribute docstring.

    Python discards those at compile time, so this reads the source -- the same place Sphinx
    and an IDE read them from, and the same place a person reads them from.
    """
    try:
        source = textwrap.dedent(inspect.getsource(cls))
    except (OSError, TypeError):  # pragma: no cover - every exported class is importable
        return set()
    body = ast.parse(source).body[0]
    if not isinstance(body, ast.ClassDef):  # pragma: no cover
        return set()
    documented: set[str] = set()
    pending: str | None = None
    for node in body.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            pending = node.target.id
        elif pending is not None and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                documented.add(pending)
            pending = None
        else:
            pending = None
    return documented


def _can_refuse(function: object) -> bool:
    """Whether calling this can raise -- its own ``raise``, or one in something it calls.

    One level, not none and not the whole graph. None was tried and is too weak: ``set_scope``
    contains no ``raise`` of its own and refuses a malformed class name through
    ``validate_scope``, so a caller meets a ``ValueError`` the docstring never mentioned.
    The whole graph is too strong -- every serializer eventually reaches something that can
    raise, and the rule would collapse into "every method needs a Raises: block".

    One level is where a validator sits in this package: a public method that refuses
    something does it by calling a named validator on the first lines of its body.
    """
    try:
        source = textwrap.dedent(inspect.getsource(function))  # type: ignore[arg-type]
    except (OSError, TypeError):  # pragma: no cover
        return False
    tree = ast.parse(source)
    if any(isinstance(node, ast.Raise) for node in ast.walk(tree)):
        return True
    module = inspect.getmodule(function)
    owner = _OWNER_OF.get(getattr(function, "__qualname__", ""))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = _callee(node.func, module, owner)
        if callee is None:
            continue
        if _has_raise(callee):
            return True
        # A *private* helper is part of the method, not a separate contract: a caller sent to
        # read ``_accessible_document``'s docstring has been sent to the wrong place, so its
        # refusals are the method's refusals. Public callees stop here -- they document
        # themselves, and following them reaches something that raises from everywhere.
        if callee.__name__.startswith("_") and _can_refuse(callee):
            return True
    return False


def _callee(func: ast.expr, module: object, owner: type | None) -> object:
    """Resolve a call target to a function of this package, or ``None``.

    Three shapes, because a method refuses through all three. A bare name is a module-level
    helper (``validate_scope``). ``self.something()`` and ``cls(...)`` are the two the first
    version missed, and missing them was not academic: ``LabelSpec.parse`` refuses through
    ``cls(spec)`` and the three serializers refuse through ``self._accessible_document()``,
    so four methods that raise for a caller were exempted from having to say so.
    """
    if isinstance(func, ast.Name):
        if func.id == "cls" and owner is not None:
            return owner.__init__
        return _owned(getattr(module, func.id, None))
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        if func.value.id in ("self", "cls") and owner is not None:
            return _owned(getattr(owner, func.attr, None))
        return _owned(getattr(getattr(module, func.value.id, None), func.attr, None))
    return None


def _owned(callee: object) -> object:
    """``callee`` if it is a function this package defines, else ``None``."""
    if isinstance(callee, property):
        callee = callee.fget
    if not inspect.isfunction(callee) or not (callee.__module__ or "").startswith("svgplot"):
        return None
    return callee


def _has_raise(callee: object) -> bool:
    try:
        source = textwrap.dedent(inspect.getsource(callee))  # type: ignore[arg-type]
    except (OSError, TypeError):  # pragma: no cover
        return False
    return any(isinstance(node, ast.Raise) for node in ast.walk(ast.parse(source)))


_OWNER_OF = {f"{class_name}.{method_name}": getattr(sp, class_name) for class_name, method_name in _METHODS} | {
    f"{class_name}.__init__": getattr(sp, class_name) for class_name in _CLASSES
}


def test_the_registry_is_not_empty() -> None:
    """Without this, a change that emptied ``__all__`` or broke the filter would turn every
    parametrized case below into zero cases and the file into a green no-op."""
    assert len(_PUBLIC) >= 20, _PUBLIC
    assert len(_CLASSES) >= 4, _CLASSES
    assert len(_METHODS) == 19, _METHODS


@pytest.mark.parametrize("name", _PUBLIC)
def test_every_public_parameter_is_named_in_its_docstring(name: str) -> None:
    signature = _signature(name)
    if signature is None:
        pytest.skip(f"{name} has no introspectable signature")
    prose = _prose(getattr(sp, name).__doc__)

    missing = [parameter for parameter in signature.parameters if not _names(prose, parameter)]

    assert prose.strip(), f"{name} has no docstring outside its Raises: block"
    assert not missing, f"{name} never explains {missing} outside its Raises: block"


@pytest.mark.parametrize("name", _PUBLIC)
def test_every_public_function_documents_what_it_refuses(name: str) -> None:
    """This package refuses a lot on purpose -- 290 raise sites, and the refusals are the
    part a caller meets first. A function that raises without saying so sends them to the
    traceback to find out what the contract was."""
    assert "Raises:" in (getattr(sp, name).__doc__ or ""), f"{name} has no Raises: block"


@pytest.mark.parametrize("name", _CLASSES)
def test_every_public_class_explains_what_it_is_built_from(name: str) -> None:
    """Constructor parameters, by whichever of the three routes a reader would find them."""
    cls = getattr(sp, name)
    signature = _signature(name)
    if signature is None:  # pragma: no cover - every exported class is constructible
        pytest.skip(f"{name} has no introspectable signature")
    documented = _prose(cls.__doc__) + _prose(cls.__init__.__doc__)
    fields = _attribute_docs(cls)

    missing = [
        parameter for parameter in signature.parameters if parameter not in fields and not _names(documented, parameter)
    ]

    assert (cls.__doc__ or "").strip(), f"{name} has no docstring"
    assert not missing, f"{name} never explains {missing}"


@pytest.mark.parametrize(("class_name", "method_name"), _METHODS, ids=lambda item: str(item))
def test_every_public_method_explains_its_parameters(class_name: str, method_name: str) -> None:
    method = _resolve(class_name, method_name)
    try:
        signature = inspect.signature(method)  # type: ignore[arg-type]
    except (TypeError, ValueError):  # pragma: no cover
        pytest.skip(f"{class_name}.{method_name} has no introspectable signature")
    prose = _prose(method.__doc__)

    missing = [
        parameter for parameter in signature.parameters if parameter not in ("self", "cls") and not _names(prose, parameter)
    ]

    assert prose.strip(), f"{class_name}.{method_name} has no docstring outside its Raises: block"
    assert not missing, f"{class_name}.{method_name} never explains {missing} outside its Raises: block"


@pytest.mark.parametrize(("class_name", "method_name"), _METHODS, ids=lambda item: str(item))
def test_a_method_that_refuses_says_so(class_name: str, method_name: str) -> None:
    """Only where the method itself raises -- see this module's docstring for why the rule is
    conditional here and unconditional for functions."""
    method = _resolve(class_name, method_name)
    if not _can_refuse(method):
        pytest.skip(f"{class_name}.{method_name} refuses nothing")

    assert "Raises:" in (method.__doc__ or ""), f"{class_name}.{method_name} raises without saying so"


def test_the_shared_theme_paragraph_is_one_paragraph() -> None:
    """``theme=`` is explained by a copy in each chart module, so the copies have to agree.

    Duplication was the deliberate choice -- it is how ``width``/``height`` are already handled,
    and a docstring assembled by a decorator is not the text in the file. The cost of that
    choice is drift, and this is what pays it.

    All sixteen, not the thirteen that were missing it. The other three named ``theme`` only in
    an aside about hue colouring -- "colors cycling through the theme's palette" -- which
    satisfies the coverage gate by the letter while telling a reader nothing about the
    parameter, the exact failure this file's ``Raises:`` rule was narrowed to stop.
    """
    charts = pathlib.Path(sp.__file__).parent / "charts"
    carrying = [path.stem for path in sorted(charts.glob("*.py")) if _THEME_PARAGRAPH in path.read_text()]
    take_theme = [name for name in _PUBLIC if "theme" in ((_signature(name) or {}) and _signature(name).parameters)]

    assert len(carrying) == 16, carrying
    assert len(take_theme) == 17, take_theme  # the sixteen charts, plus apply_context
