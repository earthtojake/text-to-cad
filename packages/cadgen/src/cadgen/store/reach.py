"""Static reach inside one module: the top-level statements a build can execute
through the names it takes from the module, and a hash over exactly those.

A helper module is tracked by the names a model reaches in it (``STORE.md`` §3,
"functions by reach"). This module answers questions about ONE file's bytes and
nothing else — no filesystem, no import resolution, no model detection — so the
same bytes always analyse the same way (for one interpreter version):

- :func:`analyze` splits the module into top-level **statements**, each with
  the module-scope names it binds and reads, the attribute chains it walks on
  those names, the imports it contains, every name it loads at all (a
  syntactic superset the walk follows as edges too) and a digest of its
  ``ast.dump``. A statement is a **definition** (an undecorated ``def`` with
  inert defaults/annotations, or a single-name literal assignment without
  rebinding) or **preamble** (everything else: imports, calls, conditionals,
  loops, attribute writes, decorated definitions, defaults that call — anything
  that runs or may register something at import). Preamble is always part of a
  slice; a definition is part of it only when a reached name binds it.
- :func:`close_names` expands a set of reached names within the module: a
  reached definition's reads reach the definitions they name, transitively.
- :func:`slice_hash` hashes preamble + the reached definitions in source
  order, with the reached names and whether each is bound. It is comment- and
  formatting-insensitive like the whole-file semantic hash.

Scopes are resolved here, in one pass over the tree, with Python's rules: a
function's parameters and assignments are its own, a comprehension's targets
are its own, class bodies are invisible to the scopes nested in them, defaults,
decorators, bases and a comprehension's first iterable belong to the enclosing
scope.

**Anything dynamic makes the whole module the slice** (``ModuleSyntax.dynamic``
names why): a star import, ``globals()``/``locals()``/``vars()`` (and then
every module it imports: ``unbounded``), a module-level ``__getattr__``, or a
module-scope name nothing binds. A construct that can reach ANY module's
namespace by string or by introspection sets ``ModuleSyntax.reflective``
(``exec``/``eval``/``compile``/``__import__``, ``importlib``, ``sys.modules``,
frames, ``__globals__``, ``inspect``, ``pickle`` …): the caller hashes the
model's whole closure whole. Uses that reach OUT of the module — a module alias
used bare (``getattr(geo, n)``, ``vars(geo)``, passing ``geo`` along) or
written to (``geo.X = 1``) — are reported per statement for the closure walk to
turn into whole-file edges on the target.
"""

from __future__ import annotations

import ast
import builtins
import copy
import hashlib
import sys
from dataclasses import dataclass
from typing import Iterable, Mapping

_BUILTIN_NAMES = frozenset(dir(builtins)) | frozenset({
    "__file__", "__name__", "__doc__", "__spec__", "__package__", "__loader__",
    "__path__", "__builtins__", "__annotations__", "__cached__", "__all__",
    "__class__", "__qualname__", "__module__", "__debug__",
})
# Builtins exposing the calling module's namespace — and, through the module
# objects it imported, theirs: the module and every module it imports whole.
_NAMESPACE_BUILTINS = frozenset({"globals", "locals", "vars"})
# Builtins that execute or import by string: any module can be reached.
_STRING_BUILTINS = frozenset({"exec", "eval", "compile", "__import__"})
# Modules whose API resolves modules or attributes from strings, or reaches a
# namespace through frames, functions or the object graph.
_REFLECTIVE_MODULES = frozenset({
    "importlib", "builtins", "runpy", "pkgutil", "zipimport", "imp",
    "inspect", "pydoc", "gc", "ctypes", "code", "codeop", "timeit", "cProfile",
    "profile", "pdb", "trace", "doctest", "unittest",
    "pickle", "_pickle", "cloudpickle", "dill", "joblib", "jsonpickle",
    "marshal", "shelve", "copyreg",
})
# Attributes that lead from an object to a namespace: a function's globals, a frame.
_REFLECTIVE_ATTRS = frozenset({
    "__globals__", "__builtins__", "f_globals", "f_locals", "f_builtins", "f_back",
    "tb_frame", "gi_frame", "cr_frame", "ag_frame", "_getframe", "_current_frames",
})
# ``sys`` attributes exposing every loaded module or a frame.
_SYS_REFLECTIVE = frozenset({"modules", "_getframe", "_current_frames", "__dict__"})
_MODULE_HOOKS = frozenset({"__getattr__", "__dir__"})
# Interpreters that never evaluate annotations at definition time (PEP 649/749).
_LAZY_ANNOTATIONS = sys.version_info >= (3, 14)


