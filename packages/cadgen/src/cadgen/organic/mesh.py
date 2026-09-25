"""Explicit, millimetre-based mesh operations; no implicit repair or remeshing."""

from __future__ import annotations

import hashlib
import io
import json
import math
import subprocess
import struct
import tempfile
from pathlib import Path
from typing import Any

from cadgen._internal.atomic_replace import write_bytes_atomic


_LINEAR_COLOR_ATTRIBUTE = "cadgen_color_linear"
# Float32 transfer-function roundoff is below one hundredth of an 8-bit step.
_SRGB_EIGHT_BIT_ROUNDOFF = 1e-7


def _deps():
    try:
        import numpy as np
        import trimesh
        import manifold3d as mf
    except ImportError as exc:
        raise RuntimeError("Organic mesh operations need cadgen[organic]; install that extra.") from exc
    return np, trimesh, mf


def _positive(value: float, name: str, *, zero: bool = False) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0 or (value == 0 and not zero):
        raise ValueError(f"{name} must be finite and {'nonnegative' if zero else 'positive'}")
    return value


def _has_image_texture(material):
    image_fields = (
        "image", "baseColorTexture", "metallicRoughnessTexture",
        "normalTexture", "occlusionTexture", "emissiveTexture",
    )
    return any(getattr(material, field, None) is not None for field in image_fields)


def _linear_to_srgb(values, np):
    return np.where(
        values <= 0.0031308, 12.92 * values,
        1.055 * np.power(values, 1 / 2.4) - 0.055,
    )


def _srgb_to_linear(values, np):
    return np.where(
        values <= 0.04045, values / 12.92,
        np.power((values + 0.055) / 1.055, 2.4),
    )


def _texture_vertex_rgba(mesh, np, *, linear=False, material_factor=None):
    """Bake image-free material and glTF COLOR_0, with explicit alpha policy."""
    material = mesh.visual.material
    if _has_image_texture(material):
        raise ValueError("GLB image textures need baking to vertex colors before shared export")
    factor = getattr(material, "baseColorFactor", None)
    if material_factor is not None:
        # Read at the glTF boundary before PBRMaterial's uint8 setter rounds it.
        material_color = np.asarray(material_factor, dtype=np.float32)
        if (material_color.shape != (4,) or not np.isfinite(material_color).all()
                or (material_color < 0).any() or (material_color > 1).any()):
            raise ValueError("glTF baseColorFactor must be finite RGBA in [0, 1]")
    elif factor is not None:
        material_color = np.asarray(factor, dtype=np.float32) / 255.0
    else:
        diffuse = getattr(material, "diffuse", None)
        material_color = (np.asarray(diffuse, dtype=np.float32) / 255.0
                          if diffuse is not None else np.ones(4, dtype=np.float32))
        material_color[:3] = _srgb_to_linear(material_color[:3], np)
    if len(material_color) == 3:
        material_color = np.append(material_color, 1.0)
    if material_color.shape != (4,):
        raise ValueError("Material base color must be RGB or RGBA")
    attributes = mesh.visual.vertex_attributes
    color = attributes.get("color")
    if color is None:
        # TextureVisuals.copy() drops its vertex_attributes; Trimesh.copy()
        # retains the mesh's vertex_attributes through copy and placement.
        color = mesh.vertex_attributes.get(_LINEAR_COLOR_ATTRIBUTE)
    if color is not None:
        source = np.asarray(color)
        if source.shape not in ((len(mesh.vertices), 3), (len(mesh.vertices), 4)):
            raise ValueError("GLB vertex COLOR_0 must have one RGB or RGBA value per vertex")
        vertex_color = source.astype(np.float32)
        if np.issubdtype(source.dtype, np.integer):
            vertex_color /= np.iinfo(source.dtype).max
        if source.shape[1] == 3:
            vertex_color = np.column_stack((vertex_color, np.ones(len(source), dtype=np.float32)))
    else:
        vertex_color = np.ones((len(mesh.vertices), 4), dtype=np.float32)
    # COLOR_0 and the material factor multiply in linear glTF space.
    combined = vertex_color * material_color
    mode = getattr(material, "alphaMode", None)
    if mode is None:
        # glTF PBR defaults to OPAQUE. Legacy non-PBR materials may have
        # authored alpha without a glTF mode, so preserve that as blending.
        mode = ("OPAQUE" if hasattr(material, "baseColorFactor")
                else "BLEND" if np.any(combined[:, 3] < 1) else "OPAQUE")
    if mode not in {"OPAQUE", "MASK", "BLEND"}:
        raise ValueError(f"Unsupported GLB alphaMode {mode!r}")
    cutoff = None
    if mode == "MASK":
        cutoff = getattr(material, "alphaCutoff", None)
        cutoff = 0.5 if cutoff is None else float(cutoff)
        if not math.isfinite(cutoff) or not 0 <= cutoff <= 1:
            raise ValueError("GLB alphaCutoff must be finite in [0, 1]")
    if mode == "OPAQUE":
        combined[:, 3] = 1
    if not linear:
        combined[:, :3] = _linear_to_srgb(combined[:, :3], np)
    return combined, mode, cutoff


