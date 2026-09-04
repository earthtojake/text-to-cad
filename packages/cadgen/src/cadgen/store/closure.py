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

    def as_json(self) -> dict:
        return {"hash": self.hash, "files": list(self.files)}


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
    script's folder and project roots on ``sys.path``), under a private module
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
def _model_function_name(path_str: str) -> str | None:
    """The decorated model function's name when ``path`` is a model file, else None.
    Static (AST) so nothing is imported to answer it."""
    from cadgen.metadata import parse_generator_metadata

    try:
        metadata = parse_generator_metadata(Path(path_str))
    except Exception:  # noqa: BLE001 - an unparseable file is not a model file
        return None
    if metadata is None or not getattr(metadata, "is_decorated", False):
        return None
    return str(getattr(metadata, "entry_function", "") or "") or None


def is_model_file(path: Path) -> bool:
    return _model_function_name(str(Path(path).resolve())) is not None


def forget_model_files() -> None:
    _model_function_name.cache_clear()


# --- static import resolution -------------------------------------------------


def _search_roots(script: Path) -> list[Path]:
    """Where a model's imports resolve: its own folder, then any ancestor that
    is a project root (holds ``STEP/`` or ``robot_common/`` packages) — the
    same roots the runner seeds onto ``sys.path``."""
    roots = [script.parent]
    for parent in script.parents:
        if (parent / "STEP" / "__init__.py").is_file() or (parent / "robot_common" / "__init__.py").is_file():
            roots.append(parent)
    return roots


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


def _taken_names(tree: ast.Module, alias: str) -> set[str]:
    """Attribute names read off ``alias`` anywhere in the module (``alias.x``)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == alias:
            names.add(node.attr)
    return names


def static_imports(script: Path) -> StaticImports:
    """Direct first-party imports of ``script``, classified by the boundary rule."""
    script = Path(script).resolve()
    try:
        tree = ast.parse(script.read_bytes(), filename=str(script))
    except (OSError, SyntaxError, ValueError):
        return StaticImports((), ())
    roots = _search_roots(script)
    sources: list[Path] = []
    children: list[Path] = []
    constants: dict[str, dict[str, str]] = {}
    seen: set[Path] = set()

    def classify(target: Path, taken: set[str] | None) -> None:
        if target in seen or target == script or not is_first_party_source_file(target):
            return
        seen.add(target)
        model_fn = _model_function_name(str(target))
        if model_fn is None:
            sources.append(target)
            return
        if taken is None:  # star import: everything, by file
            sources.append(target)
            return
        # A model file. Names beyond the model function are value edges when
        # every one is a module-level literal (tracked by value hash); any other
        # name — a helper, a bd object, an expression — makes the file a source edge.
        # (`import arm` with only `arm.arm()` calls records {"arm"}; nothing taken
        # statically at all is a result edge too.)
        beyond = set(taken) - {model_fn}
        literals = (module_constant_hashes(target, beyond) or {}) if beyond else {}
        if set(literals) == beyond:
            children.append(target)
            if literals:
                constants.setdefault(str(target), {}).update(literals)
        else:
            sources.append(target)

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = _resolve_module(alias.name, roots)
                if target is None:
                    continue
                taken = _taken_names(tree, alias.asname or alias.name.split(".")[0])
                classify(target, taken)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # `from .chain import X` / `from . import chain` inside a package:
                # relative to the importing file's own directory, `level - 1` up.
                base = script.parent
                for _ in range(node.level - 1):
                    base = base.parent
                from_roots: list[Path] = [base]
            else:
                from_roots = roots
            module = node.module or ""
            prefix = f"{module}." if module else ""
            target = _resolve_module(module, from_roots) if module else None
            names = {alias.name for alias in node.names}
            if "*" in names:
                if target is not None:
                    classify(target, None)  # star import: treat as source
                continue
            # `from pkg import module` resolves the submodule, not a name in pkg.
            submodules = {n for n in names if _resolve_module(prefix + n, from_roots) is not None}
            for sub in submodules:
                sub_target = _resolve_module(prefix + sub, from_roots)
                if sub_target is not None:
                    classify(sub_target, _taken_names(tree, sub))
            names -= submodules
            if names and target is not None:
                classify(target, names)
    return StaticImports(tuple(sources), tuple(children), constants)


def static_closure(script: Path) -> StaticImports:
    """Transitive static closure stopping at model files. Model files reached
    through a result or value edge are children (not descended into); source-edge
    model files and every non-model file are descended into and collected."""
    script = Path(script).resolve()
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
        imports = static_imports(current)
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
    children: Iterable[Path] = (),
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
    statics = static_closure(script)
    child_files: set[Path] = set(Path(c).resolve() for c in children) | set(statics.child_models)
    # Files exclusively owned by children: their own static closures, minus
    # anything this script also reaches through a source edge.
    child_owned: set[Path] = set(child_files)
    for child in list(child_files):
        for source in static_closure(child).source_files:
            child_owned.add(source)
    ours: set[Path] = {script, *statics.source_files}
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