@dataclass(frozen=True)
class Alias:
    """One name an import statement binds."""

    module: str          # dotted module the name is bound to; "" for ``from . import x``
    level: int           # relative-import level
    attr: str | None     # the name ``from module import attr`` takes; None for ``import module``
    # ``import a.b.c`` binds ``a`` but executes ``a``, ``a.b`` and ``a.b.c``.
    executes: str | None = None


@dataclass(frozen=True)
class Header:
    """What executing a top-level ``def`` runs: its decorators, defaults,
    annotations and type parameters -- never its body. Importing a child model
    file runs its model definitions' headers in the importer's process."""

    reads: tuple[str, ...]
    chains: tuple[tuple[str, tuple[str, ...]], ...]
    stores: tuple[str, ...]
    loads: tuple[tuple[str, tuple[str, ...]], ...]
    # sha256 of ast.dump(the def with its body emptied), a cadgen model
    # decorator's literal arguments read as one placeholder: evaluating a literal
    # runs nothing, and cadgen's decorators keep what they are given to the child.
    digest: bytes
    aliases: tuple[tuple[str, Alias], ...] = ()
    stars: tuple[Alias, ...] = ()


@dataclass(frozen=True)
class Statement:
    index: int
    definition: bool
    binds: tuple[str, ...]                                      # module-scope names this statement binds
    reads: tuple[str, ...]                                      # names read bare, resolved to module scope
    chains: tuple[tuple[str, tuple[str, ...]], ...]             # (name, attribute chain) reads
    stores: tuple[str, ...]                                     # names whose attribute is written or deleted
    aliases: tuple[tuple[str, Alias], ...]                      # import bindings inside this statement
    stars: tuple[Alias, ...]                                    # star imports inside this statement
    # Every other name the statement loads, with its attribute chain, whatever
    # scope binds it: followed as edges too, so reach never rests on scoping alone.
    loads: tuple[tuple[str, tuple[str, ...]], ...]
    digest: bytes                                               # sha256 of ast.dump(statement)
    header: Header | None = None                                # a top-level def's import-time part


@dataclass(frozen=True)
class ModuleSyntax:
    statements: tuple[Statement, ...]
    definitions: Mapping[str, tuple[int, ...]]   # name -> definition statements binding it
    preamble: tuple[int, ...]                    # statement indices that are always in the slice
    preamble_bound: frozenset[str]               # names a preamble statement binds
    aliases: Mapping[str, tuple[Alias, ...]]     # module-scope import bindings (top level + inside preamble)
    dynamic: str | None                          # why the whole module must be tracked, or None
    # The dynamism can reach into other modules: every module this one imports
    # is tracked whole too, not only this one.
    unbounded: bool
    # Why ANY module's namespace is reachable from this file (by string or by
    # introspection): the model's whole closure is hashed whole. Implies dynamic.
    reflective: str | None
    guards: frozenset[int]                       # unshadowed ``if __name__ == "__main__":`` blocks
    whole_hash: str                              # the whole-file semantic hash of these bytes


# --- the whole-file semantic hash ------------------------------------------------


def _dump_frame() -> tuple[str, str, str] | None:
    """``ast.dump`` of a module as (prefix, suffix, empty) around its statements'
    dumps joined by ", " — so the whole-file hash reuses the per-statement dumps.
    None if this interpreter's format does not decompose that way."""
    pieces = [ast.Pass(), ast.Break()]
    parts = [ast.dump(piece) for piece in pieces]
    whole = ast.dump(ast.Module(body=pieces, type_ignores=[]))
    joined = ", ".join(parts)
    start = whole.find(joined)
    if start < 0:
        return None
    prefix, suffix = whole[:start], whole[start + len(joined):]
    single = ast.dump(ast.Module(body=[ast.Pass()], type_ignores=[]))
    if single != prefix + parts[0] + suffix:
        return None
    return prefix, suffix, ast.dump(ast.Module(body=[], type_ignores=[]))


_DUMP_FRAME = _dump_frame()