def _gltf_material_factors(path: Path, trimesh):
    """Map loaded primitive names to unrounded glTF base-color factors."""
    if path.suffix.lower() == ".gltf":
        header = json.loads(path.read_text(encoding="utf-8"))
    else:
        with path.open("rb") as stream:
            prefix = stream.read(20)
            if len(prefix) != 20:
                raise ValueError("GLB has no JSON chunk")
            magic, version, _, length, chunk_type = struct.unpack("<IIIII", prefix)
            if magic != 0x46546C67 or version != 2 or chunk_type != 0x4E4F534A:
                raise ValueError("Expected a glTF 2.0 GLB JSON chunk")
            header = json.loads(stream.read(length).decode("utf-8"))
    materials = header.get("materials", [])
    names = {}
    counts = {}
    factors = {}
    for source_mesh in header.get("meshes", []):
        for primitive in source_mesh.get("primitives", []):
            # Mirror trimesh's primitive naming, including non-triangle names.
            name = trimesh.util.unique_name(
                source_mesh.get("name", "GLTF"), names, counts=counts
            )
            if primitive.get("mode", 4) not in {0, 1, 4, 5}:
                continue
            names[name] = True
            material_index = primitive.get("material")
            if material_index is None:
                continue
            if (not isinstance(material_index, int) or isinstance(material_index, bool)
                    or material_index < 0 or material_index >= len(materials)):
                raise ValueError("glTF primitive has an invalid material index")
            material = materials[material_index]
            factors[name] = material.get("pbrMetallicRoughness", {}).get(
                "baseColorFactor", [1.0, 1.0, 1.0, 1.0]
            )
    return factors


def _set_linear_color_visual(mesh, rgba, mode, cutoff, np, trimesh):
    """Keep float COLOR_0 on both the visual and the copy-stable mesh."""
    colors = np.asarray(rgba, dtype=np.float32)
    mesh.visual = trimesh.visual.TextureVisuals(
        material=trimesh.visual.material.PBRMaterial(
            baseColorFactor=[1.0, 1.0, 1.0, 1.0],
            alphaMode=mode, alphaCutoff=cutoff,
        )
    )
    mesh.visual.vertex_attributes["color"] = colors.copy()
    mesh.vertex_attributes[_LINEAR_COLOR_ATTRIBUTE] = colors.copy()


def _gltf_color_visual_to_srgb(mesh, np, trimesh):
    """Convert only glTF ColorVisuals: its COLOR_0 is linear, unlike authored colors."""
    kind = mesh.visual.kind
    source = np.asarray(mesh.visual.vertex_colors if kind == "vertex" else mesh.visual.face_colors)
    colors = source.astype(np.float32)
    if np.issubdtype(source.dtype, np.integer):
        colors /= np.iinfo(source.dtype).max
    if colors.shape[1] == 3:
        colors = np.column_stack((colors, np.ones(len(colors), dtype=np.float32)))
    if colors.shape[1] != 4:
        raise ValueError("glTF COLOR_0 must be RGB or RGBA")
    colors[:, :3] = _linear_to_srgb(colors[:, :3], np)
    colors[:, 3] = 1  # no material means glTF's default OPAQUE mode
    colors = np.rint(np.clip(colors, 0, 1) * 255).astype(np.uint8)
    mesh.visual = trimesh.visual.ColorVisuals(
        mesh=mesh, **({"vertex_colors": colors} if kind == "vertex" else {"face_colors": colors})
    )


