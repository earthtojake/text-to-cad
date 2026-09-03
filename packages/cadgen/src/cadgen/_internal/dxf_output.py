"""The generated-DXF output record: gen-side freshness for drawing targets.

A drawing generator's product is the `.dxf` file itself (design/
standalone-viewer.md Phase A) — the viewer parses it directly, so there is no
drawing package. What remains, in the store's ``records/`` tier, is this one
small record, which is what makes an unchanged source a no-op.

The record is keyed by the DRAWING'S CONTENT HASH — the same rule render
packages follow — so a moved, renamed, or copied project resolves its own
record by construction and rebuilds nothing. It maps every source closure
known to have produced these exact bytes:

    <sha256(dxf bytes)>.dxf-export.json = {
      "kind": "dxf-export-record",
      "closures": { "<closureHash>": ["<closure file>", ...], ... }
    }

A closure MAP rather than a single entry, because two different sources can
legitimately emit byte-identical drawings; one record per content serves both
without flip-flopping. Everything here is stdlib-only — the render side
imports this module into a process that must never load ezdxf/OCP.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from cadgen._internal.atomic_replace import replace_atomic
from cadgen._internal.source_hash import closure_hash_matches
from cadgen.catalog import artifact_file_hash, artifact_path_key

DXF_EXPORT_RECORD_NAME = "dxf-export.json"
DXF_EXPORT_RECORD_KIND = "dxf-export-record"


def dxf_export_record_path(output_path: Path) -> Path:
    """The freshness record for a written drawing, keyed by its bytes. A
    missing/unreadable drawing resolves to a deterministic never-written path
    so existence checks just answer "no record"."""
    from cadgen.store.paths import index_dir

    digest = artifact_file_hash(Path(output_path))
    if digest is None:
        return index_dir("dxf") / f"unbuilt-{artifact_path_key(Path(output_path))}"
    return index_dir("dxf") / digest


def _read_record(record_path: Path) -> dict | None:
    try:
        payload = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("kind") != DXF_EXPORT_RECORD_KIND:
        return None
    return payload


def record_dxf_output(script_path: Path, output_path: Path, *, source_closure) -> None:
    """Merge this build's closure into the drawing's content-keyed record
    after a successful generate+write. Best-effort: a failed record only
    costs a future re-render."""
    del script_path  # identity is the drawing's content; the closure carries the source
    record_path = dxf_export_record_path(output_path)
    record_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_record(record_path) or {"kind": DXF_EXPORT_RECORD_KIND, "closures": {}}
    closures = existing.get("closures")
    if not isinstance(closures, dict):
        closures = {}
    closures[str(source_closure.closure_hash)] = list(source_closure.files)
    payload = {"kind": DXF_EXPORT_RECORD_KIND, "closures": closures}
    temporary = record_path.with_name(f"{record_path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    replace_atomic(temporary, record_path)


def dxf_output_current(script_path: Path, output_path: Path | None = None) -> bool:
    """Whether the drawing on disk is the CURRENT product of this source: its
    content-keyed record names a closure that still re-hashes unchanged.
    ``output_path`` defaults to the script's sibling ``.dxf``."""
    script_path = Path(script_path)
    output = (
        Path(output_path).expanduser().resolve()
        if output_path is not None
        else script_path.resolve().with_suffix(".dxf")
    )
    if not output.is_file():
        return False
    record = _read_record(dxf_export_record_path(output))
    if record is None:
        return False
    closures = record.get("closures")
    if not isinstance(closures, dict):
        return False
    base = script_path.resolve().parent
    for closure_hash, files in closures.items():
        if isinstance(files, list) and files and closure_hash_matches(closure_hash, files, base=base):
            return True
    return False