def semantic_hash(tree: ast.Module, dumps: list[str] | None = None) -> str:
    """``ast1:`` + sha256 of ``ast.dump(tree)`` (positions excluded): the
    whole-file semantic hash. ``dumps`` are the statements' own dumps, when the
    caller already has them."""
    if _DUMP_FRAME is None:
        text = ast.dump(tree)
    else:
        if dumps is None:
            dumps = [ast.dump(node) for node in tree.body]
        prefix, suffix, empty = _DUMP_FRAME
        text = prefix + ", ".join(dumps) + suffix if dumps else empty
    return "ast1:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- scopes -----------------------------------------------------------------------


class _Scope:
    __slots__ = ("kind", "parent", "bound", "imported", "declared_global", "declared_nonlocal")

    def __init__(self, kind: str, parent: "_Scope | None") -> None:
        self.kind = kind            # "module" | "class" | "function" (defs, lambdas, type params) | "comprehension"
        self.parent = parent
        self.bound: set[str] = set()
        self.imported: set[str] = set()
        self.declared_global: set[str] = set()
        self.declared_nonlocal: set[str] = set()


_MODULE, _CLASS_OWN, _LOCAL, _LOCAL_IMPORT = "module", "class", "local", "import"


def _resolve(name: str, scope: _Scope) -> str:
    """Where a load of ``name`` in ``scope`` resolves: the module (or builtins),
    a class body's own binding (whose LOAD_NAME may still fall back to the
    module), a local of some function scope, or a local import binding."""
    if scope.kind == "class":
        if name in scope.declared_global:
            return _MODULE
        enclosing = _function_binding(name, scope.parent)
        if enclosing is not None:
            return enclosing  # a free variable of the enclosing function (class dict first)
        return _CLASS_OWN if name in scope.bound else _MODULE
    return _function_binding(name, scope) or _MODULE


def _function_binding(name: str, scope: _Scope | None) -> str | None:
    while scope is not None:
        if scope.kind == "module":
            return None
        if scope.kind != "class":  # class bodies are invisible to nested scopes
            if name in scope.declared_global:
                return None
            if name in scope.declared_nonlocal:
                return _LOCAL
            if name in scope.bound:
                return _LOCAL_IMPORT if name in scope.imported else _LOCAL
        scope = scope.parent
    return None


_LEAVES = (ast.expr_context, ast.operator, ast.boolop, ast.unaryop, ast.cmpop, ast.Constant)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


class _Facts:
    """What one top-level statement binds, loads and imports, scope-resolved."""

    __slots__ = ("top", "scopes", "loads", "stores", "globals", "aliases", "module_aliases",
                 "stars", "reflective", "safe_vars", "sys_names")

    def __init__(self) -> None:
        self.top = _Scope("module", None)
        self.scopes: list[_Scope] = [self.top]
        self.loads: list[tuple[ast.Name, _Scope, tuple[str, ...]]] = []
        self.stores: list[tuple[str, _Scope]] = []   # attribute written/deleted on a name
        self.globals: set[str] = set()                # names a ``global`` statement declares
        self.aliases: list[tuple[str, Alias]] = []
        self.module_aliases: list[tuple[str, Alias]] = []
        self.stars: list[Alias] = []
        self.reflective: str | None = None
        self.safe_vars: set[int] = set()              # ``vars`` Name nodes called with an argument
        self.sys_names: set[str] = set()              # names bound to the ``sys`` module

    def scope(self, kind: str, parent: _Scope) -> _Scope:
        scope = _Scope(kind, parent)
        self.scopes.append(scope)
        return scope

    def flag(self, why: str) -> None:
        self.reflective = self.reflective or why

    def module_writes(self) -> set[str]:
        """Names the statement may bind in the module namespace: its own
        module-scope bindings, and ``global`` writes in scopes nested in it."""
        names = set(self.top.bound)
        for scope in self.scopes[1:]:
            names.update(scope.declared_global & scope.bound)
        return names


def _bind_import(facts: _Facts, scope: _Scope, name: str, alias: Alias) -> None:
    scope.bound.add(name)
    scope.imported.add(name)
    facts.aliases.append((name, alias))
    if scope is facts.top:
        facts.module_aliases.append((name, alias))


def _arguments(args: ast.arguments) -> list[ast.arg]:
    found = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    if args.vararg is not None:
        found.append(args.vararg)
    if args.kwarg is not None:
        found.append(args.kwarg)
    return found