def _load_scene(path: Path):
    np, trimesh, _ = _deps()
    if path.suffix.lower() not in {".glb", ".gltf", ".obj", ".stl", ".3mf"}:
        raise ValueError("Expected a GLB, glTF, OBJ, STL or 3MF mesh document")
    gltf_source = path.suffix.lower() in {".glb", ".gltf"}
    material_factors = _gltf_material_factors(path, trimesh) if gltf_source else {}
    scene = trimesh.load_scene(path, process=False, allow_remote=False)
    pieces = []
    nodes = []
    for name in sorted(scene.graph.nodes_geometry):
        transform, geometry_name = scene.graph[name]
        mesh = scene.geometry[geometry_name]
        if not isinstance(mesh, trimesh.Trimesh):
            raise ValueError(f"Node {name!r} is not a triangle mesh")
        original = mesh
        mesh = original.copy()
        # trimesh.copy() drops glTF COLOR_0 stored on TextureVisuals in
        # vertex_attributes even when there is no image texture.
        original_attributes = getattr(original.visual, "vertex_attributes", None)
        copied_attributes = getattr(mesh.visual, "vertex_attributes", None)
        if original_attributes is not None and copied_attributes is not None:
            for key in original_attributes:
                copied_attributes[key] = np.array(original_attributes[key], copy=True)
        if gltf_source and getattr(mesh.visual, "kind", None) in {"vertex", "face"}:
            _gltf_color_visual_to_srgb(mesh, np, trimesh)
        elif gltf_source and getattr(mesh.visual, "kind", None) == "texture":
            if not _has_image_texture(mesh.visual.material):
                if geometry_name not in material_factors:
                    raise ValueError(f"Cannot match glTF material for geometry {geometry_name!r}")
                rgba, mode, cutoff = _texture_vertex_rgba(
                    mesh, np, linear=True, material_factor=material_factors[geometry_name]
                )
                _set_linear_color_visual(mesh, rgba, mode, cutoff, np, trimesh)
        mesh.apply_transform(transform)
        pieces.append(mesh)
        nodes.append({"name": str(name), "geometry": str(geometry_name),
                      "vertices": len(mesh.vertices), "triangles": len(mesh.faces)})
    if not pieces:
        raise ValueError("Document contains no triangle mesh instances")
    if len(pieces) == 1:
        mesh = pieces[0]
    else:
        # trimesh.concatenate drops TextureVisuals COLOR_0. Bake untextured
        # materials per piece before joining, so separate part colors survive.
        merged_colors = []
        alpha_settings = []
        unbaked_images = False
        for piece in pieces:
            kind = getattr(piece.visual, "kind", None)
            if kind == "texture":
                if _has_image_texture(piece.visual.material):
                    unbaked_images = True
                    merged_colors = []
                    break
                rgba, mode, cutoff = _texture_vertex_rgba(piece, np, linear=True)
                merged_colors.append(rgba)
                alpha_settings.append((mode, cutoff))
            elif kind == "vertex":
                rgba = np.asarray(piece.visual.vertex_colors, dtype=np.float32) / 255.0
                rgba[:, :3] = _srgb_to_linear(rgba[:, :3], np)
                merged_colors.append(rgba)
                alpha_settings.append(("BLEND" if np.any(rgba[:, 3] < 1) else "OPAQUE", None))
            elif kind is None:
                merged_colors.append(np.ones((len(piece.vertices), 4), dtype=np.float32))
                alpha_settings.append(("OPAQUE", None))
            else:
                merged_colors = []
                break
        mesh = trimesh.util.concatenate(pieces)
        if merged_colors:
            # ColorVisuals stores only uint8 and can move a MASK alpha across
            # its cutoff. Keep linear COLOR_0 as float until the GLB writer's
            # final normalized-uint16 encoding.
            rgba = np.asarray(np.clip(np.concatenate(merged_colors), 0, 1), dtype=np.float32)
            if len(set(alpha_settings)) == 1:
                mode, cutoff = alpha_settings[0]
                mesh.metadata["organic_alpha_mode"] = mode
                if cutoff is not None:
                    mesh.metadata["organic_alpha_cutoff"] = cutoff
            else:
                mode, cutoff = "OPAQUE", None
                mesh.metadata["organic_mixed_alpha_modes"] = True
            srgb = rgba.copy()
            srgb[:, :3] = _linear_to_srgb(srgb[:, :3], np)
            color_bytes = np.rint(srgb * 255).astype(np.uint8)
            eight_bit = color_bytes.astype(np.float32) / 255
            if (np.array_equal(srgb[:, 3], eight_bit[:, 3])
                    and np.all(np.abs(srgb[:, :3] - eight_bit[:, :3])
                               <= _SRGB_EIGHT_BIT_ROUNDOFF)):
                # Keep ColorVisuals only when alpha is exact and RGB differs
                # by no more than the float32 transfer-function roundoff.
                mesh.visual = trimesh.visual.ColorVisuals(mesh=mesh, vertex_colors=color_bytes)
            else:
                _set_linear_color_visual(mesh, rgba, mode, cutoff, np, trimesh)
        if unbaked_images:
            mesh.metadata["organic_unbaked_image_textures"] = True
    if not np.isfinite(mesh.vertices).all() or not len(mesh.faces):
        raise ValueError("Mesh has non-finite vertices or no triangles")
    return mesh, nodes


