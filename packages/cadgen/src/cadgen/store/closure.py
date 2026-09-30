"""A model's closure: the source files its build depends on, and their hash.

**Model files are node boundaries.** Python imports run once, so "which frame
executed a file" cannot attribute module bodies. The boundary is decided
statically by what the importer TAKES from a model file:

- only model functions (``from arm import arm``; ``import arm`` + ``arm.arm()``)
  → a **result edge**: ``arm.py`` is excluded from this closure and the child
  is tracked by its pinned tree hash (``record.children``);
- a plainly hashable constant (``from plate import WIDTH`` — a number, str,
  bool, None, or tuples/lists/dicts of those, however the module computed it)
  → a **value edge**: the file stays out of the closure and the record carries
  ``constants[<module>][<name>] = sha256(canonical repr)``; the gate imports
  the module kernel-free and compares values;
- anything else (a helper function, a build123d object, an expression) → a
  **source edge**: the file is in the closure like any other.

Constants by value, functions by reach, models by result.

**Non-model files are sliced by reach.** A helper module (``lib/frame.py``) is
in the closure of every model whose static reach enters it, but what the
record hashes is the part of it the model can execute: the module's preamble
(imports, module-level calls and conditionals, decorated definitions — anything
that runs at import) plus every definition a reached name binds, closed within
the module and across modules (a reached function's reads, its decorators,
defaults and annotations reach what they name). Editing a definition the model
never reaches leaves it current; the analysis is ``cadgen.store.reach``, the
walk is :class:`_Walk`. Anything the analysis cannot see falls back to the
whole file, per module: a star import, ``exec``/``eval``/``globals()``,
``importlib``/``sys.modules``, a module-level ``__getattr__``, an unresolved
name, a module alias used bare (``getattr(geo, name)``) or written to
(``geo.X = 1``) — the target of an escape is whole too, and a package alias
escaping makes the whole package whole. A file reached only by execution (a
dynamic load static analysis never saw) is whole. The record keeps each sliced
file's reached names (``closure.names``); the gate re-slices the file on disk by
those names and compares.

**Hash at execution.** The closure hash a record carries is over the bytes that
RAN: files are hashed when they are loaded/executed (the loader has the script's
bytes; the ``exec`` audit hook fires per first-party file), never after the body
returns. An edit landing mid-build is therefore never hashed into a record over
geometry the pre-edit source produced. The reach analysis runs over those same
captured bytes, so a slice and its hash describe one revision.

Hashes are the semantic (AST) digest for ``.py`` (``ast1:``), the slice digest
for a sliced file (``slice3:``), and the byte digest otherwise, via
``cadgen._internal.source_hash`` and ``cadgen.store.reach`` — a comment-only
edit is not a change.
"""

from __future__ import annotations

import dataclasses
import functools
import hashlib
import sys
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

from cadgen._internal.source_hash import (
    _SEMANTIC_HASH_SETTLE_NS,
    _semantic_source_bytes,
    _semantic_source_hash,
    is_first_party_source_file,
)
from cadgen.store.reach import Alias, ModuleSyntax, analyze, slice_hash


@dataclass(frozen=True)
class Closure:
    hash: str
    files: tuple[str, ...]  # relative to the model's folder, sorted
    # model file (relative to the model's folder) -> constant name -> value hash
    constants: dict[str, dict[str, str]] = field(default_factory=dict)
    # relative path -> that file's hash as taken for this closure, so a stale
    # verdict can NAME the file that moved (lazily executed files included).
    shas: dict[str, str] = field(default_factory=dict)
    # relative path -> the names reached in a SLICED file (sorted). A file
    # absent here is tracked whole.
    names: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def as_json(self) -> dict:
        return {
            "hash": self.hash,
            "files": list(self.files),
            "shas": dict(self.shas),
            "names": {rel: list(names) for rel, names in self.names.items()},
        }


# --- constants by value -----------------------------------------------------------


def _canonical(value: object) -> str:
    if isinstance(value, dict):
        items = sorted(((_canonical(k), _canonical(v)) for k, v in value.items()))
        return "{" + ",".join(f"{k}:{v}" for k, v in items) + "}"
    if isinstance(value, (list, tuple, set, frozenset)):
        parts = [_canonical(v) for v in value]
        if isinstance(value, (set, frozenset)):
            parts.sort()
        return f"{type(value).__name__}[{','.join(parts)}]"
    return f"{type(value).__name__}:{value!r}"


_PLAIN_SCALARS = (bool, int, float, str, bytes, type(None))
_KERNEL_PACKAGES = frozenset({"build123d", "OCP", "cadquery"})


