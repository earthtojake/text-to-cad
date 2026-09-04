"""Component extraction helpers and the view-directory assembly.json reader.

A model's result is a TREE in the store (``cadgen.store.build`` emits it):
one content-addressed component per unique part (exact ``.brep`` + ``.surf``
render bytes) plus occurrences -> component + world transform. This module
holds the per-component extraction (content hashing, surf/brep workers, the
worker pool) that build uses, and the assembly.json reader consumers apply to a
VIEW directory (``cadgen.store.view``) when they need the tree shape.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Mapping

from cadgen._internal.atomic_replace import replace_atomic, temp_suffix
from cadgen._internal.cache_schema import CACHE_SCHEMA_VERSION
from cadgen.coordination import (
    PHASE_COMPONENTS,
    PHASE_FINALIZE,
    PHASE_PACKAGE,
    resolve as resolve_progress,
)
PACKAGE_KIND = "assembly-package"
# Self-contained content-addressed packages: each model's components live INSIDE its own package
# at <store>/packages/<stepHash>-v<N>/components/<geomHash>.glb, referenced by the
# assembly.json via the flat relative ref components/<geomHash>.glb. Within-model dedup (repeated
# parts share one cid) is preserved; components are not shared ACROSS packages, so each
# view directory is a complete, relocatable unit.
COMPONENT_DIRNAME = "components"
DESCRIPTOR_NAME = "assembly.json"
# Source-provenance keys stripped from a component GLB's embedded STEP_TOPOLOGY so the
# component is a pure function of geometry+tolerances (content-addressable). All of this
# is model-level and lives in assembly.json or the source sidecar
# (the .step.json sidecar), not the reusable leaf.
COMPONENT_PROVENANCE_KEYS = (
    "sourceKind",
    "sourcePath",
    "kinematics",
    "animation",
    "sourceHash",
    "sourceClosureHash",
    "sourceClosureFiles",
    "stepPath",
    "stepHash",
    "generatedAt",
)
def is_assembly_package(path: Path) -> bool:
    """True when ``path`` is a view directory (has assembly.json)."""
    return path.is_dir() and (path / DESCRIPTOR_NAME).is_file()


def read_package_descriptor(path: Path) -> dict[str, Any] | None:
    """Load an assembly.json from a view directory (or its assembly.json path).

    Returns None for anything that is not a view directory with a readable
    assembly.json (missing, partial, or a stray file at the tree path)."""
    if path.is_dir():
        descriptor_path = path / DESCRIPTOR_NAME
    elif path.name == DESCRIPTOR_NAME:
        descriptor_path = path
    else:
        return None
    if not descriptor_path.is_file():
        return None
    try:
        descriptor = json.loads(descriptor_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return descriptor if isinstance(descriptor, dict) else None


def _component_id(source_hash: str) -> str:
    # The cid is the first 64 bits of the content hash, not an accident of slicing:
    # a tree build holds dozens of components, so the birthday bound at 2^32
    # distinct shapes is unreachable by ~9 orders of magnitude, and the hash is
    # salted by CACHE_SCHEMA_VERSION (see _content_hash_and_bytes) so an extractor
    # change re-keys every cid at once. A collision would only merge two dedup
    # entries within one build -- never a cross-package effect.
    return source_hash[:16]


def _content_hash_and_bytes(shape: Any) -> tuple[str, bytes]:
    """The content hash AND the location-stripped BREP bytes it digests, from a
    single serialization.

    The digest is salted with :data:`CACHE_SCHEMA_VERSION` because the cid
    addresses a BUILT component GLB, not the geometry alone. Each GLB embeds the
    topology tables the extractor produced, so a change to what the extractor
    emits makes every cached component wrong while its geometry — and therefore
    an unsalted digest — is unchanged. The build reuses any ``<cid>.glb`` already
    on disk, so without the salt an extractor fix would leave every existing
    tree serving the old tables behind an assembly.json that claims to be current.

    Two occurrences of the same part share an underlying ``TShape`` (``.moved()``
    only swaps the location), so stripping the location and serializing yields an
    identical digest for every repeat — the content-addressing that dedups the
    components. Stable across builds/processes (unlike Python ``hash``).

    Triangulation and normals are excluded so the digest is geometry-only:
    meshing a part attaches a triangulation to its shared ``TShape``, and a
    triangulation-sensitive hash would change after the first component is built,
    breaking the content-addressed cache on re-hash. The same bytes are the
    worker-build payload, so returning both avoids serializing each missing
    component's BREP twice (once to hash, once for the payload)."""
    brep = _shape_brep_bytes(shape)
    digest = hashlib.sha256()
    digest.update(str(CACHE_SCHEMA_VERSION).encode("utf-8"))
    digest.update(b"\x00")
    digest.update(brep)
    return digest.hexdigest(), brep


