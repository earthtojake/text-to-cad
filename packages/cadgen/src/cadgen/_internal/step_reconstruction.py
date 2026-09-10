"""Experimental numerical recipe replay. Imported only in a disposable worker.
The target BREP is read after replay, solely for geometric comparison.
"""

import io, json, math, sys
from pathlib import Path
from OCP.BinTools import BinTools
from OCP.BRep import BRep_Tool
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
from OCP.BRepTools import BRepTools
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeWire,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakePolygon,
)
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepLib import BRepLib_ToolTriangulatedShape
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism, BRepPrimAPI_MakeRevol
from OCP.Bnd import Bnd_Box
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Ax1, gp_Ax2, gp_Circ
from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID, TopAbs_REVERSED, TopAbs_EDGE
from OCP.TopExp import TopExp
from OCP.TopLoc import TopLoc_Location
from OCP.TopTools import TopTools_IndexedMapOfShape
from OCP.TopoDS import TopoDS, TopoDS_Shape


def items(shape, kind):
    m = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, kind, m)
    return [m.FindKey(i) for i in range(1, m.Extent() + 1)]


def mass(shape, area=False):
    p = GProp_GProps()
    (BRepGProp.SurfaceProperties_s if area else BRepGProp.VolumeProperties_s)(
        shape, p, 1e-10
    )
    return p.Mass()


def cross(a, b):
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def normalize(a):
    l = math.sqrt(sum(v * v for v in a))
    return [v / l for v in a]


def positive(shape):
    if mass(shape) < 0:
        shape.Reverse()
    return shape


def sketch(profile):
    polylines = []
    if profile["kind"] == "polygon":
        points = profile["points"]
        if len(points) < 3:
            raise ValueError("Sketch needs at least three vertices")
        polygon = BRepBuilderAPI_MakePolygon()
        for point in points:
            polygon.Add(gp_Pnt(*point))
        polygon.Close()
        wire = polygon.Wire()
        polylines = [points + [points[0]]]
    elif profile["kind"] == "axial":
        axis, origin = profile["axis"], profile["origin"]
        side = normalize(cross(axis, [1, 0, 0] if abs(axis[0]) < 0.9 else [0, 1, 0]))
        points = [
            [origin[i] + side[i] * r + axis[i] * z for i in range(3)]
            for r, z in profile["profile"]
        ]
        polygon = BRepBuilderAPI_MakePolygon()
        for p in points:
            polygon.Add(gp_Pnt(*p))
        polygon.Close()
        wire = polygon.Wire()
        polylines = [points + [points[0]]]
    else:
        builder = BRepBuilderAPI_MakeWire()
        for use in profile["edges"]:
            c = use["curve"]
            a, b = c["range"]
            origin = c["origin"]
            if c["kind"] == "line":
                points = [
                    [origin[i] + c["dir"][i] * t for i in range(3)] for t in [a, b]
                ]
                edge = BRepBuilderAPI_MakeEdge(
                    gp_Pnt(*points[0]), gp_Pnt(*points[1])
                ).Edge()
            elif c["kind"] == "circle":
                frame = gp_Ax2(
                    gp_Pnt(*origin),
                    gp_Dir(*cross(c["xdir"], c["ydir"])),
                    gp_Dir(*c["xdir"]),
                )
                edge = BRepBuilderAPI_MakeEdge(gp_Circ(frame, c["radius"]), a, b).Edge()
                points = [
                    [
                        origin[i]
                        + c["radius"]
                        * (math.cos(t) * c["xdir"][i] + math.sin(t) * c["ydir"][i])
                        for i in range(3)
                    ]
                    for t in [a + (b - a) * j / 96 for j in range(97)]
                ]
            else:
                raise ValueError("Unsupported sketch curve")
            if use["reversed"]:
                edge.Reverse()
                points.reverse()
            builder.Add(edge)
            polylines.append(points)
        if not builder.IsDone():
            raise ValueError("Open or disconnected sketch")
        wire = builder.Wire()
    face = BRepBuilderAPI_MakeFace(wire, True).Face()
    if not BRepCheck_Analyzer(face).IsValid():
        raise ValueError("Invalid sketch face")
    return face, polylines