def _plain(value: object) -> bool:
    if isinstance(value, _PLAIN_SCALARS):
        return True
    if isinstance(value, dict):
        return all(_plain(k) and _plain(v) for k, v in value.items())
    if isinstance(value, (list, tuple, set, frozenset)):
        return all(_plain(v) for v in value)
    return False


class _KernelImport(ImportError):
    """Raised by the gate's import guard: this module pulls the CAD kernel."""


class _KernelGuard:
    """A meta-path finder that refuses a FIRST import of a kernel package."""

    def find_spec(self, name: str, path=None, target=None):  # noqa: ANN001 - importlib protocol
        if name.split(".")[0] in _KERNEL_PACKAGES and name not in sys.modules:
            raise _KernelImport(name)
        return None


def module_constant_hashes(path: Path, names: Iterable[str]) -> dict[str, str] | None:
    """Import the model file at ``path`` kernel-free and hash each of ``names``
    whose value is plainly hashable (numbers, str, bool, None, tuples/lists/dicts
    of those): ``sha256`` of the value's canonical repr. Names bound to anything
    else — a helper, a build123d object — are absent (tracked by file). ``None``
    when the module cannot be imported without pulling the kernel (or at all):
    the caller treats every name as a source edge / the record as stale.

    The import runs under the closure scan's own loader conventions (the
    script's folder and the caller's ``PYTHONPATH`` on ``sys.path``), under a private module
    name so a long-lived process never serves a cached module."""
    import importlib.util
    from importlib.machinery import SourceFileLoader

    resolved = Path(path).resolve()
    roots = [str(r) for r in _search_roots(resolved)]
    added = [r for r in roots if r not in sys.path]
    sys.path[:0] = added
    guard = _KernelGuard()
    sys.meta_path.insert(0, guard)
    try:
        name = f"_cadgen_constants_{hashlib.sha256(str(resolved).encode('utf-8')).hexdigest()[:16]}"
        loader = SourceFileLoader(name, str(resolved))
        spec = importlib.util.spec_from_loader(name, loader)
        if spec is None:
            return None
        module = importlib.util.module_from_spec(spec)
        # Compile the bytes on disk NOW — never the cached .pyc, whose mtime+size
        # check misses an edit that keeps the file's size within the same second.
        exec(compile(loader.get_data(str(resolved)), str(resolved), "exec"), module.__dict__)
    except Exception:  # noqa: BLE001 - a kernel pull or any import failure: not by value
        return None
    finally:
        sys.meta_path.remove(guard)
        for r in added:
            try:
                sys.path.remove(r)
            except ValueError:
                pass
    found: dict[str, str] = {}
    for name in names:
        if not hasattr(module, name):
            continue
        value = getattr(module, name)
        if _plain(value):
            found[name] = hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()
    return found


def changed_constant(script: Path, constants: Mapping[str, Mapping[str, str]]) -> str | None:
    """The first recorded constant whose literal value differs now, as
    ``<module>:<NAME>`` — or None when every one still hashes the same. A module
    gone, or a name no longer bound to a literal, counts as changed."""
    base = Path(script).resolve().parent
    for rel, names in sorted(constants.items()):
        resolved = _resolve_relative(str(rel), base)
        now = module_constant_hashes(resolved, names) if resolved is not None else None
        for name, recorded in sorted(names.items()):
            if now is None or now.get(name) != recorded:
                return f"{rel}:{name}"
    return None


# --- model-file detection -------------------------------------------------------


@functools.lru_cache(maxsize=4096)
def _model_function_names(path_str: str) -> frozenset[str]:
    """All declared model names, without importing or choosing one model.

    A multi-model file still forms a result boundary when the importer takes
    only decorated functions. Each model keeps that file's whole closure.
    """
    from cadgen.metadata import model_function_names

    return frozenset(model_function_names(Path(path_str)))


def is_model_file(path: Path) -> bool:
    return bool(_model_function_names(str(Path(path).resolve())))


def forget_model_files() -> None:
    _model_function_names.cache_clear()


# --- static reach: import resolution and the walk ------------------------------


def _search_roots(script: Path) -> list[Path]:
    """Where a model's imports resolve: the same roots the runner seeds onto
    ``sys.path`` — the script's own folder, then the caller's ``PYTHONPATH``
    (``cadgen._internal.import_roots``). Nothing inferred from directory names.
    One process, one ``sys.path``: every module the walk reaches resolves its
    absolute imports against the ROOT script's roots, exactly as the interpreter
    does; only relative imports are anchored on the importing file's package."""
    from cadgen._internal.import_roots import import_roots

    return [Path(root) for root in import_roots(script)]