def _facts(mesh) -> dict[str, Any]:
    np, _, _ = _deps()
    counts = np.bincount(mesh.edges_unique_inverse)
    return {
        "vertices": len(mesh.vertices), "triangles": len(mesh.faces),
        "bounds": mesh.bounds.tolist(), "extents": mesh.extents.tolist(),
        "boundary_edges": int((counts == 1).sum()),
        "nonmanifold_edges": int((counts > 2).sum()),
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "signed_volume": float(mesh.volume),
    }


def inspect_mesh(path: str | Path) -> dict[str, Any]:
    """Inspect raw and position-welded topology without modifying the file.

    Bounds/volume use source coordinates; this inspection never infers the
    intended physical size from a normalized AI asset or from unitless STL/OBJ.
    Welding here is diagnostic only, including across UV/normal seams.
    """
    path = Path(path)
    mesh, nodes = _load_scene(path)
    raw = _facts(mesh)
    welded = mesh.copy()
    welded.merge_vertices(merge_tex=True, merge_norm=True)
    return {
        "source": str(path), "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "coordinate_units": "source; explicit conversion required before authoring",
        "instances": nodes, "raw": raw, "position_welded": _facts(welded),
        "solid_ready": bool(welded.is_volume),
        "self_intersection": "not tested by topology inspection",
    }


def load_mesh(path: str | Path, *, up: str, height_mm: float | None = None,
              mm_per_unit: float | None = None):
    """Load placed instances into Z-up millimetres with one explicit scale.

    Supply either target height or millimetres per source unit. The original
    origin is preserved (rotated and scaled); no automatic recentering.
    """
    np, _, _ = _deps()
    if (height_mm is None) == (mm_per_unit is None):
        raise ValueError("Specify exactly one of height_mm or mm_per_unit")
    if up not in {"y", "z"}:
        raise ValueError("up must be 'y' or 'z'")
    mesh, _ = _load_scene(Path(path))
    transform = np.eye(4)
    if up == "y":
        transform[:3, :3] = [[1, 0, 0], [0, 0, -1], [0, 1, 0]]
    mesh.apply_transform(transform)
    if height_mm is not None:
        if mesh.extents[2] <= 0:
            raise ValueError("Cannot scale a mesh with zero height")
        scale = _positive(height_mm, "height_mm") / mesh.extents[2]
    else:
        scale = _positive(mm_per_unit, "mm_per_unit")
    mesh.apply_scale(scale)
    return mesh


