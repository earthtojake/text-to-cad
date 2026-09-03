"""Input-addressed index entries: records, op-memo entries, mesh entries.

Every entry is a small JSON file written temp + rename. The key is what
PRODUCED the entry (a model's script, an op's inputs, a surface × tolerance),
never the content — that is the one distinction between ``index/`` and
``objects/``.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterator

from cadgen._internal.atomic_replace import replace_atomic, temp_suffix
from cadgen.store.paths import index_dir


def model_key(script_path: Path | str) -> str:
    """A model's index key: sha256 of its resolved script path."""
    try:
        resolved = str(Path(script_path).expanduser().resolve())
    except (OSError, ValueError, RuntimeError):
        resolved = os.path.abspath(str(script_path))
    return hashlib.sha256(resolved.encode("utf-8")).hexdigest()


def entry_path(kind: str, key: str) -> Path:
    return index_dir(kind) / key


def read_entry(kind: str, key: str) -> dict[str, Any] | None:
    try:
        data = json.loads(entry_path(kind, key).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_entry(kind: str, key: str, payload: dict[str, Any]) -> None:
    target = entry_path(kind, key)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}{temp_suffix()}")
    tmp.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    replace_atomic(tmp, target)


def remove_entry(kind: str, key: str) -> None:
    try:
        entry_path(kind, key).unlink()
    except OSError:
        pass


def iter_entries(kind: str) -> Iterator[tuple[str, Path]]:
    root = index_dir(kind)
    if not root.is_dir():
        return
    for entry in sorted(root.iterdir()):
        if entry.is_file() and not entry.name.startswith("."):
            yield entry.name, entry
