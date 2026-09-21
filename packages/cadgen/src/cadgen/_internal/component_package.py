"""Component serialization, intrinsic appearance and extraction helpers.

Canonical geometry inputs contain exact encoded BREP and effective face-color
recipes. Disposable surfaces are derived by ``cadgen.store.surfaces`` under a
separately attested producer. Native imports remain local to operations.
"""

from __future__ import annotations

import contextlib
import io
import struct
import hashlib
import json
import math
import os
import time
from pathlib import Path
from typing import Any, Mapping

from cadgen._internal.atomic_replace import replace_atomic, temp_suffix
PACKAGE_KIND = "assembly-package"
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
    # Trees use a short map key alongside the complete geometry content hash.
    # Publication and capture reject a short-ID collision instead of merging it.
    return source_hash[:16]


def _normalized_face_colors(value: object) -> dict[int, tuple[float, float, float, float]]:
    """Canonical extraction input: positive face ordinals and finite RGBA.

    Channels are clamped just as the STEP color writer clamps them. Converting
    keys must never silently merge two different finishes for one face.
    """
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("cad_face_ordinal_colors must map face ordinals to RGBA")
    normalized: dict[int, tuple[float, float, float, float]] = {}
    for raw_ordinal, raw_color in value.items():
        try:
            ordinal = int(raw_ordinal)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError(f"invalid face color ordinal {raw_ordinal!r}") from error
        if ordinal <= 0 or isinstance(raw_ordinal, bool) or (
            not isinstance(raw_ordinal, str) and raw_ordinal != ordinal
        ):
            raise ValueError(f"invalid face color ordinal {raw_ordinal!r}")
        try:
            channels = tuple(float(channel) for channel in raw_color)
        except (TypeError, ValueError) as error:
            raise ValueError(f"face {ordinal} color must be finite RGBA") from error
        if len(channels) != 4 or not all(math.isfinite(channel) for channel in channels):
            raise ValueError(f"face {ordinal} color must be finite RGBA")
        color = tuple(min(1.0, max(0.0, channel)) for channel in channels)
        if ordinal in normalized and normalized[ordinal] != color:
            raise ValueError(f"conflicting colors for face ordinal {ordinal}")
        normalized[ordinal] = color
    return dict(sorted(normalized.items()))


def _content_hash_and_bytes(shape: Any, *, face_colors: object = None) -> tuple[str, bytes]:
    """The complete geometry-input identity and its admitted encoded BREP bytes."""
    prepared = prepare_geometry_component(shape, face_colors=face_colors)
    return prepared["entry"]["contentHash"], prepared["payload"]