def _solid(mesh, *, allow_empty: bool = False):
    np, _, mf = _deps()
    if not len(mesh.faces):
        if allow_empty:
            return mf.Manifold()
        raise ValueError("Empty mesh is not a printable part")
    vertices = np.array(mesh.vertices, dtype=np.float64, order="C", copy=True)
    faces = np.array(mesh.faces, dtype=np.uint64, order="C", copy=True)
    if not np.isfinite(vertices).all():
        raise ValueError("Non-finite mesh vertices")
    result = mf.Manifold(mf.Mesh64(vertices, faces))
    _check_solid(result, allow_empty=allow_empty)
    return result


def _check_solid(solid, *, allow_empty: bool = False):
    _, _, mf = _deps()
    if solid.status() != mf.Error.NoError:
        raise ValueError(f"Manifold rejected geometry: {solid.status()}")
    if solid.is_empty():
        if not allow_empty:
            raise ValueError("Operation produced an empty solid")
    elif not math.isfinite(solid.volume()) or solid.volume() <= 0:
        raise ValueError("Expected an outward-oriented positive-volume solid")
    return solid


def _mesh(solid, *, allow_empty: bool = False):
    _, trimesh, _ = _deps()
    _check_solid(solid, allow_empty=allow_empty)
    m = solid.to_mesh64()
    result = trimesh.Trimesh(vertices=m.vert_properties[:, :3], faces=m.tri_verts,
                             process=False)
    if len(result.faces) and not result.is_volume:
        raise ValueError("Kernel result is not a closed positive-volume triangle mesh")
    return result


def prepare_mesh(mesh, *, fill_small_holes: bool = False,
                 simplify_mm: float = 0.0):
    """Weld seams, remove duplicate/degenerate faces, optionally cap tiny holes.

    fill_small_holes uses only trimesh's triangle/quad hole repair, never a
    voxel remesh. Unresolved defects fail loudly. Return geometry AND an audit.
    Simplification is explicit and happens before precision joints are added.
    """
    _, trimesh, _ = _deps()
    simplify_mm = _positive(simplify_mm, "simplify_mm", zero=True)
    work = mesh.copy()
    before = _facts(work)
    work.merge_vertices(merge_tex=True, merge_norm=True)
    work.update_faces(work.unique_faces())
    work.update_faces(work.nondegenerate_faces())
    work.remove_unreferenced_vertices()
    cleaned = _facts(work)
    faces_before_caps = len(work.faces)
    if fill_small_holes:
        trimesh.repair.fill_holes(work)
    cap_faces = len(work.faces) - faces_before_caps
    # Manifold's canonical topology also removes zero-area caps/edges.
    solid = _solid(work)
    canonical = _facts(_mesh(solid))
    if simplify_mm:
        solid = solid.simplify(simplify_mm)
    result = _mesh(solid)
    return result, {
        "before": before, "cleaned": cleaned, "added_cap_triangles": cap_faces,
        "canonical": canonical, "after": _facts(result),
        "simplification_tolerance_mm": simplify_mm,
        "repair": "position weld, duplicate/degenerate cleanup"
                  + (", triangle/quad hole caps" if fill_small_holes else ""),
        "self_intersection": "not independently certified; kernel/topology checks only",
    }


def boolean(operation: str, meshes):
    """Run an explicit union, difference or intersection; never repair inputs."""
    _, _, mf = _deps()
    kinds = {"union": mf.OpType.Add, "difference": mf.OpType.Subtract,
             "intersection": mf.OpType.Intersect}
    if operation not in kinds:
        raise ValueError(f"Unknown boolean {operation!r}")
    solids = [_solid(m) for m in meshes]
    if len(solids) < 2:
        raise ValueError("A boolean needs at least two operands")
    return _mesh(mf.Manifold.batch_boolean(solids, kinds[operation]), allow_empty=True)