def _type_param_scope(facts: _Facts, node: ast.AST, scope: _Scope, stack: list) -> _Scope:
    params = getattr(node, "type_params", None) or ()
    if not params:
        return scope
    inner = facts.scope("function", scope)
    for param in params:
        inner.bound.add(param.name)
        for field in ("bound", "default_value"):
            value = getattr(param, field, None)
            if value is not None:
                stack.append((value, inner))
    return inner


def _scan(statement: ast.stmt) -> _Facts:
    """One iterative pass: every node is assigned the scope it evaluates in,
    bindings are collected per scope, loads are resolved after the pass."""
    facts = _Facts()
    stack: list[tuple[ast.AST, _Scope]] = [(statement, facts.top)]
    while stack:
        node, scope = stack.pop()
        kind = type(node)
        if kind is ast.Name:
            if type(node.ctx) is ast.Load:
                facts.loads.append((node, scope, ()))
            else:
                scope.bound.add(node.id)
            continue
        if kind is ast.Constant:
            continue
        if kind is ast.Attribute:
            chain: list[str] = []
            base: ast.AST = node
            while type(base) is ast.Attribute:
                chain.append(base.attr)
                base = base.value
            chain.reverse()
            for index, attribute in enumerate(chain):
                if attribute in _REFLECTIVE_ATTRS:
                    facts.flag(f".{attribute}")
                elif index and chain[index - 1] == "sys" and attribute in _SYS_REFLECTIVE:
                    facts.flag(f"sys.{attribute}")
            if type(base) is ast.Name:
                if type(node.ctx) is ast.Load:
                    facts.loads.append((base, scope, tuple(chain)))
                else:
                    # ``geo.X = 1`` writes to geo; ``geo.X.y = 1`` also reads geo.X.
                    facts.stores.append((base.id, scope))
                    if len(chain) > 1:
                        facts.loads.append((base, scope, tuple(chain[:-1])))
            else:
                stack.append((base, scope))
            continue
        if kind is ast.Call:
            func = node.func
            if type(func) is ast.Name and func.id == "vars" and node.args:
                facts.safe_vars.add(id(func))
            stack.append((func, scope))
            stack.extend((arg, scope) for arg in node.args)
            stack.extend((keyword.value, scope) for keyword in node.keywords)
            continue
        if kind is ast.FunctionDef or kind is ast.AsyncFunctionDef or kind is ast.Lambda:
            args = node.args
            stack.extend((default, scope) for default in args.defaults)
            stack.extend((default, scope) for default in args.kw_defaults if default is not None)
            if kind is ast.Lambda:
                inner = facts.scope("function", scope)
                inner.bound.update(arg.arg for arg in _arguments(args))
                stack.append((node.body, inner))
                continue
            scope.bound.add(node.name)
            stack.extend((decorator, scope) for decorator in node.decorator_list)
            outer = _type_param_scope(facts, node, scope, stack)
            for arg in _arguments(args):
                if arg.annotation is not None:
                    stack.append((arg.annotation, outer))
            if node.returns is not None:
                stack.append((node.returns, outer))
            inner = facts.scope("function", outer)
            inner.bound.update(arg.arg for arg in _arguments(args))
            stack.extend((child, inner) for child in node.body)
            continue
        if kind is ast.ClassDef:
            scope.bound.add(node.name)
            stack.extend((decorator, scope) for decorator in node.decorator_list)
            outer = _type_param_scope(facts, node, scope, stack)
            stack.extend((base, outer) for base in node.bases)
            stack.extend((keyword.value, outer) for keyword in node.keywords)
            body = facts.scope("class", outer)
            stack.extend((child, body) for child in node.body)
            continue
        if kind in _COMPREHENSIONS:
            inner = facts.scope("comprehension", scope)
            for index, generator in enumerate(node.generators):
                # The first iterable is evaluated in the enclosing scope.
                stack.append((generator.iter, scope if index == 0 else inner))
                stack.append((generator.target, inner))
                stack.extend((condition, inner) for condition in generator.ifs)
            if kind is ast.DictComp:
                stack.append((node.key, inner))
                stack.append((node.value, inner))
            else:
                stack.append((node.elt, inner))
            continue
        if kind is ast.NamedExpr:
            # The target binds in the nearest enclosing non-comprehension scope.
            target = scope
            while target.kind == "comprehension" and target.parent is not None:
                target = target.parent
            target.bound.add(node.target.id)
            stack.append((node.value, scope))
            continue
        if kind is ast.Import:
            for alias in node.names:
                if alias.asname:
                    name, bound = alias.asname, Alias(alias.name, 0, None)
                else:
                    head = alias.name.split(".")[0]
                    name, bound = head, Alias(head, 0, None, alias.name if "." in alias.name else None)
                _bind_import(facts, scope, name, bound)
                if alias.name.split(".")[0] in _REFLECTIVE_MODULES:
                    facts.flag(f"import {alias.name}")
                if alias.name == "sys":
                    facts.sys_names.add(name)
            continue
        if kind is ast.ImportFrom:
            module = node.module or ""
            top_module = module.split(".")[0] if node.level == 0 else ""
            for alias in node.names:
                if top_module in _REFLECTIVE_MODULES:
                    facts.flag(f"from {module} import {alias.name}")
                elif top_module == "sys" and (alias.name == "*" or alias.name in _SYS_REFLECTIVE):
                    facts.flag(f"from sys import {alias.name}")
                if alias.name == "*":
                    facts.stars.append(Alias(module, node.level, None))
                    continue
                name = alias.asname or alias.name
                _bind_import(facts, scope, name, Alias(module, node.level, alias.name))
                if node.level == 0 and alias.name == "sys":
                    facts.sys_names.add(name)
            continue
        if kind is ast.Global:
            if scope.kind != "module":
                scope.declared_global.update(node.names)
            facts.globals.update(node.names)
            continue
        if kind is ast.Nonlocal:
            scope.declared_nonlocal.update(node.names)
            continue
        if kind is ast.ExceptHandler:
            if node.name:
                scope.bound.add(node.name)
        elif kind is ast.MatchAs or kind is ast.MatchStar:
            if node.name:
                scope.bound.add(node.name)
        elif kind is ast.MatchMapping:
            if node.rest:
                scope.bound.add(node.rest)
        elif kind.__name__ == "TypeAlias":  # 3.12+: ``type X[T] = value``
            stack.append((node.name, scope))
            inner = facts.scope("function", _type_param_scope(facts, node, scope, stack))
            stack.append((node.value, inner))
            continue
        for field in node._fields:
            value = getattr(node, field, None)
            if type(value) is list:
                for item in value:
                    if isinstance(item, ast.AST) and not isinstance(item, _LEAVES):
                        stack.append((item, scope))
            elif isinstance(value, ast.AST) and not isinstance(value, _LEAVES):
                stack.append((value, scope))
    return facts