def cut(body, tool):
    op = BRepAlgoAPI_Cut(body, tool)
    if not op.IsDone():
        raise ValueError("Boolean cut failed")
    return positive(op.Shape())


def fillet(body, radius, selection):
    if radius <= 0:
        raise ValueError("Invalid fillet radius")
    edges = items(body, TopAbs_EDGE)
    if selection != "all":
        if not isinstance(selection, dict) or selection.get("axis") not in (0, 1, 2):
            raise ValueError("Unsupported fillet selection")
        axis, position, box = (
            selection["axis"],
            selection["position"],
            selection["bounds"],
        )
        if len(box) != 6:
            raise ValueError("Invalid fillet bounds")
        selected = []
        for edge in edges:
            b = bounds(edge)
            if (
                abs(b[axis] - position) < 1e-5
                and abs(b[axis + 3] - position) < 1e-5
                and all(
                    b[i] >= box[i] - 1e-5 and b[i + 3] <= box[i + 3] + 1e-5
                    for i in range(3)
                )
            ):
                selected.append(edge)
        edges = selected
        if not edges or len(edges) != selection.get("count"):
            raise ValueError("Fillet boundary is missing or ambiguous")
    operation = BRepFilletAPI_MakeFillet(body)
    for edge in edges:
        operation.Add(radius, TopoDS.Edge_s(edge))
    operation.Build()
    if not operation.IsDone():
        raise ValueError("Fillet failed")
    return positive(operation.Shape())


def replay(recipe):
    """Dependencies are the actual inputs consumed by each operation."""
    validate_recipe(recipe)
    values = {}
    kinds = {}
    snapshots = []
    current = None
    for step in recipe["steps"]:
        if step["id"] in values:
            raise ValueError("Duplicate node")
        kind = step["kind"]
        sketches = (
            step.get("sketches", [])
            if kind == "loft"
            else ([step["sketch"]] if step.get("sketch") else [])
        )
        expected = (
            ([step["input"]] if step.get("input") else [])
            + sketches
            + ([step["tool"]] if step.get("tool") else [])
        )
        if step["dependsOn"] != expected or any(d not in values for d in expected):
            raise ValueError("Missing, cyclic or inconsistent dependency")
        if any(kinds.get(sketch_id) != "sketch" for sketch_id in sketches):
            raise ValueError("Operation needs a sketch")
        if step.get("tool") and (
            kind not in ("cut", "add")
            or kinds.get(step["tool"])
            not in ("extrude", "revolve", "cut", "fillet", "loft", "add")
        ):
            raise ValueError("Boolean operation needs an earlier solid tool")
        if kind in ("cut", "fillet", "add"):
            if kinds.get(step.get("input")) not in (
                "extrude",
                "revolve",
                "cut",
                "fillet",
                "loft",
                "add",
            ):
                raise ValueError("Operation needs an earlier solid")
        elif step.get("input"):
            raise ValueError("Unexpected solid dependency")
        lines = []
        if step["kind"] == "sketch":
            value, lines = sketch(step["profile"])
        else:
            face = values[step["sketch"]] if step.get("sketch") else None
            if kind == "fillet":
                value = fillet(values[step["input"]], step["radius"], step["edges"])
            elif kind in ("cut", "add") and step.get("tool"):
                if kind == "cut":
                    value = cut(values[step["input"]], values[step["tool"]])
                else:
                    operation = BRepAlgoAPI_Fuse(
                        values[step["input"]], values[step["tool"]]
                    )
                    if not operation.IsDone():
                        raise ValueError("Additive operation failed")
                    value = positive(operation.Shape())
                    if mass(value) - mass(values[step["input"]]) < 1e-7:
                        raise ValueError("Additive operation added no material")
            elif kind == "loft":
                if not 2 <= len(sketches) <= 32:
                    raise ValueError("Loft needs 2–32 sections")
                operation = BRepOffsetAPI_ThruSections(True, True, 1e-7)
                for sketch_id in sketches:
                    operation.AddWire(BRepTools.OuterWire_s(values[sketch_id]))
                operation.Build()
                if not operation.IsDone():
                    raise ValueError("Loft failed")
                value = positive(operation.Shape())
            elif step["kind"] == "revolve":
                value = positive(
                    BRepPrimAPI_MakeRevol(
                        face,
                        gp_Ax1(gp_Pnt(*step["origin"]), gp_Dir(*step["axis"])),
                        step["angle"],
                    ).Shape()
                )
            elif step["kind"] in ["extrude", "cut"]:
                tool = positive(
                    BRepPrimAPI_MakePrism(face, gp_Vec(*step["direction"])).Shape()
                )
                value = (
                    cut(values[step["input"]], tool) if step["kind"] == "cut" else tool
                )
            else:
                raise ValueError("Unsupported operation")
            if (
                not BRepCheck_Analyzer(value).IsValid()
                or len(items(value, TopAbs_SOLID)) != 1
                or mass(value) <= 0
            ):
                raise ValueError("Invalid intermediate solid")
            if (
                step["kind"] in ("cut", "fillet")
                and mass(values[step["input"]]) - mass(value) < 1e-7
            ):
                raise ValueError("Operation removed no material")
            current = value
        values[step["id"]] = value
        kinds[step["id"]] = step["kind"]
        snapshots.append(
            dict(
                step=step,
                shape=current,
                lines=lines,
                volume=mass(current) if current else 0,
            )
        )
    if (
        recipe["output"] != recipe["steps"][-1]["id"]
        or kinds[recipe["output"]] == "sketch"
    ):
        raise ValueError("Recipe must end in its final solid")
    return values[recipe["output"]], snapshots


