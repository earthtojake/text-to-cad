"""Implicit-CAD render package: what it holds, how it is written, when it is stale.

An ``.implicit.js`` source is an executable ES module whose surface is GLSL, so until now the
only way to see one was to run its shader in the browser -- a render path nothing else in the
viewer shares. The package makes it an ordinary baked mesh:

    <model-folder>/__cadgen__/models/<name>.implicit.js/
      implicit.json   # descriptor: provenance, bake settings, stats
      model.glb       # the baked mesh (quantized + meshopt-compressed)

**Baked, not live.** The mesh is sampled at the model's ``params.*.default`` values and one
fixed resolution; live parameters and animations are gone, deliberately and with no
opt-in. Those settings are invisible to every other
freshness signal -- the source is unchanged, the payload is present, the closure still hashes
-- so they are canonicalized into ``bakeHash`` and compared by BOTH freshness authorities.

**Node owns geometry; this module owns everything else.** The mesher and the GLB writer are
JS (``packages/cadjs/bin/implicit-artifact.mjs``), spawned as a child of whichever process
holds this package's generation lock. The child reports which files the model actually loaded;
the digest over them is computed HERE, because a second implementation of the closure hash is
exactly the duplication the coordination refactor deleted (§5.2).

**Write order is load-bearing:** the descriptor is removed first, ``model.glb`` is written by
the child, and the descriptor is written LAST. A reader validates the descriptor *and* every
payload it names, so a failed build leaves a package with no descriptor (``needs-build``)
rather than one claiming a mesh that is missing or half-written.

stdlib only: the viewer's long-lived server imports this for its freshness gate, exactly as it
imports ``_internal.drawing_package``, and must never load a CAD runtime to answer a GET.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from cadgen._internal.atomic_replace import replace_atomic
from cadgen._internal.node_runtime import node_builder_script, run_node_builder
from cadgen._internal.package_freshness import (
    bake_hash_matches,
    canonical_bake_hash,
    schema_version_matches,
)
from cadgen._internal.source_hash import closure_for_files, closure_hash_matches
from cadgen.catalog import render_package_dir

IMPLICIT_PACKAGE_KIND = "implicit-package"
IMPLICIT_PACKAGE_SCHEMA_VERSION = 1
IMPLICIT_DESCRIPTOR_NAME = "implicit.json"
IMPLICIT_GLB_NAME = "model.glb"

# The Node builder that meshes the model and writes model.glb.
IMPLICIT_BUILDER = "implicit-artifact.mjs"

# Sources this package is built from. `.implicit.mjs` is accepted because the loader is
# `import()` and Node resolves both.
IMPLICIT_SUFFIXES = (".implicit.js", ".implicit.mjs")

# --- the bake -------------------------------------------------------------------------
# `DEFAULT_RESOLUTION` in packages/implicitjs/src/lib/implicitCad/mesh.js, and the resolution
# all 43 shipped models were authored against. Lowering it would visibly coarsen every one of
# them to save time on an artifact that is built once and cached (§0.1 decision 2).
DEFAULT_BAKE_RESOLUTION = 144
# `DEFAULT_MAX_CELLS` in the same module: the grid is downscaled to fit this many cells, so it
# is part of what a build froze into the mesh even though it rarely binds.
DEFAULT_BAKE_MAX_CELLS = 2500000
# Bump together with any change to what the builder writes for the same inputs (the mesher's
# orientation/normal contract, the GLB preset, the welding rule). Bumping invalidates every
# implicit package, exactly once, on next open.
IMPLICIT_BAKE_FORMAT = "implicit-render-glb-v1"


def implicit_bake_settings(resolution: int | None = None) -> dict[str, object]:
    """The settings a build freezes into ``model.glb``, for :func:`canonical_bake_hash`.

    A function rather than a constant so both authorities read the CURRENT values at call
    time: the viewer's spec table stores this callable and this module calls it, which is what
    keeps them from drifting apart by one edit.

    A non-default ``resolution`` is honest about its consequence: it produces a package whose
    bake hash no other caller computes, so a viewer asking with the default will report it
    stale and rebuild. Per-model resolution needs a field the SOURCE declares (so every
    caller derives the same number); until that exists, the argument is a CLI knob for
    one-off bakes, not a way to configure a model.
    """
    return {
        "format": IMPLICIT_BAKE_FORMAT,
        "resolution": normalize_bake_resolution(resolution),
        "maxCells": DEFAULT_BAKE_MAX_CELLS,
    }


def normalize_bake_resolution(resolution: object) -> int:
    """The bake resolution to use, clamped to the mesher's own accepted range.

    Clamped HERE rather than in the builder because the number is hashed: if the mesher
    silently clamped 4000 to 256, the descriptor would record a resolution the mesh was never
    built at, and the two freshness authorities would compare a fiction.
    """
    if resolution is None:
        return DEFAULT_BAKE_RESOLUTION
    try:
        value = int(resolution)
    except (TypeError, ValueError):
        return DEFAULT_BAKE_RESOLUTION
    # Mirrors normalizeResolution() in mesh.js.
    return max(8, min(256, value))


def is_implicit_source_path(source_path: Path | str) -> bool:
    name = str(source_path).lower()
    return any(name.endswith(suffix) for suffix in IMPLICIT_SUFFIXES)


def implicit_descriptor_path(package_dir: Path) -> Path:
    return Path(package_dir) / IMPLICIT_DESCRIPTOR_NAME


def implicit_glb_path(package_dir: Path) -> Path:
    return Path(package_dir) / IMPLICIT_GLB_NAME


def load_implicit_descriptor(package_dir: Path) -> dict[str, object] | None:
    try:
        with implicit_descriptor_path(package_dir).open("r", encoding="utf-8") as handle:
            descriptor = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(descriptor, dict) or descriptor.get("kind") != IMPLICIT_PACKAGE_KIND:
        return None
    return descriptor


def _open_package(package_dir: Path) -> Path:
    """Create ``package_dir`` and REMOVE its descriptor.

    From here until the descriptor is rewritten the package reports needs-build to every
    reader, which is exactly right: its payload is being replaced. Dropping it first is what
    makes "a failed build leaves no descriptor" true of a REBUILD too."""
    package_dir.mkdir(parents=True, exist_ok=True)
    implicit_descriptor_path(package_dir).unlink(missing_ok=True)
    return package_dir


def build_implicit_mesh(
    package_dir: Path,
    source_path: Path,
    *,
    run: object,
    resolution: int,
    threads: int | None = None,
    write_glb: Path | None = None,
) -> dict[str, object]:
    """Mesh ``source_path`` into ``package_dir/model.glb``, in a Node child.

    ``run`` is the :class:`~cadgen.coordination.BuildRun` holding this package's write lock.
    Its run id is handed to the child, which checks it against the lock sentinel before
    writing anything -- so ONE run id, one status record and one progress bar span both
    runtimes, and a builder started outside the lock throws (see
    ``implicitjs/glb/assertWriteLock.js``). A run that could not take a lock at all says so
    with ``--lock-degraded``, so the child skips a check it cannot pass rather than turning a
    filesystem without advisory locks into a failed build.

    Raises on any Node-side failure; the caller must then leave no descriptor behind.
    """
    package_dir = Path(package_dir)
    run_id = str(getattr(run, "run_id", "") or "")
    if not run_id:
        # No run id means no lock was taken, and the child would refuse the write anyway.
        # Failing here says WHY, in the producer's language rather than the sentinel's.
        raise RuntimeError(
            "Building an implicit package requires the artifact_build run that holds its "
            f"write lock; got run={run!r} for {package_dir}"
        )
    args = [
        "--package-dir", str(package_dir),
        "--source-path", str(source_path),
        "--run-id", run_id,
        "--resolution", str(int(resolution)),
        "--max-cells", str(int(DEFAULT_BAKE_MAX_CELLS)),
    ]
    if bool(getattr(run, "degraded", False)):
        # Locking was unavailable, so the run id above is minted rather than stamped and the
        # child cannot verify it. Say so, instead of letting it read as a lock violation.
        args += ["--lock-degraded", "1"]
    if threads is not None:
        args += ["--threads", str(int(threads))]
    if write_glb is not None:
        # Written by the child from the SAME mesh pass, in the export preset. The package's
        # own model.glb is quantized, meshopt-compressed and in glTF metres -- the right file
        # for the viewer and the wrong one to hand a slicer -- so the sibling is encoded
        # separately rather than copied.
        args += ["--write-glb", str(Path(write_glb).expanduser().resolve())]
    payload = run_node_builder(node_builder_script(IMPLICIT_BUILDER), args, run=run)
    if not payload.get("ok"):
        raise RuntimeError(f"Implicit mesh build failed: {package_dir}")
    if str(payload.get("runId") or "") != run_id:
        # The child echoes the id it verified against the sentinel. A mismatch means the
        # process that wrote the payload was not the one holding the lock.
        raise RuntimeError(
            f"Implicit builder reported a different run id than the lock holder: {package_dir}"
        )
    if not implicit_glb_path(package_dir).is_file():
        raise RuntimeError(f"Implicit builder wrote no {IMPLICIT_GLB_NAME}: {package_dir}")
    return payload


def _closure_files_from_payload(payload: dict[str, object]) -> list[str]:
    files = payload.get("closureFiles")
    return [str(file) for file in files if str(file or "").strip()] if isinstance(files, list) else []


def _stats_from_payload(payload: dict[str, object]) -> dict[str, object]:
    return {
        key: payload[key]
        for key in ("triangleCount", "vertexCount", "bytes")
        if isinstance(payload.get(key), (int, float)) and not isinstance(payload.get(key), bool)
    }


def _write_descriptor(package_dir: Path, descriptor: dict[str, object]) -> dict[str, object]:
    """Write ``implicit.json`` LAST, atomically. Temp + replace so a reader sees the old
    descriptor or the new one, never a partial parse."""
    descriptor_path = implicit_descriptor_path(package_dir)
    temp_path = descriptor_path.with_name(f".{descriptor_path.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(descriptor, handle, indent=2, sort_keys=True)
        handle.write("\n")
    replace_atomic(temp_path, descriptor_path)
    return descriptor


def write_implicit_package(
    source_path: Path,
    *,
    run: object,
    resolution: int | None = None,
    threads: int | None = None,
    write_glb: Path | None = None,
) -> dict[str, object]:
    """Build the implicit package for one ``.implicit.js`` and return its descriptor.

    With ``write_glb`` set, the sibling export GLB is written from the same mesh pass."""
    resolved_source = Path(source_path).expanduser().resolve()
    if not resolved_source.is_file():
        raise FileNotFoundError(f"Implicit CAD source does not exist: {resolved_source}")
    if not is_implicit_source_path(resolved_source):
        raise RuntimeError(
            f"Implicit render artifacts require a <name>.implicit.js source: {resolved_source}"
        )
    bake_resolution = normalize_bake_resolution(resolution)
    package_dir = _open_package(render_package_dir(resolved_source))
    payload = build_implicit_mesh(
        package_dir,
        resolved_source,
        run=run,
        resolution=bake_resolution,
        threads=threads,
        write_glb=write_glb,
    )
    # The child reported WHICH files the model loaded; the digest over them is computed here,
    # with the same function every other package format uses (§5.2). `_semantic_source_hash`
    # byte-hashes non-`.py` inputs, so a `.js` closure validates through exactly the path a
    # generated STEP or drawing does.
    closure = closure_for_files(
        resolved_source,
        _closure_files_from_payload(payload),
        base=resolved_source.parent,
    )
    bake = implicit_bake_settings(bake_resolution)
    descriptor: dict[str, object] = {
        "kind": IMPLICIT_PACKAGE_KIND,
        "packageSchemaVersion": IMPLICIT_PACKAGE_SCHEMA_VERSION,
        # The validator's generated-vs-imported discriminator, not a claim about the
        # language: "python" selects the branch that re-hashes a recorded SOURCE CLOSURE
        # (viewer/server_py/artifact.py), which is what a script-generated package of any
        # language needs. An implicit model IS generated -- by a JS module -- so it takes
        # that branch. `sourceLanguage` records what it actually is.
        "sourceKind": "python",
        "sourceLanguage": "javascript",
        # Relative to the MODEL folder, like every other package's provenance.
        "sourcePath": resolved_source.name,
        "sourceClosureHash": closure.closure_hash,
        "sourceClosureFiles": list(closure.files),
        "glb": IMPLICIT_GLB_NAME,
        "bake": bake,
        "bakeHash": canonical_bake_hash(bake),
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    for key in ("name", "units"):
        value = str(payload.get(key) or "").strip()
        if value:
            descriptor[key] = value
    bbox = payload.get("bbox")
    if isinstance(bbox, dict) and isinstance(bbox.get("min"), list) and isinstance(bbox.get("max"), list):
        descriptor["bbox"] = {"min": list(bbox["min"]), "max": list(bbox["max"])}
    stats = _stats_from_payload(payload)
    if stats:
        descriptor["stats"] = stats
    return _write_descriptor(package_dir, descriptor)


def implicit_package_current(source_path: Path, *, resolution: int | None = None) -> bool:
    """True when the model's implicit package exists, was baked with the current settings,
    and its recorded source closure still hashes unchanged.

    Every gate the viewer's validator applies is applied here, check for check. They have to
    be: this predicate is what decides a build no-ops, so a check the viewer makes and this
    one does not turns a stale package into a silent ``ready`` rather than a rebuild -- and a
    check this one makes and the viewer does not rebuilds forever
    (``cadgen._internal.package_freshness``).
    """
    resolved_source = Path(source_path).expanduser().resolve()
    package_dir = render_package_dir(resolved_source)
    descriptor = load_implicit_descriptor(package_dir)
    if descriptor is None:
        return False
    if not schema_version_matches(descriptor, IMPLICIT_PACKAGE_SCHEMA_VERSION):
        return False
    if not bake_hash_matches(descriptor, canonical_bake_hash(implicit_bake_settings(resolution))):
        return False
    glb_ref = str(descriptor.get("glb") or "").strip()
    glb_path = (package_dir / glb_ref) if glb_ref else implicit_glb_path(package_dir)
    if not glb_path.is_file():
        return False
    closure_hash = str(descriptor.get("sourceClosureHash") or "").strip()
    closure_files = descriptor.get("sourceClosureFiles")
    if not closure_hash or not isinstance(closure_files, list) or not closure_files:
        return False
    return closure_hash_matches(closure_hash, closure_files, base=resolved_source.parent)