# --- definitions and preamble ---------------------------------------------------


def _literal(node: ast.AST) -> bool:
    """Closed literal syntax, without names or Python protocol dispatch.

    Do not infer purity from a callable's module or from the absence of Calls:
    attributes, operators, unpacking, formatting and conversions can all run
    user code. New expression syntax is non-inert until explicitly handled.
    """
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(_literal(item) for item in node.elts)
    if isinstance(node, ast.Dict):
        return all(key is not None and _literal(key) and _literal(value)
                   for key, value in zip(node.keys, node.values))
    return (isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub))
            and isinstance(node.operand, ast.Constant)
            and type(node.operand.value) in (int, float, complex))


def _is_main_guard(node: ast.stmt) -> bool:
    """``if __name__ == "__main__":`` — never runs on import."""
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    test = node.test
    if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq) or len(test.comparators) != 1:
        return False
    sides = (test.left, test.comparators[0])
    return (any(isinstance(s, ast.Name) and s.id == "__name__" for s in sides)
            and any(isinstance(s, ast.Constant) and s.value == "__main__" for s in sides)
            and not node.orelse)


# cadgen's model decorators, as ``cadgen.metadata`` recognises them.
_MODEL_DECORATORS = frozenset({"step", "dxf", "pcb", "harness", "stl", "glb", "threemf"})
_PLACEHOLDER = "<literal>"


