"""The library's reference, read off its own declarations: the public Python API of ``cad``, each name with
its kind, its signature and its docstring.

``python -m cad._internal.reference --docs`` prints it as the JSON the documentation site reads; a test holds
the site's copy to it, so the reference cannot drift from the code. What is public is what the package
declares, never a guess:

* the root's ``__all__`` (``__version__``, ``CadDeprecationWarning``) and its document types, one object each
  (``cad.registry.DOCUMENT_TYPES``);
* of each document type, what its registry entry gives it -- its decorator, its reader, its operations and its
  edit -- and whatever else its package's own ``__all__`` names (``cad._internal.document_type``);
* each integration's namespace (``cad.registry.INTEGRATIONS``, in its order) and the names its ``__all__``
  declares, a public submodule's (``cad.build123d.materials``) with its own ``__all__``.

The document types are read at run time: ``import cad`` loads no CAD kernel, and their operations are
objects the registry makes. An integration's names are read from its source with ``ast`` instead, never
imported: each is defined by a module that needs its extra (build123d, trimesh, MuJoCo, Blender, KiCad's
kicode), and the reference must come out the same where none is installed. Only the package itself is
imported, for its ``__all__``, which loads nothing of its tool's.

The output is deterministic: annotations as their source writes them (a value read at run time rendered
without module prefixes, the same on every Python the library supports), defaults as their source or
``repr`` writes them, no addresses or paths, and every docstring once, in ``texts``.
"""

from __future__ import annotations

import ast
import collections.abc
import enum
import importlib
import inspect
import json
import re
import sys
import types
import typing
from pathlib import Path
from typing import Any

__all__ = ["as_docs", "as_docs_json", "main"]

_ROOT = Path(__file__).resolve().parent.parent  # the ``cad`` package


# --- signatures, one shape for both sources ---------------------------------------------------------------

def _render(parameters: list[tuple[str, str, str | None, str | None]], returns: str | None) -> str:
    """``(a, /, b: int = 1, *args, c, **kw) -> R`` from ``(kind, name, annotation, default)`` rows, where
    ``kind`` is ``inspect.Parameter``'s kind name; laid out as ``inspect.Signature`` lays one out."""
    words: list[str] = []
    positional_only = False
    star = False
    for kind, name, annotation, default in parameters:
        if kind != "POSITIONAL_ONLY" and positional_only:
            words.append("/")
            positional_only = False
        if kind == "KEYWORD_ONLY" and not star:
            words.append("*")
            star = True
        if kind == "VAR_POSITIONAL":
            star = True
            name = f"*{name}"
        elif kind == "VAR_KEYWORD":
            name = f"**{name}"
        positional_only = kind == "POSITIONAL_ONLY"
        word = name if annotation is None else f"{name}: {annotation}"
        if default is not None:
            word += f" = {default}" if annotation is not None else f"={default}"
        words.append(word)
    if positional_only:
        words.append("/")
    return f"({', '.join(words)})" + (f" -> {returns}" if returns is not None else "")


_PREFIXES = re.compile(r"\b(?:typing|typing_extensions|collections\.abc|pathlib(?:\._local)?|builtins|"
                       r"types|cad(?:\.\w+)*)\.(?=[A-Za-z_])")


def _annotation(value: Any) -> str | None:
    """An annotation as its source writes it: a string (``from __future__ import annotations``) as it is, its
    quotes taken off; a value made at run time rendered the same on every Python (3.14 says ``X | None`` where
    3.13 said ``Optional[X]``, and ``pathlib._local.Path`` where 3.12 said ``pathlib.Path``)."""
    if value is inspect.Parameter.empty:
        return None
    if isinstance(value, str):
        text = value.strip()
        while len(text) > 1 and text[0] == text[-1] and text[0] in "'\"":
            text = text[1:-1].strip()
        return text
    return _typed(value)


def _typed(value: Any) -> str:
    if value is None or value is type(None):
        return "None"
    if value is Ellipsis:
        return "..."
    if value is typing.Any:
        return "Any"
    if isinstance(value, typing.TypeVar):
        return value.__name__
    if isinstance(value, typing.ForwardRef):
        return value.__forward_arg__
    origin, arguments = typing.get_origin(value), typing.get_args(value)
    if origin is typing.Union or (origin is not None and origin is getattr(types, "UnionType", None)):
        return " | ".join(_typed(argument) for argument in arguments)
    if origin is typing.Literal:
        return f"Literal[{', '.join(repr(argument) for argument in arguments)}]"
    if origin is typing.Annotated:
        return _typed(arguments[0])
    if origin is collections.abc.Callable and arguments:
        given, result = arguments[:-1], arguments[-1]
        inner = "..." if given == (Ellipsis,) else "[" + ", ".join(_typed(argument) for argument in given) + "]"
        return f"Callable[{inner}, {_typed(result)}]"
    if origin is not None:
        name = getattr(origin, "__qualname__", None) or _PREFIXES.sub("", repr(origin))
        return f"{name}[{', '.join(_typed(argument) for argument in arguments)}]" if arguments else name
    if isinstance(value, type):
        return value.__qualname__
    return _PREFIXES.sub("", repr(value))


