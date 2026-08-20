from __future__ import annotations

from pathlib import Path
from typing import Any

from OCP.BRep import BRep_Builder
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.TopTools import TopTools_IndexedMapOfShape
from OCP.TopoDS import TopoDS
from OCP.TopoDS import TopoDS_Compound

from cadgen.metadata import MeshSettings

from cadgen._internal.step_scene_cache import load_step_scene_cached
from cadgen._internal.step_scene_geometry import _bbox_from_points, _bbox_from_shape, _merge_bbox, _transform_bbox
from cadgen._internal.step_scene_loader import _located_shape, _selector_id
from cadgen._internal.step_scene_types import AdaptiveMeshResolution, LoadedStepScene, OccurrenceNode, _enum_name


def mesh_step_scene(
    scene: LoadedStepScene,
    *,
    linear_deflection: float,
    angular_deflection: float,
    relative: bool,
    parallel: bool = True,
) -> None:
    signature = (float(linear_deflection), float(angular_deflection), bool(relative))
    if scene.mesh_signature == signature:
        return
    for shape in scene.prototype_shapes.values():
        BRepMesh_IncrementalMesh(
            shape,
            signature[0],
            signature[2],
            signature[1],
            # OCCT's in-mesh parallelism is nondeterministic (triangle/vertex
            # ordering varies run to run). Whole-scene sidecar meshing keeps it
            # for throughput; per-component builds pass parallel=False so a
            # component GLB is reproducible and process-pool workers do not
            # oversubscribe cores with nested OCCT threads.
            parallel,
        )
    scene.mesh_signature = signature


def _iter_leaf_occurrences(nodes: list[OccurrenceNode]) -> list[OccurrenceNode]:
    leaves: list[OccurrenceNode] = []
    stack = list(reversed(nodes))
    while stack:
        node = stack.pop()
        if node.prototype_key is not None:
            leaves.append(node)
        if node.children:
            stack.extend(reversed(node.children))
    return leaves


def occurrence_selector_id(node: OccurrenceNode) -> str:
    return _selector_id(node.path)


def scene_leaf_occurrences(scene: LoadedStepScene) -> list[OccurrenceNode]:
    return _iter_leaf_occurrences(scene.roots)


def scene_occurrence_shape(scene: LoadedStepScene, node: OccurrenceNode) -> Any:
    if node.prototype_key is None or node.prototype_key not in scene.prototype_shapes:
        raise RuntimeError(f"Occurrence {occurrence_selector_id(node)} has no prototype shape")
    return _located_shape(scene.prototype_shapes[node.prototype_key], node.location)


def _leaf_shape(obj: Any) -> Any:
    """Wrap a raw OCCT leaf in its matching build123d type (Solid, Shell, ...).

    ``build123d.Shape(obj=...)`` yields an untyped ``Shape`` that is missing the
    per-type API (``.volume`` and friends). build123d's own importer downcasts and
    looks the concrete class up in ``topods_lut``; do the same so a single-solid
    STEP round-trips to a ``Solid``, not a bare ``Shape``.
    """
    import build123d
    from build123d.importers import topods_lut
    from build123d.topology import downcast

    downcast_obj = downcast(obj)
    factory = topods_lut.get(type(downcast_obj))
    if factory is None:
        return build123d.Shape(obj=downcast_obj)
    return factory(downcast_obj)


