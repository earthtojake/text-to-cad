"""Build the CAD Viewer render package for one implicit CAD model.

The implicit analogue of :mod:`cadgen.dxf_artifact`, and the SINGLE producer behind both
entrypoints that build an implicit package -- ``skills/implicit-cad/scripts/gen`` and the
viewer's ``POST /__cad/artifact``. A second producer that assembled the lock, the status
record and the currency gate by hand is exactly how the defects the coordination refactor
fixed came to exist.

The whole body runs inside ``artifact_build``: the lock is held across the freshness
re-check, the Node mesher, and the descriptor write. The mesher is a CHILD of this process
(``packages/cadjs/bin/implicit-artifact.mjs``) and dies with it -- an orphaned builder still
writing into a package no one holds a lock over is the failure mode this shape exists to
prevent (§4.1-§4.3).

No OCP: an implicit model is GLSL and JS, so nothing here loads a CAD runtime.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cadgen._internal.implicit_package import (
    implicit_package_current,
    is_implicit_source_path,
    load_implicit_descriptor,
    normalize_bake_resolution,
    write_implicit_package,
)
from cadgen.catalog import render_package_dir
from cadgen.cli_logging import CliLogger
from cadgen._internal.cli_locking import (
    add_lock_timeout_argument,
    contended_payload,
    deadline_ms,
    lock_wait_notice,
)
from cadgen.coordination import IMPLICIT_PACKAGE, artifact_build
from cadgen.render import relative_to_cwd


def _result_payload(
    source_path: Path,
    *,
    descriptor: dict[str, object] | None,
    skipped: bool = False,
) -> dict[str, object]:
    package_dir = render_package_dir(source_path)
    payload: dict[str, object] = {
        "ok": True,
        "sourcePath": relative_to_cwd(source_path),
        "packagePath": relative_to_cwd(package_dir),
        "sourceKind": str((descriptor or {}).get("sourceKind") or "python"),
    }
    if descriptor:
        glb_ref = str(descriptor.get("glb") or "").strip()
        if glb_ref:
            payload["glbPath"] = relative_to_cwd(package_dir / glb_ref)
        closure_hash = str(descriptor.get("sourceClosureHash") or "").strip()
        if closure_hash:
            payload["sourceClosureHash"] = closure_hash
        bake_hash = str(descriptor.get("bakeHash") or "").strip()
        if bake_hash:
            payload["bakeHash"] = bake_hash
        bake = descriptor.get("bake")
        if isinstance(bake, dict) and bake.get("resolution") is not None:
            payload["resolution"] = bake["resolution"]
        stats = descriptor.get("stats")
        if isinstance(stats, dict):
            payload["stats"] = dict(stats)
    if skipped:
        payload["skipped"] = True
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cadgen.implicit_artifact",
        description="Generate the CAD Viewer implicit-package artifact for one .implicit.js model.",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository/workspace root (accepted for CLI parity with step_artifact_cli).",
    )
    parser.add_argument("--source-path", required=True, help="Implicit CAD source path (<name>.implicit.js).")
    parser.add_argument(
        "--resolution",
        type=int,
        help="Longest-axis sampling resolution to bake. Default: the shipped bake resolution.",
    )
    parser.add_argument(
        "--threads",
        type=int,
        help="Worker threads for sampling/polygonizing. Default: this machine's parallelism.",
    )
    parser.add_argument(
        "--write-glb",
        metavar="OUTPUT",
        help="Also write an export-preset GLB to this path, from the same mesh pass.",
    )
    parser.add_argument("--force", action="store_true", help="Regenerate even if a current artifact exists.")
    parser.add_argument("--verbose", action="store_true", help="Show detailed timing on stderr.")
    add_lock_timeout_argument(parser)
    return parser


def build_implicit_artifact(
    *,
    repo_root: Path,
    source_path: Path,
    resolution: int | None = None,
    threads: int | None = None,
    write_glb: Path | None = None,
    force: bool = False,
    logger: CliLogger | None = None,
    sink: object | None = None,
    lock_timeout_s: float = 0.0,
) -> dict[str, object]:
    """Build the implicit package for one model and RETURN the result payload (the exact
    dict the CLI prints). Mirrors :func:`cadgen.dxf_artifact.build_dxf_artifact`.

    ``write_glb`` also leaves an export-preset GLB at that path. A requested sibling that is
    not on disk makes the build NOT current -- the mesh is what produces both files, and
    unlike a cached DXF the package's compressed render GLB cannot be turned back into an
    export one -- so asking for a missing sibling re-bakes, and asking for one that is
    already there costs nothing."""
    del repo_root  # payload paths are cwd-relative; kept for CLI parity with step_artifact_cli
    resolved_source = Path(source_path).expanduser().resolve()
    if not resolved_source.is_file():
        raise FileNotFoundError(f"Implicit CAD source does not exist: {resolved_source}")
    if not is_implicit_source_path(resolved_source):
        raise RuntimeError(
            f"Implicit render artifacts require a <name>.implicit.js source: {resolved_source}"
        )
    if logger is None:
        logger = CliLogger("implicit-artifact", verbose=False)
    bake_resolution = normalize_bake_resolution(resolution)
    sibling = Path(write_glb).expanduser().resolve() if write_glb is not None else None
    package_dir = render_package_dir(resolved_source)

    def _is_current() -> bool:
        if sibling is not None and not sibling.is_file():
            return False
        return implicit_package_current(resolved_source, resolution=bake_resolution)

    with artifact_build(
        IMPLICIT_PACKAGE,
        package_dir,
        is_current=_is_current,
        force=force,
        sink=sink,
        deadline_ms=deadline_ms(lock_timeout_s),
        on_wait=lock_wait_notice(logger, relative_to_cwd(resolved_source)),
    ) as run:
        if run.contended:
            logger.info(f"another run is building {relative_to_cwd(resolved_source)}; not waiting")
            return contended_payload(
                source_ref=relative_to_cwd(resolved_source), package_dir=package_dir
            )
        if run.skipped:
            payload = _result_payload(
                resolved_source,
                descriptor=load_implicit_descriptor(package_dir),
                skipped=True,
            )
        else:
            logger.debug(
                f"meshing {relative_to_cwd(resolved_source)} at resolution {bake_resolution}"
            )
            payload = _result_payload(
                resolved_source,
                descriptor=write_implicit_package(
                    resolved_source,
                    run=run,
                    resolution=bake_resolution,
                    threads=threads,
                    write_glb=sibling,
                ),
            )
        if sibling is not None:
            payload["path"] = str(sibling)
            payload["filename"] = sibling.name
        return payload


def run_cli_payload(
    argv: list[str] | None = None,
    *,
    reset_runtime_closure: bool = False,
) -> dict[str, object]:
    """Parse CLI ``argv`` and run :func:`build_implicit_artifact`, RETURNING its payload.
    The in-process primitive shared by ``main()``, the CAD Viewer's warm worker, and any
    caller that wants the dict rather than the printed line.

    ``reset_runtime_closure`` is accepted for parity with the STEP and DXF entrypoints and
    is deliberately ignored: those evict the warm interpreter's cached generator MODULES
    between builds, and an implicit model has none here -- it is a JS module loaded fresh in
    a Node child that exits with the build, so every run starts cold by construction."""
    del reset_runtime_closure
    args = build_parser().parse_args(argv)
    logger = CliLogger("implicit-artifact", verbose=bool(args.verbose))
    payload = build_implicit_artifact(
        repo_root=Path(args.repo_root),
        source_path=Path(args.source_path),
        resolution=args.resolution,
        threads=args.threads,
        write_glb=Path(args.write_glb) if args.write_glb else None,
        force=bool(args.force),
        logger=logger,
        lock_timeout_s=float(args.lock_timeout or 0.0),
    )
    logger.total()
    return payload


def main(argv: list[str] | None = None) -> int:
    payload = run_cli_payload(argv)
    print(json.dumps(payload, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
