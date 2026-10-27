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
is `Face(BRepBuilderAPI_MakeFace(plane.wrapped).Face())`; `Location.to_tuple()` →
`(tuple(location.position), tuple(location.orientation))`;
`Location.to_axis`, `Axis.to_plane`, `Edge.to_axis`, `Edge.to_wire`,
`Wire.to_wire`, `Face.to_arcs` and `Shape.relocate` are gone, and the centre
arcs take `arc_size` in place of `end_angle`/`angular_direction`. `Vertex.X/Y/Z`
read the native point live rather than the coordinates given at construction.


build123d 0.13 adds a native `Shape.material` property and shape provenance.
Custom shape copying must retain `topo_path` and `_history` by reference, as
build123d's own `__deepcopy__` does; the history contains kernel handles that
cannot be pickled.

## Native materials

Use build123d's native `bd_materials` library. Its catalogue factories return
`FinishedMaterial` objects, with physical properties in `.material` and native
`threejs_materials.PbrProperties` in `.pbr`:

```python
from bd_materials import metals
from cadgen import paint

aluminum = metals.aluminum(metals.Alu.G6061_T6)
aluminum.pbr = aluminum.pbr.override(
    roughness=0.35, metalness=0.9, clearcoat=0.2)
housing.material = aluminum
housing.color = "#606b78"
paint(housing, housing.faces().sort_by(bd.Axis.Z)[-1], metals.copper())
```

Prepare the look with `PbrProperties.override`, assigning its result back to `.pbr`.
Set the material after geometry, then set any explicit colour: native material
assignment also sets shape colour. For transmission, it infers a preview alpha
(`transmission=1` gives alpha `0.3`), even when PBR `opacity=1`. To keep an opaque base
colour with physical transmission, assign an opaque `housing.color` after its material,
as above.

PBR controls include `metalness`, `roughness`, `ior`, `clearcoat`,
`clearcoat_roughness`, `anisotropy`, `anisotropy_rotation` (radians), `transmission`,
`attenuation_color`, `attenuation_distance` (metres), `emissive`, `emissive_intensity`,
and `opacity`. Base-colour floats are sRGB ratios; emission and attenuation floats
are linear RGB. Hex strings preserve the intended picked colour without that ambiguity.

Native family factories such as `metals.custom_metal` create custom physics. Density is
a single value in kg/m³. Mechanical properties are ranges, with modulus in GPa and
strengths in MPa; a custom factory also accepts a number as an exact range. Native
`shape.mass()` and the physical material's `mass(volume_mm3)` return grams by default;
`cadgen inspect` reports kilograms. For the full authoring example, see
[materials in the 0.7-to-0.8 guide](migrating-0.7-to-0.8.md#6-move-materials-into-the-body-make-colours-hex).

XBF keeps native physics and the complete resolved PBR data. Reading it returns a native
finished material with that look, rather than recreating its finish recipe. Scalar
clearcoat, anisotropy, transmission, attenuation and emission survive viewer and GLB paths;
OCCT snapshots retain their documented approximations. Native texture maps survive XBF,
but the viewer, GLB export and snapshots explicitly refuse them until UV mapping is
supported.

The XBF format is `xbf/9`; `bd_materials` and `threejs_materials` versions join the build
key. The engine reads `xbf/8` and `xbf/9`. Opening an `xbf/8` file or cached snapshot
converts its material metadata in memory, without source code or a rebuild. Original
source and cache bytes, cache records and revisions, and the build closure and toolchain
provenance stay unchanged; a separate migration record identifies the conversion.

An explicit `cadgen export saved-v8.xbf upgraded-v9.xbf` saves the complete upgraded XCAF
document atomically to a different path. Export back over the source path is refused.
Exporting a cached document by id to XBF also saves its upgraded form. The viewer's
original-file download keeps the original XBF bytes, and ordinary current-format
XBF-to-XBF translation remains refused. Unsupported formats or failed conversions preserve
original bytes and cache records and give a clear error. Explicitly running model source
still checks its build key and rebuilds normally when it differs. See the
[persisted-document policy](../../packages/cadgen/README.md#the-design-laws).

OCP 8.0.1 also leaves `XCAFDoc_VisMaterialPBR.EmissiveFactor` unbound. To set it, put emission
in `XCAFDoc_VisMaterialCommon.EmissiveColor`, call `ConvertToPbrMaterial()`, then set the other
PBR fields. To read it, use `ConvertToCommonMaterial().EmissiveColor`. cadgen uses these
native conversions for XBF and GLB materials. The scalar topology checkers name fewer
faults than the unavailable status list; an invalid shape with no accessible diagnostic
remains an error, never a valid result.

## Export changes and known kernel issues

Regenerating a STEP file with OCP 8 can rewrite much of its text even when its
geometry is unchanged. Compare dimensions, volume, solid count and rendered
geometry; a textual STEP diff alone does not establish a geometry change.
This was observed in the [original migration review](https://github.com/earthtojake/text-to-cad/pull/628#issuecomment-6190559383).

Two OCP 8.0.1 geometry regressions were independently reproduced on macOS arm64:

- [`BRepBndLib.AddOptimal_s` can underbound a B-spline shape](https://github.com/Open-Cascade-SAS/OCCT/issues/1604).
  the native operation measures a 60 mm loft span as 59.912 mm. cadgen now
  measures free-form bounds using native distances to six exterior support
  planes, without tessellating or changing the geometry. The original loft
  regression passes unchanged, as do analytical bounds checks for translated
  and rotated ellipsoids through part inspection and face picking. Direct
  callers of OCP's `AddOptimal_s` still encounter the upstream defect.
- [A sweep with a binormal guide can distort the profile](https://github.com/gumyr/build123d/issues/1474).
  A 6 × 6 rectangle swept 30 mm along a straight line, with a parallel guide,
  has volume 1,080 mm³ on the released 0.8.0 dependencies. On OCP 8.0.1 it has
  volume 1,072.310 mm³ and a 6.331 mm width, while still reporting valid.
  Shape validity alone does not establish dimensional correctness.

The guided-sweep defect remains an upstream limitation in the published OCP 8.0.1
wheels. The current model corpus uses no auxiliary-guide sweeps. An experimental kernel
fix is not shipping in this release, which retains build123d 0.13/OCP 8. For a model that
uses a guide, check dimensions and volume against the intended profile; shape validity
alone does not establish correctness.

The separate [F1 airbox loft Boolean instability](https://github.com/Open-Cascade-SAS/OCCT/issues/1643)
also occurs on 7.9 and is not a newly introduced OCP 8 regression. The sample
retains its existing guarded fuzzy union: check that the result contains at
least approximately the larger input volume, then use the authored fallback
when it does not. This is a sample-specific guard, not a general Boolean repair.
