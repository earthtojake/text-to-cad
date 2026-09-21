"""The ONE mesh-export engine and its freshness ledger.

Every mesh serialization (STL/3MF/GLB) — a `@stl`/`@glb`/`@threemf`
declaration produced by a model-script run, or an ad-hoc `cadgen stl|3mf|glb
build` — funnels through :func:`run_mesh_exporter`, so the front doors cannot
drift: one Node invocation, one tessellation per distinct tolerance pair,
formats serialized from it (design/unified-tessellation.md).

Freshness rides content-keyed records in the store's ``index/mesh`` tier: a
record is keyed by the
WRITTEN file's bytes and names the source documents (by content hash) and the
effective tolerances that produced it — plus, for an animated GLB, the clip
request and embedded animation source that produced the motion, which the document's
own bytes do not cover. Both front doors read and write the
same ledger, so a CLI export satisfies a declaration's gate and vice versa.
Records are best-effort: losing one costs a re-export, never correctness.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cadgen._internal.mesh_animation import AnimationSnapshot

MESH_EXPORT_BUILDER = "mesh-export.mjs"
MESH_EXPORT_RECORD_KIND = "mesh-export"
# Mirrored by cadgen-js/glb/writeGlb.js. This is the final GLB serializer's
# revision, not the glTF container version and not a tessellation-cache salt.
GLB_SERIALIZATION_VERSION = 3

# Declarable formats, and the decorator that declares each (the digit rule
# forbids ``@3mf``, so 3MF's decorator is ``@threemf``).
MESH_EXPORT_FORMATS = ("stl", "3mf", "glb")
MESH_DECORATOR_FORMATS = {"stl": "stl", "glb": "glb", "threemf": "3mf"}
MESH_FORMAT_SUFFIX = {"stl": ".stl", "3mf": ".3mf", "glb": ".glb"}


@dataclass(frozen=True)
class MeshExportJob:
    """One output the exporter must write: format, destination, and the
    tolerances it tessellates at (``None`` = the tessellator's defaults). The
    geometry is the document's tree as stored; a mesh never moves it.

    ``animation`` is the GLB door's clip request (cadgen._internal.mesh_animation)
    and nothing else carries one: a clip becomes glTF node animation, which STL
    and 3MF have nowhere to put. ``animation_key`` is that request plus the
    embedded animation source, folded into the freshness variant so an edited clip
    is a miss rather than a stale file reported current.
    """

    fmt: str
    out: Path
    mesh_tolerance: float | None = None
    mesh_angular_tolerance: float | None = None
    animation: dict | None = None
    animation_key: str | None = None


def run_mesh_exporter(
    package_dir: Path,
    jobs: "list[MeshExportJob]",
    *,
    name: str,
    default_color: str | None,
    logger: Any,
    animation_source: AnimationSnapshot | None = None,
    appearance: object = None,
) -> dict:
    """STL/3MF/GLB through the ONE tessellation path.

    One Node invocation serves every job: the bundled exporter tessellates each
    component's exact surfaces once PER DISTINCT TOLERANCE PAIR — the same
    watertight tessellator the viewport uses — then serializes each job from
    its pair's tessellation. Boundary vertices lie on the exact STEP edge
    curves, colors carry per face/occurrence/part, and the bytes are
    deterministic. Tolerances are the tessellator's units — chord RELATIVE to
    each component's bounding diagonal, angular in radians.

    ``animation_source`` captures ``animation.source`` from the DOCUMENT's sidecar, and is required
    exactly when a job carries an ``animation``: the builder compiles its pinned text through
    the same loader the viewer uses and samples the named clip into keyframes.
    Returns the builder's payload, whose per-file ``animation`` block reports
    what was baked and what the sampling could not carry."""
    import subprocess
    import tempfile
    from contextlib import ExitStack

    from cadgen._internal.node_runtime import cad_node_executable, node_builder_script

    if appearance is not None:
        from cadgen._internal.source_sidecar import apply_appearance

        # export_view supplies a private projection; immutable store objects
        # and component tessellation identities remain unchanged.
        descriptor_path = package_dir / "assembly.json"
        descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
        descriptor_path.write_text(json.dumps(apply_appearance(descriptor, appearance), sort_keys=True), encoding="utf-8")

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
        # Job-scoped for the same reason: a clip belongs to ONE output, and a
        # run-level default would animate formats that cannot carry it.
        if job.animation is not None:
            argv += ["--animation", json.dumps(job.animation, sort_keys=True, separators=(",", ":"))]
    if default_color is not None:
        argv += ["--default-color", default_color]
    label = "+".join(job.fmt for job in jobs)
    with ExitStack() as resources:
        if animation_source is not None:
            module_dir = Path(resources.enter_context(tempfile.TemporaryDirectory(
                prefix="cadgen-animation-source-",
            )))
            module_path = module_dir / animation_source.path.name
            module_path.write_text(animation_source.source, encoding="utf-8", newline="")
            # The shared loader imports text via a data URL (relative imports
            # are unsupported). Preserve its original filename in diagnostics;
            # the mutable document sibling is never read again by this export.
            argv += ["--animation-source", str(module_path)]
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
    # What the sampling could not carry -- a frozen opacity, a tube shipped at
    # rest, a span past the end of a clip that does not loop -- rides the payload
    # to the caller's RESULT rather than the log. The builder refuses anything
    # worse; these are the choices the caller already made, and a file that made
    # them silently is the whole failure this door avoids. Logging them here as
    # well would say each one twice to a human and still leave --json silent.
    return payload


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
    animation_key: str | None = None,
    appearance_key: str | None = None,
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
        output_entry = {
            "sha256": digest,
            "declared": fmt,
            "document": str(document_hash),
            "chord": _tolerance_token(mesh_tolerance),
            "angle": _tolerance_token(mesh_angular_tolerance),
            "anim": animation_key,
            "appearance": _appearance_key(appearance_key),
        }
        serialization_version = _serialization_version(fmt)
        if serialization_version is not None:
            output_entry["serializer"] = serialization_version
        outputs[str(Path(output_path).expanduser().resolve())] = output_entry
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
        animation_key=animation_key,
        appearance_key=appearance_key,
    )


def _appearance_key(value: str | None) -> str:
    from cadgen._internal.source_sidecar import appearance_digest

    return value if value is not None else appearance_digest(None)


def _serialization_version(fmt: str) -> int | None:
    return GLB_SERIALIZATION_VERSION if str(fmt) == "glb" else None


def mesh_variant_key(
    fmt: str,
    mesh_tolerance: float | None,
    mesh_angular_tolerance: float | None,
    animation_key: str | None = None,
    appearance_key: str | None = None,
) -> str:
    """One mesh variant of a document — format × serializer × chord × angle × clip — the key
    of the ARTIFACT-side ledger (``index/document/<sha256(bytes)>.meshes``).

    Only GLB carries a serializer revision; STL/3MF variants stay unchanged.
    An ANIMATED GLB appends the clip request folded with the embedded animation
    bytes (mesh_animation.animation_variant_token), so it can never be satisfied
    by the static file at the same path, nor by a GLB of a clip since edited."""
    serialization_version = _serialization_version(fmt)
    return "|".join(
        (
            str(fmt),
            _tolerance_token(mesh_tolerance),
            _tolerance_token(mesh_angular_tolerance),
        )
        + (() if serialization_version is None else (f"serializer:{serialization_version}",))
        + (f"appearance:{_appearance_key(appearance_key)}",)
        + (() if animation_key is None else (f"anim:{animation_key}",))
    )


def record_document_mesh(
    output_path: Path,
    *,
    document_hash: str,
    fmt: str,
    mesh_tolerance: float | None,
    mesh_angular_tolerance: float | None,
    animation_key: str | None = None,
    appearance_key: str | None = None,
) -> None:
    """A bare door's ledger: the mesh cut from THESE bytes at this variant has
    this sha. Artifact → artifact (STORE.md §2, the law) — no record is opened,
    so the same bytes anywhere satisfy the same door. Best-effort."""
    try:
        from cadgen.store.records import note_document_mesh

        digest = _sha256_of(Path(output_path))
        if digest:
            key = mesh_variant_key(fmt, mesh_tolerance, mesh_angular_tolerance, animation_key, appearance_key)
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
    animation_key: str | None = None,
    appearance_key: str | None = None,
) -> bool:
    """Whether the mesh on disk is THE export of these document bytes at this
    variant: the document entry's ledger names its sha and the bytes verify."""
    from cadgen.store.records import document_mesh_sha

    path = Path(output_path)
    if not document_hash or not path.is_file():
        return False
    key = mesh_variant_key(fmt, mesh_tolerance, mesh_angular_tolerance, animation_key, appearance_key)
    expected = document_mesh_sha(str(document_hash), key)
    return bool(expected) and _sha256_of(path) == expected


def mesh_export_current(
    output_path: Path,
    *,
    model: Path,
    document_hash: str | None,
    mesh_tolerance: float | None,
    mesh_angular_tolerance: float | None,
    animation_key: str | None = None,
    appearance_key: str | None = None,
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
        and entry.get("anim") == animation_key
        and entry.get("appearance") == _appearance_key(appearance_key)
        and entry.get("serializer") == _serialization_version(entry.get("declared"))
        and _sha256_of(path) == entry.get("sha256")
    )