def _cadgen_decorators(tree: ast.Module) -> tuple[frozenset[str], frozenset[str]]:
    """Top-level names bound to cadgen's model decorators, and to the cadgen
    module itself -- the same reading as ``cadgen.metadata``."""
    names: set[str] = set()
    modules: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module in {"cadgen", "cadgen.authoring"}:
            names.update(alias.asname or alias.name for alias in node.names if alias.name in _MODEL_DECORATORS)
        elif isinstance(node, ast.Import):
            modules.update(alias.asname or "cadgen" for alias in node.names if alias.name == "cadgen")
    return frozenset(names), frozenset(modules)


def _placeholder_literals(decorator: ast.expr, names: frozenset[str], modules: frozenset[str]) -> ast.expr:
    """A cadgen model decorator call with each literal argument read as one
    placeholder. Anything else -- another decorator, a call or a name among the
    arguments -- stays as written: evaluating it runs code at import."""
    if not isinstance(decorator, ast.Call):
        return decorator
    target = decorator.func
    ours = (isinstance(target, ast.Name) and target.id in names) or (
        isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
        and target.value.id in modules and target.attr in _MODEL_DECORATORS)
    if not ours:
        return decorator

    def value(node: ast.expr) -> ast.expr:
        return ast.Constant(value=_PLACEHOLDER) if _literal(node) else node

    return ast.Call(func=target, args=[value(arg) for arg in decorator.args],
                    keywords=[ast.keyword(arg=keyword.arg, value=value(keyword.value)) for keyword in decorator.keywords])


def _categorized(facts: _Facts) -> tuple[set[str], set[tuple[str, tuple[str, ...]]], set[str], set[tuple[str, tuple[str, ...]]]]:
    """(reads, chains, stores, loads) of one scan, scope-resolved as a statement's are."""
    reads: set[str] = set(facts.globals)
    chains: set[tuple[str, tuple[str, ...]]] = set()
    loads: set[tuple[str, tuple[str, ...]]] = set()
    for name_node, scope, chain in facts.loads:
        where = _resolve(name_node.id, scope)
        if where == _LOCAL:
            loads.add((name_node.id, chain))
        elif chain:
            chains.add((name_node.id, chain))
        else:
            reads.add(name_node.id)
    stores = {name for name, scope in facts.stores if _resolve(name, scope) != _LOCAL}
    loads -= chains
    loads.difference_update((name, ()) for name in reads)
    return reads, chains, stores, loads


def _header(node: ast.FunctionDef | ast.AsyncFunctionDef, names: frozenset[str], modules: frozenset[str]) -> Header:
    stripped = copy.copy(node)
    stripped.body = [ast.Pass()]
    stripped.decorator_list = [_placeholder_literals(d, names, modules) for d in node.decorator_list]
    reads, chains, stores, loads = _categorized(_scan(stripped))
    return Header(reads=tuple(sorted(reads)), chains=tuple(sorted(chains)), stores=tuple(sorted(stores)),
                  loads=tuple(sorted(loads)), digest=hashlib.sha256(ast.dump(stripped).encode("utf-8")).digest())


def _future_annotations(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue  # the docstring
        if not (isinstance(node, ast.ImportFrom) and node.module == "__future__"):
            return False
        if any(alias.name == "annotations" for alias in node.names):
            return True
    return False


def _classify(node: ast.stmt, rebound: set[str], lazy: bool) -> bool:
    """Only deferred function bodies and closed literals may be omitted.

    Everything else executes as preamble, including all classes/decorators,
    evaluated annotations, calls, aliases and augmented assignments. Even
    inert evaluation can release an old value on rebinding (__del__), so
    repeated bindings cannot be omitted either. ``lazy``: annotations are
    never evaluated at definition time (``from __future__ import annotations``,
    Python 3.14+), so they cannot disqualify a definition.
    """
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.name in rebound or node.decorator_list or getattr(node, "type_params", ()):
            return False
        args = node.args
        evaluated = [*args.defaults, *[d for d in args.kw_defaults if d is not None]]
        if not lazy:
            evaluated += [a.annotation for a in _arguments(args) if a.annotation is not None]
            if node.returns is not None:
                evaluated.append(node.returns)
        # Even a bare name can retain an object in defaults/annotations and
        # change when its finalizer runs. Only closed literals are optional.
        return all(_literal(value) for value in evaluated)
    if (isinstance(node, ast.Assign) and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)):
        return node.targets[0].id not in rebound and _literal(node.value)
    if (lazy and isinstance(node, ast.AnnAssign) and node.simple and isinstance(node.target, ast.Name)
            and node.value is not None):
        return node.target.id not in rebound and _literal(node.value)
    return False


