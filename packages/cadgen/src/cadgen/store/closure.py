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
in the closure of every model whose reach enters it, but what the record hashes
is the part of it the model can execute: the module's preamble (imports,
module-level calls and conditionals, decorated definitions — anything that runs
at import) plus every definition a reached name binds, closed within the module
and across modules (a reached function's loads, its decorators, defaults and
annotations reach what they name). Editing a definition the model never reaches
leaves it current; the analysis is ``cadgen.store.reach``, the walk is
:class:`_Walk`. The walk starts at the script and, after it, at every
first-party file the build executed that it did not reach and no child owns (a
plugin imported for its side effect, a ``sys.path`` insert): each such file is
walked whole, so what IT reaches in other files is sliced in too.

Anything the analysis cannot see falls back to whole files. Per module: a star
import, ``globals()``/``locals()``/``vars()`` (and every module it imports), a
module-level ``__getattr__``, an unresolved name, a module alias used bare
(``getattr(geo, name)``) or written to (``geo.X = 1``) — the target of an
escape is whole too, with every module bound in it, and a package alias
escaping makes the whole package whole. Per closure: when any walked file can
reach an arbitrary module's namespace by string or introspection (``exec``,
``importlib``, ``sys.modules``, frames, ``__globals__``, ``inspect`` …), every
file is hashed whole. The record keeps each sliced file's reached names
(``closure.names``) and whole-file hash (``closure.wholes``); the gate reuses
the recorded slice while the whole-file hash is unchanged and re-slices the
file on disk by those names only when it moved.

**Hash at execution.** The closure hash a record carries is over the bytes that
RAN: files are hashed when they are loaded/executed (the loader has the script's
bytes; the ``exec`` audit hook fires per first-party file), never after the body
returns. An edit landing mid-build is therefore never hashed into a record over
geometry the pre-edit source produced. The reach analysis runs over those same
captured bytes, so a slice and its hash describe one revision.

Hashes are the semantic (AST) digest for ``.py`` (``ast1:``), the slice digest
for a sliced file (``slice4:``), and the byte digest otherwise, via
``cadgen._internal.source_hash`` and ``cadgen.store.reach`` — a comment-only
edit is not a change.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import sys
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

from cadgen._internal.atomic_replace import is_transient_name
from cadgen._internal.source_hash import (
    _semantic_source_bytes,
    _semantic_source_hash,
    is_first_party_source_file,
)
from cadgen.store.reach import (
    IMPORT_SLICE_PREFIX,
    SLICE_PREFIX,
    Alias,
    ModuleSyntax,
    analyze,
    import_slice_hash,
    slice_hash,
)

