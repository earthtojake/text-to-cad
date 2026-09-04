"""Dependency capture for a model's closure.

The closure of a model (the files whose content decides whether its record is
current) is the union of three channels this module provides:

1. **Static import closure** of the model's file: every first-party file
   reachable through ``import``/``from … import`` statements, resolved
   recursively with a stat-keyed cache. This is what keeps the closure SOUND in
   a warm process: audit ``exec`` events only fire when a module body actually
   executes, so a model imported after a sibling already loaded ``_spec`` would
   otherwise record a closure missing ``_spec`` — and a ``_spec`` edit would
   then read as current. Static resolution sees the import statement whether or
   not the import re-executed.
2. **Dynamic execution capture**: first-party files whose module bodies ran
   during the build (``record_first_party_execution``), which catches dynamic
   loads static analysis cannot see (``importlib`` path loads).
3. **Noted data reads**: non-Python inputs under the model root, reported
   explicitly by cadgen's own loaders via :func:`note_scope_read` (C++ file
   opens inside OCCT are invisible to Python audit events, so loaders must
   self-report) plus an ``open`` audit hook that catches Python-level reads.

A build that reads something this module cannot track (an oversized or
unresolvable input) is UNTRACKABLE and its record must never be published.

Closure hashing and validation reuse ``source_hash``'s semantic machinery:
``.py`` files hash comment-insensitively by AST, data files by bytes, and
paths are stored relative to the model root so records validate across
checkouts with identical layout. The ``scope`` in this module's identifiers is
the recording window of one build, not a store concept.
"""

from __future__ import annotations

import ast
import contextlib
import os
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

from cadgen._internal.source_hash import (
    closure_for_files,
    is_first_party_source_file,
    record_first_party_execution,
)

# Data files larger than this are not content-hashed per validation; a scope
# reading one becomes untrackable rather than slow.
MAX_TRACKED_READ_BYTES = 32 * 1024 * 1024



# ---------------------------------------------------------------------------
# Static import closure


# (path str) -> (mtime_ns, size, tuple of resolved child paths)
_STATIC_IMPORT_CACHE: dict[str, tuple[int, int, tuple[str, ...]]] = {}


def _direct_imports(path: Path, root: Path) -> tuple[str, ...]:
    """First-party files directly imported by ``path``'s source, resolved
    against the scope root, the file's own directory, and loaded modules."""
    key = str(path)
    try:
        stat = path.stat()
    except OSError:
        return ()
    cached = _STATIC_IMPORT_CACHE.get(key)
    if cached is not None and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
        return cached[2]
    names: set[str] = set()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        _STATIC_IMPORT_CACHE[key] = (stat.st_mtime_ns, stat.st_size, ())
        return ()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.partition(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.partition(".")[0])
    resolved: list[str] = []
    for name in sorted(names):
        target = _resolve_module_file(name, search_dirs=(path.parent, root))
        if target is not None:
            resolved.append(str(target))
    result = tuple(resolved)
    _STATIC_IMPORT_CACHE[key] = (stat.st_mtime_ns, stat.st_size, result)
    return result


def _resolve_module_file(name: str, *, search_dirs: tuple[Path, ...]) -> Path | None:
    for base in search_dirs:
        candidate = base / f"{name}.py"
        if candidate.is_file():
            return candidate.resolve()
        package = base / name / "__init__.py"
        if package.is_file():
            return package.resolve()
    module = sys.modules.get(name)
    file_name = getattr(module, "__file__", None)
    if file_name:
        try:
            path = Path(file_name).resolve()
        except OSError:
            return None
        if path.suffix == ".py" and is_first_party_source_file(path):
            return path
    return None


def static_import_closure(entry_file: Path, root: Path) -> set[Path]:
    """All first-party files reachable from ``entry_file`` via static imports
    (inclusive of the entry file)."""
    entry_file = entry_file.resolve()
    root = root.resolve()
    seen: set[Path] = set()
    stack = [entry_file]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        for child in _direct_imports(current, root):
            child_path = Path(child)
            if child_path not in seen:
                stack.append(child_path)
    return seen


# ---------------------------------------------------------------------------
# Scope recording (dynamic channels)


@dataclass
class ScopeRecording:
    root: Path
    exec_files: set[Path] = field(default_factory=set)
    reads: set[Path] = field(default_factory=set)
    untrackable: list[str] = field(default_factory=list)

    def note_read(self, path: Path) -> None:
        try:
            resolved = Path(path).resolve()
        except OSError:
            return
        if not _is_within(resolved, self.root):
            return  # outside the model: not this scope's input
        if "__pycache__" in resolved.parts:
            return  # derived caches, never freshness inputs
        if resolved.suffix in (".py", ".pyc"):
            return  # python inputs travel through the exec/static channels
        try:
            size = resolved.stat().st_size
        except OSError:
            return  # probe of a missing file: nothing was read
        if size > MAX_TRACKED_READ_BYTES:
            self.untrackable.append(f"oversized read: {resolved}")
            return
        self.reads.add(resolved)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


_local = threading.local()


def _scope_stack() -> list[ScopeRecording]:
    stack = getattr(_local, "stack", None)
    if stack is None:
        stack = _local.stack = []
    return stack


def note_scope_read(path: Path | str) -> None:
    """Called by cadgen loaders that read model-adjacent data files through
    C++ (OCCT readers), which Python audit events cannot see."""
    for scope in _scope_stack():
        scope.note_read(Path(path))


_OPEN_HOOK_INSTALLED = False


def _open_audit_hook(event: str, args: tuple) -> None:
    if event != "open" or not args:
        return
    stack = getattr(_local, "stack", None)
    if not stack:
        return
    mode = args[1] if len(args) > 1 else "r"
    if isinstance(mode, str) and any(ch in mode for ch in "wax+"):
        return  # writes are outputs, not inputs
    target = args[0]
    if not isinstance(target, (str, bytes, os.PathLike)):
        return
    try:
        path = Path(os.fsdecode(target))
    except (TypeError, ValueError):
        return
    for scope in stack:
        scope.note_read(path)


@contextlib.contextmanager
def scoped_recording(entry_file: Path, root: Path):
    """Record one scope's dynamic channels; combine with the static closure
    via :func:`scope_closure` after the scope returns."""
    global _OPEN_HOOK_INSTALLED
    if not _OPEN_HOOK_INSTALLED:
        sys.addaudithook(_open_audit_hook)
        _OPEN_HOOK_INSTALLED = True
    recording = ScopeRecording(root=Path(root).resolve())
    _scope_stack().append(recording)
    try:
        with record_first_party_execution() as executed:
            yield recording
    finally:
        _scope_stack().pop()
        recording.exec_files |= {Path(p) for p in executed}
        # A child's inputs are also the parent's inputs.
        parent_stack = _scope_stack()
        if parent_stack:
            parent = parent_stack[-1]
            parent.reads |= recording.reads
            parent.untrackable.extend(recording.untrackable)


def scope_closure(entry_file: Path, recording: ScopeRecording):
    """The scope's validated identity: (closure_hash, files-relative-to-root),
    or ``None`` when the scope is untrackable."""
    if recording.untrackable:
        return None
    files = static_import_closure(entry_file, recording.root)
    files |= recording.exec_files
    files |= recording.reads
    return closure_for_files(Path(entry_file).resolve(), files, base=recording.root)