# --- the module ------------------------------------------------------------------


def analyze(source: bytes, filename: str = "<module>") -> ModuleSyntax:
    """Analyse one module's bytes. Raises ``SyntaxError``/``ValueError`` like
    ``ast.parse`` on invalid source, and ``RecursionError``/``MemoryError`` on
    pathologically deep source (the caller hashes such bytes whole)."""
    tree = ast.parse(source, filename=filename)
    dumps = [ast.dump(node) for node in tree.body]
    whole_hash = semantic_hash(tree, dumps)
    lazy = _LAZY_ANNOTATIONS or _future_annotations(tree)
    facts = [_scan(node) for node in tree.body]
    writes = [f.module_writes() for f in facts]
    name_rebound = any("__name__" in names for names in writes)
    guards = frozenset(index for index, node in enumerate(tree.body)
                       if not name_rebound and _is_main_guard(node))

    # Possible namespace writes, including conditional and ``global`` writes.
    # Rebinding can run a finalizer even for a literal RHS. A main guard never
    # runs on import, so what it binds rebinds nothing.
    seen: set[str] = set(_BUILTIN_NAMES)
    rebound: set[str] = set()
    module_bound: set[str] = set()
    for index, names in enumerate(writes):
        if index not in guards:
            rebound.update(seen & names)
            seen.update(names)
            module_bound.update(names)

    module_aliases: dict[str, list[Alias]] = {}
    for index, f in enumerate(facts):
        if index not in guards:
            for name, alias in f.module_aliases:
                module_aliases.setdefault(name, []).append(alias)
    frozen_aliases = {name: tuple(bound) for name, bound in module_aliases.items()}
    sys_names = {name for f in facts for name in f.sys_names}
    decorator_names, decorator_modules = _cadgen_decorators(tree)

    statements: list[Statement] = []
    definitions: dict[str, list[int]] = {}
    preamble: list[int] = []
    preamble_bound: set[str] = set()
    must_bind: list[set[str]] = []
    dynamic: str | None = None
    unbounded = False
    reflective: str | None = None
    for index, node in enumerate(tree.body):
        f = facts[index]
        guard = index in guards
        definition = guard or _classify(node, rebound, lazy)
        binds = () if guard else tuple(sorted(writes[index]))
        reads: set[str] = set(f.globals)
        chains: set[tuple[str, tuple[str, ...]]] = set()
        loads: set[tuple[str, tuple[str, ...]]] = set()
        free: set[str] = set()
        for name_node, scope, chain in f.loads:
            name = name_node.id
            where = _resolve(name, scope)
            if where == _LOCAL:
                loads.add((name, chain))
            elif chain:
                chains.add((name, chain))
            else:
                reads.add(name)
            if where == _MODULE:
                free.add(name)
            if guard:
                continue
            if name == "__builtins__":
                reflective = reflective or "__builtins__"
            if name in sys_names and (not chain or chain[0] in _SYS_REFLECTIVE):
                reflective = reflective or (f"{name}.{chain[0]}" if chain else f"{name} used bare")
            if where == _MODULE and name not in module_bound:
                if name in _STRING_BUILTINS:
                    reflective = reflective or f"{name}()"
                elif name in _NAMESPACE_BUILTINS and not (name == "vars" and id(name_node) in f.safe_vars):
                    dynamic = dynamic or f"{name}()"
                    unbounded = True
        stores: set[str] = set()
        for name, scope in f.stores:
            where = _resolve(name, scope)
            if where != _LOCAL:
                stores.add(name)
                if where == _MODULE:
                    free.add(name)
        if not guard:
            if f.stars:
                dynamic = dynamic or "star import"
            reflective = reflective or f.reflective
            hooks = sorted(writes[index] & _MODULE_HOOKS)
            if hooks:
                dynamic = dynamic or f"module hook {hooks[0]}"
            must_bind.append(free)
        loads -= chains
        loads.difference_update((name, ()) for name in reads)
        header = None
        if not guard and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            header = _header(node, decorator_names, decorator_modules)
        statements.append(Statement(
            index=index, definition=definition, binds=binds, reads=tuple(sorted(reads)),
            chains=tuple(sorted(chains)), stores=tuple(sorted(stores)), aliases=tuple(f.aliases),
            stars=tuple(f.stars), loads=tuple(sorted(loads)),
            digest=hashlib.sha256(dumps[index].encode("utf-8")).digest(), header=header,
        ))
        if definition:
            for name in binds:
                definitions.setdefault(name, []).append(index)
        else:
            preamble.append(index)
            preamble_bound.update(binds)

    if reflective is not None:
        dynamic, unbounded = dynamic or reflective, True
    # Unresolved names: a module-scope read that nothing binds and no builtin answers.
    if dynamic is None:
        for free in must_bind:
            missing = sorted(name for name in free if not (
                name in definitions or name in preamble_bound or name in frozen_aliases or name in _BUILTIN_NAMES))
            if missing:
                dynamic = f"unresolved name {missing[0]}"
                break

    return ModuleSyntax(
        statements=tuple(statements),
        definitions={name: tuple(v) for name, v in definitions.items()},
        preamble=tuple(preamble),
        preamble_bound=frozenset(preamble_bound),
        aliases=frozen_aliases,
        dynamic=dynamic,
        unbounded=unbounded,
        reflective=reflective,
        guards=guards,
        whole_hash=whole_hash,
    )