# What analysing a file can raise besides a bug: invalid source, or source too
# deep for the parser/``ast.dump``. Such a file is hashed whole.
_UNANALYSABLE = (SyntaxError, ValueError, RecursionError, MemoryError)


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
    # relative path -> a SLICED file's whole-file semantic hash, of the same
    # bytes its slice was taken from: while the file still hashes to it, the
    # recorded slice stands without re-analysing the file.
    wholes: dict[str, str] = field(default_factory=dict)
    # listing entry (``<folder>/``) -> the names its digest leaves out (sorted):
    # the model's own outputs in that folder, never its inputs.
    own: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def as_json(self) -> dict:
        return {
            "hash": self.hash,
            "files": list(self.files),
            "shas": dict(self.shas),
            "names": {rel: list(names) for rel, names in self.names.items()},
            "wholes": dict(self.wholes),
            "own": {rel: list(names) for rel, names in self.own.items()},
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


# sha256(source bytes) -> {model function: format}. Keyed by content, never by
# path: a warm process outlives edits, and a file that gains or loses a model
# decorator must be read as what it is now.
_MODEL_FORMATS: OrderedDict[bytes, dict[str, str]] = OrderedDict()
_MODEL_FORMATS_MAX = 4096
_MODEL_FORMATS_LOCK = threading.Lock()


def _model_formats_of(payload: bytes, filename: str) -> dict[str, str]:
    key = hashlib.sha256(payload).digest()
    with _MODEL_FORMATS_LOCK:
        cached = _MODEL_FORMATS.get(key)
        if cached is not None:
            _MODEL_FORMATS.move_to_end(key)
            return cached
    from cadgen.metadata import model_function_formats

    formats = model_function_formats(payload, filename)
    with _MODEL_FORMATS_LOCK:
        _MODEL_FORMATS[key] = formats
        while len(_MODEL_FORMATS) > _MODEL_FORMATS_MAX:
            _MODEL_FORMATS.popitem(last=False)
    return formats


def _pinned(formats: Mapping[str, str]) -> frozenset[str]:
    """The models a call PINS. A drawing, a board or a harness is not one: called
    inside another build, a ``@dxf``, ``@pcb`` or ``@harness`` function runs its
    body inline, so taking it is taking source."""
    return frozenset(name for name, fmt in formats.items() if fmt not in ("dxf", "pcb", "harness"))


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


@dataclass(frozen=True, slots=True)
class _Resolved:
    """A first-party import target: the files importing it executes (package
    ``__init__``s, then the module), the module's own file, and the directory
    its submodules live in when it is a package. ``absent`` lists the files
    whose appearance would make the import resolve differently -- each was
    checked and missing -- and ``root`` is the index of the search root the
    target was found in."""

    executed: tuple[Path, ...]
    module: Path | None
    package_dir: Path | None
    absent: tuple[Path, ...] = ()
    root: int = 0


def _resolve_dotted(parts: list[str], roots: Iterable[Path]) -> _Resolved | None:
    absent: list[Path] = []
    for position, root in enumerate(roots):
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
                absent.append(package_init)  # a package beside it would win
                return _Resolved(tuple(executed), module_file.resolve(), None, tuple(absent), position)
            elif (current / part).is_dir():
                # A namespace portion: nothing executes, and a regular package
                # or module of the same name would win over it.
                absent.extend((package_init, module_file))
                current = current / part
            else:
                absent.extend((package_init, module_file))  # either would resolve in this root
                ok = False
                break
        if ok:
            module = executed[-1] if executed else None
            return _Resolved(tuple(executed), module, current, tuple(absent), position)
    return None


def _first_party_target(resolved: _Resolved) -> bool:
    """Whether an import resolved to model-side code (not the runtime or an
    installed package that happens to sit on a search root)."""
    if resolved.module is not None:
        return is_first_party_source_file(resolved.module)
    return resolved.package_dir is not None and is_first_party_source_file(resolved.package_dir / "__init__.py")


_SYNTAX_MAX_BYTES = 32 * 1024 * 1024
_SYNTAX_MAX_ENTRIES = 2048


class _SyntaxMemo:
    """Bounded byte-to-analysis memo: an LRU by accounted bytes and entries.

    A recipe is a pure function of the exact source bytes (for this
    interpreter), so one process-wide memo (``_SYNTAX``) serves the exec hook,
    every build's walk and every gate: each distinct file revision is analysed
    once. A recipe holds no resolved path, model classification or verdict."""

    def __init__(self) -> None:
        self.entries: OrderedDict[bytes, tuple[int, ModuleSyntax]] = OrderedDict()
        self.size = 0
        self.lock = threading.Lock()

    def get(self, payload: bytes, filename: str) -> ModuleSyntax:
        with self.lock:
            cached = self.entries.get(payload)
            if cached is not None:
                self.entries.move_to_end(payload)
                return cached[1]
        syntax = analyze(payload, filename)
        charge = 512 + sys.getsizeof(payload) + sys.getsizeof(syntax) + retained_syntax_size(syntax)
        with self.lock:
            if payload not in self.entries and charge <= _SYNTAX_MAX_BYTES:
                self.entries[payload] = (charge, syntax)
                self.size += charge
                while self.size > _SYNTAX_MAX_BYTES or len(self.entries) > _SYNTAX_MAX_ENTRIES:
                    self.size -= self.entries.popitem(last=False)[1][0]
        return syntax


_SYNTAX = _SyntaxMemo()


def retained_syntax_size(syntax: ModuleSyntax) -> int:
    """A conservative byte charge for one module's analysis: every digest, name
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
            + size(syntax.preamble_bound) + size(syntax.aliases) + size(syntax.guards)
            + size(syntax.whole_hash))


def execution_digest(payload: bytes, filename: str = "<module>") -> str:
    """The semantic hash of bytes that ran (``_semantic_source_bytes``' value),
    taken through the shared analysis memo, so the closure's reach analysis of
    the same bytes is a hit rather than a second parse."""
    try:
        return _SYNTAX.get(payload, filename).whole_hash
    except Exception:  # noqa: BLE001 - an audit hook must never fail the exec it observes
        return _semantic_source_bytes(payload)


@dataclass(frozen=True)
class StaticImports:
    """What a script statically reaches, split by the boundary rule."""

    source_files: tuple[Path, ...]  # non-model files + model files taken as source
    child_models: tuple[Path, ...]  # model files taken only through their model function or literals
    constants: dict[str, dict[str, str]] = field(default_factory=dict)  # model path -> name -> hash
    # non-model source file -> the names reached in it (sorted), or None when the
    # whole file is tracked (dynamic, escaped, or walked whole).
    names: dict[Path, tuple[str, ...] | None] = field(default_factory=dict)


@dataclass
class _FileState:
    syntax: ModuleSyntax | None
    reached: set[int] = field(default_factory=set)
    headers: set[int] = field(default_factory=set)  # model definitions reached for their header only
    names: set[str] = field(default_factory=set)
    whole: bool = False


# Module attributes the import system sets: reading one reaches no definition.
_IMPORT_SYSTEM_ATTRS = frozenset({
    "__name__", "__file__", "__doc__", "__package__", "__path__", "__cached__", "__annotations__",
})


class _Walk:
    """The static reach walk from one root script (``STORE.md`` §3).

    Every statement of the root is reached. A reached statement's imports
    execute their modules (preamble), its loads reach definitions in this
    module or, through an import alias, names in another module; a module alias
    used bare or written to makes its target whole. Model files are node
    boundaries classified by what the walk TAKES from them (result, value or
    source edge); only non-model files are sliced. :meth:`walk_root` adds
    another root walked whole — a file the build executed that static reach
    never saw. Statements are processed from a worklist, so reach depth never
    becomes interpreter recursion."""

    def __init__(self, root: Path, *, syntax: _SyntaxMemo, sources: Mapping[str, bytes] | None,
                 model_boundaries: bool = True, import_time: bool = False) -> None:
        self.root = root
        self.roots = _search_roots(root)
        self.syntax = syntax
        self.sources = sources or {}
        self.model_boundaries = model_boundaries
        # Only what importing runs: a model file is followed like a helper, but
        # the bodies of the model functions it declares are never reached.
        self.import_time = import_time
        self.files: dict[Path, _FileState] = {}
        self.model_taken: dict[Path, set[str] | None] = {}
        self.model_source: set[Path] = set()
        self.constants: dict[str, dict[str, str]] = {}
        self.zones: set[Path] = set()
        self.escaped: set[Path] = set()
        self.queue: list[tuple[Path, int, bool]] = []   # (file, statement, header only) not yet followed
        self.escapes: list[Path] = []             # escaped modules whose bound modules escape next
        # Resolution facts the walk relied on: files whose appearance would make
        # a first-party import resolve differently, and the last search root one
        # resolved in (an earlier root gaining a module could shadow it).
        self.absent: set[Path] = set()
        self.root_used = -1
        self._formats: dict[Path, dict[str, str]] = {}
        # Files whose import the walk has run. Not the same as loaded: a package
        # __init__ can be read for a submodule's name before its own import
        # statement is followed, and its preamble must still be walked then.
        self.touched: set[Path] = set()

    # -- models ------------------------------------------------------------------

    def _formats_of(self, path: Path) -> dict[str, str]:
        """The models a file declares, read from the bytes that ran when the
        exec hook captured them, else from the file."""
        formats = self._formats.get(path)
        if formats is None:
            payload = self.sources.get(str(path))
            if payload is None:
                try:
                    payload = path.read_bytes()
                except OSError:
                    payload = b""
            formats = self._formats[path] = _model_formats_of(payload, str(path)) if payload else {}
        return formats

    def _pinned_models(self, path: Path) -> frozenset[str]:
        return _pinned(self._formats_of(path))

    def _declared_models(self, path: Path) -> frozenset[str]:
        return frozenset(self._formats_of(path))

    # -- resolution --------------------------------------------------------------

    def _dotted(self, parts: list[str], roots: list[Path]) -> _Resolved | None:
        resolved = _resolve_dotted(parts, roots)
        if resolved is not None and _first_party_target(resolved):
            self.absent.update(resolved.absent)
            if roots is self.roots:
                self.root_used = max(self.root_used, resolved.root)
        return resolved

    def _sub(self, resolved: _Resolved, name: str) -> _Resolved | None:
        if resolved.package_dir is None:
            return None
        return self._dotted([name], [resolved.package_dir])

    # -- files -------------------------------------------------------------------

    def _load(self, path: Path) -> _FileState:
        state = self.files.get(path)
        if state is not None:
            return state
        try:
            payload = self.sources.get(str(path))
            if payload is None:
                payload = path.read_bytes()
            syntax = self.syntax.get(payload, str(path))
        except (OSError, *_UNANALYSABLE):
            syntax = None
        state = self.files[path] = _FileState(syntax=syntax)
        return state

    def _in_zone(self, path: Path) -> bool:
        return any(zone in path.parents for zone in self.zones)

    def touch(self, path: Path) -> None:
        """A module that executes (its preamble), by import."""
        if path == self.root or not is_first_party_source_file(path):
            return
        if self.model_boundaries and self._pinned_models(path):
            self.model_taken.setdefault(path, set())
            self._reclassify(path)
            return
        if path in self.touched:
            return
        self.touched.add(path)
        state = self._load(path)
        if state.syntax is None:
            self.make_whole(path)
        elif state.syntax.dynamic is not None:
            self.make_whole(path)
        elif self._in_zone(path):
            self.make_whole(path)
        else:
            models = self._declared_models(path) if self.import_time else frozenset()
            for index in state.syntax.preamble:
                if models and models.intersection(state.syntax.statements[index].binds):
                    # Importing runs a model definition's header -- its decorators
                    # and defaults -- but never its body.
                    self.reach_header(path, index)
                else:
                    self.reach_statement(path, index)

    def make_whole(self, path: Path) -> None:
        state = self._load(path)
        if state.whole:
            return
        state.whole = True
        if state.syntax is None:
            return
        # A main guard runs only when its file is the script itself.
        guards = frozenset() if path == self.root else state.syntax.guards
        for statement in state.syntax.statements:
            if statement.index not in guards:
                self.reach_statement(path, statement.index)
        if state.syntax.unbounded:
            # globals()/vars()/exec…: this module can reach any name of any
            # module it imports, so those are whole too.
            for statement in state.syntax.statements:
                if statement.index in guards:
                    continue
                for _name, alias in statement.aliases:
                    target = self._alias_source(path, alias)
                    if target is not None:
                        self.escape(target)

    def zone(self, package_dir: Path) -> None:
        """A package alias escaped bare: every file of that package it reaches
        is reachable by name — the whole package is tracked whole."""
        if package_dir in self.zones:
            return
        self.zones.add(package_dir)
        for path in list(self.files):
            if package_dir in path.parents and path not in self.model_taken:
                self.make_whole(path)

    def reach_name(self, path: Path, name: str) -> None:
        state = self._load(path)
        syntax = state.syntax
        if syntax is None:
            return
        if self.import_time and name in self._declared_models(path):
            return  # a model function's body runs when it is called, never on import
        bound = name in syntax.definitions or name in syntax.aliases or name in syntax.preamble_bound
        if not bound and name.startswith("__") and name.endswith("__"):
            if name not in _IMPORT_SYSTEM_ATTRS:
                # ``geo.__dict__`` and the like: every name of the module.
                self.escape(path)
            return
        if state.whole or name in state.names:
            return
        state.names.add(name)
        indices = syntax.definitions.get(name, ())
        for index in indices:
            self.reach_statement(path, index)
        for alias in syntax.aliases.get(name, ()):
            self.alias_use(path, alias, ())  # a re-export: follow it
        if not bound:
            self.make_whole(path)  # nothing binds it statically

    def reach_statement(self, path: Path, index: int) -> None:
        state = self._load(path)
        if index in state.reached or state.syntax is None:
            return
        state.reached.add(index)
        self.queue.append((path, index, False))

    def reach_header(self, path: Path, index: int) -> None:
        """What executing a model definition runs without calling it."""
        state = self._load(path)
        if index in state.reached or index in state.headers or state.syntax is None:
            return
        if state.syntax.statements[index].header is None:
            self.reach_statement(path, index)
            return
        state.headers.add(index)
        self.queue.append((path, index, True))

    def _follow(self, path: Path, index: int, header: bool) -> None:
        syntax = self.files[path].syntax
        statement = syntax.statements[index]
        part = statement.header if header else statement
        # One statement can contain several lexical scopes. Keep every
        # candidate binding: a later nested import must not hide an earlier
        # scope's dependency just because both use the same alias.
        local: dict[str, list[Alias]] = {}
        for name, alias in part.aliases:
            local.setdefault(name, []).append(alias)
        for _name, alias in part.aliases:
            self.import_edge(path, alias)
        for alias in part.stars:
            self.import_edge(path, alias, whole=True)
        for name in part.reads:
            self.name_use(path, syntax, local, name, ())
        for group in (part.chains, part.loads):
            for name, chain in group:
                self.name_use(path, syntax, local, name, chain)
        for name in part.stores:
            aliases = local.get(name, []) + list(syntax.aliases.get(name, ()))
            for alias in aliases:
                target = self._alias_module(path, alias)
                if target is not None and target.module is not None:
                    self.escape(target.module)
                    self.make_whole(path)  # a monkeypatch: this module is dynamic too
            if name in syntax.definitions:
                self.reach_name(path, name)

    def _drain(self) -> None:
        while self.queue or self.escapes:
            if self.queue:
                self._follow(*self.queue.pop())
                continue
            # A module whose namespace escaped exposes every module bound in it.
            target = self.escapes.pop()
            syntax = self.files[target].syntax if target in self.files else None
            for aliases in (syntax.aliases.values() if syntax is not None else ()):
                for alias in aliases:
                    bound = self._alias_module(target, alias)
                    if bound is not None and bound.module is not None:
                        self.escape(bound.module)

    # -- edges -------------------------------------------------------------------

    def _resolve(self, importer: Path, alias: Alias) -> _Resolved | None:
        if alias.level == 0:
            return self._dotted(alias.module.split("."), self.roots) if alias.module else None
        base = importer.parent
        for _ in range(alias.level - 1):
            base = base.parent
        if alias.module:
            return self._dotted(alias.module.split("."), [base])
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
        return self._sub(resolved, alias.attr)

    def _alias_source(self, importer: Path, alias: Alias) -> Path | None:
        """The first-party module file an alias takes its binding from: the
        submodule for ``from pkg import sub``, else the module the name lives in."""
        resolved = self._resolve(importer, alias)
        if resolved is None:
            return None
        if alias.attr is not None:
            sub = self._sub(resolved, alias.attr)
            if sub is not None:
                return sub.module
        return resolved.module

    def _shadowing(self, package: _Resolved, name: str) -> None:
        """``from pkg import name`` or ``pkg.name`` where ``name`` is a submodule:
        a binding of ``name`` in ``pkg/__init__.py`` wins unless the submodule
        was imported first, so that binding is reached too -- and when there is
        none, the name is still part of the slice, marked unbound, so adding one
        later is an edit the gate sees."""
        init = package.module
        if init is None or package.package_dir is None or init.parent != package.package_dir.resolve():
            return
        if init == self.root or not is_first_party_source_file(init):
            return
        state = self._load(init)
        syntax = state.syntax
        if syntax is None:
            return
        if name in syntax.definitions or name in syntax.preamble_bound or name in syntax.aliases:
            self.name_edge(init, name)
        elif not state.whole:
            state.names.add(name)

    def _beyond_call(self, module: Path, name: str) -> None:
        """``arm.__wrapped__``: an attribute of a pinned model function can reach
        what the pin stands for -- its body -- so the file is taken as source."""
        if self.model_boundaries and name in self._pinned_models(module):
            self.escape(module)

    def import_edge(self, importer: Path, alias: Alias, *, whole: bool = False) -> None:
        if alias.executes:
            # ``import a.b.c`` binds ``a`` but executes every package on the way.
            executes = self._dotted(alias.executes.split("."), self.roots)
            for executed in (executes.executed if executes is not None else ()):
                self.touch(executed)
        resolved = self._resolve(importer, alias)
        if resolved is None:
            return
        for executed in resolved.executed:
            self.touch(executed)
        target = resolved
        if alias.attr is not None:
            sub = self._sub(resolved, alias.attr)
            if sub is None:
                # A from-import reaches the name it binds -- the importer's body
                # may call it. Importing alone runs none of it: an import-time walk
                # follows only what import-time code reads.
                if resolved.module is not None and not self.import_time:
                    self.name_edge(resolved.module, alias.attr)
                return
            self._shadowing(resolved, alias.attr)
            for executed in sub.executed:
                self.touch(executed)
            target = sub
        if whole and target.module is not None:
            self.escape(target.module)

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
            sub = self._sub(resolved, alias.attr)
            if sub is None:
                if resolved.module is not None:
                    self.name_edge(resolved.module, alias.attr)
                    if chain:
                        self._beyond_call(resolved.module, alias.attr)
                return
            self._shadowing(resolved, alias.attr)
            target = sub
        for position, element in enumerate(chain):
            sub = self._sub(target, element)
            if sub is None:
                if target.module is not None:
                    self.name_edge(target.module, element)
                    if position + 1 < len(chain):
                        self._beyond_call(target.module, element)
                return
            self._shadowing(target, element)
            for executed in sub.executed:
                self.touch(executed)
            target = sub
        if target.module is not None:
            self.escape(target.module)

    def name_edge(self, target: Path, name: str) -> None:
        if target == self.root or not is_first_party_source_file(target):
            return
        if self.model_boundaries and self._pinned_models(target):
            taken = self.model_taken.setdefault(target, set())
            if taken is not None and name not in taken:
                taken.add(name)
                self._reclassify(target)
            return
        self.touch(target)
        self.reach_name(target, name)

    def escape(self, target: Path) -> None:
        """A module reachable by any name: tracked whole, and so is every
        module bound in it (it is reachable by any name too)."""
        if target == self.root or not is_first_party_source_file(target):
            return
        if self.model_boundaries and self._pinned_models(target):
            if self.model_taken.get(target, set()) is not None:
                self.model_taken[target] = None
                self._reclassify(target)
            if target in self.model_source and target not in self.escaped:
                self.escaped.add(target)
                self.escapes.append(target)
            return
        if target in self.escaped:
            return
        self.escaped.add(target)
        self.touch(target)
        self.make_whole(target)
        if target.name == "__init__.py":
            self.zone(target.parent)
        self.escapes.append(target)

    def _reclassify(self, target: Path) -> None:
        """Constants by value, functions by reach, every decorated model by
        result. A module import with no statically taken names is also a
        result edge; actual model calls supply the exact function pins."""
        if target in self.model_source:
            return
        taken = self.model_taken[target]
        if taken is None:
            source = True
        else:
            beyond = taken - self._pinned_models(target)
            literals = (module_constant_hashes(target, beyond) or {}) if beyond else {}
            source = set(literals) != beyond
            if not source and literals:
                self.constants[str(target)] = dict(literals)
        if source:
            self.model_source.add(target)
            self.constants.pop(str(target), None)
            self.make_whole(target)  # a model file taken as source

    # -- running -----------------------------------------------------------------

    def run(self) -> StaticImports:
        self.make_whole(self.root)  # the script runs top to bottom
        self._drain()
        return self.result()

    def walk_root(self, path: Path) -> None:
        """Another root, walked whole like the script: a first-party file the
        build executed that this walk never reached."""
        if path == self.root or path in self.touched or path in self.model_taken:
            return
        self.make_whole(path)
        self._drain()

    def result(self) -> StaticImports:
        sources: list[Path] = []
        names: dict[Path, tuple[str, ...] | None] = {}
        for path, file_state in self.files.items():
            if path == self.root:
                continue
            sources.append(path)
            if path in self.model_taken:
                continue  # a model file taken as source: tracked whole
            names[path] = None if file_state.whole else tuple(sorted(file_state.names))
        children = [path for path in self.model_taken if path not in self.model_source]
        return StaticImports(tuple(sorted(sources)), tuple(sorted(children)), dict(self.constants), names)

    def reflective(self) -> bool:
        """Whether some walked file can reach any module's namespace."""
        return any(state.syntax is not None and state.syntax.reflective is not None for state in self.files.values())


def static_closure(script: Path) -> StaticImports:
    """Transitive static reach stopping at model files. Model files reached
    through a result or value edge are children (not descended into); source-edge
    model files are descended into whole; every non-model file is descended into
    by the names reached in it, or whole when it is dynamic."""
    script = Path(script).resolve()
    return _Walk(script, syntax=_SYNTAX, sources=None).run()


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
    # the moment the module body executes. Analysed once, here: the walk over
    # the same bytes is a memo hit.
    hashes[key] = execution_digest(payload, key)
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


def note_compiled_source(path: Path | str, source: bytes) -> None:
    """Record the exact source a loader compiled in the active build: its hash,
    and the bytes, so the reach analysis reads the revision that ran. The first
    value stands; a file edited mid-build is caught by the gate.
    """
    hashes = _ACTIVE_HASHES
    if hashes is None:
        return
    try:
        key = str(Path(path).expanduser().resolve())
    except (OSError, ValueError):
        return
    if key not in hashes:
        hashes[key] = execution_digest(source, key)
        if _ACTIVE_SOURCES is not None:
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


def _child_ownership(script: Path, statics: StaticImports, called_files: set[Path]) -> tuple[set[Path], set[Path]]:
    """(files this script owns, files exclusively owned by its children).

    Children's own static closures, minus anything this script also reaches
    through a source edge. Ownership is TRANSITIVE -- a grandchild's script and
    sources belong to the child that calls it, and the whole subtree runs in
    this process when the body imports its child. Stopping one level down put
    every grandchild model file in the parent's closure, so an edit two levels
    away rebuilt the root even when the pinned trees were unchanged.
    """
    child_owned: set[Path] = set()
    ours: set[Path] = {script, *statics.source_files}
    pending = list(called_files | set(statics.child_models))
    seen: set[Path] = set()
    while pending:
        child = pending.pop()
        if child in seen:
            continue
        seen.add(child)
        descendant = static_closure(child)
        child_owned.update((child, *descendant.source_files))
        pending.extend(descendant.child_models)
        if child in called_files and child not in statics.child_models:
            # A dynamic module can supply a decorated call AND a helper/value
            # used directly by this body. The call alone does not prove that
            # its file is exclusively child-owned. Keep that source and its
            # source closure unless static imports prove a result/value edge.
            ours.update((child, *descendant.source_files))
    return ours, child_owned - ours


def build_closure(
    script: Path,
    *,
    executed: dict[str, str],
    inputs: Mapping[Path, str] | None = None,
    listings: Iterable[Path] = (),
    outputs: Iterable[Path] = (),
    children: Iterable[Path | str] = (),
    sources: Mapping[str, bytes] | None = None,
) -> Closure:
    """The closure a build records.

    ``executed`` maps resolved paths to the hashes taken at execution
    (:class:`ExecutionHashes`), ``sources`` to the bytes captured then. The
    file set is: the script, its reach's source files, every executed
    first-party file, and ``inputs`` -- the data files the build read, each with
    the hash it was read with -- minus files that belong to a child model (its
    script and files reached only through it), which the boundary rule
    excludes. ``listings`` are the folders its code listed, each hashed by its
    entry names less the model's own ``outputs`` there (``Closure.own``). The
    reach walk starts at the script, then at every
    executed first-party ``.py`` file it did not reach and no child owns, each
    walked whole; what the children's import-time code reaches in shared files
    is reached too. A non-model file the walk sliced is hashed by its reached
    names — unless a walked file is reflective, and then every file is whole.
    """
    script = Path(script).resolve()
    base = script.parent
    captured = sources or {}
    walk = _Walk(script, syntax=_SYNTAX, sources=captured)
    statics = walk.run()
    from cadgen.store.index import split_model_ref

    # Runtime calls carry exact script::function identities. Ownership of
    # executed source remains file-based, while the record keeps those exact
    # function pins independently in its children list.
    called_files = {split_model_ref(child)[0] for child in children}
    ours, child_owned = _child_ownership(script, statics, called_files)
    # What executed but static reach never saw — a plugin imported for its side
    # effect, a module found through a sys.path insert — reaches names in the
    # files it calls into: walk it as a root, from the bytes that ran.
    runtime = sorted(path for path in map(Path, executed)
                     if path.suffix == ".py" and path not in child_owned and is_first_party_source_file(path))
    for path in runtime:
        walk.walk_root(path)
    statics = walk.result()
    ours.update(statics.source_files)
    child_owned -= ours
    # A child's files stay out of this closure (models by result), but
    # importing a child runs its import-time code in this process: what that
    # reaches in a file this closure shares with it is this model's too.
    imports = _Walk(script, syntax=_SYNTAX, sources=captured, model_boundaries=False, import_time=True)
    for child in statics.child_models:
        imports.touch(child)
    imports._drain()

    files: set[Path] = set(ours)
    for key in executed:
        path = Path(key)
        if path not in child_owned:
            files.add(path)
    # Everything else that ran in this process ran because a child was
    # imported: a child file's module body, the helpers only it imports, its
    # model definitions' headers. That is this model's input too -- it can
    # change what this body computes -- but a model's BODY never is: it runs in
    # the child's own build, or not at all. Such a file is hashed by what its
    # import runs.
    in_process = {path for path in imports.files if path != script and is_first_party_source_file(path)}
    in_process.update(path for path in map(Path, executed) if path.suffix == ".py" and is_first_party_source_file(path))
    import_time = in_process - files
    files |= import_time
    # What the build read, hashed as it read it (cadgen._internal.filetrace), and
    # the folders its code listed.
    read = {Path(path).resolve(): digest for path, digest in (inputs or {}).items()}
    files |= set(read)
    listed = {Path(path).resolve() for path in listings}
    # Something walked can reach any module's namespace by string or by
    # introspection: no slice is safe, every file is hashed whole.
    reflective = walk.reflective() or imports.reflective()
    pairs: list[tuple[str, str]] = []
    names: dict[str, tuple[str, ...]] = {}
    wholes: dict[str, str] = {}
    for path in files:
        rel = _relative(path, base)
        if path in import_time:
            ran = imports.files.get(path)
            if not reflective and ran is not None and not ran.whole and ran.syntax is not None:
                reached = tuple(sorted(ran.names))
                models = imports._declared_models(path)
                pairs.append((rel, import_slice_hash(ran.syntax, reached, models) if models
                               else slice_hash(ran.syntax, reached)))
                names[rel] = reached
                wholes[rel] = ran.syntax.whole_hash
                continue
        state = walk.files.get(path)
        syntax = state.syntax if state is not None else None
        reached = None if reflective else statics.names.get(path)
        shared = imports.files.get(path)
        if reached is not None and shared is not None:
            reached = None if shared.whole else tuple(sorted(set(reached) | shared.names))
        if reached is not None and syntax is not None:
            # Sliced, over the very bytes the walk analysed: those the exec
            # hook captured when the module ran, else the file as it was read.
            pairs.append((rel, slice_hash(syntax, reached)))
            names[rel] = reached
            wholes[rel] = syntax.whole_hash
            continue
        file_hash = read.get(path) or executed.get(str(path))
        if file_hash is None and syntax is not None:
            file_hash = syntax.whole_hash
        if file_hash is None:
            try:
                file_hash = _semantic_source_hash(path)
            except OSError:
                continue
        pairs.append((rel, file_hash))
    # What the imports resolved to depends on files that do NOT exist too: each
    # stays in the closure, recorded absent, so one appearing -- an __init__.py
    # in a namespace package, a package beside a module, a module in an earlier
    # root -- is a change like any edit. And past the script's own folder, on the
    # search roots themselves.
    for rel in sorted({ABSENT_MARK + _relative(path, base) for path in walk.absent | imports.absent}):
        pairs.append((rel, ABSENT))
    # A folder the model's code listed (a glob of profiles, one part each): a file
    # added or removed there changes what the body saw. The model's own outputs
    # there are left out, as they are of the files it read: a first build lists
    # the folder before they exist and publishes them after, and a rebuild lists
    # the previous run's. A sibling model's outputs stay in -- a body may list the
    # folder to find them.
    written = [Path(path).resolve() for path in outputs]
    own: dict[str, tuple[str, ...]] = {}
    for directory in sorted(listed):
        rel = _relative(directory, base).rstrip("/") + "/"
        left_out = _own_entries(directory, written)
        if left_out:
            own[rel] = left_out
        pairs.append((rel, _listing_digest(directory, left_out)))
    root_used = max(walk.root_used, imports.root_used)
    if root_used > 0:
        count = root_used + 1
        pairs.append((ROOTS_KEY.format(count=count), _roots_digest(walk.roots[:count], base)))
    constants = {_relative(Path(module), base): dict(values) for module, values in statics.constants.items()}
    return Closure(
        hash=closure_hash(pairs),
        files=tuple(sorted(rel for rel, _ in pairs)),
        constants=constants,
        shas={rel: file_hash for rel, file_hash in sorted(pairs)},
        names=dict(sorted(names.items())),
        wholes=dict(sorted(wholes.items())),
        own=own,
    )


def sliced_source_hash(path: Path, names: Iterable[str]) -> str:
    """The slice hash of ``path`` as it is on disk now, by the recorded names —
    what the gate compares for a sliced closure file that changed."""
    payload = path.read_bytes()
    try:
        return slice_hash(_SYNTAX.get(payload, str(path)), tuple(names))
    except _UNANALYSABLE:
        return _semantic_source_bytes(payload)  # unanalysable: the whole-file hash


def import_sliced_source_hash(path: Path, names: Iterable[str]) -> str:
    """The import-time slice of a child model file as it is on disk now: its
    models, and so which definitions count by their header, are read from the
    same bytes."""
    payload = path.read_bytes()
    try:
        syntax = _SYNTAX.get(payload, str(path))
    except _UNANALYSABLE:
        return _semantic_source_bytes(payload)
    models = frozenset(_model_formats_of(payload, str(path)))
    return import_slice_hash(syntax, tuple(names), models) if models else slice_hash(syntax, tuple(names))


# A closure entry for a file the imports relied on NOT existing is its path
# behind ABSENT_MARK, hashed ABSENT while it still does not exist; ROOTS_KEY is
# the entry for the search roots past the script's own folder that an import
# resolved in. Both describe themselves, so any re-hash reads them without the
# recorded hashes.
ABSENT_MARK = "!"
ABSENT = "absent"
ROOTS_KEY = "<import roots {count}>"
_ROOTS_PREFIX = "<import roots "


def _roots_count(rel: str) -> int | None:
    if not (rel.startswith(_ROOTS_PREFIX) and rel.endswith(">")):
        return None
    try:
        return int(rel[len(_ROOTS_PREFIX):-1])
    except ValueError:
        return None


def source_files(files: Iterable[str]) -> list[str]:
    """The files a closure names that exist -- without its absent, roots and listing entries."""
    return [rel for rel in files
            if _roots_count(rel) is None and not rel.startswith(ABSENT_MARK) and not rel.endswith("/")]


def _listing_digest(directory: Path, own: Iterable[str] = ()) -> str:
    """A folder the model's code listed, as what it saw: its sorted entry names,
    less ``own``, the entries that hold the model's own outputs, and less the
    entries cadgen keeps there only while it writes (``is_transient_name``): a
    sibling's build stages its STEP beside its output, so a listing taken during
    a parallel build would otherwise go stale once that build ends."""
    own = frozenset(own)
    try:
        names = sorted(name for name in os.listdir(directory)
                       if name not in own and not is_transient_name(name))
    except OSError:
        return "missing"
    return "listing:" + hashlib.sha256("\0".join(names).encode("utf-8")).hexdigest()


def _own_entries(directory: Path, outputs: Iterable[Path]) -> tuple[str, ...]:
    """The entries of a listed folder that hold the model's own outputs: each
    output written there, and each folder there one was written into."""
    entries: set[str] = set()
    for output in outputs:
        try:
            inside = output.relative_to(directory).parts
        except ValueError:
            continue
        if inside:
            entries.add(inside[0])
    return tuple(sorted(entries))


def _roots_digest(roots: Iterable[Path | str], base: Path) -> str:
    """``roots:<sha>`` over the search roots, each relative to the model's
    folder where it can be."""
    listed = [_relative(Path(root), base) for root in roots]
    return "roots:" + hashlib.sha256("\0".join(listed).encode("utf-8")).hexdigest()


def _roots_now(base: Path, count: int) -> str:
    """The digest over the first ``count`` search roots a build would use now:
    a root appended after them cannot shadow anything they resolved."""
    return _roots_digest(_search_roots(base / "_")[:count], base)


def file_hash_now(path: Path, rel: str, names: Mapping[str, Iterable[str]] | None,
                  shas: Mapping[str, str] | None = None, wholes: Mapping[str, str] | None = None) -> str:
    """One recorded closure file hashed as the gate compares it now: whole, or
    by its recorded names when sliced. A sliced file whose whole-file hash is
    still the recorded one keeps its recorded slice without re-analysis."""
    recorded = (shas or {}).get(rel)
    reached = (names or {}).get(rel)
    if reached is None:
        return _semantic_source_hash(path)
    whole = (wholes or {}).get(rel)
    if (recorded and whole and recorded.startswith((SLICE_PREFIX, IMPORT_SLICE_PREFIX))
            and _semantic_source_hash(path) == whole):
        return recorded
    if recorded and recorded.startswith(IMPORT_SLICE_PREFIX):
        return import_sliced_source_hash(path, reached)
    return sliced_source_hash(path, reached)


def entry_hash_now(base: Path, rel: str, names: Mapping[str, Iterable[str]] | None,
                   shas: Mapping[str, str] | None = None, wholes: Mapping[str, str] | None = None,
                   own: Mapping[str, Iterable[str]] | None = None) -> str | None:
    """One recorded closure entry as it hashes now, relative to the model's
    folder ``base``: a file (``file_hash_now``), or None when it is gone; a file
    recorded absent, ABSENT while it still is; the search roots, their digest; a
    listed folder, its entry names less the recorded ``own`` ones."""
    if rel.startswith(ABSENT_MARK):
        candidate = Path(rel[len(ABSENT_MARK):])
        return ABSENT if not (candidate if candidate.is_absolute() else base / candidate).exists() else "present"
    if rel.endswith("/"):
        candidate = Path(rel)
        return _listing_digest(candidate if candidate.is_absolute() else base / candidate, (own or {}).get(rel, ()))
    count = _roots_count(rel)
    if count is not None:
        return _roots_now(base, count)
    resolved = _resolve_relative(rel, base)
    if resolved is None:
        return None
    return file_hash_now(resolved, rel, names, shas, wholes)


def changed_closure_files(script: Path, shas: Mapping[str, str], names: Mapping[str, Iterable[str]] | None = None,
                          wholes: Mapping[str, str] | None = None,
                          own: Mapping[str, Iterable[str]] | None = None) -> list[str]:
    """The recorded closure files whose content hash differs now (a missing file
    counts, and so does one recorded absent that exists), in recorded order.
    Empty when nothing moved -- or when the record carries no per-file hashes,
    in which case the caller can only say "changed". A file in ``names`` is
    compared by its slice; any other is hashed whole; a listed folder leaves
    out its ``own`` entries."""
    base = Path(script).resolve().parent
    changed: list[str] = []
    for rel, recorded in shas.items():
        try:
            now = entry_hash_now(base, str(rel), names, shas, wholes, own)
        except OSError:
            now = None
        if now != recorded:
            changed.append(str(rel))
    return changed


def current_closure_hash(script: Path, files: Iterable[str], names: Mapping[str, Iterable[str]] | None = None, *,
                         shas: Mapping[str, str] | None = None, wholes: Mapping[str, str] | None = None,
                         own: Mapping[str, Iterable[str]] | None = None) -> str | None:
    """Re-hash a recorded file list as it is on disk now; None if a file is gone.
    A file in ``names`` is compared by its slice (``shas``/``wholes``: the
    recorded slice stands while the file's whole-file hash is unchanged); any
    other is hashed whole; a listed folder leaves out its recorded ``own``
    entries, the model's outputs."""
    base = Path(script).resolve().parent
    pairs: list[tuple[str, str]] = []
    for rel in files:
        try:
            now = entry_hash_now(base, str(rel), names, shas, wholes, own)
        except OSError:
            return None
        if now is None:
            return None
        pairs.append((str(rel), now))
    return closure_hash(pairs) if pairs else None