def _default(value: Any) -> str | None:
    """A default as ``repr`` writes it, or the name of its kind for one whose repr is an address."""
    if value is inspect.Parameter.empty:
        return None
    if isinstance(value, enum.Enum):
        return f"{type(value).__name__}.{value.name}"
    if isinstance(value, Path):
        return f"Path({str(value)!r})"
    text = repr(value)
    return f"<{type(value).__name__}>" if " at 0x" in text or text.startswith("<") else text


def _runtime_signature(function: Any, *, drop_first: bool = False) -> str | None:
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return None
    rows = [(parameter.kind.name, parameter.name, _annotation(parameter.annotation), _default(parameter.default))
            for parameter in signature.parameters.values()]
    return _render(rows[1:] if drop_first else rows, _annotation(signature.return_annotation))


def _ast_signature(node: ast.FunctionDef | ast.AsyncFunctionDef, *, drop_first: bool = False) -> str:
    arguments = node.args
    positional = [*arguments.posonlyargs, *arguments.args]
    defaults: list[ast.expr | None] = [None] * (len(positional) - len(arguments.defaults)) + list(arguments.defaults)

    def text(expression: ast.expr | None) -> str | None:
        return None if expression is None else ast.unparse(expression)

    rows = [("POSITIONAL_ONLY" if index < len(arguments.posonlyargs) else "POSITIONAL_OR_KEYWORD", argument.arg,
             text(argument.annotation), text(default))
            for index, (argument, default) in enumerate(zip(positional, defaults))]
    if arguments.vararg is not None:
        rows.append(("VAR_POSITIONAL", arguments.vararg.arg, text(arguments.vararg.annotation), None))
    rows += [("KEYWORD_ONLY", argument.arg, text(argument.annotation), text(default))
             for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults)]
    if arguments.kwarg is not None:
        rows.append(("VAR_KEYWORD", arguments.kwarg.arg, text(arguments.kwarg.annotation), None))
    return _render(rows[1:] if drop_first else rows, text(node.returns))


def _doc(text: str | None) -> str | None:
    return inspect.cleandoc(text).strip() or None if text else None


# --- an integration's names, read from source ---------------------------------------------------------------

def _source(module: str) -> Path | None:
    """The file of a module of the ``cad`` package, without importing it."""
    parts = module.split(".")
    if parts[0] != "cad":
        return None
    base = _ROOT.joinpath(*parts[1:])
    for candidate in (base / "__init__.py", base.with_suffix(".py")):
        if candidate.is_file():
            return candidate
    return None


def _tree(module: str) -> ast.Module | None:
    path = _source(module)
    return None if path is None else ast.parse(path.read_text(encoding="utf-8"))


def _statements(body: list[ast.stmt]) -> typing.Iterator[ast.stmt]:
    """A module's top-level statements, those under an ``if`` (``TYPE_CHECKING``) or a ``try`` among them."""
    for statement in body:
        yield statement
        if isinstance(statement, ast.If):
            yield from _statements(statement.body)
            yield from _statements(statement.orelse)
        elif isinstance(statement, ast.Try):
            yield from _statements(statement.body)


def _imported(module: str, statement: ast.ImportFrom) -> str:
    if not statement.level:
        return statement.module or ""
    package = module if _source(module) is not None and _source(module).name == "__init__.py" else \
        module.rpartition(".")[0]  # type: ignore[union-attr]
    for _ in range(statement.level - 1):
        package = package.rpartition(".")[0]
    return f"{package}.{statement.module}" if statement.module else package


def _declared(module: str, name: str, depth: int = 0) -> tuple[str, ast.stmt | None]:
    """Where ``module``'s ``name`` is defined: the module and its ``def``, ``class`` or assignment, followed
    through the imports that re-export it; ``(module, None)`` for a submodule or a name not found."""
    tree = _tree(module)
    if tree is None or depth > 8:
        return module, None
    found: ast.stmt | None = None
    for statement in _statements(tree.body):
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and statement.name == name:
            return module, statement
        if isinstance(statement, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name
                                                     for target in statement.targets):
            found = found or statement
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name) \
                and statement.target.id == name:
            found = found or statement
        if isinstance(statement, ast.ImportFrom):
            for alias in statement.names:
                if (alias.asname or alias.name) == name:
                    origin = _imported(module, statement)
                    if _source(f"{origin}.{alias.name}") is not None:  # a submodule
                        return f"{origin}.{alias.name}", None
                    return _declared(origin, alias.name, depth + 1)
    return module, found


