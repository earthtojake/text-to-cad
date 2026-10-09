"""The ONE mesh-export engine and its freshness ledger.

Every mesh serialization (STL/3MF/GLB) — a `@stl`/`@glb`/`@threemf`
declaration produced by a model-script run, or an ad-hoc `cadgen stl|3mf|glb
build` — funnels through :func:`run_mesh_exporter`, so the front doors cannot
drift: the document's tree, the store's mesh of each component at each distinct
tolerance pair, and every format serialized from those same meshes
(``cadgen._internal.mesh_formats``; a clip's keys go in as glTF animation by
``cadgen._internal.glb_animation``, a bending tube as a skin by
``cadgen._internal.tube_skin``). The meshes are OCCT's, of each component's
exact BREP, derived in the build pool when the store lacks them -- the ones the
CAD Viewer and snapshots draw. Nothing here spawns a process of its own.

Freshness rides content-keyed records in the store's ``index/mesh`` tier: a
record is keyed by the
WRITTEN file's bytes and names the source documents (by content hash) and the
effective tolerances that produced it — plus, for an animated GLB, the clip
request and the sidecar keyframes that produced the motion, which the document's
own bytes do not cover. Both front doors read and write the
same ledger, so a CLI export satisfies a declaration's gate and vice versa.
Records are best-effort: losing one costs a re-export, never correctness.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cadgen._internal.mesh_animation import AnimationSnapshot

# Each format's final-byte revision: what the ledger compares beside the document
# and the tolerances, so a change to one format's bytes makes its ledgered exports
# misses without touching geometry or the store's meshes. Not the glTF container
# version and not a tessellation-cache salt. GLB 4, STL 1 and 3MF 1: OCCT's stored
# meshes and this package's writers replaced the JavaScript tessellator and
# serializers, so no file either wrote is reported current.
SERIALIZATION_VERSIONS = {"glb": 4, "stl": 1, "3mf": 1}
GLB_SERIALIZATION_VERSION = SERIALIZATION_VERSIONS["glb"]

# Declarable formats, and the decorator that declares each (the digit rule
# forbids ``@3mf``, so 3MF's decorator is ``@threemf``).
MESH_EXPORT_FORMATS = ("stl", "3mf", "glb")
MESH_DECORATOR_FORMATS = {"stl": "stl", "glb": "glb", "threemf": "3mf"}
MESH_FORMAT_SUFFIX = {"stl": ".stl", "3mf": ".3mf", "glb": ".glb"}


@dataclass(frozen=True)
class MeshExportJob:
    """One output the exporter must write: format, destination, and the
    tolerances it meshes at (``None`` = the store's defaults,
    ``cadgen.store.meshes.DEFAULT_CHORD``/``DEFAULT_ANGLE``). The geometry is the
    document's tree as stored; a mesh never moves it.

    ``animation`` is the GLB door's clip request (cadgen._internal.mesh_animation)
    and nothing else carries one: a clip becomes glTF node animation, which STL
    and 3MF have nowhere to put. ``animation_key`` is that request plus the
    sidecar's keyframes, folded into the freshness variant so a rebaked clip
    is a miss rather than a stale file reported current.
    """

    fmt: str
    out: Path
    mesh_tolerance: float | None = None
    mesh_angular_tolerance: float | None = None
    animation: dict | None = None
    animation_key: str | None = None


@dataclass(frozen=True)
class MeshSource:
    """What an export cuts its meshes from: a geometry tree, and the saved document
    whose bytes selected it (``None`` for a mesh-only model, whose tree is its own
    geometry). The document's index entry may name the surface producer its meshes
    were derived under, which spares a producer job."""

    tree: str
    document_hash: str | None = None


def run_mesh_exporter(
    source: MeshSource,
    jobs: "list[MeshExportJob]",
    *,
    name: str,
    default_color: str | None,
    logger: Any,
    animation_source: AnimationSnapshot | None = None,
    appearance: object = None,
) -> dict:
    """STL/3MF/GLB through the ONE mesh path.

    Every job is served from the store's mesh of each component at its tolerance
    pair -- chord RELATIVE to each component's bounding diagonal, angle in radians --
    derived ONCE per distinct pair, in one build-pool job, for whatever the store
    lacks. Each occurrence's placement is baked in, colours carry per
    face/occurrence/part, and the bytes are deterministic.

    ``appearance`` is the document sidecar's, applied to a private projection of
    the tree. ``animation_source`` captures the DOCUMENT sidecar's ``animation``
    keyframes, and is required exactly when a job carries an ``animation``: that
    job's clip is resampled at its frame rate into glTF node animation. Returns
    ``{"ok": True, "files": [{path, format, triangleCount, animation?, warnings?}, ...]}``
    in job order; an animated file's ``animation`` block reports what was baked and,
    under ``warnings``, what the sampling could not carry -- the choices the
    caller made, for its RESULT rather than the log, where ``--json`` would never
    hear them. A file's own ``warnings`` name the faces no mesher could cover
    (``cadgen.store.meshes`` ``unmeshedFaces``), which it leaves open. Anything
    worse raises, and a job that raises leaves no file."""
    from cadgen.store import meshes

    label = "+".join(job.fmt for job in jobs)
    pairs = [
        (
            float(meshes.DEFAULT_CHORD if job.mesh_tolerance is None else job.mesh_tolerance),
            float(meshes.DEFAULT_ANGLE if job.mesh_angular_tolerance is None else job.mesh_angular_tolerance),
        )
        for job in jobs
    ]
    _check_jobs(jobs, pairs, animation_source)
    with logger.timed(f"tessellate + write {label}"):
        return _export(source, jobs, pairs, name=name, default_color=default_color,
                       animation_source=animation_source, appearance=appearance)


def _check_jobs(jobs: "list[MeshExportJob]", pairs: list, animation_source: AnimationSnapshot | None) -> None:
    """Refuse a request no file should come out of, before any meshing."""
    from cadgen.store.meshes import normalize_tessellations

    if not jobs:
        raise ValueError("mesh export needs at least one output")
    if len({job.out for job in jobs}) != len(jobs):
        raise ValueError("mesh export outputs must be distinct paths")
    for job, (chord, angle) in zip(jobs, pairs):
        if job.fmt not in MESH_EXPORT_FORMATS:
            raise ValueError(f"mesh export format must be one of {', '.join(MESH_EXPORT_FORMATS)}, got {job.fmt!r}")
        try:
            normalize_tessellations([{"chordTolerance": chord, "angleTolerance": angle}])
        except ValueError as error:
            raise ValueError(f"{job.fmt} export at chord {chord:g}, angle {angle:g}: {error}") from None
        if job.animation is not None:
            if job.fmt != "glb":
                raise ValueError(f"{job.fmt} carries no animation: only glb does")
            if animation_source is None:
                raise ValueError("an animated export needs the document sidecar's animation keyframes")


def _export(source: MeshSource, jobs: "list[MeshExportJob]", pairs: list, *, name: str,
            default_color: str | None, animation_source: AnimationSnapshot | None, appearance: object) -> dict:
    from cadgen._internal import glb_animation
    from cadgen._internal.atomic_replace import write_bytes_atomic
    from cadgen._internal.mesh_formats import (
        build_primitives,
        decode_tessellation,
        glb_bytes,
        stl_bytes,
        threemf_bytes,
        total_triangles,
    )
    from cadgen.store import meshes

    descriptor, bodies = stored_meshes(source, sorted(set(pairs)), appearance)
    used = _used_components(descriptor)
    # Parsed only when a job asks for a clip; the captured text, never the sidecar.
    animation = json.loads(animation_source.data) if any(job.animation for job in jobs) and animation_source else None
    writers = {"stl": stl_bytes, "3mf": threemf_bytes, "glb": glb_bytes}
    files: list[dict | None] = [None] * len(jobs)
    for pair in sorted(set(pairs)):
        tessellations = {cid: decode_tessellation(bodies[(cid, pair)]) for cid in used}
        unmeshed = {cid: faces for cid in used if (faces := meshes.unmeshed_faces(bodies[(cid, pair)]))}
        # Every static job of one pair shares one primitive build. An ANIMATED job
        # builds its own: its nodes are per occurrence, and what its clip drops (an
        # occurrence hidden at start, one faded) changes which primitives exist.
        static = None
        for index, job in enumerate(jobs):
            if pairs[index] != pair:
                continue
            summary = None
            clip_data = None
            if job.animation is not None:
                clip = glb_animation.find_clip(animation, str(job.animation["clip"]))
                window = glb_animation.resolve_window(job.animation, clip)
                gltf_clip = glb_animation.clip_to_gltf(clip, window, drop=job.animation.get("drop") or ())
                # A bending tube's own primitives: its mesh refined and bound to its
                # skin, in place of the rest tessellation the build would place.
                primitives = build_primitives(
                    descriptor, tessellations, default_color=default_color, per_occurrence=True,
                    hidden=gltf_clip.hidden, opacity=gltf_clip.opacity,
                    overrides=_skinned_tubes(descriptor, tessellations, gltf_clip, default_color),
                )
                # The clip names the DOCUMENT's occurrences, the file holds what
                # meshed: an occurrence with no geometry is a named warning, never
                # a node that carries nothing.
                clip_data = glb_animation.restrict_to_nodes(
                    gltf_clip, {primitive.node for primitive in primitives if primitive.node})
                summary = {
                    "clip": clip_data.name, "seconds": window.seconds, "start": window.start,
                    "pivots": len(clip_data.pivots), "skins": len(clip_data.skins),
                    "joints": sum(len(skin.fractions) for skin in clip_data.skins),
                    "warnings": list(clip_data.warnings),
                }
            else:
                if static is None:
                    static = build_primitives(descriptor, tessellations, default_color=default_color)
                primitives = static
            triangles = total_triangles(primitives)
            if not triangles:
                raise RuntimeError(f"mesh export failed for {job.fmt}: the tree produced no triangles")
            if job.fmt == "glb":
                payload = glb_bytes(primitives, name=name, animation=clip_data)
            else:
                payload = writers[job.fmt](primitives, name=name)
            write_bytes_atomic(job.out, payload)
            files[index] = {"path": str(job.out), "format": job.fmt, "triangleCount": triangles,
                            **({"animation": summary} if summary is not None else {}),
                            **({"warnings": _unmeshed_warnings(descriptor, unmeshed, job.out.name)}
                               if unmeshed else {})}
    return {"ok": True, "files": files}


def _unmeshed_warnings(descriptor: dict, unmeshed: dict, written: str) -> list[str]:
    """What a file written from meshes that leave faces out says of each such component:
    its occurrences, the faces, and that the file is open where they are."""
    from cadgen.store.meshes import unmeshed_warning

    occurrences = [occurrence for occurrence in descriptor.get("occurrences") or [] if isinstance(occurrence, dict)]
    name = written.replace("{", "{{").replace("}", "}}")
    return [unmeshed_warning([(str(occurrence.get("id")), str(occurrence.get("name") or ""))
                              for occurrence in occurrences if occurrence.get("component") == cid],
                             faces, name + " has a hole in place of {them}: it is not watertight")
            for cid, faces in unmeshed.items()]


def _skinned_tubes(descriptor: dict, tessellations: dict, clip: Any, default_color: str | None) -> dict:
    """Each bending tube's primitives, keyed by occurrence: its placed mesh refined and
    bound to its skin (``tube_skin.bind``), one primitive per face colour."""
    import numpy as np

    from cadgen._internal import tube_deformation, tube_skin
    from cadgen._internal.mesh_formats import Primitive, occurrence_colors, occurrence_world_mesh

    occurrences = {str(occurrence.get("id")): occurrence for occurrence in descriptor.get("occurrences") or []}
    overrides: dict[str, list] = {}
    for index, skin in enumerate(clip.skins):
        rest = tube_skin.compile_rest(skin.rest_path)
        for member in skin.members:
            occurrence = occurrences.get(member)
            tessellation = tessellations.get(str((occurrence or {}).get("component") or ""))
            if occurrence is None or tessellation is None:
                continue
            positions, normals, triangles, ranges = occurrence_world_mesh(occurrence, tessellation)
            if not len(triangles):
                continue
            bound = tube_skin.bind(tube_deformation.RestMesh(
                positions.astype(np.float32), normals.astype(np.float32), triangles.reshape(-1).astype(np.uint32),
            ), rest, skin.spacing, skin.fractions)
            refined = bound.indices.reshape(-1, 3)
            source = (bound.source_triangles if bound.source_triangles is not None
                      else np.arange(len(refined), dtype=np.int64))
            colors = occurrence_colors(descriptor, occurrence, tessellation, default_color)
            triangle_colors = np.asarray([colors[int(face)] for face in ranges[source]])
            primitives = []
            for color in sorted(set(triangle_colors.tolist())):
                used, local = np.unique(refined[triangle_colors == color], return_inverse=True)
                primitives.append(Primitive(
                    color=color, positions=bound.positions[used], normals=bound.normals[used],
                    indices=local.astype(np.uint32).reshape(-1), joints=bound.joints[used],
                    weights=bound.weights[used], skin=index,
                ))
            overrides[member] = primitives
    return overrides


def _used_components(descriptor: dict) -> list[str]:
    """The components the occurrences place, in first-placed order."""
    components = descriptor.get("components") or {}
    used: list[str] = []
    for occurrence in descriptor.get("occurrences") or []:
        cid = str(occurrence.get("component") or "")
        if cid not in components:
            raise ValueError(f"the tree's descriptor names unknown component {cid!r}")
        if cid not in used:
            used.append(cid)
    return used


def _loaded_producer() -> dict | None:
    """This process's surface producer when its modeling kernel is already loaded
    (a model build's), so the export asks the build pool for no producer job;
    otherwise None, and the view takes the document's hint or asks the pool. A
    door process may hold OCP without build123d, and importing build123d to name
    a producer would cost more than the job it saves."""
    if "build123d" not in sys.modules:
        return None
    from cadgen.store.surfaces import producer_identity

    try:
        return producer_identity()
    except (ImportError, ValueError):
        return None


def _export_view(source: MeshSource, producer: dict | None, appearance: object) -> dict:
    from cadgen.store.view import descriptor_for_view

    descriptor = descriptor_for_view(source.tree, producer=producer, document_hash=source.document_hash)
    if descriptor is None:
        raise FileNotFoundError(f"mesh export: geometry tree missing or unreadable: {source.tree}")
    if appearance is not None:
        from cadgen._internal.source_sidecar import apply_appearance

        # A private projection: immutable store objects and the component
        # meshes' identities stay unchanged.
        descriptor = apply_appearance(descriptor, appearance)
    return descriptor


def stored_meshes(source: MeshSource, pairs: list, appearance: object,
                  components: "list[str] | None" = None) -> "tuple[dict, dict]":
    """The export's descriptor, and the stored GLB body of every placed component
    (or only ``components``) at every pair, ``{(cid, pair): bytes}``.

    What the store lacks is derived by build-pool jobs (``surfaces.derive`` with
    every pair: SURF where missing, then OCCT's mesh at each tolerance), the
    missing components dealt across the pool (``artifacts.deal``) as a view's
    are: one job did them one after another, half a cold export's wall time on
    moonwatch. A model build exporting its own outputs derives them in its own
    process, where the kernel is loaded, and deals to the pool only the shares
    past the first that repay starting a worker: a pool job there cost a cold
    box 2.6 s of kernel import for 0.03 s of work. A pinned producer this runtime
    cannot implement is replaced by the current one, once, as the views do
    (``store.view.materialize_view_surfaces``)."""
    from cadgen.daemon.artifacts import (
        SURFACES_PER_STARTED_WORKER, ArtifactJobError, deal, resolve_artifact, resolve_artifacts)
    from cadgen.store import meshes, surfaces

    descriptor = _export_view(source, _loaded_producer(), appearance)
    tessellations = [{"chordTolerance": chord, "angleTolerance": angle} for chord, angle in pairs]
    replaced = False
    while True:
        placed = descriptor["components"]
        keys = {
            (cid, pair): meshes.tessellation_key(placed[cid]["surfaceInput"], *pair)
            for cid in (components if components is not None else _used_components(descriptor)) for pair in pairs
        }
        missing = sorted({cid for (cid, _pair), key in keys.items() if meshes.probe(key) is None})
        if missing:
            producer = surfaces.producer_fields(descriptor["surfaceProducer"])
            try:
                resolve_artifacts([{"kind": "surfaces", "tree": source.tree, "cids": dealt,
                                    "producer": producer, "tessellations": tessellations}
                                   for dealt in deal(missing, per_started_worker=SURFACES_PER_STARTED_WORKER)])
            except ArtifactJobError as error:
                if replaced or not surfaces.producer_unavailable(error):
                    raise
                current = resolve_artifact({"kind": "producer"})
                if surfaces.producer_key(current) == surfaces.producer_key(producer):
                    raise
                replaced = True
                descriptor = _export_view(source, current, appearance)
                if source.document_hash:
                    from cadgen.store.records import document_entry_for_hash, note_document_tree

                    entry = document_entry_for_hash(source.document_hash)
                    if entry is not None and entry.get("tree") == source.tree:
                        note_document_tree(source.document_hash, source.tree, surface_producer=current)
                continue
        bodies = {}
        for (cid, (chord, angle)), key in keys.items():
            payload = meshes.read(key)
            if payload is None:
                raise RuntimeError(
                    f"mesh export failed: component {cid} has no stored mesh at chord {chord:g}, "
                    f"angle {angle:g} after its derivation"
                )
            bodies[(cid, (chord, angle))] = payload
        return descriptor, bodies


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
    return SERIALIZATION_VERSIONS.get(str(fmt))


def mesh_variant_key(
    fmt: str,
    mesh_tolerance: float | None,
    mesh_angular_tolerance: float | None,
    animation_key: str | None = None,
    appearance_key: str | None = None,
) -> str:
    """One mesh variant of a document — format × serializer × chord × angle × clip — the key
    of the ARTIFACT-side ledger (``index/document/<sha256(bytes)>.meshes``).

    Every format carries its own serializer revision (``SERIALIZATION_VERSIONS``).
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