def _resolve_module(name: str, roots: Iterable[Path]) -> Path | None:
    parts = name.split(".")
    for root in roots:
        candidate = root.joinpath(*parts)
        module_file = candidate.with_suffix(".py")
        if module_file.is_file():
            return module_file.resolve()
        package_init = candidate / "__init__.py"
        if package_init.is_file():
            return package_init.resolve()
    return None


@dataclass(frozen=True, slots=True)
class _Resolved:
    """A first-party import target: the files importing it executes (package
    ``__init__``s, then the module), the module's own file, and the directory
    its submodules live in when it is a package."""

    executed: tuple[Path, ...]
    module: Path | None
    package_dir: Path | None


def _resolve_dotted(parts: list[str], roots: Iterable[Path]) -> _Resolved | None:
    for root in roots:
        executed: list[Path] = []
        current = root
        ok = True
        for index, part in enumerate(parts):
            last = index == len(parts) - 1
            package_init = current / part / "__init__.py"
            module_file = current / (part + ".py")
            if package_init.is_file():
                executed.append(package_init.resolve())
                current = current / part
            elif last and module_file.is_file():
                executed.append(module_file.resolve())
                return _Resolved(tuple(executed), module_file.resolve(), None)
            elif (current / part).is_dir():
                current = current / part  # namespace package: nothing executes
            else:
                ok = False
                break
        if ok:
            module = executed[-1] if executed else None
            return _Resolved(tuple(executed), module, current)
    return None


def _resolve_sub(resolved: _Resolved, name: str) -> _Resolved | None:
    if resolved.package_dir is None:
        return None
    return _resolve_dotted([name], [resolved.package_dir])


def _parse_import_syntax(payload: bytes, filename: str) -> ModuleSyntax:
    """Only immutable syntax; no resolved paths, model names or imported values."""
    return analyze(payload, filename)


_IMPORT_SYNTAX_MAX_BYTES = 8 * 1024 * 1024
_IMPORT_SYNTAX_MAX_ENTRIES = 256


class _ImportSyntaxMemo:
    """One closure calculation's bounded byte-to-syntax recipes; never global."""

    def __init__(self) -> None:
        self.entries: OrderedDict[bytes, tuple[int, ModuleSyntax]] = OrderedDict()
        self.size = 0

    def get(self, payload: bytes, filename: str) -> ModuleSyntax:
        cached = self.entries.get(payload)
        if cached is not None:
            self.entries.move_to_end(payload)
            return cached[1]
        syntax = _parse_import_syntax(payload, filename)
        charge = 512 + sys.getsizeof(payload) + sys.getsizeof(syntax) + retained_syntax_size(syntax)
        if charge <= _IMPORT_SYNTAX_MAX_BYTES:
            self.entries[payload] = (charge, syntax)
            self.size += charge
            while self.size > _IMPORT_SYNTAX_MAX_BYTES or len(self.entries) > _IMPORT_SYNTAX_MAX_ENTRIES:
                self.size -= self.entries.popitem(last=False)[1][0]
        return syntax


def retained_syntax_size(syntax: ModuleSyntax) -> int:
    """A conservative byte charge for one module's analysis: every dump, name
    and alias it retains, each counted as its own object."""

    def size(value: object) -> int:
        total = sys.getsizeof(value)
        if isinstance(value, (tuple, frozenset)):
            total += sum(size(item) for item in value)
        elif isinstance(value, dict):
            total += sum(size(k) + size(v) for k, v in value.items())
        elif dataclasses.is_dataclass(value) and not isinstance(value, type):
            total += sum(size(getattr(value, f.name)) for f in dataclasses.fields(value))
        return total

    return (size(syntax.statements) + size(syntax.definitions) + size(syntax.preamble)
            + size(syntax.preamble_bound) + size(syntax.aliases) + size(syntax.whole_hash))


@dataclass(frozen=True)
class StaticImports:
    """What a script statically reaches, split by the boundary rule."""

    source_files: tuple[Path, ...]  # non-model files + model files taken as source
    child_models: tuple[Path, ...]  # model files taken only through their model function or literals
    constants: dict[str, dict[str, str]] = field(default_factory=dict)  # model path -> name -> hash
    # non-model source file -> the names reached in it (sorted), or None when the
    # whole file is tracked (dynamic, escaped, or reached only by execution).
    names: dict[Path, tuple[str, ...] | None] = field(default_factory=dict)


@dataclass
class _FileState:
    syntax: ModuleSyntax | None
    reached: set[int] = field(default_factory=set)
    names: set[str] = field(default_factory=set)
    whole: bool = False
    why: str | None = None  # why the file is tracked whole (diagnostics only)


