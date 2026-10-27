# Migrating model code to OpenCascade 8 (build123d 0.13+)

cadgen 0.8.1 moves from build123d 0.11 on OpenCascade 7.9 to build123d 0.13 on
OpenCascade 8.0 (`cadquery-ocp-novtk` 8.0.x). Models using removed build123d methods need the edits listed below. A model that reaches into `OCP`
directly — a bounding box without tessellation, a shape map, an explorer
downcast, a B-spline built from arrays — may hit one of the renames below.
Most name changes are one-line edits; the missing diagnostic and material fields need native operations instead.

## How it shows up

| Error | Cause |
| --- | --- |
| `ImportError: cannot import name 'TopTools_IndexedMapOfShape' from 'OCP.TopTools'` (or any `TopTools_*`, `TDF_*`, `TColStd_*`, `TColgp_*`, `BOPAlgo_ListOf*` collection) | OCCT 8 replaced the collection typedefs with `NCollection` templates; OCP 8 binds each instantiation once, under `OCP.collections`, named by its template arguments. |
| `AttributeError: type object 'TopoDS' has no attribute 'Edge_s'` (or `Face_s`, `Vertex_s`, `Wire_s`, `Shell_s`, `Solid_s`) | The static downcasts lost their `_s` suffix. |
| `TypeError: Unregistered type : Bnd_Box::Limits` from `box.Get()` | `Bnd_Box.Get()` now returns a struct OCP 8 does not bind. |
| `TypeError: Unregistered type : NCollection_Shared<NCollection_List<BRepCheck_Status>…>` from `BRepCheck_Result.Status()` | OCP 8 binds no list of `BRepCheck_Status`; read one status at a time from the per-type checkers. |

## The renames

| OpenCascade 7.9 | OpenCascade 8 |
| --- | --- |
| `from OCP.TopTools import TopTools_IndexedMapOfShape` | `from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher` |
| `from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape` | `from OCP.collections import IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher` |
| `from OCP.TopTools import TopTools_ListOfShape` | `from OCP.collections import List_TopoDS_Shape` |
| `from OCP.TDF import TDF_LabelSequence` | `from OCP.collections import Sequence_TDF_Label` |
| `from OCP.TColStd import TColStd_Array1OfInteger` | `from OCP.collections import Array1_int` |
| `from OCP.TColStd import TColStd_Array1OfReal` | `from OCP.collections import Array1_double` |
| `from OCP.TColStd import TColStd_Array2OfReal` | `from OCP.collections import Array2_double` |
| `from OCP.TColStd import TColStd_HArray1OfReal` | `from OCP.collections import HArray1_double` |
| `from OCP.TColgp import TColgp_Array1OfPnt` / `TColgp_Array1OfPnt2d` / `TColgp_Array2OfPnt` | `from OCP.collections import Array1_gp_Pnt` / `Array1_gp_Pnt2d` / `Array2_gp_Pnt` |
| `from OCP.TColgp import TColgp_HArray1OfPnt` | `from OCP.collections import HArray1_gp_Pnt` |
| `from OCP.BOPAlgo import BOPAlgo_ListOfCheckResult` | `from OCP.collections import List_BOPAlgo_CheckResult` |
| `PCDM_ReaderFilter.AppendMode_Overwrite` | `PCDM_ReaderFilter.AppendMode_e.AppendMode_Overwrite` |
| `TopoDS.Edge_s(shape)` (and `Face_s`, `Vertex_s`, `Wire_s`, `Shell_s`, `Solid_s`) | `TopoDS.Edge(shape)` (and `Face`, `Vertex`, `Wire`, `Shell`, `Solid`) |
| `xmin, ymin, zmin, xmax, ymax, zmax = box.Get()` | `lo, hi = box.CornerMin(), box.CornerMax()` then `lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()` |
| `for status in result.Status()` on a `BRepCheck_Result` | `BRepCheck_Shell(shell).Closed()`, `.Orientation()`; `BRepCheck_Face(face).IntersectWires()`, `.ClassifyWires()`, `.OrientationOfWires()`; `BRepCheck_Wire(wire).Closed()` — one `BRepCheck_Status` each |

The constructors and methods of the renamed collections are unchanged
(`Array1_double(1, n)`, `.SetValue(i, v)`, `.Extent()`, `.FindKey(i)`,
`.FindFromIndex(i)`); the import and each use take the new name.

Prefer the build123d API where it covers the job: `shape.bounding_box()` for
extents when tessellation is acceptable, `shape.faces()`/`edges()` for
enumeration, `Face.make_surface_from_array_of_points` for surfaces. A model
that reaches into OCP for a reason (an exact bounding box without
tessellation, an ordinal-stable shape map) keeps doing so with the spellings
above.

## build123d 0.11 → 0.13

Independent of the kernel, build123d 0.12 removed its deprecated API:
`Vector.to_tuple()` → `tuple(vector)`; `Face.make_plane()` → an unlimited face
is `Face(BRepBuilderAPI_MakeFace(plane.wrapped).Face())`; `Location.to_tuple`,
`Location.to_axis`, `Axis.to_plane`, `Edge.to_axis`, `Edge.to_wire`,
`Wire.to_wire`, `Face.to_arcs` and `Shape.relocate` are gone, and the centre
arcs take `arc_size` in place of `end_angle`/`angular_direction`. `Vertex.X/Y/Z`
read the native point live rather than the coordinates given at construction.


build123d 0.13 adds a `Shape.material` property and shape provenance. cadgen still accepts
its own `Material` on `.material`, with explicit colour taking precedence in either assignment
order. Native build123d materials retain their native property behavior. Custom shape copying
must retain `topo_path` and `_history` by reference, as build123d's own `__deepcopy__` does;
the history contains kernel handles that cannot be pickled.

OCP 8.0.1 also leaves `XCAFDoc_VisMaterialPBR.EmissiveFactor` unbound. To set it, put emission
in `XCAFDoc_VisMaterialCommon.EmissiveColor`, call `ConvertToPbrMaterial()`, then set the other
PBR fields. To read it, use `ConvertToCommonMaterial().EmissiveColor`. cadgen uses these
native conversions for XBF and GLB materials. The scalar topology checkers name fewer
faults than the unavailable status list; an invalid shape with no accessible diagnostic
remains an error, never a valid result.