def _content_hash_shape(shape: Any) -> str:
    """Hash a shape's complete component extraction input (see
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


def optimal_box(wrapped: Any) -> list[float] | None:
    """The TIGHT world-frame bounds of one ``TopoDS_Shape`` as
    ``[xmin, ymin, zmin, xmax, ymax, zmax]``, or None when it bounds nothing.

    ``BRepBndLib::Add`` bounds a B-spline by its CONTROL POLYGON: a NURBS
    circle of radius r reports r/cos(22.5 deg) = 1.082 r, so every rounded body
    came back ~8% too big and a reported bound could invent a clash that is not
    there (PR #370 bug record 004). ``AddOptimal`` subdivides instead.
    ``useTriangulation=False``: meshing here would mutate the shared ``TShape``
    and break content-addressed component dedup on a later in-process rebuild.
    """
    try:
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib

        box = Bnd_Box()
        BRepBndLib.AddOptimal_s(wrapped, box, False, False)
        if box.IsVoid():
            return None
        xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
        return [float(xmin), float(ymin), float(zmin), float(xmax), float(ymax), float(zmax)]
    except Exception:  # noqa: BLE001 - OCP bounds reads can raise on odd shapes
        return None


def _world_leaves(wrapped: Any) -> list[Any]:
    """The shape's leaves, each carrying its WORLD location.

    ``TopoDS_Iterator`` composes the parent's location into every child it
    yields, so recursing containers hands back exactly the placed bodies the
    occurrences describe — one leaf per occurrence, links included.
    """
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopoDS import TopoDS_Iterator

    containers = (TopAbs_ShapeEnum.TopAbs_COMPOUND, TopAbs_ShapeEnum.TopAbs_COMPSOLID)
    leaves: list[Any] = []
    stack = [wrapped]
    while stack:
        node = stack.pop()
        if node.ShapeType() not in containers:
            leaves.append(node)
            continue
        iterator = TopoDS_Iterator(node)
        while iterator.More():
            stack.append(iterator.Value())
            iterator.Next()
    return leaves


def _bbox_from_shape(shape: Any) -> dict[str, list[float]] | None:
    """The world-frame axis-aligned bounding box of a composed shape, as the
    ``{"min": [...], "max": [...]}`` the assembly.json records so a cheap whole-entry
    inspect summary does not have to re-mesh + extract full topology.

    Measured PER LEAF and merged, not once over the whole compound, because a
    leaf's box is a pure function of its geometry and rotation. Translation
    shifts the six bounds without repeating the surface-extrema calculation.
    ``op_memo.memoized_value`` keeps the untranslated box in the warm worker
    and on disk, so translated instances share that calculation. Tight bounds
    cost ~0.08 ms per face, which a whole
    150k-face assembly could not absorb on every finalize but an unchanged
    occurrence never pays twice.
    """
    try:
        from cadgen._internal import op_memo
        from OCP.TopLoc import TopLoc_Location
        from OCP.gp import gp_Vec

        boxes = []
        for leaf in _world_leaves(shape.wrapped):
            transform = leaf.Location().Transformation()
            translation = tuple(transform.TranslationPart().Coord())
            transform.SetTranslationPart(gp_Vec(0.0, 0.0, 0.0))
            untranslated = leaf.Located(TopLoc_Location(transform))
            box = op_memo.memoized_value(
                # The op_name names the FUNCTION: change what this computes and
                # change the name (or _OP_MEMO_VERSION) with it.
                "occurrence_bbox.optimal.untranslated.v1",
                op_memo.placed_shape_key(untranslated),
                lambda untranslated=untranslated: optimal_box(untranslated),
            )
            if box is not None:
                boxes.append([value + translation[index % 3] for index, value in enumerate(box)])
        if not boxes:
            return None
        return {
            "min": [min(box[axis] for box in boxes) for axis in (0, 1, 2)],
            "max": [max(box[axis] for box in boxes) for axis in (3, 4, 5)],
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


def _occurrence_material(child: Any) -> dict[str, Any] | None:
    """Private material metadata restored from a pinned model tree.

    Public ``cad_material`` mutation was replaced by ``@step(materials=...)``;
    finding that dynamic attribute is therefore a hard authoring error.
    """
    if "cad_material" in getattr(child, "__dict__", {}):
        raise ValueError(
            "cad_material authoring was removed; declare named materials with "
            "@step(materials={'definitions': ..., 'assignments': ...})"
        )
    material = getattr(child, "_cadgen_material", None)
    if not isinstance(material, dict):
        return None
    resolved: dict[str, Any] = {}
    name = material.get("name")
    if isinstance(name, str) and name.strip():
        resolved["name"] = name.strip()
    base_color = material.get("baseColor")
    if isinstance(base_color, str):
        resolved["baseColor"] = base_color
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
    face_colors = _normalized_face_colors(getattr(shape, "cad_face_ordinal_colors", None))
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

    from OCP.BinTools import BinTools
    from OCP.TopoDS import TopoDS_Shape

    topo = TopoDS_Shape()
    BinTools.Read_s(topo, io.BytesIO(payload))
    if topo.IsNull():
        raise RuntimeError("component BREP payload deserialized to a null shape")
    return _build123d_shape_from_topods(topo)


def _build123d_shape_from_topods(topo: Any) -> Any:
    """Wrap a bare ``TopoDS_Shape`` in the build123d class matching its ShapeType
    (a Solid stays a Solid; anything unknown is a Compound)."""
    import build123d
    from OCP.TopAbs import TopAbs_ShapeEnum

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
    overrides them. The shared memory policy can lower either requested count
    to fit extraction reservations inside the owning worker's allowance."""
    from cadgen.daemon.memory import component_worker_limit

    env_value = os.environ.get(env_var, "").strip()
    if env_value:
        try:
            requested = int(env_value)
        except ValueError:
            requested = 0
        return component_worker_limit(max(1, min(requested, work_count)) if requested > 1 else 1)
    if work_count < 6:
        return 1
    return component_worker_limit(max(1, min((os.cpu_count() or 2) - 2, work_count, 8)))


_SERIAL_COMPONENT_PAYLOAD_BYTES = 768 * 1024


def _component_build_worker_count(missing_count: int, *, payload_bytes: int | None = None) -> int:
    """Avoid spawn startup for small BREP batches unless workers are explicit.

    Both schedules reconstruct private shapes from the same payloads. The
    conservative byte cutoff limits only the default component scheduler;
    larger/unknown work and explicit overrides retain CPU and memory sizing.
    """
    if (payload_bytes is not None and payload_bytes <= _SERIAL_COMPONENT_PAYLOAD_BYTES
            and not os.environ.get("CADGEN_COMPONENT_WORKERS", "").strip()):
        return 1
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

    Per-face colors go into SURF and participate in the component input hash.
    Uniform occurrence color and PBR finish stay on the tree's occurrences and
    are applied per placement; they do not alter this reusable component."""
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


# The ONLY version on geometry identity. A component's cid hashes its BREP
# bytes, its intrinsic face colours, and this scheme string; nothing else.
# Bump it only when the same bytes must map to a different tree (a codec or
# interpretation change): that re-keys every user's store, so it is rare and
# deliberate. An extractor, mesher or surface fix bumps the version of that
# derived artifact (SURF_VERSION, the tessellation scheme, the index payload
# contracts) and never this string. There is no global cache-schema salt any
# more; STORE.md "Geometry identity and versions" records the rule and the
# retired salt's history.
GEOMETRY_SCHEME = "cadgen-geometry-input-v3"
GEOMETRY_CODECS = frozenset({"bintools-v4", "bintools-v3", "breptools-ascii-v3"})
COMPONENT_KINDS = frozenset({"native", "eager-only"})
_BREP_HEADERS = {
    "bintools-v4": b"\nOpen CASCADE Topology V4, (c) Open Cascade\n",
    "bintools-v3": b"\nOpen CASCADE Topology V3 (c)\n",
    "breptools-ascii-v3": b"\nCASCADE Topology V3, (c) Open Cascade\n",
}
class NativeUnavailable(RuntimeError):
    """An eager-only component cannot certify faithful native reconstruction."""

class CodecFidelityError(ValueError):
    """No permitted codec proved the required point-bearing fidelity."""

def canonical_json_bytes(value: Any) -> bytes:
    # JSON object keys are strings. Convert ordinal keys before sorting so the
    # same value has identical bytes before and after a JSON store round-trip.
    # Sorting int keys first would emit 1,2,10 while parsed keys emit 1,10,2.
    def json_value(item):
        if type(item) is dict:
            if any(type(key) not in (str, int) for key in item):
                raise ValueError("unsupported canonical JSON key")
            normalized = {str(key): json_value(part) for key, part in item.items()}
            if len(normalized) != len(item):
                raise ValueError("duplicate canonical JSON key")
            return normalized
        if isinstance(item, (list, tuple)):
            return [json_value(part) for part in item]
        return item
    return json.dumps(json_value(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()

def geometry_component_hash(codec: str, payload: bytes, face_colors: dict, *,
                   kind: str = "native", eager_surface: str | None = None) -> str:
    from cadgen.store.objects import is_object_hash

    if codec not in GEOMETRY_CODECS or kind not in COMPONENT_KINDS:
        raise ValueError("unsupported geometry codec/kind")
    if (kind == "eager-only") != is_object_hash(eager_surface):
        raise ValueError("eager-only geometry must pin its required surface")
    digest = hashlib.sha256()
    digest.update(GEOMETRY_SCHEME.encode() + b"\0" + kind.encode() + b"\0" + codec.encode() + b"\0")
    digest.update(len(payload).to_bytes(8, "big"))
    digest.update(payload)
    digest.update(canonical_json_bytes(face_colors))
    if eager_surface is not None:
        digest.update(b"\0" + eager_surface.encode())
    return digest.hexdigest()

def effective_face_colors(shape: Any, colors: Any) -> dict:
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    normalized = _normalized_face_colors(colors)
    if not normalized:
        return {}
    faces = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(getattr(shape, "wrapped", shape), TopAbs_FACE, faces)
    return {ordinal: color for ordinal, color in normalized.items() if ordinal <= faces.Extent()}

def _point_signature(shape: Any) -> tuple:
    """Exact native vertex records and referenced placements, scoped locally.

    Geometry table values intentionally stay outside the signature; their
    ordinary decoder normalization remains the existing v4 behavior. Native
    table indices preserve the point-to-geometry association. No pointer or
    native object escapes this call, and no approximate comparison is used.
    """
    from OCP.BinTools import BinTools_ShapeSet
    from OCP.TopAbs import TopAbs_VERTEX
    from OCP.TopExp import TopExp
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopTools import TopTools_IndexedMapOfShape

    local = getattr(shape, "wrapped", shape).Located(TopLoc_Location())
    vertices = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(local, TopAbs_VERTEX, vertices)
    point_vertices = [
        (i, vertices.FindKey(i)) for i in range(1, vertices.Extent() + 1)
        if not vertices.FindKey(i).TShape().Points().IsEmpty()
    ]
    if not point_vertices:
        return ()
    shape_set = BinTools_ShapeSet()
    shape_set.SetFormatNb(3)
    shape_set.SetWithTriangles(False)
    shape_set.SetWithNormals(False)
    shape_set.Add(local)

    def placement(location):
        transform = location.Transformation()
        return struct.pack(">12d", *(transform.Value(i, j) for i in range(1, 4) for j in range(1, 5)))

    result = []
    for ordinal, vertex in point_vertices:
        locations = []
        for point in vertex.TShape().Points():
            kinds = [point.IsPointOnCurve(), point.IsPointOnCurveOnSurface(), point.IsPointOnSurface()]
            if sum(kinds) != 1:
                raise CodecFidelityError("unsupported native point representation")
            locations.append(placement(point.Location()))
        stream = io.BytesIO()
        # ShapeSet strips each TShape's location before writing its geometry.
        # Keep the vertex occurrence placement separately and do the same here.
        shape_set.WriteShape(vertex.Located(TopLoc_Location()), stream)
        result.append((ordinal, placement(vertex.Location()), stream.getvalue(), tuple(locations)))
    return tuple(result)

def _binary_v3_bytes(shape: Any) -> bytes:
    from OCP.BinTools import BinTools, BinTools_FormatVersion
    from OCP.TopLoc import TopLoc_Location

    stream = io.BytesIO()
    BinTools.Write_s(
        getattr(shape, "wrapped", shape).Located(TopLoc_Location()), stream,
        False, False, BinTools_FormatVersion.BinTools_FormatVersion_VERSION_3,
    )
    return stream.getvalue()

def _ascii_v3_bytes(shape: Any) -> bytes:
    from OCP.BRepTools import BRepTools
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopTools import TopTools_FormatVersion

    stream = io.BytesIO()
    BRepTools.Write_s(
        getattr(shape, "wrapped", shape).Located(TopLoc_Location()), stream,
        False, False, TopTools_FormatVersion.TopTools_FormatVersion_VERSION_3,
    )
    return stream.getvalue()

def _decode_brep(codec: str, payload: bytes) -> Any:
    if codec not in _BREP_HEADERS:
        raise ValueError(f"unsupported BREP codec: {codec}")
    if not isinstance(payload, bytes) or not payload.startswith(_BREP_HEADERS[codec]):
        raise ValueError(f"BREP header does not match declared codec {codec}")
    from OCP.BinTools import BinTools
    from OCP.TopAbs import TopAbs_VERTEX
    from OCP.TopoDS import TopoDS, TopoDS_Shape

    shape = TopoDS_Shape()
    if codec == "breptools-ascii-v3":
        from OCP.BRep import BRep_Builder
        from OCP.BRepTools import BRepTools

        BRepTools.Read_s(shape, io.BytesIO(payload), BRep_Builder())
    else:
        BinTools.Read_s(shape, io.BytesIO(payload))
    if shape.IsNull():
        raise RuntimeError("BREP payload deserialized to a null shape")
    if shape.ShapeType() == TopAbs_VERTEX:
        shape = TopoDS.Vertex_s(shape)
    return _build123d_shape_from_topods(shape)

def _encode_brep(shape: Any) -> dict[str, Any]:

    original = _shape_brep_bytes(shape)
    original_points = _point_signature(shape)
    try:
        private = _decode_brep("bintools-v4", original)
        if _point_signature(private) != original_points:
            raise CodecFidelityError("binary v4 changed exact native point records")
        return {"codec": "bintools-v4", "bytes": original,
                "private_decoded_shape": private}
    except Exception as binary_failure:
        failures = [f"binary v4: {binary_failure}"]
    for alternate_codec, writer in (("bintools-v3", _binary_v3_bytes),
                                    ("breptools-ascii-v3", _ascii_v3_bytes)):
        try:
            alternate = writer(shape)
            private = _decode_brep(alternate_codec, alternate)
            if _shape_brep_bytes(private) != original:
                raise CodecFidelityError("original native byte fidelity not proven")
            if writer(private) != alternate:
                raise CodecFidelityError("alternate read/write is not a byte fixed point")
            return {"codec": alternate_codec, "bytes": alternate,
                    "private_decoded_shape": private}
        except Exception as alternate_failure:
            failures.append(f"{alternate_codec}: {alternate_failure}")
    raise CodecFidelityError("; ".join(failures))


def prepare_geometry_component(shape: Any, *, face_colors: object = None) -> dict[str, Any]:
    """Capture a component's owned bytes, effective recipe and private native input.

    No store write occurs here. Ordinary v4 decoding preserves the existing
    canonical worker semantics; exact native point records fence the known
    parameter-loss cases. Alternate codecs require full original-native bytes
    and their own byte fixed point. Failure retains an explicit eager surface,
    never a falsely readable native entry.
    """
    from cadgen._internal.surface_extract import extract_surface_component
    from cadgen.store.surfaces import validate_surface_bytes

    try:
        encoded = _encode_brep(shape)
        kind = "native"
    except CodecFidelityError:
        encoded = {"codec": "bintools-v4", "bytes": _shape_brep_bytes(shape),
                   "private_decoded_shape": None}
        kind = "eager-only"
    private = encoded["private_decoded_shape"]
    colors = effective_face_colors(
        private if private is not None else shape,
        getattr(shape, "cad_face_ordinal_colors", None) if face_colors is None else face_colors,
    )
    payload = encoded["bytes"]
    entry = {"kind": kind, "codec": encoded["codec"],
             "brep": hashlib.sha256(payload).hexdigest(), "faceColors": colors}
    surface = None
    if kind == "eager-only":
        from OCP.TopLoc import TopLoc_Location
        surface = extract_surface_component(getattr(shape, "wrapped", shape).Located(TopLoc_Location()), face_colors=colors)
        validate_surface_bytes(surface)
        entry["eagerSurface"] = hashlib.sha256(surface).hexdigest()
    entry["contentHash"] = geometry_component_hash(
        entry["codec"], payload, colors, kind=kind, eager_surface=entry.get("eagerSurface"),
    )
    if private is not None:
        private.cad_face_ordinal_colors = dict(colors)
    return {"entry": entry, "payload": payload, "shape": private, "surface": surface}


def decode_geometry_component(entry: dict[str, Any], payload: bytes) -> Any:
    """Privately reconstruct one verified geometry input, without surface reads."""
    validate_geometry_component(entry, payload)
    if entry["kind"] == "eager-only":
        raise NativeUnavailable("eager-only component has no admitted native representation")
    try:
        shape = _decode_brep(entry["codec"], payload)
        colors = effective_face_colors(shape, entry["faceColors"])
    except MemoryError:
        raise
    except Exception as exc:
        # Hash/header integrity is independent of native readability. OCP
        # failures use several exception types; readers treat them uniformly
        # as an invalid encoded input and can repair from the selected STEP.
        raise ValueError(f"unreadable {entry['codec']} geometry payload") from exc
    if canonical_json_bytes(colors) != canonical_json_bytes(entry["faceColors"]):
        raise ValueError("intrinsic recipe names an absent native face")
    shape.cad_face_ordinal_colors = colors
    return shape


def validate_geometry_component(entry: Any, payload: bytes, *, cid: str | None = None) -> None:
    """Kernel-free verification of a complete encoded geometry input."""
    if type(entry) is not dict or entry.get("kind") not in COMPONENT_KINDS or entry.get("codec") not in GEOMETRY_CODECS:
        raise ValueError("unsupported geometry component")
    allowed = {"kind", "codec", "brep", "faceColors", "contentHash", "color"}
    if entry["kind"] == "eager-only":
        allowed.add("eagerSurface")
    if set(entry) - allowed:
        raise ValueError("unknown geometry component field")
    if not isinstance(payload, bytes) or not payload.startswith(_BREP_HEADERS[entry["codec"]]):
        raise ValueError("BREP header does not match declared codec")
    if hashlib.sha256(payload).hexdigest() != entry.get("brep"):
        raise ValueError("geometry BREP object identity mismatch")
    colors = _normalized_face_colors(entry.get("faceColors"))
    if canonical_json_bytes(colors) != canonical_json_bytes(entry.get("faceColors")):
        raise ValueError("noncanonical intrinsic appearance recipe")
    full = geometry_component_hash(entry["codec"], payload, colors, kind=entry["kind"],
                                   eager_surface=entry.get("eagerSurface"))
    if entry.get("contentHash") != full or (cid is not None and cid != full[:16]):
        raise ValueError("geometry input identity mismatch")
