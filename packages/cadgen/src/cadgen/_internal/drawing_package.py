"""Drawing-package render artifact for DXF entries.

The DXF analog of the component-GLB package: a `<name>.dxf.py` generator's build
product — or an imported `<name>.dxf`'s — is a self-contained package directory under
the model folder's ``__cadgen__/models/``, keyed by the entry filename:

    <model-folder>/__cadgen__/models/<name>.dxf.py/
      drawing.json    # descriptor: provenance + freshness metadata
      drawing.dxf     # the drawing itself (exchange artifact)
      preview.glb     # the baked 3D flat pattern (render artifact)

**Two payloads with different jobs.** ``drawing.dxf`` is the exchange artifact (exported,
downloaded, re-imported); ``preview.glb`` is what the viewport renders. The GLB is not an
optimization: with the 2D SVG view deleted, the 3D mesh is the ONLY DXF view, and baking it
here is what lets the browser stop carrying ~1,800 lines of DXF parsing and extrusion.
It is built by a Node child of whichever
process holds this package's generation lock, because the mesher is JS and is reused verbatim
rather than reimplemented.

The descriptor carries the same provenance the assembly package records
(``sourceKind``/``sourcePath``/``sourceHash``/``sourceClosureHash``/``sourceClosureFiles``/
``generatedAt``) plus the preview's ``bake``/``bakeHash``. The viewer's freshness gate reads it
exactly as it reads ``assembly.json``.

**Write order is load-bearing:** the descriptor is removed first, the payloads are written,
and the descriptor is written LAST. A reader validates the descriptor *and* every payload it
names, so a failed build leaves a package with no descriptor (``needs-build``) rather than one
claiming a preview that is missing or half-written.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from cadgen._internal.atomic_replace import replace_atomic
from cadgen._internal.file_metadata import text_to_cad_identity_metadata, write_dxf_text_to_cad_metadata
from cadgen._internal.node_runtime import node_builder_script, run_node_builder
from cadgen._internal.package_freshness import (
    bake_hash_matches,
    canonical_bake_hash,
    schema_version_matches,
)
from cadgen._internal.source_hash import (
    PythonSourceClosure,
    closure_hash_matches,
    python_source_hash,
)
from cadgen.catalog import render_package_dir
from cadgen.drawing_checks import document_is_drawing
from cadgen.render import relative_to_file, sha256_file

DRAWING_PACKAGE_KIND = "drawing-package"
# Bumped from 1 when the package gained ``preview.glb``. This is the stack's single
# invalidation channel (viewer/server_py/artifact.py, package_freshness): every drawing
# package written before the preview reports unsupported and rebuilds once, lazily.
# v4: previewStats gained bendAxisX, which the viewer's fold needs. A package without it is
# not merely old -- its Bends tab can never fold -- so every v3 package must rebuild.
# v5: the package gained geometry.json (the parsed 2D contours), which the viewer's curved
# bend mode re-meshes from. A package without it cannot render curved bends.
# v6: geometry.json grew text markings, the layer summary (colors, kinds), and the source
# units scale (dxf-geometry/2), and the parser now honors $INSUNITS — an inch-unit package
# built before v6 is both missing overlays and 25.4x too small.
#
# Named for the file format, not for "drawings": a second 2D format would parse and bake
# differently, so it gets its own cache key rather than sharing this one and forcing every
# DXF package to rebuild whenever it changes.
DXF_PACKAGE_SCHEMA_VERSION = 6
DRAWING_DESCRIPTOR_NAME = "drawing.json"
DRAWING_PREVIEW_NAME = "preview.glb"
# What KIND of DXF the package holds, decided from the file itself at build time. A cut layout
# bakes a 3D prism of its profile; a dimensioned drawing has no flat pattern and carries only
# its 2D geometry. Recorded so a reader does not have to re-parse the DXF to find out.
DRAWING_PROFILE_CUT = "cut"
DRAWING_PROFILE_DRAWING = "drawing"


def descriptor_is_drawing(descriptor: object) -> bool:
    """Whether this package holds a dimensioned drawing rather than a cut layout."""
    if not isinstance(descriptor, dict):
        return False
    return str(descriptor.get("profile") or "").strip().lower() == DRAWING_PROFILE_DRAWING


def drawing_payload_keys(descriptor: object) -> tuple[str, ...]:
    """The payload refs this package must hold, which depends on what it is.

    ONE definition, because cadgen's producer gate and the viewer's validator must ask the
    same question -- a check one makes and the other does not is either a silent stale package
    or a rebuild that never finishes.
    """
    return ("geometry",) if descriptor_is_drawing(descriptor) else ("preview", "geometry")

# The Node builder that turns drawing.dxf into preview.glb.
DRAWING_PREVIEW_BUILDER = "dxf-artifact.mjs"

# --- the preview bake -----------------------------------------------------------------
# What the build FROZE into preview.glb, canonicalized into the descriptor's ``bakeHash`` and
# compared by BOTH freshness authorities -- this module's ``drawing_package_current`` (which
# decides a build no-ops) and the viewer's spec table (which decides what a status GET
# answers). Changing any value here invalidates every drawing package, exactly once.
#
# It is now just the geometry contract, because nothing configurable is baked. Thickness and
# bend angle are RENDER-TIME parameters applied to the baked prism (see previewGlb.js), so
# they can change per view without invalidating anything -- a slider must not be able to make
# a cache stale. Thickness in particular used to live here as a frozen 2.0 mm that no user
# could change and every edit invalidated.
#
# Mirrors DXF_PREVIEW_BAKE_FORMAT in packages/cadjs/src/lib/dxf/previewGlb.js. Bump it there
# and here together when the baked geometry's contract changes.
# v2: CAD Z-up positions. v3: reference-thickness prism, thickness applied at render.
# v4: $INSUNITS honored, geometry scaled to mm at parse time.
DRAWING_PREVIEW_BAKE_FORMAT = "dxf-preview-glb-v4"


def drawing_preview_bake_settings() -> dict[str, object]:
    """The preview settings this producer bakes, for :func:`canonical_bake_hash`.

    A function rather than a constant so both authorities read the CURRENT value at call
    time -- the viewer's spec table stores this callable, and this module calls it -- which is
    what keeps them from drifting apart by one edit.
    """
    return {"format": DRAWING_PREVIEW_BAKE_FORMAT}


def drawing_descriptor_path(package_dir: Path) -> Path:
    return Path(package_dir) / DRAWING_DESCRIPTOR_NAME


def drawing_preview_path(package_dir: Path) -> Path:
    return Path(package_dir) / DRAWING_PREVIEW_NAME


def load_drawing_descriptor(package_dir: Path) -> dict[str, object] | None:
    try:
        with drawing_descriptor_path(package_dir).open("r", encoding="utf-8") as handle:
            descriptor = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(descriptor, dict) or descriptor.get("kind") != DRAWING_PACKAGE_KIND:
        return None
    return descriptor


@contextlib.contextmanager
def _deterministic_dxf_output(document: object):
    """Make ezdxf output a pure function of the drawing content while saving.

    ezdxf stamps volatile metadata into every file (julian-date headers, random
    fingerprint/version GUIDs, created/written-by markers with timestamps), which
    would churn the package's dxfHash on every rebuild. The cached drawing is a
    content-addressed render artifact — provenance lives in drawing.json — so it
    is saved with ezdxf's fixed-metadata mode plus a pinned ezdxf marker string
    (the written-by marker is stamped unconditionally on export and is not
    covered by the fixed-metadata option): identical geometry produces identical
    bytes."""
    try:
        import ezdxf
        from ezdxf import document as ezdxf_document
    except ImportError:
        yield
        return
    options = ezdxf.options
    previous_fixed = bool(getattr(options, "write_fixed_meta_data_for_testing", False))
    # Tolerate ezdxf API drift: if the marker hook disappears, output degrades to
    # "written-by marker not pinned" instead of every build crashing.
    previous_marker = getattr(ezdxf_document, "ezdxf_marker_string", None)
    fixed_marker = f"{ezdxf.__version__} @ 2000-01-01T00:00:00+00:00"
    previous_created: str | None = None
    metadata = None
    options.write_fixed_meta_data_for_testing = True
    try:
        if previous_marker is not None:
            ezdxf_document.ezdxf_marker_string = lambda: fixed_marker
        metadata_reader = getattr(document, "ezdxf_metadata", None)
        if callable(metadata_reader):
            metadata = metadata_reader()
            # The created-by marker was stamped when the generator constructed the
            # document (before this save path had any control); pin it for the
            # cached package write and RESTORE it afterwards so later saves of the
            # same document (e.g. a --dxf export) keep real provenance.
            try:
                previous_created = metadata[ezdxf_document.CREATED_BY_EZDXF]
            except Exception:  # noqa: BLE001 - ezdxf metadata API drift; a missing created-by marker degrades gracefully
                previous_created = None
            metadata[ezdxf_document.CREATED_BY_EZDXF] = fixed_marker
        yield
    finally:
        options.write_fixed_meta_data_for_testing = previous_fixed
        if previous_marker is not None:
            ezdxf_document.ezdxf_marker_string = previous_marker
        if metadata is not None and previous_created is not None:
            metadata[ezdxf_document.CREATED_BY_EZDXF] = previous_created


def serialize_drawing_document(document: object) -> str:
    """An ezdxf document as DXF text, with volatile metadata pinned.

    Determinism is kept for the EXPORT path rather than for a hash: no `.dxf` is cached any
    more, so nothing compares these bytes -- but downloading the same drawing twice should
    still hand back identical files, and ezdxf otherwise stamps julian dates and fresh GUIDs
    into every save.
    """
    saveas = getattr(document, "write", None)
    if not callable(saveas):
        raise TypeError(
            f"gen_dxf() envelope field 'document' must be a DXF document, got {type(document).__name__}"
        )
    buffer = io.StringIO()
    with _deterministic_dxf_output(document):
        document.write(buffer)  # type: ignore[attr-defined]
    return buffer.getvalue()


def _open_package(package_dir: Path) -> Path:
    """Create ``package_dir`` and CLEAR it.

    From here until the descriptor is rewritten the package reports needs-build to every
    reader, which is exactly right: its payloads are being replaced. Dropping the descriptor
    first is what makes "a failed build leaves no descriptor" true of a REBUILD too --
    otherwise a Node-side failure would leave the previous descriptor standing over a stale
    (or absent) ``preview.glb``.

    Clearing the REST is what keeps "the descriptor names its payloads" honest in both
    directions. Removing a payload from the format used to leave the old file sitting in
    every existing package forever -- which is how ``drawing.dxf`` would have lingered after
    the cache stopped holding DXFs at all. A package now contains exactly what the build that
    wrote it produced.

    Only files are removed, and only inside the package. The lock sentinels live beside the
    directory, not in it, so a concurrent holder is untouched.
    """
    package_dir.mkdir(parents=True, exist_ok=True)
    drawing_descriptor_path(package_dir).unlink(missing_ok=True)
    for entry in package_dir.iterdir():
        if entry.is_file():
            entry.unlink(missing_ok=True)
    return package_dir


def build_drawing_preview(
    package_dir: Path,
    *,
    dxf_text: str,
    run: object,
    name: str = "",
    profile: str = DRAWING_PROFILE_CUT,
) -> dict[str, object]:
    """Build ``preview.glb`` from the package's ``drawing.dxf``, in a Node child.

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
    if not str(dxf_text or "").strip():
        raise RuntimeError(f"No DXF content to build a preview from: {package_dir}")
    run_id = str(getattr(run, "run_id", "") or "")
    if not run_id:
        # No run id means no lock was taken, and the child would refuse the write anyway.
        # Failing here says WHY, in the language of the producer rather than the sentinel.
        raise RuntimeError(
            "Building a drawing package requires the artifact_build run that holds its write "
            f"lock; got run={run!r} for {package_dir}"
        )
    args = [
        "--package-dir", str(package_dir),
        "--run-id", run_id,
        "--name", name or package_dir.name,
        "--profile", str(profile or DRAWING_PROFILE_CUT),
    ]
    if bool(getattr(run, "degraded", False)):
        # Locking was unavailable, so the run id above is minted rather than stamped and the
        # child cannot verify it. Say so, instead of letting it read as a lock violation:
        # this used to fail every DXF build on a filesystem without advisory locks.
        args += ["--lock-degraded", "1"]
    payload = run_node_builder(
        node_builder_script(DRAWING_PREVIEW_BUILDER),
        args,
        run=run,
        stdin_text=dxf_text,
    )
    if not payload.get("ok"):
        raise RuntimeError(f"DXF preview build failed: {package_dir}")
    if str(payload.get("runId") or "") != run_id:
        # The child echoes the id it verified against the sentinel. A mismatch means the
        # process that wrote the payload was not the one holding the lock.
        raise RuntimeError(
            f"DXF preview builder reported a different run id than the lock holder: {package_dir}"
        )
    # A drawing profile writes geometry.json and no prism, by design; anything else must have
    # produced the preview it claims. Checking what the child SAID it wrote against what is on
    # disk is the point of this gate -- a builder that silently skipped its payload would leave
    # a descriptor pointing at nothing.
    wrote_preview = str(payload.get("preview") or "").strip()
    if wrote_preview and not drawing_preview_path(package_dir).is_file():
        raise RuntimeError(f"DXF preview builder wrote no {DRAWING_PREVIEW_NAME}: {package_dir}")
    geometry_ref = str(payload.get("geometryFile") or "").strip()
    if not geometry_ref or not (package_dir / geometry_ref).is_file():
        raise RuntimeError(f"DXF preview builder wrote no geometry payload: {package_dir}")
    if not wrote_preview and str(payload.get("profile") or "").strip().lower() != DRAWING_PROFILE_DRAWING:
        raise RuntimeError(f"DXF preview builder wrote no {DRAWING_PREVIEW_NAME}: {package_dir}")
    return payload


