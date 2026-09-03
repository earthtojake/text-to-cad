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

Identity is the SCRIPT. A generated document carries no tie back to its
source (a generated file is independent of its script), so the store keeps
the reverse map itself: ``index/document/<sha256(document path)>`` names the
model that wrote the document. A missing entry reads as "an imported
document" — the document is its own source and keys on its own path — which
costs one rebuild and never correctness.
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


def note_document(document: Path | str, model: Path | str) -> None:
    """Remember that ``model`` wrote ``document`` (the reverse map a door needs
    to find a document's record). Idempotent; atomic."""
    write_entry("document", model_key(document), {"model": _resolved(model)})


def forget_document(document: Path | str) -> None:
    remove_entry("document", model_key(document))


def source_for_document(document: Path | str) -> Path:
    """The model a document belongs to: the script the store remembers writing
    it (when that script still exists), else the document itself (an imported
    source)."""
    document = Path(document)
    entry = read_entry("document", model_key(document)) or {}
    recorded = str(entry.get("model") or "").strip()
    if recorded:
        candidate = Path(recorded)
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
