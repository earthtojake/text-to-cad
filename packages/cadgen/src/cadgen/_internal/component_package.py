"""Component-GLB package emit.

Every model's render artifact is a package directory under the per-folder
``__cadgen__`` home, holding one content-addressed component GLB per unique
part (mesh + embedded local topology) plus an ``assembly.json`` descriptor mapping
occurrences -> component + world transform. Components are keyed by their source
STEP content hash, so editing one part rebuilds only that component; the rest are
reused from the package's content-addressed cache.

This is the build side only; consumers (viewer/snapshot/inspect) compose the
assembly manifest from the package at read time (see the design doc, sec. 6/8).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from cadgen._internal.atomic_replace import replace_atomic, temp_suffix
from cadgen.catalog import render_package_dir
from cadgen._internal.generation import (
    DEFAULT_MESH_ANGULAR_TOLERANCE,
    DEFAULT_MESH_TOLERANCE,
)
from cadgen._internal.glb import export_assembly_glb_from_scene
from cadgen._internal.package_freshness import STEP_PACKAGE_VERSION
from cadgen.coordination import (
    PHASE_COMPONENTS,
    PHASE_FINALIZE,
    PHASE_PACKAGE,
    require_write_lock,
    resolve as resolve_progress,
)
from cadgen.step_export import build_build123d_step_scene
from cadgen._internal.step_scene import (
    extract_selectors_from_scene,
    mesh_step_scene,
)

PACKAGE_KIND = "assembly-package"
# The single version for a STEP package: descriptor layout plus the bytes inside the
# component GLBs it references. Defined in the stdlib-only _internal.package_freshness so
# BOTH freshness authorities gate on one constant -- the viewer's validator cannot import
# this module (it pulls in the CAD runtime), and a second hand-copied number is how the two
# drift. It also salts the component cid below, which is what makes a payload change
# actually re-emit rather than be reused by geometry.
PACKAGE_SCHEMA_VERSION = STEP_PACKAGE_VERSION
# Self-contained content-addressed packages: each model's components live INSIDE its own package
# at <folder>/__cadgen__/models/<step-filename>/components/<geomHash>.glb, referenced by the
# descriptor via the flat relative ref components/<geomHash>.glb. Within-model dedup (repeated
# parts share one cid) is preserved; components are not shared ACROSS packages, so each
# package directory is a complete, relocatable unit.
COMPONENT_DIRNAME = "components"
DESCRIPTOR_NAME = "assembly.json"
# Source-provenance keys stripped from a component GLB's embedded STEP_TOPOLOGY so the
# component is a pure function of geometry+tolerances (content-addressable). All of this
# is model-level and lives on the descriptor (assembly.json), not the reusable leaf.
COMPONENT_PROVENANCE_KEYS = (
    "sourceKind",
    "sourcePath",
    "paramsPath",
    "sourceHash",
    "sourceClosureHash",
    "sourceClosureFiles",
    "stepPath",
    "stepHash",
    "generatedAt",
    "assemblyMates",
)
# Lazy full-manifest sidecar inside the package, built on demand by inspect_refs
# (faces/edges/selectors) — the build itself never produces it (that is the win).
TOPOLOGY_GLB_NAME = "topology.glb"


def assembly_topology_glb_path(entry_path: Path) -> Path:
    """Path to the lazy full-manifest single GLB inside an assembly package. inspect's
    selector queries build + cache it here on first use; renders never need it.
    Keyed by the ENTRY file (the same key as the package itself)."""
    return render_package_dir(entry_path) / TOPOLOGY_GLB_NAME


def is_assembly_package(path: Path) -> bool:
    """True when ``path`` is a component-package directory (has assembly.json)."""
    return path.is_dir() and (path / DESCRIPTOR_NAME).is_file()


def read_package_descriptor(path: Path) -> dict[str, Any] | None:
    """Load a package descriptor from a package dir (or its assembly.json path).

    Returns None for anything that is not a package directory with a readable
    descriptor (missing, partial, or a stray file at the package path)."""
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


def assembly_package_current(step_path: Path) -> bool:
    """True when a package descriptor exists and every referenced component GLB is
    present. Source-change detection is left to the descriptor's provenance
    (stepHash/sourceClosure) read through the package-aware manifest reader; this only
    guards the package's own existence so a missing/partial package forces a rebuild."""
    package_dir = render_package_dir(step_path)
    descriptor = read_package_descriptor(package_dir)
    if descriptor is None or descriptor.get("kind") != PACKAGE_KIND:
        return False
    components = descriptor.get("components") or {}
    if not components:
        return False
    return all(
        (package_dir / str(entry.get("glb", ""))).is_file()
        for entry in components.values()
    )