def split_plane(mesh, *, origin, normal, gap_mm: float = 0.0):
    """Return negative and positive sides of a plane, capped, with a seam gap."""
    np, _, _ = _deps()
    n = np.asarray(normal, dtype=float)
    p = np.asarray(origin, dtype=float)
    if n.shape != (3,) or p.shape != (3,) or not np.isfinite([n, p]).all() or not np.linalg.norm(n):
        raise ValueError("Plane needs finite origin and nonzero normal vectors")
    gap = _positive(gap_mm, "gap_mm", zero=True)
    n /= np.linalg.norm(n)
    offset = float(n @ p)
    s = _solid(mesh)
    return (_mesh(s.trim_by_plane(-n, -offset + gap / 2)),
            _mesh(s.trim_by_plane(n, offset + gap / 2)))


def from_cad(shape, *, tolerance_mm: float = 0.03):
    """Tessellate an authored build123d shape in mm; retain CAD source separately."""
    _, trimesh, _ = _deps()
    tolerance = _positive(tolerance_mm, "tolerance_mm")
    vertices, faces = shape.tessellate(tolerance, angular_tolerance=0.1)
    mesh = trimesh.Trimesh([tuple(v) for v in vertices], faces, process=False)
    mesh.merge_vertices(merge_tex=True, merge_norm=True)
    return _mesh(_solid(mesh))


def stl_roundtrip(mesh, *, max_error_mm: float = 0.001):
    """Return the actual float32 STL geometry and an export audit, without repair.

    STL discards vertex identity. Coincident sheets that a solid kernel keeps
    topologically separate can become non-manifold when a slicer welds them.
    Reject such geometry before writing and check motion on this returned mesh.
    """
    np, trimesh, _ = _deps()
    budget = _positive(max_error_mm, "max_error_mm", zero=True)
    original = _solid(mesh)
    vertices = np.asarray(mesh.vertices)
    rounded = vertices.astype(np.float32).astype(np.float64)
    error = float(np.linalg.norm(rounded - vertices, axis=1).max())
    if not math.isfinite(error) or error > budget:
        raise ValueError(f"STL coordinate rounding {error} mm exceeds {budget} mm")
    result = trimesh.load_mesh(io.BytesIO(mesh.export(file_type="stl")), file_type="stl", process=True)
    if not result.is_volume:
        raise ValueError("STL round trip is not a closed positive-volume mesh; resolve coincident or degenerate features in source")
    reread = _solid(result)
    if len(original.decompose()) != len(reread.decompose()):
        raise ValueError("STL round trip changed the connected component count")
    return result, {"coordinate_precision": "float32 STL, position-welded on read",
                    "maximum_coordinate_rounding_mm": error, "maximum_allowed_rounding_mm": budget,
                    "triangles": len(result.faces), "watertight": bool(result.is_watertight),
                    "components": len(reread.decompose()), "volume_mm3": float(result.volume)}