def _content_hash_shape(shape: Any) -> str:
    """sha256 of a shape's location-stripped BREP bytes (see
    :func:`_content_hash_and_bytes`)."""
    return _content_hash_and_bytes(shape)[0]


def _transform_from_location(location: Any) -> list[float]:
    """Flatten a build123d ``Location`` to a 16-float row-major 4x4 matrix."""
    trsf = location.wrapped.Transformation()
    rows = [trsf.Value(r, c) for r in range(1, 4) for c in range(1, 5)]
    return [
        rows[0], rows[1], rows[2], rows[3],
        rows[4], rows[5], rows[6], rows[7],
        rows[8], rows[9], rows[10], rows[11],
        0.0, 0.0, 0.0, 1.0,
    ]


def _bbox_from_shape(shape: Any) -> dict[str, list[float]] | None:
    """The world-frame axis-aligned bounding box of a composed shape, as the
    ``{"min": [...], "max": [...]}`` the assembly.json records so a cheap whole-entry
    inspect summary does not have to re-mesh + extract full topology.

    Computed from the geometric representation (``useTriangulation=False``) so it
    never tessellates the shape — meshing would mutate the shared ``TShape`` and
    break content-addressed component dedup on a later in-process rebuild."""
    try:
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib

        box = Bnd_Box()
        BRepBndLib.Add_s(shape.wrapped, box, False)
        xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
        return {
            "min": [float(xmin), float(ymin), float(zmin)],
            "max": [float(xmax), float(ymax), float(zmax)],
        }
    except Exception:  # noqa: BLE001 - OCP bounds reads can raise on odd shapes; a component without bounds is None
        return None


def _occurrence_color(child: Any) -> list[float] | None:
    color = getattr(child, "color", None)
    if color is None:
        return None
    try:
        return [float(color.red), float(color.green), float(color.blue), float(color.alpha)]
    except AttributeError:
        try:
            return [float(c) for c in tuple(color)]
        except TypeError:
            return None


_MATERIAL_KEYS = ("roughness", "metalness", "clearcoat", "clearcoatRoughness", "opacity")


def _occurrence_material(child: Any) -> dict[str, float] | None:
    """Optional per-occurrence PBR overrides authored as a plain
    ``cad_material`` dict attribute on the source shape (keys from
    ``_MATERIAL_KEYS``, values clamped to [0, 1]). Colors alone cannot
    express brushed-vs-polished finishing; these ride the assembly.json so the
    viewer can override its theme material per part."""
    material = getattr(child, "cad_material", None)
    if not isinstance(material, dict):
        return None
    resolved: dict[str, float] = {}
    for key in _MATERIAL_KEYS:
        value = material.get(key)
        if value is None:
            continue
        try:
            resolved[key] = min(1.0, max(0.0, float(value)))
        except (TypeError, ValueError):
            continue
    return resolved or None


def _unlocated_shape(shape: Any) -> Any:
    """A copy of ``shape`` moved to the identity location (its LOCAL frame), preserving the
    ``label``/``color`` a clean component still carries. Mirrors ``_content_hash_shape``'s
    location stripping so the emitted GLB is the exact local geometry the cid addresses.

    Uses OCCT's ``TopoDS_Shape.Located`` (shares the underlying ``TShape``, O(1)) rather than
    build123d's ``shape.located()``, which ``copy.deepcopy``s the whole shape graph on every
    call (~5 s per component on tom — historically ~85% of the fresh-build time). The
    geometry-only content hash is unaffected: it excludes triangulation, and distinct parts
    keep distinct ``TShape``s, so meshing one component never perturbs another's digest.

    Parametric build123d primitives (``Box``/``Cylinder``/...) reject a ``TopoDS`` constructor,
    so for those the cheap OCCT wrap raises ``TypeError`` and we fall back to build123d's
    ``located()`` (correct, and primitives are small so the deepcopy is negligible)."""
    from OCP.TopLoc import TopLoc_Location

    try:
        local = type(shape)(shape.wrapped.Located(TopLoc_Location()))
    except TypeError:
        from build123d import Location

        local = shape.located(Location())
    label = getattr(shape, "label", "")
    if label:
        local.label = label
    color = getattr(shape, "color", None)
    if color is not None:
        local.color = color
    face_colors = getattr(shape, "cad_face_ordinal_colors", None)
    if face_colors:
        local.cad_face_ordinal_colors = face_colors
    return local