class _Walk:
    """The static reach walk from one root script (``STORE.md`` §3).

    Every statement of the root is reached. A reached statement's imports
    execute their modules (preamble), its reads reach definitions in this
    module or, through an import alias, names in another module; a module alias
    used bare or written to makes its target whole. Model files are node
    boundaries classified by what the walk TAKES from them (result, value or
    source edge), exactly as before; only non-model files are sliced."""

    def __init__(self, root: Path, *, syntax: _ImportSyntaxMemo, sources: Mapping[str, bytes] | None,
                 descend: bool, model_boundaries: bool = True) -> None:
        self.root = root
        self.roots = _search_roots(root)
        self.syntax = syntax
        self.sources = sources or {}
        self.descend = descend
        self.model_boundaries = model_boundaries
        self.files: dict[Path, _FileState] = {}
        self.model_taken: dict[Path, set[str] | None] = {}
        self.model_source: set[Path] = set()
        self.constants: dict[str, dict[str, str]] = {}
        self.zones: set[Path] = set()

    # -- files -------------------------------------------------------------------

    def _load(self, path: Path) -> _FileState:
        state = self.files.get(path)
        if state is not None:
            return state
        if not self.descend and path != self.root:
            # The direct view only names its targets; it never reads them.
            state = self.files[path] = _FileState(syntax=None, whole=True)
            return state
        try:
            payload = self.sources.get(str(path))
            if payload is None:
                payload = path.read_bytes()
            syntax = self.syntax.get(payload, str(path))
        except (OSError, SyntaxError, ValueError):
            syntax = None
        state = self.files[path] = _FileState(syntax=syntax)
        return state

    def _in_zone(self, path: Path) -> bool:
        return any(zone in path.parents for zone in self.zones)

    def touch(self, path: Path) -> None:
        """A module that executes (its preamble), by import."""
        if path == self.root or not is_first_party_source_file(path):
            return
        if self.model_boundaries and _model_function_names(str(path)):
            self.model_taken.setdefault(path, set())
            self._reclassify(path)
            return
        if path in self.files:
            return
        state = self._load(path)
        if not self.descend:
            return
        if state.syntax is None:
            self.make_whole(path, "unparseable")
        elif state.syntax.dynamic is not None:
            self.make_whole(path, state.syntax.dynamic)
        elif self._in_zone(path):
            self.make_whole(path, "package escaped")
        else:
            for index in state.syntax.preamble:
                self.reach_statement(path, index)

    def make_whole(self, path: Path, why: str) -> None:
        state = self._load(path)
        if state.whole:
            return
        state.whole = True
        state.why = why
        if state.syntax is None or (not self.descend and path != self.root):
            return
        for index in range(len(state.syntax.statements)):
            self.reach_statement(path, index)
        if state.syntax.unbounded:
            # exec/eval/importlib/sys.modules: this module can reach any name of
            # any module it imports, so those are whole too.
            for statement in state.syntax.statements:
                for _name, alias in statement.aliases:
                    target = self._alias_source(path, alias)
                    if target is not None:
                        self.escape(target, f"imported by unbounded {path.name}")

    def zone(self, package_dir: Path) -> None:
        """A package alias escaped bare: every file of that package it reaches
        is reachable by name — the whole package is tracked whole."""
        if package_dir in self.zones:
            return
        self.zones.add(package_dir)
        for path in list(self.files):
            if package_dir in path.parents and path not in self.model_taken:
                self.make_whole(path, "package escaped")

    def reach_name(self, path: Path, name: str) -> None:
        state = self._load(path)
        if state.whole or name in state.names or state.syntax is None:
            return
        state.names.add(name)
        syntax = state.syntax
        indices = syntax.definitions.get(name, ())
        for index in indices:
            self.reach_statement(path, index)
        for alias in syntax.aliases.get(name, ()):
            self.alias_use(path, alias, ())  # a re-export: follow it
        if not indices and name not in syntax.aliases and name not in syntax.preamble_bound:
            self.make_whole(path, f"unknown name {name}")  # nothing binds it statically

    def reach_statement(self, path: Path, index: int) -> None:
        state = self._load(path)
        if index in state.reached or state.syntax is None:
            return
        state.reached.add(index)
        statement = state.syntax.statements[index]
        # One statement can contain several lexical scopes. Keep every
        # candidate binding: a later nested import must not hide an earlier
        # scope's dependency just because both use the same alias.
        local: dict[str, list[Alias]] = {}
        for name, alias in statement.aliases:
            local.setdefault(name, []).append(alias)
        for _name, alias in statement.aliases:
            self.import_edge(path, alias)
        for alias in statement.stars:
            self.import_edge(path, alias, whole=True)
        for name in statement.reads:
            self.name_use(path, state.syntax, local, name, ())
        for name, chain in statement.chains:
            self.name_use(path, state.syntax, local, name, chain)
        for name in statement.stores:
            aliases = local.get(name, []) + list(state.syntax.aliases.get(name, ()))
            for alias in aliases:
                target = self._alias_module(path, alias)
                if target is not None and target.module is not None:
                    self.escape(target.module, f"written to by {path.name}")
                    self.make_whole(path, f"writes to module {name}")  # a monkeypatch: this module is dynamic too
            if name in state.syntax.definitions:
                self.reach_name(path, name)

    # -- edges -------------------------------------------------------------------

    def _resolve(self, importer: Path, alias: Alias) -> _Resolved | None:
        if alias.level == 0:
            return _resolve_dotted(alias.module.split("."), self.roots) if alias.module else None
        base = importer.parent
        for _ in range(alias.level - 1):
            base = base.parent
        if alias.module:
            return _resolve_dotted(alias.module.split("."), [base])
        init = base / "__init__.py"
        return _Resolved((init.resolve(),) if init.is_file() else (), init.resolve() if init.is_file() else None, base)

    def _alias_module(self, importer: Path, alias: Alias) -> _Resolved | None:
        """The module an alias binds (a submodule for ``from pkg import sub``), or
        None when it binds a plain name or nothing first-party."""
        resolved = self._resolve(importer, alias)
        if resolved is None:
            return None
        if alias.attr is None:
            return resolved
        return _resolve_sub(resolved, alias.attr)

    def _alias_source(self, importer: Path, alias: Alias) -> Path | None:
        """The first-party module file an alias takes its binding from: the
        submodule for ``from pkg import sub``, else the module the name lives in."""
        resolved = self._resolve(importer, alias)
        if resolved is None:
            return None
        if alias.attr is not None:
            sub = _resolve_sub(resolved, alias.attr)
            if sub is not None:
                return sub.module
        return resolved.module

    def import_edge(self, importer: Path, alias: Alias, *, whole: bool = False) -> None:
        resolved = self._resolve(importer, alias)
        if resolved is None:
            return
        for executed in resolved.executed:
            self.touch(executed)
        target = resolved
        if alias.attr is not None:
            sub = _resolve_sub(resolved, alias.attr)
            if sub is None:
                if resolved.module is not None:
                    self.name_edge(resolved.module, alias.attr)
                return
            for executed in sub.executed:
                self.touch(executed)
            target = sub
        if whole and target.module is not None:
            self.escape(target.module, f"star-imported by {importer.name}")

    def name_use(self, path: Path, syntax: ModuleSyntax, local: Mapping[str, Iterable[Alias]], name: str, chain: tuple[str, ...]) -> None:
        for alias in local.get(name, ()):
            self.alias_use(path, alias, chain)
        if name in syntax.definitions:
            self.reach_name(path, name)
        for alias in syntax.aliases.get(name, ()):
            self.alias_use(path, alias, chain)

    def alias_use(self, importer: Path, alias: Alias, chain: tuple[str, ...]) -> None:
        resolved = self._resolve(importer, alias)
        if resolved is None:
            return
        target = resolved
        if alias.attr is not None:
            sub = _resolve_sub(resolved, alias.attr)
            if sub is None:
                if resolved.module is not None:
                    self.name_edge(resolved.module, alias.attr)
                return
            target = sub
        for element in chain:
            sub = _resolve_sub(target, element)
            if sub is None:
                if target.module is not None:
                    self.name_edge(target.module, element)
                return
            for executed in sub.executed:
                self.touch(executed)
            target = sub
        if target.module is not None:
            self.escape(target.module, f"module used bare in {importer.name}")

    def name_edge(self, target: Path, name: str) -> None:
        if target == self.root or not is_first_party_source_file(target):
            return
        if self.model_boundaries and _model_function_names(str(target)):
            taken = self.model_taken.setdefault(target, set())
            if taken is not None and name not in taken:
                taken.add(name)
                self._reclassify(target)
            return
        self.touch(target)
        if self.descend:
            self.reach_name(target, name)

    def escape(self, target: Path, why: str) -> None:
        """A module reachable by any name: tracked whole."""
        if target == self.root or not is_first_party_source_file(target):
            return
        if self.model_boundaries and _model_function_names(str(target)):
            if self.model_taken.get(target, set()) is not None:
                self.model_taken[target] = None
                self._reclassify(target)
            return
        self.touch(target)
        self.make_whole(target, why)
        if target.name == "__init__.py":
            self.zone(target.parent)

    def _reclassify(self, target: Path) -> None:
        """Constants by value, functions by file, every decorated model by
        result. A module import with no statically taken names is also a
        result edge; actual model calls supply the exact function pins."""
        if target in self.model_source:
            return
        taken = self.model_taken[target]
        if taken is None:
            source = True
        else:
            beyond = taken - _model_function_names(str(target))
            literals = (module_constant_hashes(target, beyond) or {}) if beyond else {}
            source = set(literals) != beyond
            if not source and literals:
                self.constants[str(target)] = dict(literals)
        if source:
            self.model_source.add(target)
            self.constants.pop(str(target), None)
            self.make_whole(target, "model file taken as source")

    # -- running -----------------------------------------------------------------

    def run(self) -> StaticImports:
        self.make_whole(self.root, "the script itself")
        sources: list[Path] = []
        names: dict[Path, tuple[str, ...] | None] = {}
        for path, file_state in self.files.items():
            if path == self.root:
                continue
            sources.append(path)
            if path in self.model_taken:
                continue  # a model file taken as source: tracked whole
            names[path] = None if (file_state.whole or not self.descend) else tuple(sorted(file_state.names))
        children = [path for path in self.model_taken if path not in self.model_source]
        return StaticImports(tuple(sorted(sources)), tuple(sorted(children)), dict(self.constants), names)


