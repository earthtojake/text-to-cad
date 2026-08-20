"""Export one implicit CAD model to a standalone STL/3MF/GLB file.

The implicit analogue of :mod:`cadgen.step_export_target`, and for the same reason: the CAD
Viewer's "Export model" action must not mesh geometry in the browser. It used to -- the
client loaded the ``.implicit.js`` module, meshed and serialized it in the tab, and POSTed
the bytes for the server to write -- which made the viewer carry a second, live geometry
runtime purely so a menu item could work. The mesher is JS either way; the difference is
which process runs it, and running it here means the viewer keeps exactly one render path.

**Live-valued, unlike the render package.** ``model.glb`` is baked at ``params.*.default``
and one fixed resolution, on purpose. An export is not: ``--params`` / ``--animation`` /
``--resolution`` are passed straight through to the exporter, because an export is a file
the user asked for rather than a cache the viewer reads. Nothing about the baked package
constrains it, and it deliberately does not touch that package.

**The lock it takes is the generator lock, not the write lock.** An export writes somewhere
else entirely and rewrites nothing inside ``__cadgen__``, so claiming the write lock would
make a perfectly current model report ``generating`` with an empty progress bar. Taking
nothing would let a concurrent render build mesh the same model at the same time. So it
occupies the GENERATOR, which is exactly the case ``generator_busy`` exists for.

No OCP: an implicit model is GLSL and JS.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from cadgen._internal.implicit_package import is_implicit_source_path
from cadgen._internal.node_runtime import (
    NodeBuilderError,
    cad_node_executable,
    node_child_env,
    node_package_root,
    node_resolve_bootstrap,
)
from cadgen.catalog import render_package_dir
from cadgen.coordination import IMPLICIT_PACKAGE, generator_busy
from cadgen.render import relative_to_cwd

# The formats the exporter offers, in menu order. Mirrors IMPLICIT_CAD_EXPORT_FORMATS in
# packages/implicitjs/src/lib/implicitCad/export.js, which is also where the CLI's
# flag-per-format surface is derived from.
IMPLICIT_EXPORT_FORMATS = ("stl", "glb", "3mf")

# The shipped export CLI. Not a builder under packages/cadjs/bin: this one predates the
# render packages, is a user-facing command in its own right, and is reused rather than
# reimplemented (design §4.7 -- "alignment, not creation").
IMPLICIT_EXPORT_CLI = ("implicitjs", "scripts", "export.mjs")


def normalize_export_format(value: str) -> str:
    fmt = str(value or "").strip().lower().lstrip(".")
    if fmt in IMPLICIT_EXPORT_FORMATS:
        return fmt
    raise ValueError(f"Unsupported implicit CAD export format: {value or '(missing)'}")


def implicit_export_cli() -> Path:
    """Absolute path of ``packages/implicitjs/scripts/export.mjs``.

    Derived from :func:`node_package_root` so it is right in the dev checkout AND in a
    vendored skill runtime. Missing is a PACKAGING failure -- a runtime that ships cadgen
    but not implicitjs cannot export this format at all -- so it says which path it looked
    at rather than failing later with a confusing node error.
    """
    path = node_package_root().joinpath(*IMPLICIT_EXPORT_CLI)
    if not path.is_file():
        raise NodeBuilderError(
            f"The implicit CAD export CLI is missing: {path}. The runtime that ships cadgen "
            "must also ship packages/implicitjs; set CADGEN_NODE_PACKAGES to the packages "
            "directory that holds it."
        )
    return path


def _last_json_object(stdout: str) -> dict[str, object]:
    """The last JSON object printed on stdout, matching the contract every other cadgen
    export CLI uses. Tolerant of incidental output before it, exactly as
    ``cadgen_bridge`` and ``run_node_builder`` already are."""
    for line in reversed([line.strip() for line in str(stdout or "").splitlines()]):
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        if isinstance(payload, dict):
            return payload
    # `--json` pretty-prints, so the object spans lines; parse the whole stream as a
    # fallback before giving up.
    try:
        payload = json.loads(str(stdout or ""))
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        return payload
    raise NodeBuilderError(
        "The implicit CAD export CLI printed no result JSON. It must be run with --json."
    )


def export_implicit_model(
    *,
    source_path: Path,
    fmt: str,
    out_path: Path,
    resolution: int | None = None,
    params: str = "",
    animation: str = "",
) -> dict[str, object]:
    """Mesh ``source_path`` and write it to ``out_path`` in ``fmt``. Returns the payload the
    CLI prints (``{"ok": true, "path": ..., "filename": ...}``)."""
    resolved_source = Path(source_path).expanduser().resolve()
    if not resolved_source.is_file():
        raise FileNotFoundError(f"Implicit CAD source does not exist: {resolved_source}")
    if not is_implicit_source_path(resolved_source):
        raise RuntimeError(
            f"Implicit CAD export requires a <name>.implicit.js source: {resolved_source}"
        )
    export_format = normalize_export_format(fmt)
    destination = Path(out_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "--input", str(resolved_source),
        f"--{export_format}", str(destination),
        "--json",
    ]
    if resolution is not None:
        args += ["--resolution", str(int(resolution))]
    if str(params or "").strip():
        args += ["--params", str(params)]
    if str(animation or "").strip():
        args += ["--animation", str(animation)]
    argv = [
        cad_node_executable(),
        "--import",
        node_resolve_bootstrap(),
        str(implicit_export_cli()),
        *args,
    ]
    with generator_busy(IMPLICIT_PACKAGE, render_package_dir(resolved_source)):
        proc = subprocess.run(  # noqa: S603 - argv is fully constructed, never shell-parsed
            argv,
            env=node_child_env(),
            capture_output=True,
            text=True,
            check=False,
        )
    if proc.returncode != 0:
        detail = str(proc.stderr or "").strip().splitlines()
        raise NodeBuilderError(
            "Implicit CAD export failed"
            + (f": {detail[0]}" if detail else f" with exit code {proc.returncode}")
        )
    payload = _last_json_object(proc.stdout)
    files = payload.get("files")
    written = files[0] if isinstance(files, list) and files and isinstance(files[0], dict) else {}
    written_path = Path(str(written.get("output") or destination)).resolve()
    if not written_path.is_file():
        raise NodeBuilderError(f"Implicit CAD export wrote no file: {written_path}")
    return {
        "ok": True,
        "path": str(written_path),
        "filename": written_path.name,
        "format": export_format,
        "sourcePath": relative_to_cwd(resolved_source),
        "bytes": int(written.get("bytes") or written_path.stat().st_size),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cadgen.implicit_export",
        description="Export one .implicit.js model to a standalone STL/3MF/GLB file.",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository/workspace root (accepted for CLI parity with step_export_target).",
    )
    parser.add_argument("--source-path", required=True, help="Implicit CAD source (<name>.implicit.js).")
    parser.add_argument("--format", required=True, choices=list(IMPLICIT_EXPORT_FORMATS))
    parser.add_argument("--out", required=True, help="Destination file path.")
    parser.add_argument("--resolution", type=int, help="Longest-axis sampling resolution.")
    parser.add_argument("--params", default="", help="JSON object of implicit parameter values.")
    parser.add_argument("--animation", default="", help="JSON object of implicit animation state.")
    return parser


def run_cli_payload(
    argv: list[str] | None = None,
    *,
    reset_runtime_closure: bool = False,
) -> dict[str, object]:
    """Parse CLI ``argv`` and run :func:`export_implicit_model`, RETURNING its payload and
    RAISING on failure -- callers own the error envelope. The in-process primitive shared by
    ``main()`` and the CAD Viewer's warm worker.

    ``reset_runtime_closure`` is accepted for parity with the STEP and DXF entrypoints and
    ignored for the same reason :mod:`cadgen.implicit_artifact` ignores it: the model is a JS
    module loaded in a Node child that exits with the run, so there is no warm Python
    generator-module state to evict."""
    del reset_runtime_closure
    args = build_parser().parse_args(argv)
    del args.repo_root  # payload paths are absolute; kept for CLI parity
    return export_implicit_model(
        source_path=Path(args.source_path),
        fmt=args.format,
        out_path=Path(args.out),
        resolution=args.resolution,
        params=args.params,
        animation=args.animation,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        payload = run_cli_payload(argv)
    except Exception as exc:  # noqa: BLE001 - the contract is one JSON line, always
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")))
        return 1
    print(json.dumps(payload, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