def scene_to_build123d_compound(scene: LoadedStepScene, *, label: str | None = None) -> Any:
    """Reconstruct the scene's shape from a loaded scene.

    Mirrors what ``build123d.import_step`` produces topologically AND chromatically,
    including its root handling: a single-root STEP returns that root directly and a
    multi-root STEP is wrapped in a container Compound. Otherwise it is
    the occurrence tree with each leaf prototype placed by its world transform,
    labeled by its occurrence name, and tagged with its STEP color (per-occurrence
    color first, prototype color second). Geometry is the exact BREP from the scene,
    so a cache-backed scene yields a shape topologically identical to a fresh import.
    The ``.color`` attribute is what the STEP exporter (``set_label_color``) and the
    downstream GLB pipeline read to round-trip the visual into rendered artifacts.
    """
    import build123d

    def node_label(node: OccurrenceNode) -> str:
        return str(node.name or node.source_name or occurrence_selector_id(node)).strip()

    def node_color(node: OccurrenceNode) -> tuple[float, ...] | None:
        if node.color is not None:
            return tuple(node.color)
        if node.prototype_key is not None:
            prototype_color = scene.prototype_colors.get(node.prototype_key)
            if prototype_color is not None:
                return tuple(prototype_color)
        return None

    def build_node(node: OccurrenceNode) -> Any:
        if node.children:
            compound = build123d.Compound(
                children=[build_node(child) for child in node.children],
                label=node_label(node),
            )
            color = node_color(node)
            if color is not None:
                compound.color = color
            return compound
        shape = _leaf_shape(scene_occurrence_shape(scene, node))
        shape.label = node_label(node)
        color = node_color(node)
        if color is not None:
            shape.color = color
        return shape

    roots = [build_node(root) for root in scene.roots]
    if not roots:
        raise RuntimeError(f"STEP scene has no geometry: {scene.step_path}")
    if len(roots) == 1:
        # A single-root STEP is returned as that root, never wrapped: build123d's
        # own import_step does the same ("Remove empty Compound wrapper if single
        # free object"). Wrapping would add an assembly level that is not in the
        # file, pushing every occurrence path one segment deeper (o1.1 -> o1.1.1)
        # so selector refs differ depending on whether the STEP was opened
        # directly or returned from a generator's gen_step().
        single = roots[0]
        if label:
            single.label = label
        return single
    # Multiple free roots still need a container to be one shape, which is also
    # what build123d falls back to.
    return build123d.Compound(children=roots, label=label or scene.step_path.stem)


def import_step(step_path: Path, *, label: str | None = None) -> Any:
    """``build123d.import_step`` backed by the inline ``__cadgen__`` scene cache.

    Returns a shape topologically identical to ``import_step`` — including the root
    itself, not a wrapper around it — but
    reuses the cached binary BREP, so warm loads are ~tens of ms instead of a full
    text-STEP re-parse. Cold loads cost the same as ``import_step`` (plus a small
    cache write). Per-occurrence and prototype STEP colors are applied via
    ``scene_to_build123d_compound``, so the returned shape is a colored drop-in.
    Falls back to a raw import if the scene cannot be reconstructed.
    """
    import build123d

    resolved = Path(step_path).expanduser().resolve()
    try:
        scene = load_step_scene_cached(resolved)
        # No filename fallback for the label: build123d keeps the STEP's own root
        # name, and deriving it from the path would make identical STEP content
        # produce different trees depending on where the file happens to live.
        return scene_to_build123d_compound(scene, label=label)
    except Exception:  # noqa: BLE001 - if the topology-aware load fails for any reason, fall back to build123d's import
        return build123d.import_step(resolved)


def scene_occurrence_prototype_shape(scene: LoadedStepScene, node: OccurrenceNode) -> Any:
    if node.prototype_key is None or node.prototype_key not in scene.prototype_shapes:
        raise RuntimeError(f"Occurrence {occurrence_selector_id(node)} has no prototype shape")
    return scene.prototype_shapes[node.prototype_key]


def scene_export_shape(scene: LoadedStepScene) -> Any:
    if scene.export_shape is not None:
        return scene.export_shape
    leaf_shapes = [
        scene_occurrence_shape(scene, node)
        for node in _iter_leaf_occurrences(scene.roots)
        if node.prototype_key is not None and node.prototype_key in scene.prototype_shapes
    ]
    if not leaf_shapes:
        raise RuntimeError(f"No CAD geometry available for STL export: {scene.step_path}")
    if len(leaf_shapes) == 1:
        scene.export_shape = leaf_shapes[0]
        return scene.export_shape
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for shape in leaf_shapes:
        builder.Add(compound, shape)
    scene.export_shape = compound
    return scene.export_shape