def static_imports(script: Path, *, _syntax: _ImportSyntaxMemo | None = None) -> StaticImports:
    """Direct first-party imports of ``script``, classified by the boundary rule."""
    script = Path(script).resolve()
    walk = _Walk(script, syntax=_syntax if _syntax is not None else _ImportSyntaxMemo(), sources=None, descend=False)
    return walk.run()


def static_closure(script: Path, *, _syntax: _ImportSyntaxMemo | None = None, _sources: Mapping[str, bytes] | None = None) -> StaticImports:
    """Transitive static reach stopping at model files. Model files reached
    through a result or value edge are children (not descended into); source-edge
    model files are descended into whole; every non-model file is descended into
    by the names reached in it, or whole when it is dynamic."""
    script = Path(script).resolve()
    walk = _Walk(script, syntax=_syntax if _syntax is not None else _ImportSyntaxMemo(), sources=_sources, descend=True)
    return walk.run()


# --- hash at execution ----------------------------------------------------------


_ACTIVE_HASHES: dict[str, str] | None = None
_ACTIVE_SOURCES: dict[str, bytes] | None = None
_HOOK_INSTALLED = False


def _exec_hash_hook(event: str, args: tuple) -> None:
    hashes = _ACTIVE_HASHES
    if hashes is None or event != "exec" or not args:
        return
    file_name = getattr(args[0], "co_filename", None)
    if not file_name:
        return
    try:
        path = Path(file_name).resolve()
    except (OSError, ValueError):
        return
    key = str(path)
    if key in hashes or not path.is_file() or not is_first_party_source_file(path):
        return
    try:
        payload = path.read_bytes()
    except OSError:
        return
    # One read: the hash AND the bytes the reach analysis will slice, taken at
    # the moment the module body executes.
    hashes[key] = _semantic_source_bytes(payload)
    sources = _ACTIVE_SOURCES
    if sources is not None:
        sources[key] = payload


