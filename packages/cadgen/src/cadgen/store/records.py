"""Records: the mutable per-model entry in ``index/model/``.

A record says what a model's build depended on and what it produced::

    {
      "model": "/abs/src/robot.py",
      "kind": "step",
      "entryKind": "assembly",
      "tree": "<tree object hash>",
      "closure": {"hash": "…", "files": ["robot.py", "lib/frame.py"]},
      "children": [{"model": "/abs/src/arm.py", "tree": "…"}],
      "outputs": {"/abs/STEP/robot.step": {"sha256": "…"}, …}
    }

``children`` is recorded from the CALLS the body made, never derived from the
tree's links — that is what makes the link/component decision in
``cadgen.store.trees`` safe. ``closure.files`` are relative to the script's
folder and hashed by ``cadgen.store.closure``.

Identity is the SCRIPT. A generated document maps to its record through the
sidecar's ``sourcePath``; an imported document (a vendor ``.step`` with no
script) is its own source and keys on its own path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cadgen.store.index import model_key, read_entry, remove_entry, write_entry

RECORD_KIND = "record"


def read_record(model: Path | str) -> dict[str, Any] | None:
    data = read_entry("model", model_key(model))
    if data is None or data.get("kind") != RECORD_KIND:
        return None
    return data


def write_record(model: Path | str, payload: dict[str, Any]) -> None:
    body = dict(payload)
    body["kind"] = RECORD_KIND
    body["model"] = _resolved(model)
    write_entry("model", model_key(model), body)


def remove_record(model: Path | str) -> None:
    remove_entry("model", model_key(model))


def update_record(model: Path | str, **fields: Any) -> dict[str, Any] | None:
    """Merge ``fields`` into an existing record (atomic rewrite). None if absent."""
    record = read_record(model)
    if record is None:
        return None
    record.update(fields)
    write_record(model, record)
    return record


def _resolved(path: Path | str) -> str:
    try:
        return str(Path(path).expanduser().resolve())
    except (OSError, ValueError, RuntimeError):
        import os

        return os.path.abspath(str(path))


def source_for_document(document: Path | str) -> Path:
    """The model a document belongs to: the script its sidecar names when the
    document was generated, else the document itself (an imported source)."""
    document = Path(document)
    try:
        from cadgen._internal.source_sidecar import read_source_sidecar

        sidecar = read_source_sidecar(document) or {}
    except Exception:  # noqa: BLE001 - an unreadable sidecar is "no sidecar"
        sidecar = {}
    if str(sidecar.get("sourceKind") or "").strip().lower() == "python":
        recorded = str(sidecar.get("sourcePath") or "").strip()
        if recorded:
            candidate = (document.parent / recorded).resolve()
            if candidate.is_file():
                return candidate
    try:
        return document.expanduser().resolve()
    except (OSError, ValueError, RuntimeError):
        return document


def record_for_document(document: Path | str) -> dict[str, Any] | None:
    """The record behind a ``.step`` on disk (generated or imported), or None."""
    return read_record(source_for_document(document))


def current_tree(model: Path | str) -> str | None:
    record = read_record(model)
    if record is None:
        return None
    tree = str(record.get("tree") or "").strip()
    return tree or None