def _scene_mesh_resolution_hints(scene: LoadedStepScene) -> dict[str, Any]:
    prototype_face_counts: dict[int, int] = {}
    prototype_edge_counts: dict[int, int] = {}
    prototype_curved_face_counts: dict[int, int] = {}
    prototype_curved_edge_counts: dict[int, int] = {}
    for key, shape in scene.prototype_shapes.items():
        face_map = TopTools_IndexedMapOfShape()
        edge_map = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, TopAbs_FACE, face_map)
        TopExp.MapShapes_s(shape, TopAbs_EDGE, edge_map)
        prototype_face_counts[key] = int(face_map.Extent())
        prototype_edge_counts[key] = int(edge_map.Extent())
        curved_faces = 0
        for face_index in range(1, face_map.Extent() + 1):
            try:
                surface = BRepAdaptor_Surface(TopoDS.Face_s(face_map.FindKey(face_index)))
                if _enum_name(surface.GetType(), "GeomAbs_") != "plane":
                    curved_faces += 1
            except Exception:  # noqa: BLE001 - OCP surface reads can raise on odd faces; count them as curved
                curved_faces += 1
        curved_edges = 0
        for edge_index in range(1, edge_map.Extent() + 1):
            try:
                curve = BRepAdaptor_Curve(TopoDS.Edge_s(edge_map.FindKey(edge_index)))
                if _enum_name(curve.GetType(), "GeomAbs_") != "line":
                    curved_edges += 1
            except Exception:  # noqa: BLE001 - OCP curve reads can raise on odd edges; count them as curved
                curved_edges += 1
        prototype_curved_face_counts[key] = curved_faces
        prototype_curved_edge_counts[key] = curved_edges

    leaves = scene_leaf_occurrences(scene)
    occurrence_face_count = sum(
        prototype_face_counts.get(int(node.prototype_key), 0)
        for node in leaves
        if node.prototype_key is not None
    )
    occurrence_edge_count = sum(
        prototype_edge_counts.get(int(node.prototype_key), 0)
        for node in leaves
        if node.prototype_key is not None
    )
    occurrence_curved_face_count = sum(
        prototype_curved_face_counts.get(int(node.prototype_key), 0)
        for node in leaves
        if node.prototype_key is not None
    )
    occurrence_curved_edge_count = sum(
        prototype_curved_edge_counts.get(int(node.prototype_key), 0)
        for node in leaves
        if node.prototype_key is not None
    )
    prototype_face_count = sum(prototype_face_counts.values())
    prototype_edge_count = sum(prototype_edge_counts.values())
    prototype_curved_face_count = sum(prototype_curved_face_counts.values())
    prototype_curved_edge_count = sum(prototype_curved_edge_counts.values())
    complexity_score = (
        float(occurrence_face_count)
        + (float(occurrence_edge_count) * 0.35)
        + (float(prototype_face_count) * 0.5)
        + (float(len(leaves)) * 24.0)
    )
    curvature_pressure_score = (
        (float(occurrence_curved_face_count) * 1.6)
        + (float(occurrence_curved_edge_count) * 0.9)
        + (float(prototype_curved_face_count) * 0.8)
        + (float(prototype_curved_edge_count) * 0.4)
    )
    # The diagonal is computed UNCONDITIONALLY: the meter-scale deflection floor
    # in adaptive_mesh_resolution_from_hints depends on it, and the scenes that
    # need the floor most (thousands of occurrence faces, e.g. a full launch
    # stack) are exactly the ones a face-count guard would skip. The cost is
    # small: _bbox_from_shape uses BRepBndLib without tessellation per unique
    # prototype, plus an 8-corner transform per leaf occurrence.
    prototype_boxes = {
        key: _bbox_from_shape(shape, tight=False)
        for key, shape in scene.prototype_shapes.items()
    }
    occurrence_boxes = [
        _transform_bbox(prototype_boxes[int(node.prototype_key)], node.transform)
        for node in leaves
        if node.prototype_key is not None and int(node.prototype_key) in prototype_boxes
    ]
    bbox = _merge_bbox(occurrence_boxes) if occurrence_boxes else _bbox_from_points([])
    diagonal: float | None = float(bbox.get("diag") or 0.0)
    if diagonal <= 50.0:
        scale_factor = 0.65
    elif diagonal <= 150.0:
        scale_factor = 0.8
    elif diagonal <= 500.0:
        scale_factor = 1.0
    elif diagonal <= 1500.0:
        scale_factor = 1.18
    else:
        scale_factor = 1.35
    return {
        "bboxDiag": None if diagonal is None else round(diagonal, 3),
        "prototypeFaceCount": prototype_face_count,
        "prototypeEdgeCount": prototype_edge_count,
        "prototypeCurvedFaceCount": prototype_curved_face_count,
        "prototypeCurvedEdgeCount": prototype_curved_edge_count,
        "occurrenceFaceCount": occurrence_face_count,
        "occurrenceEdgeCount": occurrence_edge_count,
        "occurrenceCurvedFaceCount": occurrence_curved_face_count,
        "occurrenceCurvedEdgeCount": occurrence_curved_edge_count,
        "leafOccurrenceCount": len(leaves),
        "complexityScore": round(complexity_score, 3),
        "effectiveComplexityScore": round(complexity_score * scale_factor, 3),
        "curvaturePressureScore": round(curvature_pressure_score * scale_factor, 3),
    }


