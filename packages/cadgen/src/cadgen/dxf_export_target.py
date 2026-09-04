"""Export one generated drawing to a standalone ``.dxf`` file.

The DXF analogue of :mod:`cadgen.step_export_target`, and the module the CAD
Viewer's export route spawns for a ``.dxf.py`` entry. It is a thin front over
:func:`generate_dxf_targets`: generation ALWAYS writes the drawing (design/
standalone-viewer.md Phase A), so an export is just a generation run with the
output renamed — and an unchanged source whose recorded output already matches
is a no-op.

Emits a single final JSON line on stdout: ``{"ok": true, "path": ..., "filename": ...}``
or ``{"ok": false, "error": ...}`` (the Node spawner parses the last stdout JSON line).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def export_dxf_to_path(source_path: Path, out_path: Path) -> dict:
    from cadgen._internal.generation import generate_dxf_targets

    source_path = Path(source_path)
    out_path = Path(out_path).expanduser().resolve()
    if not str(source_path).lower().endswith(".dxf.py"):
        return {"ok": False, "error": f"Not a DXF generator: {source_path}"}
    generate_dxf_targets([str(source_path)], output=str(out_path))
    if not out_path.is_file():
        return {"ok": False, "error": f"export did not write {out_path}"}
    return {"ok": True, "path": str(out_path), "filename": out_path.name}


def run_cli_payload(argv: list[str]) -> dict:
    parser = argparse.ArgumentParser(prog="python -m cadgen.dxf_export_target")
    parser.add_argument("--repo-root", default="")
    parser.add_argument("--source-path", required=True)
    parser.add_argument("--out", required=True)
    # Accepted for spawn-contract parity with the other export modules; exports
    # rebuild only when stale regardless, and verbosity is the logger's business.
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.repo_root).resolve() if args.repo_root else Path.cwd()
    source = Path(args.source_path)
    if not source.is_absolute():
        source = root / source
    try:
        return export_dxf_to_path(source, Path(args.out))
    except Exception as exc:  # noqa: BLE001 - the CLI boundary: report, do not traceback
        return {"ok": False, "error": str(exc)}


def main(argv: list[str] | None = None) -> int:
    import sys

    payload = run_cli_payload(list(argv) if argv is not None else sys.argv[1:])
    print(json.dumps(payload, separators=(",", ":")))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
