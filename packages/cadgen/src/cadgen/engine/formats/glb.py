"""A GLB read by OCCT's glTF reader (``RWGltf_CafReader``) into an XCAF document, as the stills
hold it: its node tree as the structure's tree, each mesh a part (one face per primitive), each
placement an instance, each primitive's material the structure's material and its base colour
texture drawn on it.

- **Frame**: OCCT reads glTF's Y-up metres as Z-up millimetres, as the viewer places a GLB
  (``glbMeshData.js``: a build123d root correction undone, else Y up turned to Z up, times 1000);
  a file whose nodes declare ``extras.cadUpAxis: "z"`` is read Z up, as the viewer reads it. A
  placement is the product of the nodes' down the tree; the uniform scale a part's every
  placement shares (OCCT keeps the file's units in its nodes' locations) is moved into the part's
  points, so its placements are rigid and its points millimetres. A length of the file -- where
  ``display.clip.at`` stands -- is in glTF's metres, as the viewer reads one (``millimetresPerUnit``
  1000); the viewer's scene draws those metres as millimetres (core's ``lib/render/glbScene.js``), so a
  Quick Edit packet's camera, Measure's points and the ink are millimetres already
  (``millimetresPerSceneUnit`` 1).
- **Parts**: a mesh's triangulations (nodes, triangles, normals, texture coordinates), read from
  OCCT's binary shape format with numpy (``mesh.py``'s way); one face per primitive, with the
  viewer's feature edges (``buffer.py``, three's rounding at 1e-4 of the file's metres).
- **Materials**: each primitive's ``XCAFDoc_VisMaterial`` -- base colour (linear), metallic,
  roughness, emission, alpha (a ``BLEND`` material's; an opaque one is opaque) -- with what OCCT
  does not read of the file's material (the engine's KHR extensions: IOR, transmission, clear coat,
  anisotropy, emissive strength) taken from the file's own JSON, the material matched by its name
  and factors. A primitive without one is the look's fill. Its base colour texture is OCCT's own
  (``XCAFDoc_VisMaterial.FillAspect``'s texture set), drawn over the material's colour in the lit
  looks (Solid, Shaded, Preview) and not in the colour-only ones (Parts, X-ray, Hidden line).

What a GLB holds and a still does not draw is said (``warnings``): animations (drawn at rest),
skins and morph targets (their meshes as authored), and textures beyond the base colour.
"""

from __future__ import annotations

import json
import math
import struct
from pathlib import Path
from typing import Any

import numpy as np

from cadgen.engine.formats import Foreign, FormatError, Part, Placed, assemble, files_of
from cadgen.engine.formats.buffer import buffer
from cadgen.engine.formats.gltf import look_extensions

__all__ = ["glb_file", "read_glb"]


def _json(path: Path) -> dict[str, Any]:
    """The GLB's JSON chunk (what OCCT does not read of it: the materials' extensions, the up axis),
    framed by the container's constants as the engine's GLB writer declares them."""
    from cadgen.engine.export.glb import JSON_CHUNK, MAGIC

    data = path.read_bytes()
    if len(data) < 20 or struct.unpack_from("<I", data)[0] != MAGIC:
        raise FormatError(f"{path.name} is not a GLB (binary glTF): it does not begin with glTF")
    length, kind = struct.unpack_from("<II", data, 12)
    if kind != JSON_CHUNK:
        raise FormatError(f"{path.name}: a GLB's first chunk is its JSON")
    try:
        return json.loads(data[20:20 + length])
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FormatError(f"{path.name}: its JSON does not read ({error})") from None


def _quiet() -> Any:
    """OCCT's messages to the terminal held back while it reads (the render process's stdout is
    its protocol); the gravity of each printer before, to give back."""
    from OCP.Message import Message, Message_Gravity

    printers = Message.DefaultMessenger_s().Printers()
    kept = []
    for at in range(1, printers.Size() + 1):
        printer = printers.Value(at)
        kept.append((printer, printer.GetTraceLevel()))
        printer.SetTraceLevel(Message_Gravity.Message_Fail)
    return kept


def _loud(kept: Any) -> None:
    for printer, level in kept:
        printer.SetTraceLevel(level)


