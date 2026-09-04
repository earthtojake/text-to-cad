"""The ONE mesh-export engine and its freshness ledger.

Every mesh serialization (STL/3MF/GLB) — a `@stl`/`@glb`/`@threemf`
declaration produced by a model-script run, or an ad-hoc `cadgen stl|3mf|glb
build` — funnels through :func:`run_mesh_exporter`, so the front doors cannot
drift: one Node invocation, one tessellation per distinct tolerance pair,
formats serialized from it (design/unified-tessellation.md).

Freshness rides content-keyed records in the store's ``index/mesh`` tier: a
record is keyed by the
WRITTEN file's bytes and names the source documents (by content hash) and the
effective tolerances that produced it. Both front doors read and write the
same ledger, so a CLI export satisfies a declaration's gate and vice versa.
Records are best-effort: losing one costs a re-export, never correctness.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MESH_EXPORT_BUILDER = "mesh-export.mjs"
MESH_EXPORT_RECORD_KIND = "mesh-export"

# Declarable formats, and the decorator that declares each (the digit rule
# forbids ``@3mf``, so 3MF's decorator is ``@threemf``).
MESH_EXPORT_FORMATS = ("stl", "3mf", "glb")
MESH_DECORATOR_FORMATS = {"stl": "stl", "glb": "glb", "threemf": "3mf"}
MESH_FORMAT_SUFFIX = {"stl": ".stl", "3mf": ".3mf", "glb": ".glb"}


@dataclass(frozen=True)
class MeshExportJob:
    """One output the exporter must write: format, destination, and the
    tolerances it tessellates at (``None`` = the tessellator's defaults). The
    geometry is the document's tree as stored; a mesh never moves it."""

    fmt: str
    out: Path
    mesh_tolerance: float | None = None
    mesh_angular_tolerance: float | None = None


def run_mesh_exporter(
    package_dir: Path,
    jobs: "list[MeshExportJob]",
    *,
    name: str,
    default_color: str | None,
    logger: Any,
) -> None:
    """STL/3MF/GLB through the ONE tessellation path.

    One Node invocation serves every job: the bundled exporter tessellates each
    component's exact surfaces once PER DISTINCT TOLERANCE PAIR — the same
    watertight tessellator the viewport uses — then serializes each job from
    its pair's tessellation. Boundary vertices lie on the exact STEP edge
    curves, colors carry per face/occurrence/part, and the bytes are
    deterministic. Tolerances are the tessellator's units — chord RELATIVE to
    each component's bounding diagonal, angular in radians."""
    import subprocess

    from cadgen._internal.node_runtime import cad_node_executable, node_builder_script

    argv = [
        str(cad_node_executable()),
        str(node_builder_script(MESH_EXPORT_BUILDER)),
        "--package-dir", str(package_dir),
        "--name", name,
    ]
    for job in jobs:
        argv += ["--format", job.fmt, "--out", str(job.out)]
        # Job-scoped: the Node CLI binds tolerance flags to the most recent
        # --format/--out pair (flags before any pair set the run defaults).
        if job.mesh_tolerance is not None:
            argv += ["--chord-tolerance", repr(float(job.mesh_tolerance))]
        if job.mesh_angular_tolerance is not None:
            argv += ["--angle-tolerance", repr(float(job.mesh_angular_tolerance))]
    if default_color is not None:
        argv += ["--default-color", default_color]
    label = "+".join(job.fmt for job in jobs)
    with logger.timed(f"tessellate + write {label}"):
        proc = subprocess.run(argv, capture_output=True, text=True)
    payload: dict = {}
    for line in reversed(proc.stdout.splitlines()):
        stripped = line.strip()
        if stripped.startswith("{"):
            try:
                payload = json.loads(stripped)
            except ValueError:
                pass
            break
    missing = [job.out for job in jobs if not job.out.is_file()]
    if not payload.get("ok") or missing:
        detail = str(payload.get("error") or proc.stderr or f"exit {proc.returncode}").strip()
        raise RuntimeError(f"mesh export failed for {label}: {detail}")


def _tolerance_token(value: float | None) -> str:
    return "default" if value is None else repr(float(value))


def _sha256_of(path: Path) -> str | None:
    import hashlib

    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def record_mesh_export(
    output_path: Path,
    *,
    model: Path,
    document_hash: str,
    fmt: str,
    mesh_tolerance: float | None,
    mesh_angular_tolerance: float | None,
) -> None:
    """Record a written mesh as one of the MODEL's outputs (STORE.md: mesh
    exports live in the model record, gated by clause 5). Best-effort."""
    try:
        from cadgen.store.records import read_record, write_record

        record = read_record(model)
        if record is None:
            return
        digest = _sha256_of(Path(output_path))
        if digest is None:
            return
        outputs = dict(record.get("outputs") or {})
        outputs[str(Path(output_path).expanduser().resolve())] = {
            "sha256": digest,
            "declared": fmt,
            "document": str(document_hash),
            "chord": _tolerance_token(mesh_tolerance),
            "angle": _tolerance_token(mesh_angular_tolerance),
        }
        record["outputs"] = outputs
        write_record(model, record)
    except Exception:  # noqa: BLE001 - a failed record only costs a re-export
        pass
    # The artifact-side ledger too, so a bare door on these same bytes is a no-op.
    record_document_mesh(
        output_path,
        document_hash=document_hash,
        fmt=fmt,
        mesh_tolerance=mesh_tolerance,
        mesh_angular_tolerance=mesh_angular_tolerance,
    )


def mesh_variant_key(
    fmt: str,
    mesh_tolerance: float | None,
    mesh_angular_tolerance: float | None,
) -> str:
    """One mesh variant of a document — format × chord × angle — the key of the
    ARTIFACT-side ledger (``index/document/<sha256(bytes)>.meshes``)."""
    return "|".join(
        (
            str(fmt),
            _tolerance_token(mesh_tolerance),
            _tolerance_token(mesh_angular_tolerance),
        )
    )


def record_document_mesh(
    output_path: Path,
    *,
    document_hash: str,
    fmt: str,
    mesh_tolerance: float | None,
    mesh_angular_tolerance: float | None,
) -> None:
    """A bare door's ledger: the mesh cut from THESE bytes at this variant has
    this sha. Artifact → artifact (STORE.md §2, the law) — no record is opened,
    so the same bytes anywhere satisfy the same door. Best-effort."""
    try:
        from cadgen.store.records import note_document_mesh

        digest = _sha256_of(Path(output_path))
        if digest:
            key = mesh_variant_key(fmt, mesh_tolerance, mesh_angular_tolerance)
            note_document_mesh(str(document_hash), key, digest)
    except Exception:  # noqa: BLE001 - a failed ledger only costs a re-export
        pass


def document_mesh_current(
    output_path: Path,
    *,
    document_hash: str | None,
    fmt: str,
    mesh_tolerance: float | None,
    mesh_angular_tolerance: float | None,
) -> bool:
    """Whether the mesh on disk is THE export of these document bytes at this
    variant: the document entry's ledger names its sha and the bytes verify."""
    from cadgen.store.records import document_mesh_sha

    path = Path(output_path)
    if not document_hash or not path.is_file():
        return False
    key = mesh_variant_key(fmt, mesh_tolerance, mesh_angular_tolerance)
    expected = document_mesh_sha(str(document_hash), key)
    return bool(expected) and _sha256_of(path) == expected


def mesh_export_current(
    output_path: Path,
    *,
    model: Path,
    document_hash: str | None,
    mesh_tolerance: float | None,
    mesh_angular_tolerance: float | None,
) -> bool:
    """Whether the mesh on disk is the CURRENT export of this model's document
    at these tolerances: the model record lists it with matching document hash
    and tolerance pair — and its bytes verify."""
    from cadgen.store.records import read_record

    path = Path(output_path)
    if not document_hash or not path.is_file():
        return False
    record = read_record(model)
    if record is None:
        return False
    entry = (record.get("outputs") or {}).get(str(path.expanduser().resolve()))
    if not isinstance(entry, dict):
        return False
    return (
        entry.get("document") == str(document_hash)
        and entry.get("chord") == _tolerance_token(mesh_tolerance)
        and entry.get("angle") == _tolerance_token(mesh_angular_tolerance)
        and _sha256_of(path) == entry.get("sha256")
    )
