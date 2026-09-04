from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time

from cadgen._internal.atomic_replace import replace_atomic, temp_suffix
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterator, Sequence, TextIO

from cadgen.catalog import (
    CadSource,
    StepImportOptions,
    find_source_by_path,
    iter_cad_sources,
    normalize_cad_ref,
    normalize_source_ref,
    source_from_path,
)
from cadgen.cli_logging import CliLogger
from cadgen._internal.glb_topology import build_step_topology_index_manifest
from cadgen._internal.glb_topology import (
    STEP_EDGE_VISIBILITY_CLASSES,
)
from cadgen.coordination import (
    DRAWING_PACKAGE,
    PHASE_GENERATE,
    STEP_PACKAGE,
    ProgressEvent,
    artifact_build,
    generator_busy,
    render_progress_bar,
    reporting_as,
    resolve as resolve_progress,
)
from cadgen.cli_progress import (
    InlineProgressLine,
    _finished_phase_text,
    _progress_status_text,
    cli_progress_line,
)
from cadgen.metadata import GeneratorMetadata
from cadgen.render import (
    relative_to_file,
    relative_to_cwd,
)
from cadgen._internal.source_hash import (
    PythonSourceClosure,
    PythonSourceHash,
    capture_runtime_closure,
    closure_hash_matches,
    evict_first_party_modules,
    python_source_hash,
    record_first_party_execution,
)
from cadgen.step_export import build_build123d_step_scene
from cadgen._internal.step_scene import (
    load_step_scene_cached,
    LoadedStepScene,
    SelectorBundle,
    SelectorOptions,
    step_file_hash,
)
from cadgen._internal.generation_runner import (
    GIT_LFS_POINTER_PREFIX,
    _ArtifactJob,
    _effective_step_spec_for_scene,
    _ensure_step_ready,
    _generator_progress_line,
    _load_generator_module,
    _mark_scene_python_backed,
    _mark_scene_step_payload,
    _normalize_step_payload,
    _resolve_declared_kinematics,
    _run_artifact_jobs,
    _run_script_generator_inner,
    _scene_entry_kind,
    _shape_has_explicit_children,
    _shape_is_multi_child_compound,
    _shape_payload_entry_kind,
    _spec_output_dir,
    _track_spec_generation,
    _write_dxf_payload,
    _write_shape_step_payload,
    run_script_generator,
)
from cadgen._internal.generation_spec import (
    EntrySpec,
    GeneratedStepResult,
    _apply_step_options_to_spec,
    _cli_progress_line,
    _display_path,
    _entry_spec_from_source,
    _hint_float,
    _hint_int,
    _resolve_discovery_root,
    _selector_options_for_part,
    _spec_for_source_ref,
    _spec_requests_extra_outputs,
    list_entry_specs,
    selected_entry_specs,
)