def close_names(syntax: ModuleSyntax, names: Iterable[str], headers: Iterable[str] = ()) -> frozenset[str]:
    """The reached names closed within the module: every definition a reached
    definition reads, transitively. Preamble reads are roots of every slice; a
    preamble ``def`` binding a name in ``headers`` roots only its header."""
    headers = frozenset(headers)
    reached: set[str] = set()
    pending: list[str] = list(names)
    for index in syntax.preamble:
        statement = syntax.statements[index]
        if headers and statement.header is not None and headers.intersection(statement.binds):
            pending.extend(_definition_reads(statement.header))
        else:
            pending.extend(_definition_reads(statement))
    while pending:
        name = pending.pop()
        if name in reached:
            continue
        reached.add(name)
        for index in syntax.definitions.get(name, ()):
            pending.extend(_definition_reads(syntax.statements[index]))
    return frozenset(reached)


def _definition_reads(statement: Statement) -> Iterable[str]:
    yield from statement.reads
    for base, _chain in statement.chains:
        yield base
    yield from statement.stores
    for base, _chain in statement.loads:
        yield base


SLICE_PREFIX = "slice4:"


def slice_hash(syntax: ModuleSyntax, names: Iterable[str]) -> str:
    """The hash the gate compares for a sliced file: preamble plus every
    definition a name in the closed set binds, in source order, with the names
    and whether each is bound. The whole-file semantic hash when the module is
    dynamic, so a record sliced before the module turned dynamic reads stale."""
    if syntax.dynamic is not None:
        return syntax.whole_hash
    closed = close_names(syntax, names)
    digest = hashlib.sha256(b"slice4")
    for name in sorted(closed):
        digest.update(b"\0" + name.encode("utf-8") + (b"=" if name in syntax.definitions else b"!"))
    for statement in syntax.statements:
        if not statement.definition or any(name in closed for name in statement.binds):
            digest.update(b"\0\0" + statement.digest)
    return SLICE_PREFIX + digest.hexdigest()


IMPORT_SLICE_PREFIX = "islice1:"


def import_slice_hash(syntax: ModuleSyntax, names: Iterable[str], models: Iterable[str]) -> str:
    """The hash of what importing a child model file runs in the importer's
    process: its preamble -- with each definition of a model in ``models``
    counted by its header, since a model's body never runs at import -- and every
    definition a name in the closed set binds. The whole-file hash when the
    module is dynamic."""
    if syntax.dynamic is not None:
        return syntax.whole_hash
    models = frozenset(models)
    closed = close_names(syntax, names, headers=models)
    digest = hashlib.sha256(b"islice1")
    for name in sorted(closed):
        digest.update(b"\0" + name.encode("utf-8") + (b"=" if name in syntax.definitions else b"!"))
    for statement in syntax.statements:
        if statement.header is not None and models.intersection(statement.binds):
            digest.update(b"\0\1" + statement.header.digest)
        elif not statement.definition or any(name in closed for name in statement.binds):
            digest.update(b"\0\0" + statement.digest)
    return IMPORT_SLICE_PREFIX + digest.hexdigest()
