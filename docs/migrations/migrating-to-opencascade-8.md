# Migrating model code to OpenCascade 8 (build123d 0.13+)

cadgen moves from build123d 0.11 on OpenCascade 7.9 to build123d 0.13 on
OpenCascade 8.0 (`cadquery-ocp-novtk` 8.0.x). A model that only uses the
`cadgen` and `build123d` APIs needs nothing. A model that reaches into `OCP`
directly — a bounding box without tessellation, a shape map, an explorer
downcast, a B-spline built from arrays — may hit one of the renames below.
Every one of them is a one-line edit, and the error names the old spelling.

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
| `TopoDS.Edge_s(shape)` (and `Face_s`, `Vertex_s`, `Wire_s`, `Shell_s`, `Solid_s`) | `TopoDS.Edge(shape)` (and `Face`, `Vertex`, `Wire`, `Shell`, `Solid`) |
| `xmin, ymin, zmin, xmax, ymax, zmax = box.Get()` | `lo, hi = box.CornerMin(), box.CornerMax()` then `lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()` |
| `for status in result.Status()` on a `BRepCheck_Result` | `BRepCheck_Shell(shell).Closed()`, `.Orientation()`; `BRepCheck_Face(face).IntersectWires()`, `.ClassifyWires()`, `.OrientationOfWires()`; `BRepCheck_Wire(wire).Closed()` — one `BRepCheck_Status` each |

The constructors and methods of the renamed collections are unchanged
(`Array1_double(1, n)`, `.SetValue(i, v)`, `.Extent()`, `.FindKey(i)`,
`.FindFromIndex(i)`); only the import line moves. Keep the old name as an
alias on the import (`… as TColStd_Array1OfReal`) if the rest of the file
should read as before.

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