def _serialized_scene(parts: dict[str, Any], fmt: str, name: str) -> bytes:
    """Send validated Z-up mm triangles to cadgen's shared mesh exporter."""
    np, _, _ = _deps()
    from cadgen._internal.node_runtime import cad_node_executable, node_builder_script

    with tempfile.TemporaryDirectory(prefix="cadgen-organic-export-") as folder:
        root = Path(folder)
        entries = []
        for index, (part_name, mesh) in enumerate(sorted(parts.items())):
            triangles = np.asarray(mesh.vertices[mesh.faces], dtype="<f4").reshape(-1)
            positions_name = f"part-{index}.positions.bin"
            (root / positions_name).write_bytes(triangles.tobytes())
            entry = {"name": part_name, "positions": positions_name}
            if fmt == "glb":
                normals = np.asarray(mesh.vertex_normals[mesh.faces], dtype="<f4").reshape(-1)
                normals_name = f"part-{index}.normals.bin"
                (root / normals_name).write_bytes(normals.tobytes())
                entry["normals"] = normals_name
                kind = getattr(mesh.visual, "kind", None)
                colors = None
                if kind == "texture":
                    rgba, mode, cutoff = _texture_vertex_rgba(mesh, np)
                    colors = rgba[mesh.faces]
                    entry["alphaMode"] = mode
                    if cutoff is not None:
                        entry["alphaCutoff"] = cutoff
                elif kind in {"vertex", "face"}:
                    source = np.asarray(
                        mesh.visual.vertex_colors if kind == "vertex" else mesh.visual.face_colors
                    )
                    colors = (source[mesh.faces] if kind == "vertex"
                              else np.repeat(source[:, None, :], 3, axis=1))
                    colors = colors.astype(np.float32)
                    if np.issubdtype(source.dtype, np.integer):
                        colors /= 255.0
                    mode = mesh.metadata.get("organic_alpha_mode")
                    if mode:
                        entry["alphaMode"] = mode
                        if mode == "MASK":
                            entry["alphaCutoff"] = mesh.metadata["organic_alpha_cutoff"]
                if colors is not None:
                    if colors.shape[-1] == 3:
                        colors = np.concatenate((colors, np.ones((*colors.shape[:-1], 1))), axis=-1)
                    if (colors.shape[-1] != 4 or not np.isfinite(colors).all()
                            or (colors < 0).any() or (colors > 1).any()):
                        raise ValueError("Vertex colors must be finite RGBA values in [0, 1]")
                    colors_name = f"part-{index}.colors.bin"
                    (root / colors_name).write_bytes(np.asarray(colors, dtype="<f4").tobytes())
                    entry["colors"] = colors_name
            entries.append(entry)
        manifest = root / "scene.json"
        manifest.write_text(json.dumps({
            "name": name, "units": "mm", "up": "z", "parts": entries,
        }, ensure_ascii=False), encoding="utf-8")
        output = root / f"export.{fmt}"
        command = [cad_node_executable(), str(node_builder_script("mesh-export.mjs")),
                   "--mesh-scene", str(manifest), "--format", fmt, "--out", str(output)]
        result = subprocess.run(command, capture_output=True)
        if result.returncode != 0 or not output.is_file():
            detail = result.stdout.decode("utf-8", errors="replace").strip()
            error = detail or result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Organic {fmt.upper()} export failed: {error}")
        return output.read_bytes()


def write_mesh(mesh, path: str | Path) -> Path:
    """Atomically write a valid STL (mm/Z-up) or GLB (m/Y-up)."""
    path = Path(path)
    _solid(mesh)
    if path.suffix.lower() == ".stl":
        printable, audit = stl_roundtrip(mesh)
        body = _serialized_scene({path.stem: printable}, "stl", path.stem)
        _, trimesh, _ = _deps()
        reread = trimesh.load_mesh(io.BytesIO(body), file_type="stl", process=True)
        if not reread.is_volume or len(_solid(reread).decompose()) != audit["components"]:
            raise ValueError("Shared STL export changed printable topology")
        write_bytes_atomic(path, body)
        return path
    if path.suffix.lower() == ".glb":
        return write_scene({path.stem: mesh}, path)
    raise ValueError("Organic mesh output supports .stl and .glb")


def write_scene(parts: dict[str, Any], path: str | Path) -> Path:
    """Write labeled independent components to GLB; this does not fuse them."""
    path = Path(path)
    if path.suffix.lower() != ".glb" or not parts:
        raise ValueError("A scene needs named parts and a .glb destination")
    for name, mesh in parts.items():
        if not isinstance(name, str) or not name:
            raise ValueError("Part names must be nonempty strings")
        if mesh.metadata.get("organic_unbaked_image_textures"):
            raise ValueError("GLB image textures need baking to vertex colors before shared export")
        if mesh.metadata.get("organic_mixed_alpha_modes"):
            raise ValueError("Mixed GLB alpha modes need separate named parts")
        _solid(mesh)
    body = _serialized_scene(parts, "glb", path.stem)
    write_bytes_atomic(path, body)
    return path