def _shape_brep_bytes(shape: Any) -> bytes:
    """Location-stripped binary BREP of a shape (no triangulation/normals) — the
    process-boundary payload for parallel component builds. Mirrors
    ``_content_hash_shape``'s serialization so the worker rebuilds exactly the
    geometry the cid addresses.

    Takes a build123d shape or a bare ``TopoDS_Shape``: ``inspect validate``
    ships its per-prototype payloads through here too, and it holds kernel
    shapes, not wrappers."""
    import io

    from OCP.BinTools import BinTools, BinTools_FormatVersion
    from OCP.TopLoc import TopLoc_Location

    stream = io.BytesIO()
    BinTools.Write_s(
        getattr(shape, "wrapped", shape).Located(TopLoc_Location()),
        stream,
        False,  # theWithTriangles
        False,  # theWithNormals
        # PINNED, not _CURRENT: these component objects are content-addressed — their
        # bytes ARE the cid. A floating _CURRENT would let a future OCP
        # upgrade silently re-serialize every component object and re-key every cid as a
        # dependency-update side effect. Bumping this must stay a deliberate
        # act — treat it like a schema version bump.
        BinTools_FormatVersion.BinTools_FormatVersion_VERSION_4,
    )
    return stream.getvalue()


def _build123d_shape_from_brep_bytes(payload: bytes) -> Any:
    """Rebuild a build123d shape from ``_shape_brep_bytes`` output (worker side).

    The component GLB is a pure function of geometry + mesh tolerances (labels
    and provenance are stripped), so wrapping in the ShapeType-matched build123d
    class reproduces the serial build byte-for-byte."""
    import io

    import build123d
    from OCP.BinTools import BinTools
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopoDS import TopoDS_Shape

    topo = TopoDS_Shape()
    BinTools.Read_s(topo, io.BytesIO(payload))
    if topo.IsNull():
        raise RuntimeError("component BREP payload deserialized to a null shape")
    by_type = {
        TopAbs_ShapeEnum.TopAbs_COMPOUND: build123d.Compound,
        TopAbs_ShapeEnum.TopAbs_COMPSOLID: build123d.Compound,
        TopAbs_ShapeEnum.TopAbs_SOLID: build123d.Solid,
        TopAbs_ShapeEnum.TopAbs_SHELL: build123d.Shell,
        TopAbs_ShapeEnum.TopAbs_FACE: build123d.Face,
        TopAbs_ShapeEnum.TopAbs_WIRE: build123d.Wire,
        TopAbs_ShapeEnum.TopAbs_EDGE: build123d.Edge,
        TopAbs_ShapeEnum.TopAbs_VERTEX: build123d.Vertex,
    }
    cls = by_type.get(topo.ShapeType(), build123d.Compound)
    return cls(topo)


# Some imported (vendor STEP / boolean-derived) solids serialize BREP entities
# that BinTools cannot READ back (an OCCT write/read asymmetry, e.g. point
# representations) — their payloads cannot cross a process boundary, so they
# fall back to an in-process build from the original shape.
PAYLOAD_UNREADABLE = "__payload-unreadable__"


def _build_component_surf_worker(
    args: tuple[bytes, str, str, dict | None],
) -> tuple[str, str | None]:
    """Process-pool entry: extract one component .surf from a BREP payload.

    Returns ``(cid, None)`` on success or ``(cid, error message)`` — exceptions
    are flattened so one failed component reports cleanly instead of poisoning
    the pool. A payload the worker cannot deserialize reports the
    ``PAYLOAD_UNREADABLE`` marker so the parent retries in-process."""
    payload, cid, out_surf, face_colors = args
    try:
        try:
            shape = _build123d_shape_from_brep_bytes(payload)
        except Exception as exc:  # noqa: BLE001 - marker for the parent retry
            return (cid, f"{PAYLOAD_UNREADABLE}: {type(exc).__name__}: {exc}")
        if face_colors:
            # Ordinal-keyed, so it survives the process boundary: the BinTools
            # round-trip preserves MapShapes order even though it rebuilds TShapes.
            shape.cad_face_ordinal_colors = face_colors
        _write_component_artifacts_atomic(
            shape, Path(out_surf), cad_ref=cid, brep_bytes=payload)
        return (cid, None)
    except Exception as exc:  # noqa: BLE001 - crossing a process boundary
        return (cid, f"{type(exc).__name__}: {exc}")


