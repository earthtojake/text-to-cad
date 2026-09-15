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

Constants by value, functions by file, models by result. A non-model file
(``lib/frame.py``) is in the closure of every model whose static import closure
reaches it through non-model paths — its constants are tracked by file.

**Hash at execution.** The closure hash a record carries is over the bytes that
RAN: files are hashed when they are loaded/executed (the loader has the script's
bytes; the ``exec`` audit hook fires per first-party file), never after the body
returns. An edit landing mid-build is therefore never hashed into a record over
geometry the pre-edit source produced.

Hashes are the semantic (AST) digest for ``.py`` and the byte digest otherwise,
via ``cadgen._internal.source_hash`` — a comment-only edit is not a change.
"""

from __future__ import annotations

import ast
import functools
import hashlib
import sys
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

from cadgen._internal.source_hash import (
    _semantic_source_hash,
    is_first_party_source_file,
)


@dataclass(frozen=True)
class Closure:
    hash: str
    files: tuple[str, ...]  # relative to the model's folder, sorted
    # model file (relative to the model's folder) -> constant name -> value hash
    constants: dict[str, dict[str, str]] = field(default_factory=dict)
    # relative path -> that file's hash as taken for this closure, so a stale
    # verdict can NAME the file that moved (lazily executed files included).
    shas: dict[str, str] = field(default_factory=dict)

    def as_json(self) -> dict:
        return {"hash": self.hash, "files": list(self.files), "shas": dict(self.shas)}


@dataclass(frozen=True)
class StaticImports:
    """What a script statically imports, split by the boundary rule."""

    source_files: tuple[Path, ...]  # non-model files + model files taken as source
    child_models: tuple[Path, ...]  # model files taken only through their model function or literals
    constants: dict[str, dict[str, str]] = field(default_factory=dict)  # model path -> name -> hash


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


# --- static import resolution -------------------------------------------------


def _search_roots(script: Path) -> list[Path]:
    """Where a model's imports resolve: the same roots the runner seeds onto
    ``sys.path`` — the script's own folder, then the caller's ``PYTHONPATH``
    (``cadgen._internal.import_roots``). Nothing inferred from directory names."""
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
class _ImportSyntax:
    # (from-import flag, module, relative level, (name, alias) pairs).
    imports: tuple[tuple[bool, str, int, tuple[tuple[str, str], ...]], ...]
    taken: tuple[tuple[str, tuple[str, ...] | None], ...]


def _parse_import_syntax(payload: bytes, filename: str) -> _ImportSyntax:
    """Only immutable syntax; no resolved paths, model names or imported values."""
    nodes = tuple(ast.walk(ast.parse(payload, filename=filename)))
    imports = []
    wanted = set()
    for node in nodes:
        if isinstance(node, ast.Import):
            names = tuple((alias.name, alias.asname or "") for alias in node.names)
            imports.append((False, "", 0, names))
            wanted.update(alias or name.split(".")[0] for name, alias in names)
        elif isinstance(node, ast.ImportFrom):
            names = tuple((alias.name, alias.asname or "") for alias in node.names)
            imports.append((True, node.module or "", node.level, names))
            wanted.update(alias or name for name, alias in names)
    # getattr(alias, ...), passing/copying the module, and attribute writes
    # require a source edge. Scan every scope conservatively: only direct
    # read-only Attribute bases count as statically taken names.
    attributes = {
        id(node.value): node.attr
        for node in nodes
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load)
        and isinstance(node.value, ast.Name) and node.value.id in wanted
    }
    taken: dict[str, set[str] | None] = {name: set() for name in wanted}
    for node in nodes:
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in wanted:
            if id(node) not in attributes:
                taken[node.id] = None
            elif taken[node.id] is not None:
                taken[node.id].add(attributes[id(node)])
    return _ImportSyntax(
        tuple(imports),
        tuple(sorted((name, None if names is None else tuple(sorted(names))) for name, names in taken.items())),
    )


_IMPORT_SYNTAX_MAX_BYTES = 8 * 1024 * 1024
_IMPORT_SYNTAX_MAX_ENTRIES = 256


class _ImportSyntaxMemo:
    """One closure calculation's bounded byte-to-syntax recipes; never global."""

    def __init__(self) -> None:
        self.entries: OrderedDict[bytes, tuple[int, _ImportSyntax]] = OrderedDict()
        self.size = 0

    def get(self, payload: bytes, filename: str) -> _ImportSyntax:
        cached = self.entries.get(payload)
        if cached is not None:
            self.entries.move_to_end(payload)
            return cached[1]
        syntax = _parse_import_syntax(payload, filename)

        def retained_size(value: object) -> int:
            # Shared strings/scalars counted repeatedly make this conservative.
            return sys.getsizeof(value) + (
                sum(retained_size(item) for item in value) if isinstance(value, tuple) else 0
            )

        charge = (512 + sys.getsizeof(payload) + sys.getsizeof(syntax)
                  + retained_size(syntax.imports) + retained_size(syntax.taken))
        if charge <= _IMPORT_SYNTAX_MAX_BYTES:
            self.entries[payload] = (charge, syntax)
            self.size += charge
            while self.size > _IMPORT_SYNTAX_MAX_BYTES or len(self.entries) > _IMPORT_SYNTAX_MAX_ENTRIES:
                self.size -= self.entries.popitem(last=False)[1][0]
        return syntax