class ExecutionHashes:
    """Context: hash every first-party file at the moment it executes, and keep
    the bytes so the closure's reach analysis describes the revision that ran."""

    def __init__(self) -> None:
        self.hashes: dict[str, str] = {}
        self.sources: dict[str, bytes] = {}
        self._previous: tuple[dict[str, str] | None, dict[str, bytes] | None] = (None, None)

    def __enter__(self) -> "ExecutionHashes":
        global _ACTIVE_HASHES, _ACTIVE_SOURCES, _HOOK_INSTALLED
        if not _HOOK_INSTALLED:
            sys.addaudithook(_exec_hash_hook)
            _HOOK_INSTALLED = True
        self._previous = (_ACTIVE_HASHES, _ACTIVE_SOURCES)
        _ACTIVE_HASHES = self.hashes
        _ACTIVE_SOURCES = self.sources
        return self

    def __exit__(self, *exc: object) -> None:
        global _ACTIVE_HASHES, _ACTIVE_SOURCES
        _ACTIVE_HASHES, _ACTIVE_SOURCES = self._previous
        if _ACTIVE_HASHES is not None:
            for key, value in self.hashes.items():
                _ACTIVE_HASHES.setdefault(key, value)
        if _ACTIVE_SOURCES is not None:
            for key, payload in self.sources.items():
                _ACTIVE_SOURCES.setdefault(key, payload)

    def note(self, path: Path) -> None:
        """Hash a file the build read outside the exec hook (the script's own
        bytes at load, a ``read_step`` input) — at the moment it was read."""
        try:
            resolved = Path(path).resolve()
        except (OSError, ValueError):
            return
        key = str(resolved)
        if key not in self.hashes and resolved.is_file():
            try:
                self.hashes[key] = _semantic_source_hash(resolved)
            except OSError:
                return