def bounds(shape):
    b = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, b, False, False)
    return list(b.Get())


def compare(target, result):
    missing = abs(mass(cut(target, result)))
    extra = abs(mass(cut(result, target)))
    tolerance = max(1e-6, abs(mass(target)) * 1e-8)
    box_error = max(abs(a - b) for a, b in zip(bounds(target), bounds(result)))
    area_error = abs(mass(target, True) - mass(result, True))
    volume_error = abs(mass(target) - mass(result))
    valid = BRepCheck_Analyzer(result).IsValid()
    return dict(
        passed=valid
        and missing + extra <= tolerance
        and volume_error <= tolerance
        and box_error < 1e-5
        and area_error < max(1e-5, mass(target, True) * 1e-8),
        valid=valid,
        missingVolume=missing,
        extraVolume=extra,
        volumeTolerance=tolerance,
        boundsError=box_error,
        volumeError=volume_error,
        areaError=area_error,
        targetVolume=mass(target),
        resultVolume=mass(result),
        solidCount=len(items(result, TopAbs_SOLID)),
    )


def mesh(shape):
    if shape is None:
        return {"vertices": [], "normals": []}
    box = bounds(shape)
    diagonal = math.sqrt(sum((box[i + 3] - box[i]) ** 2 for i in range(3)))
    # Preview tessellation is independent of the exact-solid verification above.
    BRepTools.Clean_s(shape)
    BRepMesh_IncrementalMesh(shape, max(0.005, diagonal / 2000), False, 0.16, False)
    vertices, normals, indices = [], [], []
    for f in items(shape, TopAbs_FACE):
        face = TopoDS.Face_s(f)
        location = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, location)
        if tri is None:
            raise ValueError("Could not tessellate a reconstruction face")
        BRepLib_ToolTriangulatedShape.ComputeNormals_s(face, tri)
        if len(indices) + tri.NbTriangles() * 3 > 500_000:
            raise ValueError("Preview exceeds the triangle limit")
        nodes = {}
        for i in range(1, tri.NbTriangles() + 1):
            ids = list(tri.Triangle(i).Get())
            if face.Orientation() == TopAbs_REVERSED:
                ids[1], ids[2] = ids[2], ids[1]
            for n in ids:
                if n in nodes:
                    indices.append(nodes[n])
                    continue
                nodes[n] = len(vertices) // 3
                indices.append(nodes[n])
                p = tri.Node(n).Transformed(location.Transformation())
                vertices.extend(round(v, 6) for v in [p.X(), p.Y(), p.Z()])
                normal = tri.Normal(n).Transformed(location.Transformation())
                sign = -1 if face.Orientation() == TopAbs_REVERSED else 1
                normals.extend(
                    round(sign * v, 6) for v in [normal.X(), normal.Y(), normal.Z()]
                )
    return {"vertices": vertices, "normals": normals, "indices": indices}


