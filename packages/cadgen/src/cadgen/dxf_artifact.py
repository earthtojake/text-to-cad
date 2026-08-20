from __future__ import annotations

import argparse
import json
from pathlib import Path

from cadgen.cli_logging import CliLogger
from cadgen._internal.cli_locking import (
    add_lock_timeout_argument,
    contended_payload,
    deadline_ms,
    lock_wait_notice,
)
from cadgen.coordination import DRAWING_PACKAGE, PHASE_FINALIZE, artifact_build
from cadgen._internal.drawing_package import (
    drawing_package_current,
    export_drawing_dxf,
    load_drawing_descriptor,
    write_imported_drawing_package,
)
from cadgen._internal.generation import (
    cli_progress_line,
    _entry_spec_from_source,
    run_script_generator,
)
from cadgen.catalog import (
    render_package_dir,
    is_dxf_generator_path,
    source_from_path,
)
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
        dxf_ref = str(descriptor.get("dxf") or "").strip()
        if dxf_ref:
            payload["dxfPath"] = relative_to_cwd(package_dir / dxf_ref)
        preview_ref = str(descriptor.get("preview") or "").strip()
        if preview_ref:
            payload["previewPath"] = relative_to_cwd(package_dir / preview_ref)
        source_hash = str(descriptor.get("sourceHash") or "").strip()
        if source_hash:
            payload["sourceHash"] = source_hash
        source_digest = str(descriptor.get("sourceDigest") or "").strip()
        if source_digest:
            payload["sourceDigest"] = source_digest
        dxf_hash = str(descriptor.get("dxfHash") or "").strip()
        if dxf_hash:
            payload["dxfHash"] = dxf_hash
    if skipped:
        payload["skipped"] = True
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cadgen.dxf_artifact",
        description="Generate the CAD Viewer drawing-package artifact for one DXF entry.",
    )
    parser.add_argument("--repo-root", default=".", help="Repository/workspace root (accepted for CLI parity with step_artifact_cli).")
    parser.add_argument(
        "--source-path",
        required=True,
        help="A gen_dxf() generator (<name>.dxf.py) or an imported <name>.dxf.",
    )
    parser.add_argument("--export", help="Also write the (fresh) drawing DXF to this path.")
    parser.add_argument("--force", action="store_true", help="Regenerate even if a current artifact exists.")
    parser.add_argument("--verbose", action="store_true", help="Show detailed timing on stderr.")
    add_lock_timeout_argument(parser)
    return parser


def _validate_generator(source_path: Path):
    source = source_from_path(source_path)
    if source is None or source.kind != "dxf" or source.generator_metadata is None:
        raise RuntimeError(f"Python generator is not a gen_dxf() CAD source: {source_path}")
    if not is_dxf_generator_path(source_path):
        raise RuntimeError(
            f"Viewer drawing artifacts require a dedicated <name>.dxf.py generator: {source_path}"
        )
    return source


def build_dxf_artifact(
    *,
    repo_root: Path,
    source_path: Path,
    export: Path | None = None,
    force: bool = False,
    reset_runtime_closure: bool = False,
    logger: CliLogger | None = None,
    lock_timeout_s: float = 0.0,
) -> dict[str, object]:
    """Build the drawing-package artifact for one DXF entry and RETURN the result payload
    (the exact dict the CLI prints). Mirrors :func:`cadgen.step_artifact_cli.build_step_artifact`
    for the DXF pipeline, and takes the same two inputs STEP does:

    * a ``<name>.dxf.py`` generator — run it, and the package holds what it produced;
    * an imported ``<name>.dxf`` — no generator to run, so the drawing is copied in.

    Either way the package's 3D ``preview.glb`` is baked by a Node child **inside this
    function's lock**: one run id, one status record, one progress bar across both runtimes
    (design §7.4.2). With ``export`` set, the fresh drawing DXF is also written to that path.
    """
    del repo_root  # payload paths are cwd-relative; kept for CLI parity with step_artifact_cli
    resolved_source = Path(source_path).expanduser().resolve()
    if not resolved_source.is_file():
        raise FileNotFoundError(f"DXF source does not exist: {resolved_source}")
    imported = resolved_source.suffix.lower() == ".dxf"
    source = None if imported else _validate_generator(resolved_source)
    if logger is None:
        logger = CliLogger("dxf-artifact", verbose=False)
    package_dir = render_package_dir(resolved_source)
    # The WHOLE body is coordinated, not just the generator run. Previously the currency
    # gate ran outside the lock, the generator took the lock and released it on return, and
    # the descriptor read and DXF export then ran unlocked -- so a concurrent build could
    # rewrite the package between the generator finishing and the descriptor being read.
    # This also gives a drawing build a progress record for the first time: no DXF code
    # path wrote one at all, so the viewer could never show a bar for a drawing.
    with cli_progress_line(
        relative_to_cwd(resolved_source), logger=logger, fallback="Building..."
    ) as progress_sink, artifact_build(
        DRAWING_PACKAGE,
        package_dir,
        is_current=lambda: drawing_package_current(resolved_source),
        force=force,
        deadline_ms=deadline_ms(lock_timeout_s),
        on_wait=lock_wait_notice(logger, relative_to_cwd(resolved_source)),
        sink=progress_sink,
    ) as run:
        if run.contended:
            logger.info(f"another run is building {relative_to_cwd(resolved_source)}; not waiting")
            return contended_payload(
                source_ref=relative_to_cwd(resolved_source), package_dir=package_dir
            )
        skipped = run.skipped
        if not skipped:
            if imported:
                # No generator, no ezdxf: copy the drawing in and bake its preview. The Node
                # mesh step is the only build stage an imported drawing has.
                write_imported_drawing_package(resolved_source, run=run)
            else:
                spec = _entry_spec_from_source(source)
                run_script_generator(
                    spec,
                    "gen_dxf",
                    logger=logger,
                    force=force,
                    reset_runtime_closure=reset_runtime_closure,
                    progress=run,
                )
        run.phase(PHASE_FINALIZE)
        descriptor = load_drawing_descriptor(package_dir)
        if descriptor is None:
            raise RuntimeError(
                f"drawing package was not produced: {relative_to_cwd(package_dir)}"
            )
        payload = _result_payload(resolved_source, descriptor=descriptor, skipped=skipped)
        if export is not None:
            export_path = export_drawing_dxf(resolved_source, Path(export))
            payload["path"] = str(export_path)
            payload["filename"] = export_path.name
        return payload


def run_cli_payload(
    argv: list[str] | None = None,
    *,
    reset_runtime_closure: bool = False,
) -> dict[str, object]:
    """Parse CLI ``argv`` and run :func:`build_dxf_artifact`, RETURNING its payload.
    The in-process primitive shared by ``main()`` and the CAD Viewer's warm worker —
    the worker passes ``reset_runtime_closure=True`` so repeated warm builds record
    the same closure a cold CLI does."""
    args = build_parser().parse_args(argv)
    logger = CliLogger("dxf-artifact", verbose=bool(args.verbose))
    payload = build_dxf_artifact(
        repo_root=Path(args.repo_root),
        source_path=Path(args.source_path),
        export=Path(args.export) if args.export else None,
        force=bool(args.force),
        reset_runtime_closure=reset_runtime_closure,
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