def note_declared_file_hash(path: Path) -> None:
    """Pin a declared input before the author reads it, while a build is active.

    Keep the first declaration even if the file changes or is declared again
    during the body. Publication and the next freshness gate must see that edit.
    """
    hashes = _ACTIVE_HASHES
    if hashes is None:
        return
    resolved = path.resolve()
    key = str(resolved)
    if key not in hashes:
        hashes[key] = _semantic_source_hash(resolved)


def note_consumed_file_hash(path: Path | str, digest: str, *, source: bytes | None = None) -> None:
    """Record the exact bytes a data reader consumed in the active build.

    A discovered input is normally hashed after the model body returns.  A
    path can be atomically replaced between a C++ reader opening it and that
    later hash, though, which would bind old geometry to new bytes.  Readers
    that already own the byte digest use this hook; ``ExecutionHashes.note``
    deliberately keeps the first value and therefore cannot overwrite it. A
    Python loader that owns the compiled buffer passes it as ``source`` so the
    reach analysis reads the revision that ran.
    """
    hashes = _ACTIVE_HASHES
    value = str(digest or "").strip()
    if hashes is None or not value:
        return
    try:
        resolved = Path(path).expanduser().resolve()
    except (OSError, ValueError):
        return
    key = str(resolved)
    if key not in hashes:
        hashes[key] = value
        if source is not None and _ACTIVE_SOURCES is not None:
            _ACTIVE_SOURCES[key] = source


# --- assembling the closure ------------------------------------------------------