def _component_id(source_hash: str) -> str:
    return source_hash[:16]


def _content_hash_and_bytes(shape: Any) -> tuple[str, bytes]:
    """The content hash AND the location-stripped BREP bytes it digests, from a
    single serialization.

    The digest is salted with :data:`STEP_PACKAGE_VERSION` because the cid
    addresses a BUILT component GLB, not the geometry alone. Each GLB embeds the
    topology tables the extractor produced, so a change to what the extractor
    emits makes every cached component wrong while its geometry — and therefore
    an unsalted digest — is unchanged. The build reuses any ``<cid>.glb`` already
    on disk, so without the salt an extractor fix would leave every existing
    package serving the old tables behind a descriptor that claims to be current.

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
    digest.update(str(STEP_PACKAGE_VERSION).encode("utf-8"))
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
    ``{"min": [...], "max": [...]}`` the descriptor records so a cheap whole-entry
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
    express brushed-vs-polished finishing; these ride the descriptor so the
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
    return local


def _shape_brep_bytes(shape: Any) -> bytes:
    """Location-stripped binary BREP of a shape (no triangulation/normals) — the
    process-boundary payload for parallel component builds. Mirrors
    ``_content_hash_shape``'s serialization so the worker rebuilds exactly the
    geometry the cid addresses."""
    import io

    from OCP.BinTools import BinTools, BinTools_FormatVersion
    from OCP.TopLoc import TopLoc_Location

    stream = io.BytesIO()
    BinTools.Write_s(
        shape.wrapped.Located(TopLoc_Location()),
        stream,
        False,  # theWithTriangles
        False,  # theWithNormals
        BinTools_FormatVersion.BinTools_FormatVersion_CURRENT,
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


def _build_component_glb_worker(
    args: tuple[bytes, str, str, float, float],
) -> tuple[str, str | None]:
    """Process-pool entry: build one component GLB from a BREP payload.

    Returns ``(cid, None)`` on success or ``(cid, error message)`` — exceptions
    are flattened so one failed component reports cleanly instead of poisoning
    the pool. A payload the worker cannot deserialize reports the
    ``PAYLOAD_UNREADABLE`` marker so the parent retries in-process."""
    payload, cid, out_glb, linear_deflection, angular_deflection = args
    try:
        try:
            shape = _build123d_shape_from_brep_bytes(payload)
        except Exception as exc:  # noqa: BLE001 - marker for the parent retry
            return (cid, f"{PAYLOAD_UNREADABLE}: {type(exc).__name__}: {exc}")
        _write_component_glb_atomic(
            shape,
            Path(out_glb),
            cad_ref=cid,
            linear_deflection=linear_deflection,
            angular_deflection=angular_deflection,
        )
        return (cid, None)
    except Exception as exc:  # noqa: BLE001 - crossing a process boundary
        return (cid, f"{type(exc).__name__}: {exc}")


def _component_build_worker_count(missing_count: int) -> int:
    """Worker count for parallel component builds.

    ``CADGEN_COMPONENT_WORKERS`` overrides (0/1 disables). Defaults engage only
    when enough components are missing to amortize the per-worker interpreter +
    OCP import cost (~seconds each)."""
    env_value = os.environ.get("CADGEN_COMPONENT_WORKERS", "").strip()
    if env_value:
        try:
            requested = int(env_value)
        except ValueError:
            requested = 0
        return max(1, min(requested, missing_count)) if requested > 1 else 1
    if missing_count < 6:
        return 1
    return max(1, min((os.cpu_count() or 2) - 2, missing_count, 8))


def _write_component_glb_atomic(
    shape: Any,
    out_glb: Path,
    *,
    cad_ref: str,
    linear_deflection: float,
    angular_deflection: float,
) -> Path:
    """Build to a sibling temp file and rename into place, so a killed build
    never leaves a truncated ``<cid>.glb`` that a later run would trust as a
    valid content-addressed cache hit."""
    temp_path = out_glb.with_name(f"{out_glb.name}{temp_suffix()}")
    try:
        build_component_glb_from_shape(
            shape,
            temp_path,
            cad_ref=cad_ref,
            linear_deflection=linear_deflection,
            angular_deflection=angular_deflection,
            identity_path=out_glb,
        )
        replace_atomic(temp_path, out_glb)
    finally:
        # The handle that blocks a rename blocks the delete too; letting that escape would
        # replace the real failure with a cleanup error.
        with contextlib.suppress(OSError):
            temp_path.unlink(missing_ok=True)
    return out_glb


def build_component_glb_from_shape(
    shape: Any,
    out_glb: Path,
    *,
    cad_ref: str,
    linear_deflection: float,
    angular_deflection: float,
    identity_path: Path | None = None,
) -> Path:
    """Mesh an in-memory part shape (in its local frame) to a *clean* component GLB.

    The part geometry comes straight off the assembly compound (no source STEP on
    disk), so it is meshed and selector-extracted directly from the shape. The embedded
    STEP_TOPOLOGY is stripped of all source provenance (see ``COMPONENT_PROVENANCE_KEYS``)
    so the component is a pure function of geometry + mesh tolerances — byte-deterministic
    and content-addressable. Provenance lives on the per-model descriptor, not the leaf.

    ``identity_path`` is the path the artifact will have once it is in place, for callers
    that write through a staging file. The synthetic STEP name derived below reaches the
    embedded manifest as ``faceProxy.source``, so naming the staging file instead would
    put that name in the payload and make the bytes depend on where a build staged them
    rather than on the geometry."""
    out_glb.parent.mkdir(parents=True, exist_ok=True)
    # Appended to the name rather than substituted into it, which keeps the placeholder
    # byte-identical to the one a sibling temp file used to reduce to: `<cid>.glb.tmp<pid>`
    # has `.tmp<pid>` as its last suffix, so with_suffix() yielded `<cid>.glb.step`.
    # Substituting reads better but would rewrite every component GLB and invalidate the
    # content-addressed caches keyed on them, which is a separate change.
    identity = identity_path or out_glb
    placeholder = identity.with_name(f"{identity.name}.step")
    # The shape arrives LOCATED (the occurrence is ``part.moved(transform)``). Strip the location
    # so the GLB is emitted in the part's LOCAL frame with an identity node: world placement is
    # supplied solely by the descriptor occurrence transform, and content-addressed dedup needs
    # byte-identical geometry for every repeat of a part regardless of where it sits. Without
    # this the node bakes the occurrence placement, double-placing it at compose time and giving
    # a shared (deduped) component only its first occurrence's position.
    scene = build_build123d_step_scene(_unlocated_shape(shape), placeholder)
    mesh_step_scene(
        scene,
        linear_deflection=linear_deflection,
        angular_deflection=angular_deflection,
        relative=False,
        parallel=False,
    )
    bundle = extract_selectors_from_scene(scene, cad_ref=cad_ref)
    for key in COMPONENT_PROVENANCE_KEYS:
        bundle.manifest.pop(key, None)
    # Non-deterministic build timing would defeat content-addressing — drop it; the
    # geometry counts in stats are deterministic and kept.
    stats = bundle.manifest.get("stats")
    if isinstance(stats, dict):
        stats.pop("timingMs", None)
    # Write the leaf GLB straight to ``out_glb`` (inside the package's components/ dir). Passing
    # an explicit target avoids deriving a render_package_dir() from the placeholder, which would
    # otherwise scaffold a stray __cadgen__/models/ tree next to the component.
    export_assembly_glb_from_scene(
        placeholder,
        scene,
        target_path=out_glb,
        linear_deflection=linear_deflection,
        angular_deflection=angular_deflection,
        selector_bundle=bundle,
    )
    return out_glb


def build_package_from_compound(
    compound: Any,
    *,
    package_dir: Path,
    root_name: str,
    single_component: bool = False,
    force: bool = False,
    provenance: Mapping[str, Any] | None = None,
    linear_deflection: float = DEFAULT_MESH_TOLERANCE,
    angular_deflection: float = DEFAULT_MESH_ANGULAR_TOLERANCE,
    progress: Any | None = None,
) -> dict[str, Any]:
    """Emit a render package (``__cadgen__/models/<entry>/``) from a baked ``Compound`` or single shape.

    Every model — part or assembly — is one representation: a descriptor + content-
    addressed components.

    - **assembly** (``single_component=False``): the shape-only ``gen_step`` returns a baked
      compound whose direct children are the occurrences (``part.moved(transform)`` with
      ``child.label`` the name). Each child is content-addressed by its *local* (unlocated)
      geometry, so repeated parts share one component GLB; the per-child location supplies
      the world transform. Mates ride on ``compound.assembly_mates``.
    - **part** (``single_component=True``): the whole rigid shape is one occurrence at
      identity referencing one component (its full geometry) — a degenerate package. The
      part/assembly choice is made by the caller from the generator's authored kind, never
      inferred from geometry (a multi-solid part must not look like an assembly).

    ``force`` rebuilds every component even if its ``<cid>.glb`` is present (the cid hashes
    geometry, not the mesh/selector code version). Returns build stats.

    ``progress`` (a :class:`cadgen._internal.progress.ProgressReporter`) is driven through
    the walk and the component build; the latter is the one stage of a model build with a
    denominator known before the work starts."""
    package_dir = Path(package_dir)
    progress = resolve_progress(progress)
    # Each package is a SELF-CONTAINED unit: the descriptor dir lives at
    # <folder>/__cadgen__/models/<key>/ and its content-addressed component GLBs live in a
    # components/ dir INSIDE that package (<key>/components/<hash>.glb), so the whole model —
    # descriptor plus every GLB it needs — uploads, caches, and deletes as one directory with
    # no cross-model references. The descriptor references them by the flat relative ref
    # components/<hash>.glb. Within-model dedup (repeated parts share one component via a
    # shared cid) is preserved; cross-model dedup is intentionally given up for
    # self-containment (the hit rate is low and a shared store complicates blob upload/GC).
    # THE mutation boundary for a render package. Every producer that reaches here must be
    # holding this package's write lock -- previously the lock was taken at call sites, so
    # whether a write was coordinated depended on which of four producers you arrived
    # through, and `ensure_step_topology_artifact` arrived through one that took none.
    require_write_lock(package_dir)

    comp_dir = package_dir / COMPONENT_DIRNAME
    comp_dir.mkdir(parents=True, exist_ok=True)

    from build123d import Location

    def _component_ref(cid: str) -> str:
        return os.path.relpath(comp_dir / f"{cid}.glb", package_dir).replace(os.sep, "/")

    occurrences: list[dict[str, Any]] = []
    components: dict[str, dict[str, Any]] = {}
    shapes: dict[str, Any] = {}
    # Memoize the BREP content hash per unique part, keyed on the underlying
    # ``TShape``. NOTE: build123d 0.10's ``Shape.moved()`` is deepcopy-based
    # (``BRepBuilderAPI_Copy`` per solid), so instances placed with ``.moved()``
    # carry DISTINCT TShapes and miss this memo — each instance re-serializes
    # its leaf BREPs once (content-addressing still dedups them afterwards,
    # since the copies are byte-identical). The memo still pays off for
    # occurrences that genuinely share a TShape (raw-OCCT composed assemblies,
    # ``Location``-composed placements).
    hash_memo: dict[Any, str] = {}
    # The location-stripped BREP bytes per cid, captured from the single
    # serialization that computed the content hash, so a missing component's
    # worker payload reuses them instead of re-serializing the same shape.
    # Retained ONLY for cids that will actually need a worker payload (no
    # <cid>.glb on disk yet, or --force): on the edit-path rebuild most
    # components are already built, and retaining every BREP for the whole walk
    # would hold the assembly's entire serialized geometry in memory at once.
    brep_bytes_by_cid: dict[str, bytes] = {}

    def _retain_payload_brep(content_hash: str, brep: bytes) -> None:
        cid = _component_id(content_hash)
        if cid not in brep_bytes_by_cid and (force or not (comp_dir / f"{cid}.glb").exists()):
            brep_bytes_by_cid[cid] = brep

    def _add_leaf(node: Any, world_loc: Any, occ_id: str, name: str | None = None) -> dict[str, Any]:
        try:
            memo_key = node.wrapped.TShape()
            content_hash = hash_memo.get(memo_key)
            if content_hash is None:
                content_hash, brep = _content_hash_and_bytes(node)
                hash_memo[memo_key] = content_hash
                _retain_payload_brep(content_hash, brep)
        except TypeError:  # unhashable TShape wrapper: correctness over the micro-optimization
            content_hash, brep = _content_hash_and_bytes(node)
            _retain_payload_brep(content_hash, brep)
        cid = _component_id(content_hash)
        shapes.setdefault(cid, node)
        components.setdefault(cid, {"glb": _component_ref(cid), "contentHash": content_hash})
        if name is None:
            name = str(getattr(node, "label", "") or f"part_{occ_id}")
        occurrence: dict[str, Any] = {
            "id": occ_id,
            "name": name,
            "component": cid,
            "transform": _transform_from_location(world_loc),
        }
        color = _occurrence_color(node)
        if color is not None:
            occurrence["color"] = color
        material = _occurrence_material(node)
        if material is not None:
            occurrence["material"] = material
        occurrences.append(occurrence)
        # One tick per leaf. The walk has no denominator (the leaf count is only known
        # once it ends), so this drives a count, not a percentage.
        progress.advance(detail=name)
        return {"id": occ_id, "name": name, "nodeType": "part", "leafPartIds": [occ_id], "children": []}

    # Recurse the composed compound so the descriptor preserves the assembly HIERARCHY (for the
    # viewer structure tree) while the rendered occurrences stay the flat LEAF placements: each
    # leaf is one content-addressed component, with its world transform accumulated down the path
    # (parent_world * node.location). A subassembly is a tree node grouping its descendant leaves,
    # NOT a single merged component, so the tree can drill into / select / isolate its parts.
    assembly_root: dict[str, Any] | None = None
    occurrence_tree = getattr(compound, "_occurrence_tree", None)
    progress.phase(PHASE_PACKAGE)
    if single_component:
        _add_leaf(compound, getattr(compound, "location", None) or Location(), "o1.1")
    elif occurrence_tree is not None:
        # Fast path: a raw-OCCT-composed assembly carries an explicit occurrence-metadata tree
        # (see link_assembly.compound_from_instances) because the compound has no build123d child
        # structure to walk. Each leaf node already holds its local shape + world location + name.
        def _consume(node: dict[str, Any]) -> dict[str, Any]:
            if node.get("leaf"):
                return _add_leaf(node["shape"], node["world_loc"], node["id"], name=node["name"])
            child_nodes = [_consume(child) for child in node["children"]]
            return {
                "id": node["id"],
                "name": node["name"],
                "nodeType": "subassembly",
                "leafPartIds": [leaf_id for cn in child_nodes for leaf_id in cn["leafPartIds"]],
                "children": child_nodes,
            }

        assembly_root = _consume(occurrence_tree)
        assembly_root["nodeType"] = "assembly"
    else:
        def _consume_spliced(node: dict[str, Any], parent_world_loc: Any, path: str) -> dict[str, Any]:
            # A nested compound_from_instances subtree: remap its self-relative
            # occurrence ids under the enclosing walk path and accumulate the
            # enclosing world location into its placements.
            if node.get("leaf"):
                return _add_leaf(node["shape"], parent_world_loc * node["world_loc"], path, name=node["name"])
            child_nodes = [
                _consume_spliced(child, parent_world_loc, f"{path}.{index}")
                for index, child in enumerate(node["children"], start=1)
            ]
            return {
                "id": path,
                "name": node["name"],
                "nodeType": "subassembly",
                "leafPartIds": [leaf_id for cn in child_nodes for leaf_id in cn["leafPartIds"]],
                "children": child_nodes,
            }

        def _walk(node: Any, parent_world_loc: Any, path: str) -> dict[str, Any]:
            node_loc = getattr(node, "location", None)
            world_loc = (parent_world_loc * node_loc) if node_loc is not None else parent_world_loc
            nested_tree = getattr(node, "_occurrence_tree", None)
            if nested_tree is not None:
                spliced = _consume_spliced(dict(nested_tree, leaf=False), world_loc, path)
                spliced["name"] = str(getattr(node, "label", "") or nested_tree.get("name") or path)
                return spliced
            child_shapes = list(getattr(node, "children", []) or [])
            if not child_shapes:
                return _add_leaf(node, world_loc, path)
            child_nodes = [
                _walk(child, world_loc, f"{path}.{index}")
                for index, child in enumerate(child_shapes, start=1)
            ]
            return {
                "id": path,
                "name": str(getattr(node, "label", "") or path),
                "nodeType": "subassembly",
                "leafPartIds": [leaf_id for cn in child_nodes for leaf_id in cn["leafPartIds"]],
                "children": child_nodes,
            }

        assembly_root = _walk(compound, Location(), "o1")
        assembly_root["nodeType"] = "assembly"

    if not occurrences:
        raise RuntimeError(f"model {root_name!r} has no geometry to package")

    # Content-addressed component cache: a present <cid>.glb is valid (cid IS the
    # local-geometry content hash), so editing one part only rebuilds that component.
    # ``force`` bypasses the cache (mesh/selector code changed, not the geometry).
    built: list[str] = []
    reused: list[str] = []
    missing: list[tuple[str, Any]] = []
    for cid, shape in shapes.items():
        if (comp_dir / f"{cid}.glb").exists() and not force:
            reused.append(cid)
        else:
            missing.append((cid, shape))
    # Every missing component builds from its location-stripped BREP payload —
    # the same bytes whether built in-process or in a worker — so the emitted
    # GLB is independent of worker count AND of the caller's Python class for
    # the shape (a parametric Box and an imported Solid with identical geometry
    # emit identical components; XCAF auto-labels no longer leak in).
    payloads = [
        (
            # Reuse the BREP bytes captured when this cid was content-hashed;
            # re-serialize only when the GLB present at capture time vanished
            # before the missing-scan above (so the bytes were not retained).
            brep_bytes_by_cid.get(cid) or _shape_brep_bytes(shape),
            cid,
            str(comp_dir / f"{cid}.glb"),
            linear_deflection,
            angular_deflection,
        )
        for cid, shape in missing
    ]
    workers = _component_build_worker_count(len(payloads))
    # The one stage of a model build whose denominator is known before any of the work
    # runs: the missing set is fully resolved above. Note the total is the MISSING
    # count, not the component count -- re-meshing one edited part of a 300-part
    # assembly is honestly 1/1, not 1/300.
    progress.phase(PHASE_COMPONENTS, total=len(payloads))
    if workers > 1:
        # Each missing component is meshed + selector-extracted independently
        # (the extraction is Python-heavy and GIL-bound, so threads don't
        # help). Workers write their own <cid>.glb atomically, so nothing
        # heavy pickles back.
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor, as_completed

        with ProcessPoolExecutor(
            max_workers=workers, mp_context=multiprocessing.get_context("spawn")
        ) as pool:
            # submit + as_completed rather than pool.map: map yields in SUBMISSION
            # order, so a progress count taken from it reports the length of the
            # finished PREFIX, not how many components are actually done -- one slow
            # component early in the list would pin the bar while the rest complete
            # behind it. Results are collected by cid and re-ordered below, so the
            # value this function computes is identical either way.
            futures = {pool.submit(_build_component_glb_worker, args): args[1] for args in payloads}
            errors_by_cid: dict[str, str | None] = {}
            for future in as_completed(futures):
                built_cid, error = future.result()
                errors_by_cid[built_cid] = error
                progress.advance(detail=built_cid)
        results = [(cid, errors_by_cid[cid]) for _payload, cid, *_rest in payloads]
    else:
        results = []
        for args in payloads:
            results.append(_build_component_glb_worker(args))
            progress.advance(detail=args[1])
    shapes_by_cid = dict(missing)
    for cid, error in results:
        if error is not None and error.startswith(PAYLOAD_UNREADABLE):
            # BinTools write/read asymmetry: build from the original in-process
            # shape (the pre-payload path); such components simply cannot be
            # parallelized or byte-normalized.
            _write_component_glb_atomic(
                shapes_by_cid[cid],
                comp_dir / f"{cid}.glb",
                cad_ref=cid,
                linear_deflection=linear_deflection,
                angular_deflection=angular_deflection,
            )
            built.append(cid)
            continue
        if error is not None:
            raise RuntimeError(f"component {cid} build failed: {error}")
        built.append(cid)

    # The descriptor IS the assembly's index manifest: the provenance block (schema/
    # source/step hashes, mesh, edgeRendering) the freshness gates read, plus the
    # package-specific component map + occurrence placements + mates. Provenance fields
    # come first; package fields override (occurrences here are placement dicts that
    # reference components, not the monolith's tabular occurrence rows).
    progress.phase(PHASE_FINALIZE)
    descriptor: dict[str, Any] = dict(provenance or {})
    descriptor.update(
        {
            "kind": PACKAGE_KIND,
            "packageSchemaVersion": PACKAGE_SCHEMA_VERSION,
            "rootName": root_name,
            "units": "mm",
            "components": components,
            "occurrences": occurrences,
            "assemblyMates": [
                dict(mate) for mate in (getattr(compound, "assembly_mates", None) or [])
            ],
        }
    )
    # The nested assembly hierarchy (subassembly grouping over the leaf occurrences) that the
    # viewer structure tree reads via assemblyRootFromTopology(descriptor.assembly.root).
    if assembly_root is not None:
        descriptor["assembly"] = {"root": assembly_root}
    # Lightweight geometry summary so whole-entry inspect/diff reads the descriptor
    # directly (faceCount/edgeCount need full topology and are filled on demand).
    bbox = _bbox_from_shape(compound)
    if bbox is not None:
        descriptor["bbox"] = bbox
    stats = dict(descriptor.get("stats") or {})
    stats.setdefault("occurrenceCount", len(occurrences))
    stats.setdefault("shapeCount", len(occurrences))
    descriptor["stats"] = stats
    package_dir.mkdir(parents=True, exist_ok=True)
    # Atomic: a reader polling this package must never observe a truncated descriptor.
    # write_text() truncates in place, so a concurrent status read could see half a file
    # and report the package unreadable.
    _descriptor_tmp = package_dir / f".{DESCRIPTOR_NAME}{temp_suffix()}"
    _descriptor_tmp.write_text(json.dumps(descriptor))
    replace_atomic(_descriptor_tmp, package_dir / DESCRIPTOR_NAME)
    # The lazy whole-assembly topology sidecar was extracted against the
    # previous descriptor's provenance; a rewritten package makes it stale by
    # definition, so drop it and let the next selector query rebuild it.
    (package_dir / TOPOLOGY_GLB_NAME).unlink(missing_ok=True)

    # Prune orphans: each package's components/ dir belongs to exactly ONE entry
    # (packages are self-contained; cross-model sharing was given up on purpose),
    # so any <cid>.glb the fresh descriptor no longer references is garbage from
    # an earlier geometry revision and accumulates without bound if kept. Writers
    # are serialized by the generation lock; readers re-resolve components from
    # the descriptor they load.
    referenced = {f"{cid}.glb" for cid in components}
    pruned = 0
    for stale in comp_dir.glob("*.glb"):
        if stale.name not in referenced:
            stale.unlink(missing_ok=True)
            pruned += 1
    return {
        "occurrences": len(occurrences),
        "unique_components": len(components),
        "components_built": len(built),
        "components_reused": len(reused),
        "components_pruned": pruned,
    }