def _whole_from_itself(path: Path, gltf: dict[str, Any]) -> None:
    """Refuse a GLB that names a buffer or image outside itself. OCCT's reader would resolve
    such a ``uri`` against the file's folder and read that file as the model's bytes; a GLB is
    read whole from itself, as the numpy reader (``gltf._buffers``) already requires."""
    for kind in ("buffers", "images"):
        for index, item in enumerate(gltf.get(kind) or []):
            uri = (item or {}).get("uri") if isinstance(item, dict) else None
            if uri is not None and not (isinstance(uri, str) and uri.startswith("data:") and ";base64," in uri):
                raise FormatError(f"{path.name}: {kind[:-1]} {index} is a file outside the GLB ({uri}); "
                                  "a GLB is read whole from itself")


def _document(path: Path, z_up: bool) -> Any:
    from OCP.Message import Message_ProgressRange
    from OCP.RWGltf import RWGltf_CafReader
    from OCP.RWMesh import RWMesh_CoordinateSystem
    from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFApp import XCAFApp_Application

    application = XCAFApp_Application.GetApplication_s()
    document = TDocStd_Document(TCollection_ExtendedString("BinXCAF"))
    application.InitDocument(document)
    reader = RWGltf_CafReader()
    reader.SetDocument(document)
    reader.SetSystemLengthUnit(0.001)
    reader.SetSystemCoordinateSystem(RWMesh_CoordinateSystem.RWMesh_CoordinateSystem_Zup)
    reader.SetFileLengthUnit(1.0)
    reader.SetFileCoordinateSystem(RWMesh_CoordinateSystem.RWMesh_CoordinateSystem_Zup if z_up
                                   else RWMesh_CoordinateSystem.RWMesh_CoordinateSystem_glTF)
    kept = _quiet()
    try:
        done = reader.Perform(TCollection_AsciiString(str(path)), Message_ProgressRange())
    finally:
        _loud(kept)
    if not done:
        raise FormatError(f"{path.name}: OCCT's glTF reader could not read it")
    return document


def _find(label: Any, attribute: Any, guid: Any) -> bool:
    return label.IsAttribute(guid) and label.FindAttribute(guid, attribute)


def _name(label: Any) -> str:
    from OCP.TDataStd import TDataStd_Name

    found = TDataStd_Name()
    return found.Get().ToExtString() if _find(label, found, TDataStd_Name.GetID_s()) else ""


def _matrix(location: Any) -> np.ndarray:
    value = location.Transformation().Value
    matrix = np.eye(4)
    matrix[:3, :] = [[value(row, column) for column in (1, 2, 3, 4)] for row in (1, 2, 3)]
    return matrix


def _material_label(label: Any) -> Any:
    from OCP.TDF import TDF_Label
    from OCP.XCAFDoc import XCAFDoc_VisMaterialTool

    found = TDF_Label()
    return found if XCAFDoc_VisMaterialTool.GetShapeMaterial_s(label, found) else None


def _triangulations(faces: list[Any]) -> list[tuple]:
    """Each face's triangulation as arrays: nodes (n, 3), 0-based triangles (m, 3), normals (n, 3)
    or None, texture coordinates (n, 2) or None; read from one binary shape dump with numpy."""
    import io

    from OCP.BinTools import BinTools, BinTools_FormatVersion_VERSION_4
    from OCP.BRep import BRep_Builder, BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS_Compound, TopoDS_Face

    builder = BRep_Builder()
    holder = TopoDS_Compound()
    builder.MakeCompound(holder)
    for face in faces:
        triangulation = BRep_Tool.Triangulation_s(face, TopLoc_Location())
        bare = TopoDS_Face()
        builder.MakeFace(bare, triangulation)
        builder.Add(holder, bare)
    stream = io.BytesIO()
    BinTools.Write_s(holder, stream, True, True, BinTools_FormatVersion_VERSION_4)
    data = stream.getvalue()
    at = data.index(b"\nTriangulations ")
    end = data.index(b"\n", at + 1)
    count, at = int(data[at + 16:end]), end + 1
    found = []
    for _ in range(count):
        nodes, triangles = (int(value) for value in np.frombuffer(data, "<i4", 2, at))
        has_uv, has_normals = data[at + 8], data[at + 9]
        at += 18
        points = np.frombuffer(data, "<f8", 3 * nodes, at).reshape(-1, 3)
        at += 24 * nodes
        uvs = None
        if has_uv:
            uvs = np.frombuffer(data, "<f8", 2 * nodes, at).reshape(-1, 2)
            at += 16 * nodes
        corners = np.frombuffer(data, "<i4", 3 * triangles, at).reshape(-1, 3).astype(np.int64) - 1
        at += 12 * triangles
        normals = None
        if has_normals:
            normals = np.frombuffer(data, "<f4", 3 * nodes, at).reshape(-1, 3).astype(np.float64)
            at += 12 * nodes
        found.append((points, corners, normals, uvs))
    if len(found) != len(faces):
        raise FormatError("OCCT's triangulations did not read back one per face")
    return found