def _relative(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _resolve_relative(rel: str, base: Path) -> Path | None:
    candidate = Path(rel)
    if not candidate.is_absolute():
        candidate = base / candidate
    try:
        candidate = candidate.resolve()
    except (OSError, RuntimeError):
        return None
    return candidate if candidate.is_file() else None


def closure_hash(pairs: Iterable[tuple[str, str]]) -> str:
    digest = hashlib.sha256()
    for rel, file_hash in sorted(pairs):
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def build_closure(
    script: Path,
    *,
    executed: dict[str, str],
    discovered_inputs: Iterable[Path] = (),
    children: Iterable[Path | str] = (),
    sources: Mapping[str, bytes] | None = None,
) -> Closure:
    """The closure a build records.

    ``executed`` maps resolved paths to the hashes taken at execution
    (:class:`ExecutionHashes`), ``sources`` to the bytes captured then. The
    file set is: the script, its static reach's source files, every executed
    first-party file, and discovered inputs — minus files that belong to a
    child model (its script and files reached only through it), which the
    boundary rule excludes. A non-model file the reach sliced is hashed by its
    reached names; every other file whole.
    """
    script = Path(script).resolve()
    base = script.parent
    syntax = _ImportSyntaxMemo()
    statics = static_closure(script, _syntax=syntax, _sources=sources)
    from cadgen.store.index import split_model_ref

    # Runtime calls carry exact script::function identities. Ownership of
    # executed source remains file-based, while the record keeps those exact
    # function pins independently in its children list.
    called_files = {split_model_ref(child)[0] for child in children}
    child_files = called_files | set(statics.child_models)
    # Files exclusively owned by children: their own static closures, minus
    # anything this script also reaches through a source edge. Ownership is
    # TRANSITIVE -- a grandchild's script and sources belong to the child that
    # calls it, and the whole subtree runs in this process when the body imports
    # its child. Stopping one level down put every grandchild model file in the
    # parent's closure, so an edit two levels away rebuilt the root even when
    # the pinned trees were unchanged.
    child_owned: set[Path] = set()
    ours: set[Path] = {script, *statics.source_files}
    pending = list(child_files)
    seen: set[Path] = set()
    while pending:
        child = pending.pop()
        if child in seen:
            continue
        seen.add(child)
        descendant = static_closure(child, _syntax=syntax)
        child_owned.update((child, *descendant.source_files))
        pending.extend(descendant.child_models)
        if child in called_files and child not in statics.child_models:
            # A dynamic module can supply a decorated call AND a helper/value
            # used directly by this body. The call alone does not prove that
            # its file is exclusively child-owned. Keep that source and its
            # source closure unless static imports prove a result/value edge.
            ours.update((child, *descendant.source_files))
    child_owned -= ours

    files: set[Path] = set(ours)
    for key in executed:
        path = Path(key)
        if path not in child_owned:
            files.add(path)
    for path in discovered_inputs:
        try:
            files.add(Path(path).resolve())
        except (OSError, ValueError):
            continue
    pairs: list[tuple[str, str]] = []
    names: dict[str, tuple[str, ...]] = {}
    captured = sources or {}
    for path in files:
        reached = statics.names.get(path)
        if reached is not None:
            # Sliced: hashed over the bytes that ran when the hook saw them, else
            # the file as it is now (a statically reached import that never fired).
            try:
                payload = captured.get(str(path))
                if payload is None:
                    payload = path.read_bytes()
                file_hash = slice_hash(syntax.get(payload, str(path)), reached)
            except (OSError, SyntaxError, ValueError):
                continue
            names[_relative(path, base)] = reached
        else:
            file_hash = executed.get(str(path))
            if file_hash is None:
                try:
                    file_hash = _semantic_source_hash(path)
                except OSError:
                    continue
        pairs.append((_relative(path, base), file_hash))
    constants = {_relative(Path(module), base): dict(names) for module, names in statics.constants.items()}
    return Closure(
        hash=closure_hash(pairs),
        files=tuple(sorted(rel for rel, _ in pairs)),
        constants=constants,
        shas={rel: file_hash for rel, file_hash in sorted(pairs)},
        names=dict(sorted(names.items())),
    )


# (path, names) -> (st_mtime_ns, st_size, hash): the slice twin of the whole-file
# semantic hash cache in source_hash, with the same settle rule (a fresh edit is
# re-sliced until its mtime is old enough that a same-size rewrite must move it).
_SLICE_HASH_CACHE: dict[tuple[str, tuple[str, ...]], tuple[int, int, str]] = {}


def sliced_source_hash(path: Path, names: Iterable[str]) -> str:
    """The slice hash of ``path`` as it is on disk now, by the recorded names —
    what the gate compares for a sliced closure file."""
    reached = tuple(names)
    key = (str(path), reached)
    try:
        stat = path.stat()
    except OSError:
        stat = None
    if stat is not None:
        cached = _SLICE_HASH_CACHE.get(key)
        if cached is not None and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
            return cached[2]
    payload = path.read_bytes()
    try:
        result = slice_hash(analyze(payload, str(path)), reached)
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        result = _semantic_source_bytes(payload)  # unparseable: the byte digest, whole
    if stat is not None and time.time_ns() - stat.st_mtime_ns > _SEMANTIC_HASH_SETTLE_NS:
        _SLICE_HASH_CACHE[key] = (stat.st_mtime_ns, stat.st_size, result)
    return result


def _hash_now(resolved: Path, rel: str, names: Mapping[str, Iterable[str]] | None) -> str:
    reached = (names or {}).get(rel)
    if reached is not None:
        return sliced_source_hash(resolved, reached)
    return _semantic_source_hash(resolved)


def changed_closure_files(script: Path, shas: Mapping[str, str], names: Mapping[str, Iterable[str]] | None = None) -> list[str]:
    """The recorded closure files whose content hash differs now (a missing file
    counts), in recorded order. Empty when nothing moved -- or when the record
    carries no per-file hashes, in which case the caller can only say "changed".
    A file in ``names`` is re-sliced by those names; any other is hashed whole."""
    base = Path(script).resolve().parent
    changed: list[str] = []
    for rel, recorded in shas.items():
        resolved = _resolve_relative(str(rel), base)
        try:
            now = _hash_now(resolved, str(rel), names) if resolved is not None else None
        except OSError:
            now = None
        if now != recorded:
            changed.append(str(rel))
    return changed


def current_closure_hash(script: Path, files: Iterable[str], names: Mapping[str, Iterable[str]] | None = None) -> str | None:
    """Re-hash a recorded file list as it is on disk now; None if a file is gone.
    A file in ``names`` is re-sliced by those names; any other is hashed whole."""
    base = Path(script).resolve().parent
    pairs: list[tuple[str, str]] = []
    for rel in files:
        resolved = _resolve_relative(str(rel), base)
        if resolved is None:
            return None
        try:
            pairs.append((str(rel), _hash_now(resolved, str(rel), names)))
        except OSError:
            return None
    return closure_hash(pairs) if pairs else None