def _literal_all(module: str) -> list[str] | None:
    tree = _tree(module)
    for statement in _statements(tree.body if tree is not None else []):
        if isinstance(statement, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "__all__"
                                                     for target in statement.targets):
            try:
                return [str(name) for name in ast.literal_eval(statement.value)]
            except ValueError:
                return None
    return None


def _dataclass(node: ast.ClassDef) -> bool:
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if (isinstance(target, ast.Name) and target.id == "dataclass") or \
                (isinstance(target, ast.Attribute) and target.attr == "dataclass"):
            return True
    return any(isinstance(base, ast.Name) and base.id == "NamedTuple" for base in node.bases)


def _fields(node: ast.ClassDef) -> str:
    """A dataclass's (or a NamedTuple's) constructor, from its annotated fields."""
    rows: list[tuple[str, str, str | None, str | None]] = []
    keyword_only = False
    for statement in node.body:
        if not (isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name)):
            continue
        annotation = ast.unparse(statement.annotation)
        if annotation.startswith(("ClassVar", "typing.ClassVar")):
            continue
        if annotation in ("KW_ONLY", "dataclasses.KW_ONLY"):
            keyword_only = True
            continue
        if statement.target.id.startswith("_") and statement.value is not None:
            continue  # a private field with a default: the class's own state, no argument a caller gives
        default = None if statement.value is None else ast.unparse(statement.value)
        value = statement.value
        if isinstance(value, ast.Call) and isinstance(value.func, (ast.Name, ast.Attribute)) \
                and (getattr(value.func, "id", None) or getattr(value.func, "attr", None)) == "field":
            options = {keyword.arg: keyword.value for keyword in value.keywords}
            if isinstance(options.get("init"), ast.Constant) and options["init"].value is False:
                continue
            default = (ast.unparse(options["default"]) if "default" in options
                       else "<factory>" if "default_factory" in options else None)
        rows.append(("KEYWORD_ONLY" if keyword_only else "POSITIONAL_OR_KEYWORD", statement.target.id,
                     annotation, default))
    return _render(rows, None)


def _decorated(node: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> bool:
    return any((isinstance(decorator, ast.Name) and decorator.id == name)
               or (isinstance(decorator, ast.Attribute) and decorator.attr.endswith(name.rpartition(".")[2])
                   and ast.unparse(decorator).endswith(name))
               for decorator in node.decorator_list)


def _class(node: ast.ClassDef) -> dict[str, Any]:
    init = next((statement for statement in node.body if isinstance(statement, ast.FunctionDef)
                 and statement.name == "__init__"), None)
    signature = (_ast_signature(init, drop_first=True) if init is not None
                 else _fields(node) if _dataclass(node) else None)
    members = []
    for statement in node.body:
        if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)) or statement.name.startswith("_"):
            continue
        if _decorated(statement, "property") or _decorated(statement, "cached_property"):
            members.append({"name": statement.name, "kind": "property",
                            "type": None if statement.returns is None else ast.unparse(statement.returns),
                            "doc": _doc(ast.get_docstring(statement, clean=False))})
            continue
        static = _decorated(statement, "staticmethod")
        members.append({"name": statement.name,
                        "kind": "classmethod" if _decorated(statement, "classmethod") else
                        "staticmethod" if static else "method",
                        "signature": _ast_signature(statement, drop_first=not static),
                        "doc": _doc(ast.get_docstring(statement, clean=False))})
    return {"kind": "class", "bases": [ast.unparse(base) for base in node.bases] or None, "signature": signature,
            "doc": _doc(ast.get_docstring(node, clean=False)), "members": members}


def _static_member(module: str, name: str) -> dict[str, Any]:
    """One declared name of an integration's namespace, from its source."""
    where, node = _declared(module, name)
    if node is None and where != module and _source(where) is not None:  # a public submodule
        tree = _tree(where)
        names = _literal_all(where) or []
        return {"name": name, "kind": "module", "module": where,
                "doc": _doc(ast.get_docstring(tree, clean=False)) if tree is not None else None,
                "members": [_static_member(where, member) for member in names]}
    entry: dict[str, Any] = {"name": name}
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        entry.update(kind="function", signature=_ast_signature(node), doc=_doc(ast.get_docstring(node, clean=False)))
    elif isinstance(node, ast.ClassDef):
        entry.update(_class(node))
    elif isinstance(node, (ast.Assign, ast.AnnAssign)):
        value = node.value
        text = None if value is None else ast.unparse(value)
        entry.update(kind="object",
                     type=ast.unparse(node.annotation) if isinstance(node, ast.AnnAssign) else None,
                     value=text if text is not None and len(text) <= 80 else None)
    else:
        entry.update(kind="object")
    return entry