def validate_recipe(recipe):
    if (
        not isinstance(recipe, dict)
        or recipe.get("schema") != 1
        or recipe.get("units") != "mm"
    ):
        raise ValueError("Unsupported reconstruction recipe")
    steps = recipe.get("steps")
    if not isinstance(steps, list) or not 2 <= len(steps) <= 128:
        raise ValueError("Recipe must contain 2–128 steps")

    def bounded(value, depth=0):
        if depth > 16:
            raise ValueError("Recipe is too deeply nested")
        if isinstance(value, (int, float)) and (
            not math.isfinite(value) or abs(value) > 1e7
        ):
            raise ValueError("Recipe contains out-of-range coordinates")
        if isinstance(value, str) and len(value) > 256:
            raise ValueError("Recipe text is too long")
        if isinstance(value, list):
            if len(value) > 2048:
                raise ValueError("Recipe exceeds the geometry limit")
            for child in value:
                bounded(child, depth + 1)
        if isinstance(value, dict):
            for child in value.values():
                bounded(child, depth + 1)

    bounded(recipe)
    for step in steps:
        if not isinstance(step, dict) or step.get("kind") not in (
            "sketch",
            "extrude",
            "cut",
            "revolve",
            "fillet",
            "loft",
            "add",
        ):
            raise ValueError("Unsupported reconstruction operation")
        if not isinstance(step.get("id"), str):
            raise ValueError("Missing step identity")
        if step["kind"] == "sketch" and step.get("profile", {}).get("kind") not in (
            "boundary",
            "axial",
            "polygon",
        ):
            raise ValueError("Unsupported sketch profile")


def verify_preview(recipe, brep):
    # The replay has no access to the target shape, even for sketch construction.
    result, states = replay(recipe)
    source = TopoDS_Shape()
    BinTools.Read_s(source, io.BytesIO(Path(brep).read_bytes()))
    if (
        len(items(source, TopAbs_SOLID)) != 1
        or not BRepCheck_Analyzer(source).IsValid()
    ):
        raise ValueError("Verification requires one valid reference solid")
    proof = compare(source, result)
    if not proof["passed"]:
        return {
            "status": "unverified",
            "proof": proof,
            "error": "The reconstructed solid did not match this STEP part.",
        }
    serial = []
    # Sketch frames reuse the prior solid mesh instead of duplicating it.
    mesh_index = None
    for state in states:
        step = state["step"]
        if step["kind"] != "sketch":
            mesh_index = len(serial)
        serial.append(
            {
                **{k: step[k] for k in ("id", "kind", "label", "dependsOn")},
                "measurements": step.get("measurements", []),
                "volume": state["volume"],
                **mesh(state["shape"] if step["kind"] != "sketch" else None),
                "solidFrame": mesh_index,
                "lines": state["lines"],
            }
        )
    return {
        "status": "verified",
        "steps": serial,
        "proof": proof,
        "reference": mesh(source),
        "bounds": bounds(source),
    }


def main():
    # Paths are supplied by the parent worker host, never taken from the recipe.
    request = json.loads(Path(sys.argv[1]).read_text())
    result = verify_preview(request["recipe"], request["brep"])
    payload = json.dumps(result, separators=(",", ":"), allow_nan=False)
    if len(payload) > 24 * 1024 * 1024:
        raise ValueError("Reconstruction preview exceeds the size limit")
    Path(sys.argv[2]).write_text(payload)


if __name__ == "__main__":
    main()