def parallel_worker_count(work_count: int, *, env_var: str) -> int:
    """Worker count for a spawn pool over ``work_count`` independent OCP jobs.

    ``env_var`` overrides (0/1 disables). Defaults engage only when there is
    enough work to amortize the per-worker interpreter + OCP import cost
    (~seconds each), and cap at eight so a large machine does not multiply a
    ~300 MB resident kernel by its core count. One sizing rule, every pool: the
    component build and ``inspect validate`` differ only in the variable that
    overrides them."""
    env_value = os.environ.get(env_var, "").strip()
    if env_value:
        try:
            requested = int(env_value)
        except ValueError:
            requested = 0
        return max(1, min(requested, work_count)) if requested > 1 else 1
    if work_count < 6:
        return 1
    return max(1, min((os.cpu_count() or 2) - 2, work_count, 8))


def _component_build_worker_count(missing_count: int) -> int:
    """Worker count for parallel component builds (``CADGEN_COMPONENT_WORKERS``)."""
    return parallel_worker_count(missing_count, env_var="CADGEN_COMPONENT_WORKERS")


# Where a tree build spends its wall clock, gated behind an env var so the
# hot path pays nothing when nobody is looking. Set CADGEN_PACKAGE_TIMING to a
# file path and every build appends one JSON line: the per-stage seconds plus
# the component counts they moved. This exists because the tree write is the
# dominant cost of an edit-path rebuild and "107 s in build_tree_from_compound"
# is not an actionable number -- serialize+hash, the missing scan, worker spawn,
# and the extractions themselves each want a different fix.
_TIMING_ENV = "CADGEN_PACKAGE_TIMING"


class _StageTimer:
    """Accumulating wall-clock spans, keyed by stage name. A no-op instance
    (``enabled=False``) is installed when the env var is unset so the call sites
    stay unconditional."""

    __slots__ = ("enabled", "spans", "counts")

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self.spans: dict[str, float] = {}
        self.counts: dict[str, float] = {}

    def add(self, name: str, seconds: float) -> None:
        if self.enabled:
            self.spans[name] = self.spans.get(name, 0.0) + seconds

    def count(self, name: str, value: float) -> None:
        if self.enabled:
            self.counts[name] = value

    @contextlib.contextmanager
    def span(self, name: str):
        if not self.enabled:
            yield
            return
        started = time.perf_counter()
        try:
            yield
        finally:
            self.add(name, time.perf_counter() - started)

    def dump(self, *, package_dir: Path, extra: Mapping[str, Any]) -> None:
        if not self.enabled:
            return
        path = os.environ.get(_TIMING_ENV, "").strip()
        if not path:
            return
        record = {
            "package": package_dir.name,
            "spans": {k: round(v, 4) for k, v in sorted(self.spans.items())},
            "counts": {k: v for k, v in sorted(self.counts.items())},
            **dict(extra),
        }
        with contextlib.suppress(OSError):
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")


def _write_atomic(path: Path, data: bytes) -> None:
    """Write to a sibling temp file and rename into place, so a killed build
    never leaves a truncated artifact that a later run would trust as a
    valid content-addressed cache hit."""
    temp_path = path.with_name(f"{path.name}{temp_suffix()}")
    try:
        temp_path.write_bytes(data)
        replace_atomic(temp_path, path)
    finally:
        # The handle that blocks a rename blocks the delete too; letting that
        # escape would replace the real failure with a cleanup error.
        with contextlib.suppress(OSError):
            temp_path.unlink(missing_ok=True)


def _write_component_artifacts_atomic(
    shape: Any,
    out_surf: Path,
    *,
    cad_ref: str,
    brep_bytes: bytes | None = None,
) -> Path:
    """Persist one component's DOCUMENT pair (design/
    step-document-architecture.md): ``<cid>.brep`` — the exact shape, the
    same location-stripped BinTools bytes that computed the cid — and
    ``<cid>.surf`` — the render view. Surface extraction is READING; the
    component object is a plain write when the hashing payload is already in hand.
    The surf goes in place LAST so its existence signals a complete set.

    No colour goes into the surf: the cid is geometry-only, so a colour there
    would let two occurrences of one part with different colours share one
    file and one of them render wrong. The assembly.json's occurrence carries
    colour (``_occurrence_color``) and the viewer applies it per record."""
    from cadgen._internal.surface_extract import extract_surface_component

    out_surf.parent.mkdir(parents=True, exist_ok=True)
    local = _unlocated_shape(shape)
    _write_atomic(
        out_surf.with_name(f"{cad_ref}.brep"),
        brep_bytes if brep_bytes is not None else _shape_brep_bytes(shape),
    )
    _write_atomic(
        out_surf,
        extract_surface_component(
            local.wrapped,
            face_colors=getattr(local, "cad_face_ordinal_colors", None),
        ),
    )
    return out_surf