def _sha256_of(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _edge_visibility_classes_match_manifest(
    manifest: Mapping[str, object],
    selector_options: SelectorOptions,
) -> bool:
    edge_rendering = manifest.get("edgeRendering")
    if not isinstance(edge_rendering, Mapping):
        return False
    return tuple(edge_rendering.get("visibilityClasses") or ()) == tuple(selector_options.edge_visibility_classes)


def _manifest_records_edge_visibility_classes(manifest: Mapping[str, object]) -> bool:
    """Well-formedness, not agreement: does this assembly.json say what it was built with?

    Every assembly.json written by a current build does. One that does not is
    truncated or foreign, and reusing it would serve components whose edge
    classes nothing can name.
    """
    edge_rendering = manifest.get("edgeRendering")
    if not isinstance(edge_rendering, Mapping):
        return False
    return bool(edge_rendering.get("visibilityClasses"))


def _manifest_source_sidecar(manifest: Mapping[str, object]) -> Mapping[str, object]:
    sidecar = manifest.get("_sourceSidecar")
    return sidecar if isinstance(sidecar, Mapping) else {}


def _artifact_source_kind_matches_spec(spec: EntrySpec, manifest: Mapping[str, object]) -> bool:
    # The generated-marker is the PROVENANCE RECORD every generated build writes
    # (source_sidecar.py records tier): the assembly.json itself is STEP-pure and
    # carries no sourceKind. An imported spec whose bytes resolve to a generated
    # model's tree is fine — content keying already guarantees the tree IS
    # these bytes' render.
    generated = bool(_manifest_source_sidecar(manifest))
    if spec.source != "generated" and spec.step_path is not None and spec.step_path.is_file():
        return True
    expected = spec.source == "generated" and spec.script_path is not None
    return generated == expected


def _package_descriptor_matches_spec(
    spec: EntrySpec,
    selector_options: SelectorOptions | None = None,
) -> bool | None:
    """assembly.json-based freshness for a view directory.

    Returns None when the entry's artifact is not a tree (caller falls back
    to the monolith-GLB validator). Packages carry no embedded selector/edge
    views (selector topology is extracted on demand), so routing them through
    the monolith validator always failed and every build re-ran the generator plus
    the full-scene mesh; validate against the assembly.json instead.

    Content keying does most of the gating BY CONSTRUCTION: the tree key is
    ``<sha256(document)>-v<schemaVersion>``, so a tree that resolves at all
    has the right schema and belongs to exactly these bytes — the old
    schema-version and stepHash gates all collapsed into the key. What
    remains is what the key cannot answer: provenance direction (sidecar vs
    spec), and — once a scene has been loaded and the caller can say what edge
    classes it wants — whether the tree was built with those classes. The
    source-closure gate stays the sanctioned asymmetry in the SAFE direction:
    generated outputs are detached from their code, so the viewer never checks
    source currency — here it survives purely as the explicit-build no-op
    gate, where being stricter can only make a requested build do real work,
    never trigger a needless one.

    Without ``selector_options`` the caller cannot say what it wants, and
    nothing can be inferred: the edge classes are a pure function of the STEP
    bytes, which the key already pins, so re-deriving an expectation from the
    assembly.json would only compare it against itself. All that is checkable
    there is that the assembly.json IS one — that it records the classes at all.
    The mesh comparison that used to live here weighed the assembly.json's
    recorded deflection numbers against freshly resolved ones; no tessellator
    ever read either, so the only thing a mismatch could trigger was a rebuild
    that rewrote them.
    """
    from cadgen.catalog import result_descriptor_for

    manifest = result_descriptor_for(spec.entry_path)
    if not isinstance(manifest, dict):
        return None
    if spec.source == "generated":
        # Only a SCRIPT run asks whether this tree is its own model's (the
        # provenance record). A document at a door asks nothing of records:
        # a tree for its bytes is its render (STORE.md §2, the law).
        from cadgen._internal.source_sidecar import read_source_provenance

        provenance = read_source_provenance(spec.entry_path)
        if provenance is not None:
            manifest["_sourceSidecar"] = provenance
    if not _artifact_source_kind_matches_spec(spec, manifest):
        return False
    if selector_options is None:
        return _manifest_records_edge_visibility_classes(manifest)
    return _edge_visibility_classes_match_manifest(manifest, selector_options)


def _existing_topology_artifact_matches_spec_without_scene(spec: EntrySpec) -> bool:
    """True when the entry's tree is current (no scene needed).

    The assembly.json is the ONLY artifact form, so this is a thin guard
    around :func:`_package_descriptor_matches_spec` (None -> no package -> not
    current). The pre-package monolith-GLB fallback that used to live here was
    unreachable — its validator gated on ``.is_file()`` and every artifact is a
    directory — and is deleted."""
    if spec.step_path is None or spec.kind not in {"part", "assembly"}:
        return False
    return bool(_package_descriptor_matches_spec(spec))


def _existing_topology_artifact_matches_options(spec: EntrySpec, selector_options: SelectorOptions) -> bool:
    """As above, but against explicitly supplied selector options."""
    if spec.step_path is None or spec.kind not in {"part", "assembly"}:
        return False
    return bool(_package_descriptor_matches_spec(spec, selector_options))


def _assembly_provenance_manifest(
    scene: LoadedStepScene,
    *,
    selector_options: SelectorOptions,
    step_path: Path,
    entry_kind: str,
) -> dict[str, object]:
    """The index-manifest provenance an assembly.json carries, mirroring
    the monolithic GLB's embedded STEP_topology index — but WITHOUT the expensive
    selector extraction. Sourced from the scene (sourceKind/closure), the edge-render
    options, and the STEP hash, so the build freshness gates can read it from
    assembly.json exactly as they read the monolithic manifest.

    There is no ``mesh`` section. A tree stores surfaces, not
    triangles; the client tessellates from ``.surf`` with the JS tessellator's
    own relative tolerances. The deflection numbers this block used to carry
    reached no mesher, and the adaptive ``resolution`` beside them was the
    INPUT to a decision whose output — ``edgeRendering.visibilityClasses`` — is
    recorded right here.
    """
    import os

    from cadgen._internal.glb_topology import step_topology_capabilities

    # STEP-pure by contract: nothing here may derive from the Python source.
    # Source-derived state (provenance, pose, mates) rides the source sidecar
    # (_source_sidecar_payload below) — the assembly.json is the cache engine's
    # world and keys on the STEP bytes alone.
    minimal: dict[str, object] = {
        "capabilities": step_topology_capabilities(selector_options.edge_visibility_classes),
        "edgeRendering": {"visibilityClasses": list(selector_options.edge_visibility_classes)},
    }
    step_hash = (
        step_file_hash(step_path)
        if step_path.is_file()
        else str(getattr(scene, "step_hash", "") or "").strip()
    )
    if step_hash:
        minimal["stepHash"] = step_hash
    return build_step_topology_index_manifest(minimal, entry_kind=entry_kind)


def _source_sidecar_payload(scene: LoadedStepScene) -> dict[str, object] | None:
    """The sidecar payload for a GENERATED build, or None for an import.

    Everything source-derived lands here: provenance (the no-op gate's
    closure), the copied animation module text, and the build timestamp — the one
    volatile field, which moving here keeps the assembly.json byte-stable across
    identical rebuilds. The KINEMATICS section is injected later, once the
    staging package exists to resolve axis refs against.
    """
    from datetime import datetime, timezone

    source_kind = str(getattr(scene, "source_kind", "step") or "step").strip().lower()
    reemit_hash = str(getattr(scene, "reemit_source_hash", "") or "").strip()
    if source_kind != "python" and not reemit_hash:
        return None
    payload: dict[str, object]
    if reemit_hash:
        # `cadgen step build IN OUT`: no Python behind the document, so the
        # freshness closure is the INPUT's content hash and the annotation
        # digest. No path to anything is recorded — the pair is self-describing.
        payload = {"sourceKind": "step", "sourceHash": reemit_hash}
        annotation = str(getattr(scene, "reemit_annotation_hash", "") or "").strip()
        if annotation:
            payload["annotationHash"] = annotation
    else:
        payload = {"sourceKind": "python"}
        source_path = str(getattr(scene, "source_path", "") or "")
        if source_path:
            payload["sourcePath"] = source_path
        source_hash = str(getattr(scene, "source_hash", "") or "").strip()
        if source_hash:
            payload["sourceHash"] = source_hash
        closure_hash = str(getattr(scene, "source_closure_hash", "") or "").strip()
        closure_files = getattr(scene, "source_closure_files", ()) or ()
        if closure_hash and closure_files:
            payload["sourceClosureHash"] = closure_hash
            payload["sourceClosureFiles"] = list(closure_files)
    animation_source = getattr(scene, "animation_source", None)
    if animation_source:
        # COPIED text, never a path: the sidecar is the one durable home for
        # source-derived state, and generated files carry no reference back
        # to the source tree.
        payload["animation"] = {"clips": str(animation_source)}
    payload["generatedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return payload


def _mesh_exports_sidecar_section(spec: EntrySpec) -> list[dict[str, object]]:
    """The sidecar's ``meshExports`` section: what this model DECLARES.

    The script run is the only thing that can see ``@stl``/``@glb``/``@threemf``
    (a kinematics dict is not statically evaluable, and a CLI must never import
    a model module), so it records the declarations here and the bare mesh
    doors read them back off the DOCUMENT. ``out`` is relative to the artifact
    so the pair travels together; the tolerances are the EFFECTIVE pair the run
    wrote at, ``null`` meaning the tessellator default.
    """
    if not spec.mesh_exports or spec.step_path is None:
        return []
    base = spec.step_path.parent.resolve()
    entries: list[dict[str, object]] = []
    for declared in spec.mesh_exports:
        chord = declared.mesh_tolerance if declared.mesh_tolerance is not None else spec.mesh_tolerance
        angle = (
            declared.mesh_angular_tolerance
            if declared.mesh_angular_tolerance is not None
            else spec.mesh_angular_tolerance
        )
        entries.append(
            {
                "fmt": declared.fmt,
                "out": Path(os.path.relpath(declared.path, base)).as_posix(),
                "meshTolerance": chord,
                "meshAngularTolerance": angle,
            }
        )
    return entries


def _generate_part_outputs(
    spec: EntrySpec,
    *,
    entries_by_step_path: dict[Path, EntrySpec],
    preloaded_scene: LoadedStepScene | None = None,
    require_step_file: bool = True,
    force: bool = False,
    logger: CliLogger | None = None,
    progress: object | None = None,
) -> GeneratedStepResult:
    logger = logger or CliLogger("cad")
    progress = resolve_progress(progress)
    if spec.kind not in {"part", "assembly"} or spec.step_path is None:
        return GeneratedStepResult(spec=spec, scene=None)
    if require_step_file:
        _ensure_step_ready(spec.step_path)
    if preloaded_scene is not None:
        if preloaded_scene.step_path != spec.step_path.expanduser().resolve():
            raise RuntimeError(
                f"Preloaded STEP scene path {preloaded_scene.step_path} does not match {_display_path(spec.step_path)}"
            )

    # Any on-demand output (mesh sidecar or --step export) must be produced even when the
    # tree is current, so its presence defeats the reuse fast paths.
    has_extra_outputs = _spec_requests_extra_outputs(spec)
    package_current = (
        spec.source != "generated"
        or _assembly_glb_package_current(spec)
    )
    if (
        preloaded_scene is None
        and not has_extra_outputs
        and not force
        and package_current
        and _existing_topology_artifact_matches_spec_without_scene(spec)
    ):
        logger.debug(f"reused current tree: {_display_path(spec.step_path)}")
        return GeneratedStepResult(spec=spec, scene=None)

    if preloaded_scene is not None:
        scene = preloaded_scene
    else:
        # An imported STEP's parse is this path's equivalent of running a generator:
        # opaque, and often seconds for a large vendor file.
        progress.phase(PHASE_GENERATE)
        with logger.timed(f"load STEP {spec.cad_ref}"):
            # Cross-run binary BREP scene cache: warm rebuilds of imported
            # STEP entries skip the text-STEP parse (seconds to ~10s+ for
            # large vendor files) and deserialize cached geometry instead.
            scene = load_step_scene_cached(spec.step_path)
        if spec.source == "generated" and spec.script_path is not None:
            _mark_scene_python_backed(
                scene,
                source_identity=python_source_hash(spec.script_path),
                source_path=spec.script_path,
            )
    spec = _effective_step_spec_for_scene(spec, scene)
    entries_by_step_path = {
        **entries_by_step_path,
        spec.step_path.resolve(): spec,
    }
    selector_options = _selector_options_for_part(spec, scene=scene)
    if (
        not has_extra_outputs
        and not force
        and package_current
        and _existing_topology_artifact_matches_options(spec, selector_options)
        and _generated_assembly_glb_closure_current(spec)
    ):
        logger.debug(f"reused current tree: {_display_path(spec.step_path)}")
        return GeneratedStepResult(spec=spec, scene=scene)

    jobs: list[_ArtifactJob] = []

    artifact_results: dict[str, object] = {}

    # UNIFIED render artifact: every model — part or assembly, generated or imported — is
    # a TREE (a store object keyed by content hash: assembly.json
    # plus content-addressed components). An assembly introspects its
    # placed children as occurrences; a part is one occurrence/one component. The
    # part/assembly choice is the *authored* kind (spec.kind, from generator metadata or STEP
    # inference) — never guessed from geometry — and is recorded as entryKind on the
    # assembly.json. There is no monolithic GLB and no file-vs-dir split.
    source_compound = getattr(scene, "source_compound", None)
    single_component = spec.kind != "assembly"
    package_provenance = _assembly_provenance_manifest(
        scene, selector_options=selector_options, step_path=spec.step_path, entry_kind=spec.kind
    )

    def component_package_job() -> dict[str, object]:
        shape = source_compound
        if shape is None:
            # Imported STEP (no generator compound): compose the ALREADY-LOADED scene
            # into the packaging compound. This used to call build123d.import_step and
            # pay a second full text-STEP parse right after the scene load above.
            from cadgen._internal.step_scene_mesh import scene_to_build123d_compound

            shape = scene_to_build123d_compound(scene)
        from cadgen._internal.source_sidecar import remove_source_sidecar, write_source_sidecar
        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.records import read_record, write_record

        with logger.timed("tree: sidecar payload"):
            sidecar_payload = _source_sidecar_payload(scene)
        generated = sidecar_payload is not None
        if generated:
            mesh_export_section = _mesh_exports_sidecar_section(spec)
            if mesh_export_section:
                sidecar_payload["meshExports"] = mesh_export_section

        # Content-pure fields the tree carries (capabilities, edge classes); the
        # provenance fields (stepHash, generatedAt, sourceKind…) go to the record.
        tree_extra = {
            key: package_provenance[key]
            for key in ("capabilities", "edgeRendering")
            if key in package_provenance
        }
        # Objects first: components + tree. Harmless if this build ends up not
        # publishing its record (publish rule below) — content-addressed and GC'd.
        with logger.timed("tree: components"):
            tree_hash, tree, stats = build_tree_from_compound(
                shape,
                root_name=spec.step_path.stem,
                entry_kind=spec.kind,
                single_component=single_component,
                force=force,
                progress=progress,
                extra=tree_extra,
            )
        stats["tree"] = tree_hash

        model_path = spec.script_path if generated and spec.script_path is not None else spec.entry_path
        outputs: dict[str, object] = {}

        if generated:
            kinematics_block = getattr(scene, "kinematics", None)
            if kinematics_block:
                # Axis refs resolve against a VIEW (assembly.json + components/) of the tree (the
                # same composed selector index inspect uses). Nothing here moves
                # geometry: the tree is the result exactly as the model returned it.
                from cadgen._internal.kinematics_resolve import resolve_kinematics_block
                from cadgen.store.view import export_view

                view_dir = export_view(tree_hash)
                try:
                    with logger.timed("tree: kinematics"):
                        resolved_block, occurrence_ids = resolve_kinematics_block(
                            kinematics_block,
                            package_dir=view_dir,
                            step_path=spec.step_path,
                            source_ref=str(spec.source_ref),
                        )
                finally:
                    shutil.rmtree(view_dir, ignore_errors=True)
                sidecar_payload["kinematics"] = resolved_block
            if spec.step_output:
                write_source_sidecar(spec.entry_path, sidecar_payload)

                from cadgen.store.materialize import materialize
                from cadgen.step_export import export_build123d_step_file

                spec.step_path.parent.mkdir(parents=True, exist_ok=True)
                with logger.timed("tree: assemble STEP"):
                    exported_hash = export_build123d_step_file(
                        materialize(tree_hash, label=spec.step_path.stem), spec.step_path, logger=logger
                    )
                from cadgen.catalog import seed_artifact_hash

                seed_artifact_hash(spec.step_path, exported_hash)
                hashes = getattr(scene, "exported_step_sha256", None) or {}
                hashes[str(spec.step_path.expanduser().resolve())] = exported_hash
                scene.exported_step_sha256 = hashes
                outputs[str(spec.step_path.expanduser().resolve())] = {"sha256": exported_hash}
                from cadgen._internal.source_sidecar import source_sidecar_path

                sidecar_file = source_sidecar_path(spec.entry_path)
                if sidecar_file.is_file():
                    outputs[str(sidecar_file.resolve())] = {"sha256": _sha256_of(sidecar_file)}
            else:
                # A mesh-only model: the tree and record are the model's like any
                # other; its outputs are the declared meshes, produced from the tree
                # below. No STEP, no sidecar -- STEP is one output kind, not the primary.
                remove_source_sidecar(spec.entry_path)
        else:
            # Imported document: the source IS the file; no sidecar, no generated marker.
            remove_source_sidecar(spec.entry_path)

        # The record. Publish rule: never replace a current record with a stale one.
        closure_hash = str(getattr(scene, "source_closure_hash", "") or "")
        closure_files = list(getattr(scene, "source_closure_files", ()) or ())
        closure_shas = dict(getattr(scene, "source_closure_file_hashes", None) or {})
        closure_static = False
        reemit_source_hash = getattr(scene, "reemit_source_hash", None)
        if not generated:
            # An imported document's closure is the document itself.
            from cadgen.store.closure import closure_hash as _closure_hash

            step_hash = str(getattr(scene, "step_hash", "") or "") or step_file_hash(spec.step_path)
            closure_files = [spec.step_path.name]
            closure_shas = {spec.step_path.name: step_hash}
            closure_hash = _closure_hash([(spec.step_path.name, step_hash)])
        elif reemit_source_hash and not closure_hash:
            # A re-emitted document (`cadgen step build IN OUT`): its source is
            # another document's bytes plus the author's annotation, both compared
            # by that door — no files for the gate to re-hash.
            from cadgen.store.closure import closure_hash as _closure_hash

            closure_files = []
            closure_hash = _closure_hash(
                [("reemit", str(reemit_source_hash)), ("annotation", str(getattr(scene, "reemit_annotation_hash", "") or ""))]
            )
            closure_static = True
        # Declared mesh exports recorded by earlier runs stay listed: each one
        # carries the document hash it was cut from, so the mesh gate re-checks
        # it against THIS document and re-exports only what no longer matches.
        previous = read_record(model_path) or {}
        for output_path, entry in (previous.get("outputs") or {}).items():
            if isinstance(entry, dict) and entry.get("declared") and output_path not in outputs:
                outputs[output_path] = entry
        # Every declared mesh output is listed from the first publish, sha-less
        # until its export writes it (record_mesh_export fills the entry), so a
        # declaration the exporter failed to honour reads as STALE at the next
        # gate ("never written") instead of as a current model missing an output.
        if generated:
            for declared in spec.mesh_exports or ():
                key = str(Path(declared.path).expanduser().resolve())
                outputs.setdefault(key, {"sha256": "", "declared": declared.fmt})
        record = {
            "entryKind": spec.kind,
            "sourceKind": "step" if (not generated or reemit_source_hash) else "python",
            "tree": tree_hash,
            "closure": {"hash": closure_hash, "files": closure_files, "shas": closure_shas, "static": closure_static},
            # Literals imported from model files, tracked by VALUE (gate clause 2).
            "constants": dict(getattr(scene, "source_closure_constants", None) or {}) if generated else {},
            "children": list(getattr(scene, "store_children", None) or []),
            "outputs": outputs,
            # The bytes of the document this tree describes -- a door's one question
            # (cadgen._internal.doors.document_tree). An imported document is hashed
            # itself; a generated one carries the hash of the .step it wrote.
            "stepHash": (
                str(getattr(scene, "step_hash", "") or "")
                or (outputs and next(iter(outputs.values())).get("sha256"))
                or (
                    step_file_hash(spec.step_path)
                    if not generated and spec.step_path is not None and Path(spec.step_path).is_file()
                    else ""
                )
            ),
        }
        if reemit_source_hash:
            record["sourceHash"] = str(reemit_source_hash)
            record["annotationHash"] = str(getattr(scene, "reemit_annotation_hash", "") or "")
        if generated and sidecar_payload is not None and sidecar_payload.get("kinematics") is not None:
            record["kinematics"] = sidecar_payload.get("kinematics")
        if generated:
            from cadgen.store.publish import decide

            decision = decide(model_path, ran_closure_hash=closure_hash, ran_files=closure_files)
            if not decision.publish_outputs:
                logger.info(f"{spec.cad_ref}: {decision.reason}; objects kept, record left as is")
                stats["published"] = False
                return stats
        write_record(model_path, record)
        from cadgen.store.records import note_document_tree, note_output

        # Artifact side: the bytes of the document this tree describes → the tree
        # (a reader's one lookup; STORE.md §2). Code side: which model wrote each
        # output path (the badge's question, never a reader's).
        if tree_hash and record.get("stepHash"):
            note_document_tree(str(record["stepHash"]), str(tree_hash), kind=str(spec.kind or "step"))
        if generated:
            for output_path in outputs:
                if Path(output_path) != model_path:
                    note_output(output_path, model_path)
        stats["published"] = True
        return stats

    jobs.append(_ArtifactJob("tree", component_package_job))

    if spec.step_export_path is not None:
        def step_export_job() -> Path:
            # The STEP file is ASSEMBLED from the tree's exact-shape component objects
            # (design/step-document-architecture.md) — a save, not a
            # recompute — so this job runs after the tree job. Imported
            # sources already have the file; copy when a different path was
            # requested.
            target = spec.step_export_path
            target.parent.mkdir(parents=True, exist_ok=True)
            # The tree job already wrote the generated document to
            # spec.step_path (the store key derives from those bytes); an
            # explicit target elsewhere is a byte copy of the same document.
            if spec.step_path is not None and spec.step_path.is_file() and spec.step_path.resolve() != target.resolve():
                shutil.copyfile(spec.step_path, target)
                hashes = getattr(scene, "exported_step_sha256", None) or {}
                recorded = hashes.get(str(spec.step_path.expanduser().resolve()))
                if recorded:
                    hashes[str(target.expanduser().resolve())] = recorded
                    scene.exported_step_sha256 = hashes
            return target

        jobs.append(_ArtifactJob("STEP", step_export_job))

    artifact_results.update(_run_artifact_jobs(jobs, logger=logger))
    # The render artifact is the tree; whole-model selector topology is
    # extracted on demand by ensure_step_topology_artifact (inspect/selection renders), so
    # generation no longer returns a selector bundle.
    return GeneratedStepResult(spec=spec, scene=scene, selector_bundle=None)


def _generate_step_outputs(
    spec: EntrySpec,
    *,
    entries_by_step_path: dict[Path, EntrySpec],
    force: bool = False,
    logger: CliLogger | None = None,
    progress: object | None = None,
) -> GeneratedStepResult:
    preloaded_scene: LoadedStepScene | None = None
    # An on-demand output (mesh sidecar or --step export) must run even when the tree is
    # current, so its presence defeats the reuse fast path.
    has_extra_outputs = _spec_requests_extra_outputs(spec)
    # Reuse fast path: skip the build when the tree is already present and
    # current and nothing forces a run. A generated model's freshness rides on its recorded
    # source closure; an imported/committed STEP's freshness rides on the STEP hash recorded in
    # the tree (verified inside the artifact-matches gate), so it needs no closure check.
    if (
        not force
        and not has_extra_outputs
        and _assembly_glb_package_current(spec)
        and _existing_topology_artifact_matches_spec_without_scene(spec)
        and (spec.source != "generated" or _generated_assembly_glb_closure_current(spec))
    ):
        if logger is not None:
            logger.debug(f"reused current tree: {_display_path(spec.step_path)}")
        # Declared mesh exports are content-gated, not build-gated: a current
        # model with a deleted/stale STL heals it here from the store package
        # without a rebuild.
        _produce_declared_mesh_exports(spec, logger=logger)
        return GeneratedStepResult(spec=spec, scene=None)
    output_kwargs: dict[str, object] = {
        "entries_by_step_path": entries_by_step_path,
        "force": force,
        "progress": progress,
    }
    if logger is not None:
        output_kwargs["logger"] = logger
    if spec.source == "generated":
        preloaded_scene = run_script_generator(
            spec,
            "step",
            logger=logger,
            force=force,
            progress=progress,
            # The direct build flow: the model's own prints are the user's
            # stdout channel here (and pinned by test).
            model_prints_to_stdout=True,
        )
        spec = _effective_step_spec_for_scene(spec, preloaded_scene)
        if spec.step_path is not None:
            output_kwargs["entries_by_step_path"] = {
                **entries_by_step_path,
                spec.step_path.resolve(): spec,
            }
        output_kwargs["preloaded_scene"] = preloaded_scene
        # A @step entry never writes a STEP, so the artifact pipeline must not require one.
        output_kwargs["require_step_file"] = False
    else:
        # Imported/committed STEP target (kind supplied by the caller or inferred upstream):
        # _generate_part_outputs loads + meshes the on-disk STEP and emits the same flat
        # tree. Without this branch the function fell off the end and silently
        # returned None — no package written — while the CLI still reported success.
        output_kwargs["require_step_file"] = True
    result = _generate_part_outputs(spec, **output_kwargs)
    _record_step_export(spec, scene=preloaded_scene)
    _produce_declared_mesh_exports(spec, logger=logger)
    return result


def _produce_declared_mesh_exports(
    spec: EntrySpec, *, logger: CliLogger | None, announce: bool = True
) -> "tuple[Path, ...]":
    """Produce the model's declared ``@stl``/``@glb``/``@threemf`` outputs and
    RETURN the ones this call actually wrote.

    The return value is what ``BuildResult.exports`` reports: outputs the
    ledger already found current are not listed, because the field answers
    "what did this run write", not "what does the model declare".

    Runs through the ONE mesh engine the `cadgen stl|3mf|glb build` doors use — same Node
    invocation, same records — so the two front doors cannot drift. Each
    output is gated by its content-keyed record (document hash + effective
    tolerances): current outputs cost a stat + record read; stale or missing
    ones tessellate from the store package. Content-gated deliberately even
    under --force: a byte-identical rebuild leaves exports byte-identical by
    determinism, so rewriting them is pure waste.

    Tolerance precedence: declaration-level explicit > @step model-level
    explicit > tessellator default (matching the CLI's flag > model > default).

    ``announce`` prints the ``wrote <FMT>: <path>`` lines. A caller that
    renders the produced paths itself — a generated CLI printing its Result —
    passes False so the same file is not reported twice.
    """
    if not spec.mesh_exports or spec.entry_path is None or spec.step_path is None:
        return ()
    from cadgen.catalog import artifact_file_hash
    from cadgen._internal.mesh_export import (
        MeshExportJob,
        mesh_export_current,
        record_mesh_export,
        run_mesh_exporter,
    )

    from cadgen.catalog import result_tree_for
    from cadgen.store.view import export_view

    model = _model_for_spec(spec)
    if spec.step_output:
        document_hash = artifact_file_hash(spec.entry_path)
        tree_hash = result_tree_for(spec.entry_path)
    else:
        # A mesh-only model writes no document: its tree IS the geometry the
        # meshes are cut from, so the ledger keys on that.
        from cadgen.store.records import current_tree

        tree_hash = current_tree(model) if model is not None else None
        document_hash = tree_hash
    if document_hash is None or tree_hash is None or model is None:
        return ()
    pending: list[MeshExportJob] = []
    for declared in spec.mesh_exports:
        chord = declared.mesh_tolerance if declared.mesh_tolerance is not None else spec.mesh_tolerance
        angle = (
            declared.mesh_angular_tolerance
            if declared.mesh_angular_tolerance is not None
            else spec.mesh_angular_tolerance
        )
        if mesh_export_current(
            declared.path,
            model=model,
            document_hash=document_hash,
            mesh_tolerance=chord,
            mesh_angular_tolerance=angle,
        ):
            continue
        declared.path.parent.mkdir(parents=True, exist_ok=True)
        pending.append(
            MeshExportJob(
                fmt=declared.fmt,
                out=declared.path,
                mesh_tolerance=chord,
                mesh_angular_tolerance=angle,
            )
        )
    if not pending:
        return ()
    from cadgen.step_export_target import _color_hex

    # The Node exporter reads a view directory (assembly.json + components/): a temporary VIEW of the
    # tree, removed when the export is done (the store holds no result dirs).
    view_dir = export_view(tree_hash)
    try:
        jobs = list(pending)
        run_mesh_exporter(
            view_dir,
            jobs,
            name=spec.step_path.stem,
            default_color=_color_hex(spec.color),
            logger=logger if logger is not None else CliLogger("cadgen", verbose=False),
        )
    finally:
        shutil.rmtree(view_dir, ignore_errors=True)
    for job in jobs:
        record_mesh_export(
            job.out,
            model=model,
            document_hash=document_hash,
            fmt=job.fmt,
            mesh_tolerance=job.mesh_tolerance,
            mesh_angular_tolerance=job.mesh_angular_tolerance,
        )
        if announce:
            # stderr: stdout is the result channel (`outcome document`), and a
            # `[cadgen]`-prefixed line is the logger's voice, not a result.
            print(f"[cadgen] wrote {job.fmt.upper()}: {_display_path(job.out)}", file=sys.stderr)
    return tuple(job.out for job in jobs)


def _record_step_export(spec: EntrySpec, scene: object | None = None) -> None:
    """After a ``--write`` to an explicit target, list that file among the
    MODEL's outputs (record clause 5). Best-effort."""
    target = spec.step_export_path
    model = _model_for_spec(spec)
    if target is None or model is None:
        return
    try:
        from cadgen.store.records import read_record, write_record

        resolved = target.expanduser().resolve()
        record = read_record(model)
        if record is None or not resolved.is_file():
            return
        digest = (getattr(scene, "exported_step_sha256", None) or {}).get(str(resolved)) or _sha256_of(resolved)
        outputs = dict(record.get("outputs") or {})
        outputs[str(resolved)] = {"sha256": digest, "declared": "step"}
        record["outputs"] = outputs
        write_record(model, record)
    except Exception:
        pass


def _step_export_current(spec: EntrySpec) -> bool:
    """Whether the requested ``--write`` output is listed in the model's current
    record and its bytes verify."""
    target = spec.step_export_path
    if target is None:
        return True
    model = _model_for_spec(spec)
    if model is None:
        return False
    try:
        from cadgen.store.gate import stale
        from cadgen.store.records import read_record

        if stale(model).stale:
            return False
        record = read_record(model) or {}
        resolved = target.expanduser().resolve()
        entry = (record.get("outputs") or {}).get(str(resolved))
        return bool(entry) and resolved.is_file() and _sha256_of(resolved) == entry.get("sha256")
    except Exception:
        return False


def _generate_step_outputs_for_cli(
    spec: EntrySpec,
    *,
    entries_by_step_path: dict[Path, EntrySpec],
    logger: CliLogger,
    force: bool = False,
    progress: object | None = None,
) -> GeneratedStepResult:
    kwargs: dict[str, object] = {
        "entries_by_step_path": entries_by_step_path,
        "progress": progress,
    }
    if force:
        kwargs["force"] = True
    if logger.verbose:
        kwargs["logger"] = logger
    return _generate_step_outputs(spec, **kwargs)


def _selected_specs_for_targets(
    targets: Sequence[str],
    *,
    step_options: StepImportOptions | None = None,
) -> tuple[list[EntrySpec], list[EntrySpec]]:
    """``(all specs the targets reach, the targets' own specs)``. A target is a
    model script or a document — its outputs are what it declares (``out=``);
    nothing on the command line renames them."""
    step_options = step_options or StepImportOptions()
    explicit_specs: list[EntrySpec] = []
    unresolved_targets: list[str] = []
    for target in targets:
        target_text = str(target or "").strip()
        target_path = Path(target_text)
        resolved = target_path.resolve() if target_path.is_absolute() else (Path.cwd() / target_path).resolve()
        source = (
            source_from_path(resolved, step_options=step_options)
            if resolved.exists()
            else None
        )
        if source is None:
            unresolved_targets.append(target_text)
            continue
        explicit_specs.append(_apply_step_options_to_spec(_entry_spec_from_source(source), step_options))

    if not unresolved_targets:
        return _expand_specs_with_file_dependencies(explicit_specs), explicit_specs

    unresolved = ", ".join(unresolved_targets)
    raise FileNotFoundError(
        "CAD target path not found or not a supported source file: "
        f"{unresolved}. Pass a Python generator or STEP/STP file path."
    )


def _expand_specs_with_file_dependencies(specs: Sequence[EntrySpec]) -> list[EntrySpec]:
    # Shape-only generators don't expose a static recipe to walk for dependency
    # expansion. The Python source-closure capture in run_script_generator picks
    # up generator-side .py changes; child STEP changes require --force.
    return list(specs)


def _entries_by_step_path(specs: Sequence[EntrySpec]) -> dict[Path, EntrySpec]:
    return {
        spec.step_path.resolve(): spec
        for spec in specs
        if spec.step_path is not None
    }


def _validate_step_target(spec: EntrySpec, *, tool_name: str) -> None:
    if spec.step_path is None:
        raise ValueError(f"{tool_name} target has no STEP path: {spec.source_ref}")
    if spec.source == "generated":
        metadata = spec.generator_metadata
        if metadata is None or metadata.format != "step":
            raise ValueError(f"{tool_name} target is not a @step model: {spec.source_ref}")
        return
    raise ValueError(
        f"{tool_name} builds @step Python sources only: {spec.source_ref}. "
        "Imported STEP/STP files get render artifacts on demand (inspect, snapshot, CAD Viewer)."
    )


def _validate_dxf_target(spec: EntrySpec) -> None:
    metadata = spec.generator_metadata
    if spec.source != "generated" or spec.script_path is None or metadata is None:
        raise ValueError(f"dxf expected a generated Python source target: {spec.source_ref}")
    if metadata.format != "dxf":
        raise ValueError(f"dxf target is not a @dxf model: {spec.source_ref}")
    if spec.dxf_path is None:
        raise ValueError(f"dxf target has no configured DXF output: {spec.source_ref}")


def _generated_output_summary(spec: EntrySpec) -> str:
    if spec.step_path is not None:
        return f"wrote {spec.kind}: {_display_path(spec.step_path)}"
    return f"processed: {spec.source_ref}"


def _generated_python_glb_summary(spec: EntrySpec) -> str:
    if spec.step_path is not None and not getattr(spec, "step_output", True):
        # A mesh-only model: step_path is the logical document the store keys by,
        # never a file it wrote. Name what it did write.
        meshes = ", ".join(_display_path(Path(m.path)) for m in (spec.mesh_exports or ()))
        return f"built {spec.kind}: {meshes or spec.source_ref}"
    if spec.step_path is not None:
        return f"wrote {spec.kind}: {_display_path(spec.step_path)}"
    return f"processed: {spec.source_ref}"


def _generated_dxf_summary(spec: EntrySpec) -> str:
    output = spec.dxf_path
    if output is not None:
        return f"wrote DXF: {_display_path(output)}"
    return f"processed: {spec.source_ref}"


def _tree_event(spec: EntrySpec, state: str, **extra: object) -> None:
    """One model transition for the build tree (cadgen.cli_tree). Generated models only:
    an imported document has no body and no children to show."""
    model = _model_for_spec(spec)
    if model is None:
        return
    from cadgen.daemon.executors import emit_event, model_event

    emit_event(model_event(model, state, **extra))


def _tree_progress_sink(spec: EntrySpec, inner: object | None) -> Callable[[ProgressEvent], None]:
    """Fan a run's phase events out to the caller's sink AND the build tree."""

    def sink(event: ProgressEvent) -> None:
        if inner is not None:
            inner(event)  # type: ignore[operator]
        if event.phase == "done":
            return
        _tree_event(
            spec, "building", phase=event.label or event.phase,
            done=event.done if event.determinate else None,
            total=event.total if event.determinate else None,
        )

    return sink


class _SkippedGeneration:
    """Marker: a concurrent run ahead of us had already produced a current result."""

    __slots__ = ("spec",)

    def __init__(self, spec: EntrySpec) -> None:
        self.spec = spec


def _run_with_spec_generation_status(
    spec: EntrySpec,
    model_format: str,
    action: Callable[..., object],
    *,
    skip_if_current: Callable[[EntrySpec], bool] | None = None,
    progress_sink: object | None = None,
    logger: CliLogger | None = None,
) -> object:
    """Run ``action`` under the model's progress record.

    Delegates to :func:`cadgen.coordination.artifact_build`, the SAME primitive
    ``cadgen.step_artifact_cli`` uses, so every producer reports the same way.

    ``skip_if_current`` is re-evaluated when the run opens: a run that started behind a
    concurrent build of this model no-ops once that build has published.

    ``action`` is called as ``action(spec, run)``; ``run`` is the progress reporter.
    """
    del logger
    kind = DRAWING_PACKAGE if model_format == "dxf" else STEP_PACKAGE
    started = time.perf_counter()
    with artifact_build(
        kind,
        _spec_output_dir(spec, model_format),
        is_current=(lambda: bool(skip_if_current(spec))) if skip_if_current is not None else None,
        sink=_tree_progress_sink(spec, progress_sink),
    ) as run:
        if run.skipped:
            _tree_event(spec, "current")
            return _SkippedGeneration(spec)
        from cadgen.daemon import broker

        # One running build per core: the body and its emit hold a job slot; the
        # wait for a forced child gives it back (cadgen.store.lazy). `queued` shows
        # in the tree only when the slot did not come at once.
        with broker.held(spec.source_ref, on_queued=lambda: _tree_event(spec, "queued")):
            _tree_event(spec, "building", phase="generate")
            try:
                result = action(spec, run)
            except BaseException:
                _tree_event(spec, "failed", elapsed=time.perf_counter() - started)
                raise
    _tree_event(spec, "done", elapsed=time.perf_counter() - started, stale=_stale_after_build(spec))
    return result


def _stale_after_build(spec: EntrySpec) -> str | None:
    """The already-stale-on-completion notice: after publishing, the gate runs once
    more. A child edited during the build leaves the parent stale the moment it is done
    -- the parent built against the child it pinned -- and the tree says so instead of
    letting the next run be the first to notice."""
    model = _model_for_spec(spec)
    if model is None or spec.source != "generated":
        return None
    try:
        from cadgen.store.gate import stale

        verdict = stale(model)
    except Exception:  # noqa: BLE001 - a notice never fails a build
        return None
    if not verdict.stale:
        return None
    reason = verdict.reason
    return f"{reason}; changed during the build" if reason else "changed during the build"


def _run_selected_specs(
    selected_specs: Sequence[EntrySpec],
    *,
    action_status: str = "Generating...",
    done_status: str = "Generated",
    action: Callable[..., object],
    logger: CliLogger,
    success_message: Callable[[EntrySpec], str] | None = _generated_output_summary,
) -> list[object]:
    """Run ``action`` for each spec, narrating to ``logger`` and painting one progress line.

    A generator's own prints go straight through to stdout: the CLIs reserve stdout for the
    result (``--json``) and put every log line on stderr, so there is nothing to protect it
    from. Progress is a transient tty line that erases itself — see
    :func:`_cli_progress_line`, which stays silent under ``--verbose`` where the logger is
    already narrating every stage. The sidecar is written either way, so an open CAD Viewer
    tracks the build regardless of what this prints.
    """
    results: list[object] = []
    for spec in selected_specs:
        logger.debug(f"{action_status} {spec.source_ref}")
        with _cli_progress_line(spec, logger=logger, fallback=action_status) as progress_sink:
            with logger.timed(f"{done_status.lower()} {spec.source_ref}"):
                result = action(spec, progress_sink)
        results.append(result)
        if isinstance(result, _SkippedGeneration):
            logger.info(f"{spec.cad_ref} was built by a concurrent run; skipped")
        elif success_message is not None:
            message_spec = result.spec if isinstance(result, GeneratedStepResult) else spec
            logger.info(success_message(message_spec))
    return results


def _model_for_spec(spec: EntrySpec) -> Path | None:
    """The store identity of a spec: its script (generated) or its document (imported)."""
    if spec.source == "generated" and spec.script_path is not None:
        return spec.script_path
    return spec.entry_path


def _assembly_is_current(spec: EntrySpec) -> bool:
    """Whether a generated model is current — THE gate (``cadgen.store.gate``):
    record present, closure unchanged, children pinned at their current trees,
    tree complete, outputs verify. Parts and assemblies share it."""
    if spec.source != "generated" or spec.step_path is None:
        return False
    from cadgen.store.gate import stale

    model = _model_for_spec(spec)
    return model is not None and not stale(model).stale


def _generated_assembly_glb_closure_current(spec: EntrySpec) -> bool:
    """Whether a generated model's record is current (imported models: True —
    their document IS their source and the store keys them by its bytes)."""
    if spec.source != "generated":
        return True
    return _assembly_is_current(spec)


def _assembly_glb_package_current(spec: EntrySpec) -> bool:
    """Whether the spec's current tree exists with every object present (gate
    clause 4). A document at a door is answered from objects alone: the tree
    for its bytes, complete — no record is consulted (STORE.md §2, the law)."""
    if spec.step_path is None:
        return False
    if spec.source != "generated":
        from cadgen.catalog import result_tree_for
        from cadgen.store.trees import tree_complete

        tree = result_tree_for(spec.entry_path) if spec.entry_path is not None else None
        return bool(tree) and tree_complete(tree)
    from cadgen.store.gate import stale

    model = _model_for_spec(spec)
    return model is not None and not stale(model).stale


def generate_step_targets(
    targets: Sequence[str],
    *,
    step_options: StepImportOptions | None = None,
    force: bool = False,
    verbose: bool = False,
    json_output: bool = False,
) -> int:
    """Build trees for ``targets``. Returns the process exit code.

    ``json_output`` additionally prints one JSON line per target to STDOUT. The exit code
    alone cannot say WHICH targets were rebuilt and which were already current, and the
    logger's prose goes to stderr by design -- so without this a caller reading the streams
    apart had no machine-readable result at all.
    """
    tool_name = "cadgen"
    logger = CliLogger("cadgen", verbose=verbose)
    reported: list[dict[str, object]] = []

    def _emit(spec: EntrySpec, outcome: str) -> None:
        from cadgen.store.records import current_tree
        from cadgen.store.trees import tree_kind_for

        model = _model_for_spec(spec)
        tree = current_tree(model) if model is not None else None
        reported.append(
            {
                "ok": True,
                # Read off the tree (store.trees.tree_kind), the same answer
                # inspect gives; the authored kind only steered the packaging.
                "kind": tree_kind_for(tree) or spec.kind,
                "outcome": outcome,
                # The document the run wrote (None for a mesh-only model, which
                # declares no STEP) and the hash of the result tree it came from.
                "document": _display_path(spec.step_path) if spec.step_output else None,
                "tree": tree,
            }
        )

    def _flush() -> None:
        # STDOUT IS THE RESULT, on every CLI. `gen` used to print nothing there at all --
        # its only output was the logger's prose on stderr -- so a caller reading the two
        # streams apart got an exit code and nothing else, while export, snapshot, validate
        # and inspect all answered on stdout. One line per target, `outcome document`
        # (`outcome <tree hash>` for a model with no document), upgraded to JSON by --json.
        for entry in reported:
            if json_output:
                print(json.dumps(entry, separators=(",", ":")))
            else:
                print(f"{entry['outcome']} {entry['document'] or entry['tree']}")
    all_specs, selected_specs = _selected_specs_for_targets(targets, step_options=step_options)
    for spec in selected_specs:
        _validate_step_target(spec, tool_name=tool_name)
    if step_options is not None and step_options.has_metadata:
        selected_specs = [_apply_step_options_to_spec(spec, step_options) for spec in selected_specs]
    # Children are not rebuilt here any more: a parent depends on its children by
    # RESULT (their pinned trees, gate clause 3), and a stale child is built when
    # the parent's body calls it (cadgen.authoring._compose_child).
    # No-op fast path: skip recomposing a model the gate says is current.
    if not force:
        current_specs = [
            spec
            for spec in selected_specs
            # An explicit STEP export (--write) keeps the spec in the run
            # UNLESS the recorded export already matches the current closure —
            # then it is reused (or copied into place), never rebuilt.
            if (not _spec_requests_extra_outputs(spec) or _step_export_current(spec))
            and _assembly_is_current(spec)
            and _assembly_glb_package_current(spec)
        ]
        if current_specs:
            for spec in current_specs:
                if spec.step_export_path is not None:
                    logger.info(
                        f"{spec.cad_ref} step export is current; reusing "
                        f"{_display_path(spec.step_export_path)}"
                    )
                else:
                    logger.info(f"{spec.cad_ref} is current; not rebuilt")
                # A current model can still owe declared mesh exports (deleted
                # file, changed declaration): heal them from the store package
                # without leaving the no-op path.
                _produce_declared_mesh_exports(spec, logger=logger)
                _emit(spec, "current")
                _tree_event(spec, "current")
            current_refs = {spec.source_ref for spec in current_specs}
            selected_specs = [spec for spec in selected_specs if spec.source_ref not in current_refs]
            if not selected_specs:
                logger.total()
                _flush()
                return 0
    entries_by_step_path = _entries_by_step_path([*all_specs, *selected_specs])

    # Same condition as the fast path above, re-checked when the run opens so a run
    # that started behind a concurrent build of this model no-ops instead of
    # rebuilding it. --force and explicit extra outputs always do the work.
    def _built_by_a_peer(spec: EntrySpec) -> bool:
        if force:
            return False
        if _spec_requests_extra_outputs(spec) and not _step_export_current(spec):
            return False
        return _assembly_is_current(spec) and _assembly_glb_package_current(spec)

    def generate_step(spec: EntrySpec, progress_sink: object | None = None) -> object:
        def build(tracked_spec: EntrySpec, reporter: object) -> object:
            return _generate_step_outputs_for_cli(
                tracked_spec,
                entries_by_step_path=entries_by_step_path,
                logger=logger,
                force=force,
                progress=reporter,
            )

        return _run_with_spec_generation_status(
            spec,
            "step",
            build,
            skip_if_current=_built_by_a_peer,
            progress_sink=progress_sink,
            logger=logger,
        )

    results = _run_selected_specs(
        selected_specs,
        action=generate_step,
        logger=logger,
        success_message=_generated_python_glb_summary,
    )
    for spec, result in zip(selected_specs, results):
        _emit(spec, "skipped-peer" if isinstance(result, _SkippedGeneration) else "built")
    logger.total()
    _flush()
    return 0


def generate_dxf_targets(
    targets: Sequence[str],
    *,
    force: bool = False,
    verbose: bool = False,
    json_output: bool = False,
) -> int:
    """Build drawings. A drawing is a model (STORE.md §3), so its run answers on
    stdout exactly as a STEP model's does: one `outcome document` line per
    target, upgraded to JSON by ``json_output`` (``tree`` is null — a drawing
    has no geometry tree)."""
    from cadgen.store.gate import stale

    reported: list[dict[str, object]] = []

    def _emit(spec: EntrySpec, outcome: str) -> None:
        reported.append(
            {
                "ok": True,
                "kind": "drawing",
                "outcome": outcome,
                "document": _display_path(spec.dxf_path) if spec.dxf_path is not None else None,
                "tree": None,
            }
        )

    def _flush() -> None:
        for entry in reported:
            if json_output:
                print(json.dumps(entry, separators=(",", ":")))
            else:
                print(f"{entry['outcome']} {entry['document']}")

    def dxf_output_current(script_path: Path, output_path: Path | None) -> bool:
        # The ONE gate every model answers to (STORE.md §4): the drawing's record,
        # its closure, its pinned children and its .dxf output.
        if output_path is None:
            return False
        verdict = stale(script_path)
        return not verdict.stale

    tool_name = "dxf"
    logger = CliLogger("cadgen", verbose=verbose)
    all_specs, selected_specs = _selected_specs_for_targets(targets)
    for spec in selected_specs:
        _validate_dxf_target(spec)

    # The .dxf IS the product: every drawing writes the `.dxf` its decorator
    # declares (`out=`, else the sibling `<name>.dxf`). The viewer parses that
    # file directly; there is no drawing package.
    def _effective_output(spec: EntrySpec) -> Path | None:
        return spec.dxf_path

    # No-op fast path: skip regenerating a drawing whose source closure is
    # unchanged and whose recorded output still verifies byte-for-byte.
    if not force:
        current_specs = [
            spec
            for spec in selected_specs
            if spec.script_path is not None
            and dxf_output_current(spec.script_path, _effective_output(spec))
        ]
        for spec in current_specs:
            logger.info(f"{spec.cad_ref} is current; not rebuilt")
            _emit(spec, "current")
        current_refs = {spec.source_ref for spec in current_specs}
        selected_specs = [spec for spec in selected_specs if spec.source_ref not in current_refs]
    if selected_specs:
        # Re-checked when the run opens, like the STEP path: a run that started behind
        # a concurrent build of this drawing must not regenerate it.
        def _built_by_a_peer(spec: EntrySpec) -> bool:
            if force or spec.script_path is None:
                return False
            return dxf_output_current(spec.script_path, _effective_output(spec))

        results = _run_selected_specs(
            selected_specs,
            action=lambda spec, progress_sink=None: _run_with_spec_generation_status(
                spec,
                "dxf",
                lambda tracked_spec, reporter: run_script_generator(
                    tracked_spec,
                    "dxf",
                    logger=logger,
                    progress=reporter,
                    model_prints_to_stdout=True,
                ),
                skip_if_current=_built_by_a_peer,
                progress_sink=progress_sink,
                logger=logger,
            ),
            logger=logger,
            success_message=_generated_dxf_summary,
        )
        for spec, result in zip(selected_specs, results):
            _emit(spec, "skipped-peer" if isinstance(result, _SkippedGeneration) else "built")
    logger.total()
    _flush()
    return 0