def _write_descriptor(package_dir: Path, descriptor: dict[str, object]) -> dict[str, object]:
    """Write ``drawing.json`` LAST, atomically. Temp + replace so a reader sees the old
    descriptor or the new one, never a partial parse."""
    descriptor_path = drawing_descriptor_path(package_dir)
    temp_path = descriptor_path.with_name(f".{descriptor_path.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(descriptor, handle, indent=2, sort_keys=True)
        handle.write("\n")
    replace_atomic(temp_path, descriptor_path)
    return descriptor


def write_drawing_package(
    document: object,
    *,
    script_path: Path,
    source_closure: PythonSourceClosure | None,
    run: object = None,
) -> dict[str, object]:
    """Save ``document`` (an ezdxf document) into the generator's drawing package, bake its
    3D preview, and write the descriptor. Returns the descriptor dict.

    Called from inside ``run_script_generator``, which every drawing producer -- the ``dxf``
    gen CLI and ``cadgen.dxf_artifact`` alike -- runs under ``artifact_build``. Building the
    preview HERE rather than in each producer is what stops a second producer from writing a
    package that can never be current."""
    saveas = getattr(document, "saveas", None)
    if not callable(saveas):
        raise TypeError(
            f"gen_dxf() envelope field 'document' must be a DXF document, got {type(document).__name__}"
        )
    resolved_script = script_path.resolve()
    package_dir = _open_package(render_package_dir(resolved_script))
    source_identity = python_source_hash(resolved_script)
    # Serialised to a STRING, never to a file in the package. The drawing is an input to the
    # bake, not a product of it, and a generated DXF is reproducible on demand -- so it is
    # streamed to the mesher and nothing lands in __cadgen__ but preview.glb.
    dxf_text = serialize_drawing_document(document)
    # A dimensioned drawing has no flat pattern, so there is nothing to bake and nothing to
    # fold: preview.glb is the 3D prism of a CUT profile. The file says which it is (see
    # cadgen.drawing_checks.document_is_drawing), so a drawing package carries its 2D geometry
    # and declares the omission rather than failing on a preview it should never have had.
    is_drawing, _ = document_is_drawing(document)
    # The builder still runs: geometry.json is the parsed 2D drawing, which is what the viewer
    # renders and what a drawing package is FOR. Only the 3D prism is skipped.
    preview = build_drawing_preview(
        package_dir,
        dxf_text=dxf_text,
        run=run,
        name=resolved_script.name,
        profile=DRAWING_PROFILE_DRAWING if is_drawing else DRAWING_PROFILE_CUT,
    )
    descriptor: dict[str, object] = {
        "kind": DRAWING_PACKAGE_KIND,
        "profile": DRAWING_PROFILE_DRAWING if is_drawing else DRAWING_PROFILE_CUT,
        "packageSchemaVersion": DXF_PACKAGE_SCHEMA_VERSION,
        "sourceKind": "python",
        # Like the assembly package, sourcePath/sourceClosureFiles are relative to the
        # MODEL folder (the directory holding the .dxf.py), not the __cadgen__ dir.
        "sourcePath": resolved_script.name,
        "sourceHash": source_identity.source_hash,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **_preview_descriptor_fields(preview),
    }
    if source_closure is not None and source_closure.files:
        descriptor["sourceClosureHash"] = source_closure.closure_hash
        descriptor["sourceClosureFiles"] = list(source_closure.files)
    return _write_descriptor(package_dir, descriptor)


def write_imported_drawing_package(
    dxf_path: Path,
    *,
    run: object = None,
) -> dict[str, object]:
    """Build the drawing package for an IMPORTED ``.dxf`` and return the descriptor.

    Same package, same payloads, same validator; the only differences are that there is no
    generator to run (the DXF is copied in rather than saved out) and that freshness is the
    imported kind -- a plain content digest of the source file rather than a source closure.
    This mirrors an imported ``.step`` exactly: the VIEWER owns and builds it on demand, while
    the gen CLI stays ``.dxf.py``-only (design §0.1)."""
    resolved_dxf = Path(dxf_path).expanduser().resolve()
    if not resolved_dxf.is_file():
        raise FileNotFoundError(f"DXF file does not exist: {resolved_dxf}")
    package_dir = _open_package(render_package_dir(resolved_dxf))
    # READ, not copied. The user's file is right there and the package is keyed to its path,
    # so a copy bought no resilience -- only a duplicate of an input and a second hash of the
    # same bytes. Streaming it is also what makes this indistinguishable from the generated
    # path inside the builder.
    preview = build_drawing_preview(
        package_dir,
        dxf_text=resolved_dxf.read_text(encoding="utf-8", errors="replace"),
        run=run,
        name=resolved_dxf.name,
    )
    descriptor: dict[str, object] = {
        "kind": DRAWING_PACKAGE_KIND,
        "packageSchemaVersion": DXF_PACKAGE_SCHEMA_VERSION,
        "sourceKind": "dxf",
        "sourcePath": resolved_dxf.name,
        # The imported digest the spec table names (`source_digest_field`). Fails closed:
        # a descriptor with no digest for a file that is right there is not current.
        "sourceDigest": sha256_file(resolved_dxf),
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **_preview_descriptor_fields(preview),
    }
    return _write_descriptor(package_dir, descriptor)


def _preview_descriptor_fields(preview: dict[str, object] | None) -> dict[str, object]:
    """The preview payload ref plus the bake block and its hash.

    ``None`` for a drawing: no bake happened, so recording a bakeHash would claim a preview
    that does not exist and the freshness gates would then chase it forever.
    """
    if preview is None:
        return {}
    geometry = str(preview.get("geometryFile") or "").strip() or None
    # A drawing has no prism, so no preview ref and no bake to record. Claiming either would
    # send both freshness gates chasing a payload that was never written.
    if str(preview.get("profile") or "").strip().lower() == DRAWING_PROFILE_DRAWING:
        return {"geometry": geometry}
    bake = drawing_preview_bake_settings()
    fields: dict[str, object] = {
        "preview": DRAWING_PREVIEW_NAME,
        "geometry": geometry,
        "bake": bake,
        "bakeHash": canonical_bake_hash(bake),
    }
    stats = {
        key: preview[key]
        # bendLineCount rides along: it is a fact about the DRAWING that the viewer needs to
        # decide whether a Bends tab applies, and re-deriving it would mean parsing the DXF
        # on a catalog scan.
        for key in ("triangleCount", "vertexCount", "bytes", "bendLineCount")
        if isinstance(preview.get(key), (int, float)) and not isinstance(preview.get(key), bool)
    }
    axes = preview.get("bendAxisX")
    if isinstance(axes, list) and axes:
        stats["bendAxisX"] = [float(v) for v in axes if isinstance(v, (int, float))]
    if stats:
        fields["previewStats"] = stats
    return fields


def export_drawing_dxf(script_path: Path, export_path: Path) -> Path:
    """Write a generated drawing's DXF to ``export_path`` by RUNNING its generator.

    There is no cached `.dxf` to copy: __cadgen__ holds only what the viewer renders, so a
    download regenerates, exactly as a `.step.py` download does. Measured at roughly two
    seconds, almost all of it Python start and the ezdxf import rather than the drawing --
    paid on an explicit click, never on a viewport open.

    The document is validated on the way out for the same reason generation validates it: an
    export is a deliverable, and shipping a drawing whose cut profile does not close would be
    worse than failing here.
    """
    from cadgen._internal.generation import _normalize_dxf_payload
    from cadgen.drawing_checks import raise_on_error_findings, validate_drawing_document
    from cadgen.sources import load_source_module

    resolved_script = script_path.resolve()
    module = load_source_module(resolved_script)
    generator = getattr(module, "gen_dxf", None)
    if not callable(generator):
        raise RuntimeError(f"DXF export requires a gen_dxf() generator: {resolved_script}")
    envelope = _normalize_dxf_payload(generator(), script_path=resolved_script)
    document = envelope.get("document")
    findings = validate_drawing_document(document)
    raise_on_error_findings(findings, label=str(resolved_script))

    export_path = Path(export_path).expanduser().resolve()
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(serialize_drawing_document(document), encoding="utf-8")
    write_dxf_text_to_cad_metadata(
        export_path,
        text_to_cad_identity_metadata(
            source_path=relative_to_file(resolved_script, export_path),
            source_hash=python_source_hash(resolved_script).source_hash,
        ),
    )
    return export_path


def drawing_package_current(source_path: Path) -> bool:
    """True when ``source_path``'s drawing package exists, records the current schema and
    bake, holds every payload it names, and still matches its source (the CLI no-op fast path
    and the producer's under-lock re-check, mirroring the STEP `_assembly_is_current` gate).

    ``source_path`` is the ``.dxf.py`` generator for a generated drawing, or the ``.dxf``
    itself for an imported one; the descriptor's ``sourceKind`` decides which provenance
    question is asked, exactly as the viewer's validator does.

    Every gate here mirrors the viewer's validator (``viewer/server_py/artifact.py``) check
    for check. They have to: this predicate is what decides a build no-ops, so a check the
    viewer makes and this one does not turns a stale package into a silent ``ready`` rather
    than a rebuild — and a check this one makes and the viewer does not rebuilds forever.
    """
    resolved_source = Path(source_path).resolve()
    package_dir = render_package_dir(resolved_source)
    descriptor = load_drawing_descriptor(package_dir)
    if descriptor is None:
        return False
    if not schema_version_matches(descriptor, DXF_PACKAGE_SCHEMA_VERSION):
        return False
    # The preview settings this build froze into preview.glb. No other signal can see a
    # change to them, so without this a thickness edit would leave every built package
    # rendering its old bake, silently.
    # The package's payloads, named by the descriptor. A missing preview.glb has to be
    # stale here as well as in the viewer, or the CLI would report "current" over a package
    # the viewer cannot render. There is no longer a `dxf` payload to check: the cache holds
    # what was computed, and a generated drawing's DXF is produced on demand.
    # A drawing package has no preview and no bake -- see write_drawing_package. Requiring one
    # here would report every drawing stale forever, which is how a "current" check turns into
    # a rebuild loop.
    if not descriptor_is_drawing(descriptor):
        if not bake_hash_matches(descriptor, canonical_bake_hash(drawing_preview_bake_settings())):
            return False
    for payload_key in drawing_payload_keys(descriptor):
        payload_ref = str(descriptor.get(payload_key) or "").strip()
        if not payload_ref or not (package_dir / payload_ref).is_file():
            return False
    if str(descriptor.get("sourceKind") or "").strip().lower() == "python":
        closure_hash = str(descriptor.get("sourceClosureHash") or "").strip()
        closure_files = descriptor.get("sourceClosureFiles")
        if not closure_hash or not isinstance(closure_files, list) or not closure_files:
            return False
        return closure_hash_matches(closure_hash, closure_files, base=resolved_source.parent)
    # Imported: the file on disk must still hash to the digest the descriptor recorded.
    # Fails closed on a missing digest, matching the viewer and cadgen's own producer gate.
    recorded = str(descriptor.get("sourceDigest") or "").strip()
    if not resolved_source.is_file():
        return False
    return bool(recorded) and recorded == sha256_file(resolved_source)