def static_imports(script: Path, *, _syntax: _ImportSyntaxMemo | None = None) -> StaticImports:
    """Direct first-party imports of ``script``, classified by the boundary rule."""
    script = Path(script).resolve()
    try:
        # Fresh bytes every time, even within this one closure calculation.
        # A recipe hit skips syntax analysis, never filesystem resolution.
        payload = script.read_bytes()
        syntax = (_syntax.get(payload, str(script)) if _syntax is not None
                  else _parse_import_syntax(payload, str(script)))
    except (OSError, SyntaxError, ValueError):
        return StaticImports((), ())
    roots = _search_roots(script)
    sources: list[Path] = []
    children: list[Path] = []
    constants: dict[str, dict[str, str]] = {}
    imports: dict[Path, set[str] | None] = {}
    taken_by_name = dict(syntax.taken)

    def taken_names(name: str) -> set[str] | None:
        taken = taken_by_name[name]
        return None if taken is None else set(taken)

    def note(target: Path, taken: set[str] | None) -> None:
        if target == script or not is_first_party_source_file(target):
            return
        previous = imports.get(target, set())
        imports[target] = None if taken is None or previous is None else previous | taken

    # A later import, including one inside a function, may take a helper from
    # a file first seen through a model name. Classify the union so normalizing
    # a runtime child ref never hides that source dependency.
    for from_import, module, level, aliases in syntax.imports:
        if not from_import:
            for name, alias in aliases:
                target = _resolve_module(name, roots)
                if target is None:
                    continue
                taken = taken_names(alias or name.split(".")[0])
                note(target, taken)
        else:
            if level:
                # `from .chain import X` / `from . import chain` inside a package:
                # relative to the importing file's own directory, `level - 1` up.
                base = script.parent
                for _ in range(level - 1):
                    base = base.parent
                from_roots: list[Path] = [base]
            else:
                from_roots = roots
            prefix = f"{module}." if module else ""
            target = _resolve_module(module, from_roots) if module else None
            names = {name for name, _alias in aliases}
            if "*" in names:
                if target is not None:
                    note(target, None)  # star import: treat as source
                continue
            # `from pkg import module` resolves the submodule, not a name in pkg.
            for name, alias in aliases:
                sub_target = _resolve_module(prefix + name, from_roots)
                if sub_target is not None:
                    note(sub_target, taken_names(alias or name))
                    names.discard(name)
            if names and target is not None:
                note(target, names)
    for target, taken in imports.items():
        model_names = _model_function_names(str(target))
        if not model_names or taken is None:
            sources.append(target)
            continue
        # Constants by value, functions by file, every decorated model by
        # result. A module import with no statically taken names is also a
        # result edge; actual model calls supply the exact function pins.
        beyond = taken - model_names
        literals = (module_constant_hashes(target, beyond) or {}) if beyond else {}
        if set(literals) == beyond:
            children.append(target)
            if literals:
                constants.setdefault(str(target), {}).update(literals)
        else:
            sources.append(target)
    return StaticImports(tuple(sources), tuple(children), constants)


def static_closure(script: Path, *, _syntax: _ImportSyntaxMemo | None = None) -> StaticImports:
    """Transitive static closure stopping at model files. Model files reached
    through a result or value edge are children (not descended into); source-edge
    model files and every non-model file are descended into and collected."""
    script = Path(script).resolve()
    syntax = _syntax if _syntax is not None else _ImportSyntaxMemo()
    sources: set[Path] = set()
    children: set[Path] = set()
    constants: dict[str, dict[str, str]] = {}
    stack = [script]
    visited: set[Path] = set()
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        imports = static_imports(current, _syntax=syntax)
        for child in imports.child_models:
            children.add(child)
        for module, names in imports.constants.items():
            constants.setdefault(module, {}).update(names)
        for source in imports.source_files:
            if source not in sources and source != script:
                sources.add(source)
                stack.append(source)
    return StaticImports(tuple(sorted(sources)), tuple(sorted(children)), constants)