def _authored(gltf: dict[str, Any]) -> list[dict[str, Any]]:
    """The file's materials as JSON, for what OCCT does not read of them."""
    return [material for material in gltf.get("materials") or [] if isinstance(material, dict)]


def _extensions(authored: list[dict[str, Any]], name: str, colour: tuple, metallic: float, roughness: float) -> dict:
    """The material OCCT read, matched in the file by name and factors: what its extensions say."""
    def close(a: Any, b: Any) -> bool:
        return all(abs(float(x) - float(y)) < 1e-4 for x, y in zip(a, b))

    for material in authored:
        pbr = material.get("pbrMetallicRoughness") or {}
        if (str(material.get("name") or "") == name and close(pbr.get("baseColorFactor", (1, 1, 1, 1)), colour)
                and close([pbr.get("metallicFactor", 1.0), pbr.get("roughnessFactor", 1.0)], [metallic, roughness])):
            return material.get("extensions") or {}
    return {}


def _vis_material(label: Any, authored: list[dict[str, Any]]) -> tuple[tuple, dict[str, Any], Any]:
    """A material label as the structure's colour (linear RGBA) and material, and its texture set
    (None without a base colour texture)."""
    from OCP.Graphic3d import Graphic3d_AlphaMode, Graphic3d_AspectFillArea3d
    from OCP.XCAFDoc import XCAFDoc_VisMaterialTool

    material = XCAFDoc_VisMaterialTool.GetMaterial_s(label)
    pbr = material.PbrMaterial() if material.HasPbrMaterial() else None
    if pbr is not None:
        rgb = pbr.BaseColor.GetRGB()
        alpha = pbr.BaseColor.Alpha() if material.AlphaMode() == Graphic3d_AlphaMode.Graphic3d_AlphaMode_Blend else 1.0
        colour = (rgb.Red(), rgb.Green(), rgb.Blue(), alpha)
        metallic, roughness, ior = float(pbr.Metallic), float(pbr.Roughness), float(pbr.RefractionIndex)
        glow = material.ConvertToCommonMaterial().EmissiveColor
        emissive = [float(glow.Red()), float(glow.Green()), float(glow.Blue())]
    else:  # a material OCCT read as the common (Phong) model: its diffuse colour
        common = material.CommonMaterial()
        rgb = common.DiffuseColor
        colour = (rgb.Red(), rgb.Green(), rgb.Blue(), 1.0 - float(common.Transparency))
        metallic, roughness, ior, emissive = 0.0, 0.5, 1.5, [0.0, 0.0, 0.0]
    colour = tuple(round(float(c), 6) for c in colour)
    raw = material.RawName()
    name = raw.ToCString() if raw is not None else _name(label)
    found: dict[str, Any] = {"name": name or "glTF material", "color": list(colour), "metallic": round(metallic, 6),
                             "roughness": round(roughness, 6), "ior": round(ior, 6), "emissive": emissive}
    found.update(look_extensions(_extensions(authored, name, colour, metallic, roughness)))
    aspect = Graphic3d_AspectFillArea3d()
    material.FillAspect(aspect)
    texture = aspect.TextureSet() if aspect.ToMapTexture() else None
    return colour, found, texture