# --- the document types, read at run time ------------------------------------------------------------------

def _type_members(entry: Any) -> list[dict[str, Any]]:
    """A document type's names: its decorator, its reader, its operations, its edit, then whatever else its
    package's ``__all__`` declares."""
    import cad
    from cad.engine import model as engine_model

    owner = getattr(cad, entry.id)
    members: list[dict[str, Any]] = []
    if entry.decorator:
        # ``cad.model`` is its own ``__call__``; a file's type hands its call to the engine's decorator of
        # that type, whose signature and words are the type's own (a mesh's alone takes a tolerance).
        if entry.id == "model":
            call = type(owner).__call__
            signature, doc = _runtime_signature(call, drop_first=True), _doc(call.__doc__)
        else:
            maker = getattr(engine_model, entry.id)
            signature, doc = _runtime_signature(maker), _doc(maker.__doc__)
        members.append({"name": entry.id, "kind": "decorator", "signature": signature, "doc": doc})
    names = [*(["read"] if entry.reader else []), *entry.operation_names, *(["edit"] if entry.edit else [])]
    names += sorted(set(getattr(owner, "__all__", ())) - set(names))
    for name in names:
        value = getattr(owner, name)
        operation = entry.operation(name)
        summary = operation.summary if operation is not None else None
        doc = _doc(getattr(value, "__doc__", None))
        head = f"cad.{entry.id}.{name}: {summary}."
        if doc is not None and summary is not None and doc.startswith(head):
            doc = _doc(doc[len(head):])  # the summary, said by its own field; the rest is the verb's, shared
        members.append({"name": name, "kind": "function", "operation": operation is not None, "summary": summary,
                        "signature": _runtime_signature(value), "doc": doc})
    return members


def as_docs() -> dict[str, Any]:
    """The library's public API: the root's names, each document type's and each integration's; every
    docstring an index into ``texts``."""
    import cad
    from cad.registry import DOCUMENT_TYPES, INTEGRATIONS

    names = []
    for name in cad.__all__:
        if name in DOCUMENT_TYPES:
            continue
        if name == "__version__":
            names.append({"name": name, "kind": "attribute", "type": "str",
                          "doc": "The release of the library this is, as its distribution's metadata says it."})
            continue
        value = getattr(cad, name)
        names.append({"name": name, "kind": "class" if isinstance(value, type) else "object",
                      "bases": [base.__qualname__ for base in value.__bases__] if isinstance(value, type) else None,
                      "doc": _doc(value.__doc__)})
    document_types = [{"name": entry.id, "module": f"cad.{entry.id}", "title": entry.title,
                       "doc": _doc(getattr(cad, entry.id).__doc__), "members": _type_members(entry)}
                      for entry in DOCUMENT_TYPES.values()]
    integrations = []
    for name in INTEGRATIONS:
        module = f"cad.{name}"
        package = importlib.import_module(module)  # its __all__ alone: the package loads nothing of its tool's
        declared = list(getattr(package, "__all__", ()))
        integrations.append({"name": name, "module": module, "doc": _doc(package.__doc__),
                             "members": [_static_member(module, member) for member in declared]})
    return _shared({"module": "cad", "doc": _doc(cad.__doc__), "names": names, "documentTypes": document_types,
                    "integrations": integrations})


def _shared(reference: dict[str, Any]) -> dict[str, Any]:
    """``reference`` with every ``doc`` an index into ``texts`` (in the order first met), so a docstring many
    types share is written once, and every field that says nothing (null, false, an empty list) left out."""
    texts: dict[str, int] = {}

    def walk(value: Any) -> Any:
        if isinstance(value, list):
            return [walk(item) for item in value]
        if not isinstance(value, dict):
            return value
        return {key: (texts.setdefault(item, len(texts)) if key == "doc" else walk(item))
                for key, item in value.items() if item is not None and item is not False and item != []}

    shared = walk(reference)
    return {**shared, "texts": list(texts)}


def as_docs_json() -> str:
    """``as_docs`` as the file the documentation site reads."""
    return json.dumps(as_docs(), indent=1, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--docs"]:
        sys.stdout.write(as_docs_json())
        return 0
    sys.stderr.write("usage: python -m cad._internal.reference --docs\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