# --- hash at execution ----------------------------------------------------------


_ACTIVE_HASHES: dict[str, str] | None = None
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
        hashes[key] = _semantic_source_hash(path)
    except OSError:
        return


class ExecutionHashes:
    """Context: hash every first-party file at the moment it executes."""

    def __init__(self) -> None:
        self.hashes: dict[str, str] = {}
        self._previous: dict[str, str] | None = None

    def __enter__(self) -> "ExecutionHashes":
        global _ACTIVE_HASHES, _HOOK_INSTALLED
        if not _HOOK_INSTALLED:
            sys.addaudithook(_exec_hash_hook)
            _HOOK_INSTALLED = True
        self._previous = _ACTIVE_HASHES
        _ACTIVE_HASHES = self.hashes
        return self

    def __exit__(self, *exc: object) -> None:
        global _ACTIVE_HASHES
        _ACTIVE_HASHES = self._previous
        if self._previous is not None:
            for key, value in self.hashes.items():
                self._previous.setdefault(key, value)

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


def note_consumed_file_hash(path: Path | str, digest: str) -> None:
    """Record the exact bytes a data reader consumed in the active build.

    A discovered input is normally hashed after the model body returns.  A
    path can be atomically replaced between a C++ reader opening it and that
    later hash, though, which would bind old geometry to new bytes.  Readers
    that already own the byte digest use this hook; ``ExecutionHashes.note``
    deliberately keeps the first value and therefore cannot overwrite it.
    """
    hashes = _ACTIVE_HASHES
    value = str(digest or "").strip()
    if hashes is None or not value:
        return
    try:
        resolved = Path(path).expanduser().resolve()
    except (OSError, ValueError):
        return
    hashes.setdefault(str(resolved), value)


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
) -> Closure:
    """The closure a build records.

    ``executed`` maps resolved paths to the hashes taken at execution
    (:class:`ExecutionHashes`). The file set is: the script, its static
    closure's source files, every executed first-party file, and discovered
    inputs — minus files that belong to a child model (its script and files
    reached only through it), which the boundary rule excludes.
    """
    script = Path(script).resolve()
    base = script.parent
    syntax = _ImportSyntaxMemo()
    statics = static_closure(script, _syntax=syntax)
    from cadgen.store.index import split_model_ref

    # Runtime calls carry exact script::function identities. Ownership of
    # executed source remains file-based, while the record keeps those exact
    # function pins independently in its children list.
    called_files = {split_model_ref(child)[0] for child in children}
    child_files = called_files | set(statics.child_models)
    # Files exclusively owned by children: their own static closures, minus
    # anything this script also reaches through a source edge.
    child_owned: set[Path] = set(child_files)
    ours: set[Path] = {script, *statics.source_files}
    for child in list(child_files):
        sources = static_closure(child, _syntax=syntax).source_files
        child_owned.update(sources)
        if child in called_files and child not in statics.child_models:
            # A dynamic module can supply a decorated call AND a helper/value
            # used directly by this body. The call alone does not prove that
            # its file is exclusively child-owned. Keep that source and its
            # source closure unless static imports prove a result/value edge.
            ours.update((child, *sources))
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
    for path in files:
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
    )


def changed_closure_files(script: Path, shas: Mapping[str, str]) -> list[str]:
    """The recorded closure files whose content hash differs now (a missing file
    counts), in recorded order. Empty when nothing moved -- or when the record
    carries no per-file hashes, in which case the caller can only say "changed"."""
    base = Path(script).resolve().parent
    changed: list[str] = []
    for rel, recorded in shas.items():
        resolved = _resolve_relative(str(rel), base)
        try:
            now = _semantic_source_hash(resolved) if resolved is not None else None
        except OSError:
            now = None
        if now != recorded:
            changed.append(str(rel))
    return changed


def current_closure_hash(script: Path, files: Iterable[str]) -> str | None:
    """Re-hash a recorded file list as it is on disk now; None if a file is gone."""
    base = Path(script).resolve().parent
    pairs: list[tuple[str, str]] = []
    for rel in files:
        resolved = _resolve_relative(str(rel), base)
        if resolved is None:
            return None
        try:
            pairs.append((str(rel), _semantic_source_hash(resolved)))
        except OSError:
            return None
    return closure_hash(pairs) if pairs else None