def _smooth(positions: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    """three's ``computeVertexNormals`` on an indexed mesh: each vertex the sum of its triangles'
    area-weighted normals."""
    summed = np.zeros_like(positions)
    a, b, c = (positions[triangles[:, at]] for at in range(3))
    normal = np.cross(c - b, a - b)
    for column in range(3):
        np.add.at(summed, triangles[:, column], normal)
    return summed


def _scale(matrix: np.ndarray) -> float:
    return float(np.cbrt(abs(np.linalg.det(matrix[:3, :3])))) or 1.0


def read_glb(path: Path) -> tuple[list[Part], list[Placed], dict[str, Any], list[str]]:
    """The GLB at ``path`` as parts, their placements, the tree and the warnings (see the module docstring)."""
    from OCP.TDF import TDF_Label
    from OCP.collections import Sequence_TDF_Label
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool

    path = Path(path)
    gltf = _json(path)
    _whole_from_itself(path, gltf)
    z_up = any(str(((node or {}).get("extras") or {}).get("cadUpAxis") or "").lower() == "z"
               for node in gltf.get("nodes") or [] if isinstance(node, dict))
    document = _document(path, z_up)
    authored = _authored(gltf)
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())

    leaves: dict[str, int] = {}  # a leaf label's entry: its part
    sources: list[Any] = []  # each part's label
    placements: list[tuple[int, np.ndarray, str]] = []

    def entry(label: Any) -> str:
        from OCP.TCollection import TCollection_AsciiString
        from OCP.TDF import TDF_Tool

        text = TCollection_AsciiString()
        TDF_Tool.Entry_s(label, text)
        return text.ToCString()

    # OCCT keeps a node listed by several parents as one label they share; the walk places it once
    # for each, so a small file can name an exponential tree: bounded as a document's assembly is.
    from cadgen.engine.document import MAX_ASSEMBLY_DEPTH, MAX_OCCURRENCES

    visited = 0

    def visit(label: Any, world: np.ndarray, names: list[str], name: str) -> dict[str, Any]:
        nonlocal visited
        visited += 1
        if visited > MAX_OCCURRENCES:
            raise FormatError(f"{path.name}: its node tree names more than {MAX_OCCURRENCES} occurrences")
        if len(names) > MAX_ASSEMBLY_DEPTH:
            raise FormatError(f"{path.name}: its node tree is deeper than {MAX_ASSEMBLY_DEPTH} levels")
        if XCAFDoc_ShapeTool.IsReference_s(label):
            referred = TDF_Label()
            XCAFDoc_ShapeTool.GetReferredShape_s(label, referred)
            return visit(referred, world @ _matrix(XCAFDoc_ShapeTool.GetLocation_s(label)), names,
                         name or _name(referred))
        if XCAFDoc_ShapeTool.IsAssembly_s(label):
            node: dict[str, Any] = {"name": name, "children": []}
            components = Sequence_TDF_Label()
            XCAFDoc_ShapeTool.GetComponents_s(label, components, False)
            for at in range(1, components.Length() + 1):
                component = components.Value(at)
                referred = TDF_Label()
                XCAFDoc_ShapeTool.GetReferredShape_s(component, referred)
                child = _name(component) or _name(referred) or f"{name}.{at}"
                node["children"].append(visit(referred, world @ _matrix(XCAFDoc_ShapeTool.GetLocation_s(component)),
                                              names + [child], child))
            return node
        key = entry(label)
        if key not in leaves:
            leaves[key] = len(sources)
            sources.append(label)
        shape = XCAFDoc_ShapeTool.GetShape_s(label)
        placements.append((leaves[key], world @ _matrix(shape.Location()), "/".join(names)))
        return {"name": name, "prototype": leaves[key], "instance": len(placements) - 1}

    free = Sequence_TDF_Label()
    shapes.GetFreeShapes(free)
    roots = []
    for at in range(1, free.Length() + 1):
        label = free.Value(at)
        name = _name(label) or (path.stem if free.Length() == 1 else f"{path.stem}{at}")
        roots.append(visit(label, np.eye(4), [name], name))
    tree = roots[0] if len(roots) == 1 else {"name": path.stem, "children": roots}

    # Each part's scale, when every placement of it shares one: moved into its points.
    scales: dict[int, float] = {}
    for part, matrix, _path in placements:
        scale = _scale(matrix)
        scales[part] = scale if scales.get(part, scale) == scale or math.isclose(scales[part], scale, rel_tol=1e-9) \
            else float("nan")
    parts: list[Part] = []
    materials: dict[str, tuple] = {}
    for index, label in enumerate(sources):
        shape = XCAFDoc_ShapeTool.GetShape_s(label)
        own = _material_label(label)
        subs = Sequence_TDF_Label()
        XCAFDoc_ShapeTool.GetSubShapes_s(label, subs)
        by_face = {}
        for at in range(1, subs.Length() + 1):
            sub = subs.Value(at)
            found = _material_label(sub)
            if found is not None:
                by_face[XCAFDoc_ShapeTool.GetShape_s(sub).TShape()] = found
        faces, materials_of = [], []
        explorer = TopExp_Explorer(shape, TopAbs_FACE)
        while explorer.More():
            face = TopoDS.Face(explorer.Current())
            faces.append(face)
            materials_of.append(by_face.get(face.TShape(), own))
            explorer.Next()
        triangulations = _triangulations(faces) if faces else []
        points, corners, normals, uvs, ordinals = [], [], [], [], []
        base = 0
        for ordinal, (face, (nodes, triangles, shading, uv)) in enumerate(zip(faces, triangulations), 1):
            location = face.Location()
            if not location.IsIdentity():
                transform = _matrix(location)
                nodes = nodes @ transform[:3, :3].T + transform[:3, 3]
                if shading is not None:
                    shading = shading @ transform[:3, :3].T
            if face.Orientation() == TopAbs_REVERSED:
                triangles = triangles[:, [0, 2, 1]]
            points.append(nodes)
            corners.append(triangles + base)
            normals.append(shading)
            uvs.append(uv)
            ordinals.append(np.full(len(triangles), ordinal))
            base += len(nodes)
        scale = scales.get(index, 1.0)
        scale = 1.0 if math.isnan(scale) else scale
        positions = np.concatenate(points) * scale if points else np.zeros((0, 3))
        triangles = np.concatenate(corners) if corners else np.zeros((0, 3), np.int64)
        has_normals = all(item is not None for item in normals) and bool(normals)
        has_uvs = any(item is not None for item in uvs)
        # Without normals of its own, three's glTF loader smooths the mesh over its shared vertices.
        shading = np.concatenate([item for item in normals]) if has_normals else _smooth(positions, triangles)
        length = np.linalg.norm(shading, axis=1, keepdims=True)
        shading = np.where(length > 0, shading / np.where(length > 0, length, 1), 0.0)
        uv_all = np.concatenate([item if item is not None else np.zeros((len(p), 2)) for item, p in zip(uvs, points)]) \
            if has_uvs else None
        # three's rounding: 1e-4 of the file's numbers (metres), here 0.1 mm times the part's scale.
        mesh, uv_drawn = buffer(positions, triangles, faces=np.concatenate(ordinals) if ordinals else None,
                                normals=shading, uvs=uv_all, weld=0.1 * scale, hashed=10.0 * scale)
        face_colors, face_materials, textures = {}, {}, {}
        colour = None
        for ordinal, material_label in enumerate(materials_of, 1):
            if material_label is None:
                continue
            key = entry(material_label)
            if key not in materials:
                materials[key] = _vis_material(material_label, authored)
            rgba, found, texture = materials[key]
            # A paint is its colour and its material's place: two materials of one colour stay apart.
            paint = (*rgba, list(materials).index(key))
            face_colors[ordinal], face_materials[ordinal] = paint, found
            colour = colour or rgba
            if texture is not None:
                textures[paint] = texture
        name = _name(label) or f"part{index + 1}"
        parts.append(Part(name, mesh, colour, face_colors, None, face_materials,
                          uv_drawn if (has_uvs and textures) else None, textures))
    placed = []
    for part, matrix, where in placements:
        scale = scales.get(part, 1.0)
        rigid = matrix.copy()
        if not math.isnan(scale) and scale != 1.0:
            rigid[:3, :3] /= scale
        placed.append(Placed(part, rigid, where))
    warnings = []
    animations = len(gltf.get("animations") or [])
    if animations:
        warnings.append(f"its {animations} animation{'s are' if animations > 1 else ' is'} not played: drawn at rest")
    if gltf.get("skins") or any(primitive.get("targets") for mesh in gltf.get("meshes") or []
                                for primitive in (mesh or {}).get("primitives") or []):
        warnings.append("its skins and morph targets are drawn as authored, unposed")
    unused = sorted({key for material in authored for key in ("normalTexture", "occlusionTexture", "emissiveTexture")
                     if key in material} | {"metallicRoughnessTexture" for material in authored
                                            if "metallicRoughnessTexture" in (material.get("pbrMetallicRoughness") or {})})
    if unused:
        warnings.append(f"its {', '.join(unused)} are not drawn: the base colour texture is")
    return parts, placed, tree, warnings


def glb_file(path: Path) -> Foreign:
    parts, placed, tree, warnings = read_glb(path)
    if not any(part.mesh.triangles for part in parts):
        raise FormatError(f"{path.name} holds no triangles to draw")
    return assemble("glb", path, tree.get("name") or path.stem, parts, placed, tree, files_of([path]),
                    warnings=warnings, unit=1000.0, scene_unit=1.0)  # glTF's metres, drawn as millimetres