def adaptive_mesh_resolution_from_hints(hints: dict[str, Any]) -> AdaptiveMeshResolution:
    effective_score = float(hints["effectiveComplexityScore"])
    curvature_pressure = float(hints["curvaturePressureScore"])
    leaf_count = int(hints["leafOccurrenceCount"])
    face_count = int(hints["occurrenceFaceCount"])
    edge_count = int(hints["occurrenceEdgeCount"])

    if face_count >= 20000 or edge_count >= 55000 or effective_score >= 45000 or curvature_pressure >= 45000:
        profile = "large-topology"
        settings = MeshSettings(tolerance=0.025, angular_tolerance=0.75)
    elif (
        face_count >= 8000
        or edge_count >= 22000
        or effective_score >= 28000
        or curvature_pressure >= 18000
        or (leaf_count >= 80 and effective_score >= 22000)
    ):
        profile = "coarse-assembly"
        settings = MeshSettings(tolerance=0.02, angular_tolerance=0.6)
    elif (
        face_count >= 2500
        or edge_count >= 8000
        or effective_score >= 6000
        or curvature_pressure >= 9000
        or (leaf_count >= 80 and effective_score >= 6000)
        or (leaf_count >= 24 and effective_score >= 3500)
    ):
        profile = "balanced-assembly"
        settings = MeshSettings(tolerance=0.016, angular_tolerance=0.5)
    elif face_count >= 800 or edge_count >= 2500 or effective_score >= 1800 or curvature_pressure >= 3500:
        profile = "medium"
        settings = MeshSettings(tolerance=0.014, angular_tolerance=0.45)
    elif face_count >= 180 or edge_count >= 600 or effective_score >= 450 or curvature_pressure >= 900:
        profile = "fine"
        settings = MeshSettings(tolerance=0.008, angular_tolerance=0.3)
    else:
        profile = "extra-fine"
        settings = MeshSettings(tolerance=0.006, angular_tolerance=0.2)

    hints = dict(hints)
    # The absolute profile tolerances above are tuned for desk-scale parts.
    # Past that envelope, floor the linear deflection proportionally to the
    # model diagonal (~0.03% of diag) so meter-scale models do not tessellate
    # at micron-class chord error (multi-minute meshes, quarter-GB packages).
    # Angular deflection stays per-profile; it is scale-invariant.
    raw_diagonal = hints.get("bboxDiag")
    diagonal = float(raw_diagonal) if isinstance(raw_diagonal, (int, float)) else 0.0
    if diagonal > 500.0:
        scale_floor = round(diagonal * 3.0e-4, 3)
        if scale_floor > settings.tolerance:
            # When the linear floor engages, curvature quality must ride on the
            # ANGULAR deflection (scale-invariant): a coarse profile pairs the
            # floor with angular 0.6-0.75 rad, which would leave small
            # high-curvature parts (engine bells in a full stack) visibly
            # polygonal. Clamp angular so cylinders keep >=~18 segments.
            settings = MeshSettings(
                tolerance=scale_floor,
                angular_tolerance=min(settings.angular_tolerance, 0.35),
            )
            hints["scaleFloorTolerance"] = scale_floor
    hints["profile"] = profile
    return AdaptiveMeshResolution(settings=settings, profile=profile, hints=hints)


def adaptive_mesh_resolution_for_scene(scene: LoadedStepScene) -> AdaptiveMeshResolution:
    return adaptive_mesh_resolution_from_hints(_scene_mesh_resolution_hints(scene))


