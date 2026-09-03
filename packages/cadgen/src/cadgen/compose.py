"""The composition seam: ``memo`` — traced, cached model subtrees.

``memo(fn)`` wraps a function — a sibling model's imported entry function,
or any expensive pure helper — as a SCOPE
(design/production-architecture.md): its results are cached in the shared
store keyed by source — the function's file, its static import closure, plus
everything observed executing/reading during a miss — and by its arguments,
so an edit that does not reach a scope's sources skips the scope's Python,
kernel work, and any nondeterminism wholesale. Importing links; ``memo``
caches. A decorated model passed to ``memo`` is just its geometry: inside a
build a decorated name composes (returns the shape) rather than building, and
the child's own export declarations fire only when the child is the entry
being built. Validation is a semantic re-hash of
the recorded file list (stat-cached, milliseconds); a resident session can
install a cheaper validator that answers from its watcher.

Rules inherited from the op layer: a miss returns the same canonical
reconstruction a future hit would (cache-state independence); anything
unkeyable, untrackable, or unfreezable falls through to plain execution
(correctness never depends on a hit). Kill switch: ``CADGEN_SCOPE_CACHE=0``.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

from cadgen._internal import scope_capture, scope_store

_lock = threading.RLock()
_stats = {"hits": 0, "misses": 0, "unkeyable": 0, "unfreezable": 0,
          "untrackable": 0, "errors": 0}

# Optional session-installed fast validator: files-unchanged answers from a
# watcher instead of re-hashing. Returning None means "don't know, re-hash".
_scope_validator = None


def set_scope_validator(validator) -> None:
    global _scope_validator
    _scope_validator = validator


def stats() -> dict:
    with _lock:
        return dict(_stats)


def _enabled() -> bool:
    return os.environ.get("CADGEN_SCOPE_CACHE", "1") != "0"


def _args_key(args: tuple, kwargs: dict):
    from cadgen._internal.op_memo import _Unkeyable, _build_key

    try:
        return _build_key("scope", args, kwargs)
    except _Unkeyable:
        return None
    except Exception:
        return None


def _run_scope(scope_id: str, entry_file: Path, root: Path,
               call, args: tuple, kwargs: dict):
    """The shared hit/miss flow for both seam kinds."""
    if not _enabled():
        return call()

    args_key = _args_key(args, kwargs)
    if args_key is None and (args or kwargs):
        with _lock:
            _stats["unkeyable"] += 1
        return call()

    key = scope_store.scope_key(scope_id, args_key)

    entry = None
    if _scope_validator is not None:
        entry = _scope_validator(key, root)
    if entry is None:
        entry = scope_store.load_valid_scope_entry(key, base=root)
    if entry is not None:
        try:
            value = scope_store.thaw_value(entry["value"])
        except Exception:
            with _lock:
                _stats["errors"] += 1
        else:
            # A hit skips executing the scope's files, but they stay freshness
            # inputs of every ENCLOSING closure (the package gate above this
            # scope must still see edits to them).
            from cadgen._internal.source_hash import note_executed_files

            root_path = Path(root)
            note_executed_files(
                root_path / rel for rel in entry.get("files") or [])
            for outer in scope_capture._scope_stack():
                for rel in entry.get("files") or []:
                    resolved = (root_path / rel).resolve()
                    if resolved.suffix != ".py":
                        outer.reads.add(resolved)
            with _lock:
                _stats["hits"] += 1
            return value

    # A miss runs against the modules the JOB started with -- never against a
    # re-imported set. This used to evict every first-party module (and purge
    # their bytecode) right here, on every miss, so that a resident worker's
    # stale helper could not leak into a scope. That guarantee belongs to the
    # job boundary, where the generation runner and the daemon worker already
    # provide it; taken mid-job it broke the run instead: in a worker the
    # script's folder is off sys.path once its body has loaded, so a lazy
    # ``from lib import x`` inside a function after the first miss found no
    # ``lib`` at all (three builders lost cold rebuilds to it), and in-process
    # the re-import made a SECOND ``lib`` beside the one the model already held,
    # doubling every module-level cache and palette. Sources do not change inside
    # one job; nothing here may touch sys.modules.
    with scope_capture.scoped_recording(entry_file, root) as recording:
        result = call()
    with _lock:
        _stats["misses"] += 1

    closure = scope_capture.scope_closure(entry_file, recording)
    if closure is None:
        with _lock:
            _stats["untrackable"] += 1
        return result
    try:
        frozen = scope_store.freeze_value(result)
    except scope_store.Unfreezable:
        with _lock:
            _stats["unfreezable"] += 1
        return result
    except Exception:
        with _lock:
            _stats["errors"] += 1
        return result
    try:
        scope_store.save_scope_entry(
            key,
            closure_hash=closure.closure_hash,
            files=closure.files,
            frozen_value=frozen,
            scope_id=scope_id,
        )
        # The caller gets the same canonical reconstruction a future hit
        # returns: output must not depend on cache state.
        return scope_store.thaw_value(frozen)
    except Exception:
        with _lock:
            _stats["errors"] += 1
        return result


def memo(fn):
    """Cache a function as a traced scope: a sibling model's imported entry
    function, or any expensive helper. The function must be pure given its
    arguments and its source closure, and must return shapes/compounds (or
    JSON-able values). A decorated model is just its geometry here: inside a
    build its call composes, the wrapper caches the shape, and the child's own
    export declarations fire only when the child is the entry being built.
    Freshness is per RUN (like imports): each build re-imports edited modules,
    and the scope key — the child's file + traced closure + args — decides hit
    or miss."""
    import functools
    import inspect

    # The scope root is the file that DEFINES the function. A decorated model
    # arrives as the decorator's wrapper, whose own globals are cadgen's; look
    # through it to the body it wraps.
    file_name = inspect.unwrap(fn).__globals__.get("__file__")
    entry_file = Path(file_name).resolve() if file_name else None

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if entry_file is None:
            return fn(*args, **kwargs)
        scope_id = f"{entry_file.name}::{fn.__qualname__}"
        return _run_scope(
            scope_id, entry_file, entry_file.parent,
            lambda: fn(*args, **kwargs), args, kwargs,
        )

    wrapper.__cadgen_memo__ = True
    return wrapper
