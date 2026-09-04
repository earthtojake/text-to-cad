"""``cadgen store forget``: a surgical reset of what the index remembers.

The store has three resets. ``--force`` on a run rebuilds one model.
``rm -rf`` the store root forgets everything. Between them sits ``forget``:
drop the index entries for one model or one document so the next run, open or
door call does its work again, and touch nothing else.

- A **model script** argument drops its record (``index/model/<sha(script)>``).
  The next run rebuilds it; its children are untouched, and its parents see a
  moved pin only after that rebuild — exactly as after any edit.
- A **document** argument (a ``.step``/``.dxf``/mesh path) drops the
  ``index/document/<sha256(bytes)>`` entry, so the next open or door call
  compiles the file from its bytes again; when a record lists that path as an
  output, the record and its ``index/output`` note go too.

Objects are never deleted here — that is ``gc``. Nothing is refused: a target
the store never heard of is "nothing to forget".
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from cadgen.store.index import MODEL_REF_SEP, model_ref, path_key, read_entry, remove_entry, split_model_ref
from cadgen.store.records import read_record, records_for_script, remove_record


def _resolved(target: str | Path) -> Path:
    path = Path(target).expanduser()
    try:
        return path.resolve()
    except (OSError, ValueError, RuntimeError):
        return path.absolute()


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def forget(target: str | Path, *, dry_run: bool = False) -> dict[str, Any]:
    """Forget ``target``; report what was (or would be) dropped. A script drops
    the record of every model it holds; ``script.py::fn`` drops one."""
    script, function = split_model_ref(str(target))
    resolved = script if function is not None else _resolved(target)
    report: dict[str, Any] = {"target": str(target), "path": str(resolved), "dryRun": bool(dry_run), "forgot": []}
    forgot: list[dict[str, Any]] = report["forgot"]

    def drop_record(model: str | Path) -> None:
        record = read_record(model)
        if record is None:
            return
        forgot.append({"kind": "record", "model": str(record.get("model") or model), "tree": record.get("tree")})
        if not dry_run:
            remove_record(str(record.get("model") or model))

    if resolved.suffix.lower() == ".py":
        if function is not None:
            drop_record(model_ref(resolved, function))
            return report
        from cadgen.metadata import model_function_names

        names = model_function_names(resolved)
        if names:
            for name in names:
                drop_record(model_ref(resolved, name))
        else:
            # The script is gone or declares nothing: whatever records name it.
            for ref, _record in records_for_script(resolved):
                drop_record(ref)
        return report

    digest = _sha256(resolved) if resolved.is_file() else None
    if digest:
        entry = read_entry("document", digest)
        if entry:
            forgot.append({"kind": "document", "sha256": digest, "tree": entry.get("tree")})
            if not dry_run:
                remove_entry("document", digest)

    output_entry = read_entry("output", path_key(resolved)) or {}
    recorded_model = str(output_entry.get("model") or "").strip()
    if recorded_model:
        drop_record(recorded_model)
        forgot.append({"kind": "output", "path": str(resolved), "model": recorded_model})
        if not dry_run:
            remove_entry("output", path_key(resolved))
    return report


def describe(report: dict[str, Any]) -> list[str]:
    """One human line per thing forgotten, or one saying there was nothing."""
    verb = "would forget" if report.get("dryRun") else "forgot"
    lines: list[str] = []
    for item in report.get("forgot") or []:
        kind = item.get("kind")
        if kind == "record":
            tree = str(item.get("tree") or "")[:12]
            lines.append(f"{verb} record  {item.get('model')}" + (f"  (tree {tree})" if tree else ""))
        elif kind == "document":
            lines.append(f"{verb} document  {report.get('path')}  (sha {str(item.get('sha256'))[:12]}, tree {str(item.get('tree') or '')[:12]})")
        elif kind == "output":
            lines.append(f"{verb} output note  {item.get('path')}  (written by {item.get('model')})")
    if not lines:
        lines.append(f"nothing to forget: {report.get('target')}")
    return lines
