# Exports

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

## Viewer exports

The browser's Export action writes the displayed document as its code built it,
through `export/viewer.py` and the same worker writer as `cad <type> export`. Its source is the
displayed document and revision, nothing else (`viewer.exports.specification`: `{doc,
revision}`); no part, no pose, and nothing of the view -- selection, visibility, Clip, Explode,
Preview -- is an input. A posed or partial file is a function in the model's code.

- **A file the engine serves** (a STEP or an xbf) is read where a file's export runs, at the
  version shown: its `mtime_ns-size`, checked again in the worker before anything is written.
- **A held model** (by its id) is read from the worker that holds it, or from the whole
  document the server took when that worker went (**Document lifetime**), at the revision shown
  and its structure's digest; it is never built again, and one no longer held is refused.
- **A mesh file** (GLB, STL, 3MF) is named by its path at the bytes shown (the catalog's hash of
  them), checked before the job and, by its `mtime_ns-size`, again in the worker.

The page offers what the file's kind writes, and nothing is inspected first: an engine document
(a STEP, an xbf, a held model) as STEP, STL, 3MF, GLB and xbf. An opened XBF file's XBF
download returns its original bytes (`original`), including an `xbf/8` file converted in
memory for viewing. Use
`cad xbf export old.xbf upgraded.xbf` to save that conversion to a different path
(**Document compatibility**). DXF is offered where the page draws it flat on z=0; a mesh
file offers the other two mesh kinds and nothing else. A KiCad board offers KiCad's files of it, each `cad kicad_pcb export
--to <kind>` (Gerbers, Drill, Position, BOM, STEP, GLB, ODB++, IPC-2581, PDF, DXF), run by the job on its
own thread in the environment of `cad[kicad]` (made on first need), from the board at the bytes shown
(the catalog's hash, checked before; its `mtime_ns-size`, after): one file downloads as it is, a folder
of them (the Gerbers, the drill files, the PDF's two pages) as `<board>-<kind>.zip`. A job the writer refuses (a DXF
whose drawing checks fail) fails with its reason. A changed source is refused, saying to open Export again. There is no source bundle in
this interface.

The enclosing distribution owns the HTTP queue, the browser download and temporary
artifact lifetime; the library's engine owns revision validation and
translation only. One explicit job names one temporary output, with no intermediate
XBF, no source and no registry (law 2). Cancellation takes effect between worker operations, discarding an in-flight
result without killing a worker shared with another caller.

## Translation formats

The xbf is the model's result; STEP, GLB, STL, 3MF and DXF are exports of a document, and an
xbf can be one too. One writer, `export.translate(document, kind, path)`,
writes every one, whether a decorator declares the file or `cad <type> export` asks for it: the
same document writes the same bytes. The file holds what the code built. Every file is written beside its
target and moved over it, and only when its bytes change (`atomic_replace.put`): a target that
holds them already is left as it is (`cad <type> export` says `unchanged`). In a folder that takes no
new file (read-only), the bytes are made aside and compared, so an unchanged file passes, and a
changed or new one fails in one line naming the folder and its mode.

- **Sources are documents**: an `.xbf` or a `.step` (read into a document first), or a
  document's id (written from what the engine holds of it -- its worker's document, or the whole
  document the server took from the worker before it went (**Document lifetime**) -- byte for byte
  what it would write however the script has changed since, and nothing is built); from Python, a
  `Model` (called first, as the program's own call of it is: taken from its key or the engine's
  cache, or replayed, when nothing changed; then exported by its handle) too. An xbf is written from a
  STEP. An ordinary current-format xbf is not written from another xbf, which already is the
  document. A loaded `xbf/8` converted in memory is the exception: export to a different XBF
  path serializes the complete upgraded XCAF document atomically; the source path is refused
  (**Document compatibility**). Several destinations read the document
  once, and every destination is checked before any is written (`export.prepare`, then
  `Prepared.land`, `worker._export`): a kind that can refuse only once it has drawn its file -- a DXF
  (a 3D document, an edge off the plane, a layer name, the drawing checks), a GLB (a motion that does
  not settle), an MJCF or a URDF (a description that does not describe) -- is drawn then, its bytes
  held and written after, never drawn twice. So a refused export (exit 2) writes no file of its
  destinations, nor their folder. A failure only writing can meet (the disk, OCCT's STEP writer) fails
  once some are written: the earlier files stay, and the error says which were written and which not
  (`export.ExportIncomplete`, told by its cause's type), an export that failed (exit 1), never a
  refusal. An export
  runs in the worker that built the document while the file is as it left it, else in the
  daemon's documents worker, which reads it.
- **A mesh file is a source of the other mesh kinds**: `cad stl export part.stl part.3mf`, any
  pair of GLB, STL and 3MF either way. It is read as a document of its own kind
  (`export/mesh_file.py`): triangles, with the parts, names, colours and placements its format
  carries, each part's mesh the file's own (never meshed again, never cached); the GLB, STL and
  3MF writers write it as any document. It runs where a file's export runs (the daemon's
  documents worker; in this process with `daemon=False`) and loads no CAD kernel: its readers
  are numpy and the standard library (a GLB through `formats/gltf.py`, not OCCT's reader). A mesh
  has no B-rep, so no xbf, STEP or DXF is made from one (`part.stl is a mesh: it has no B-rep, and
  no STEP export is made from one`), and a mesh file is not written from one of its own kind.
  What the destination cannot hold is left out, as a CAD program's Save As does, and nothing
  warns of it:

  | from \ to | STL | GLB | 3MF |
  | --- | --- | --- | --- |
  | **STL** | -- | one part, its file's name; the viewer's normals (creased at 30 degrees) | one object, welded |
  | **GLB** | every placed triangle, one soup | -- | a part per mesh, a build item per mesh node; colours, names, metallic and roughness; textures, the materials' other extensions, normals and animations are dropped |
  | **3MF** | every placed triangle, one soup | an object a mesh, a build item a node; colours and display properties as materials; the viewer's normals | -- |

  Units are the viewer's for each format: an STL's numbers are millimetres (it says no unit; the
  viewer draws them as they are); a GLB's are glTF's metres, Y up, read as Z-up millimetres
  (times 1000) unless a node declares `extras.cadUpAxis: "z"`, and written in the document's
  millimetres under a root node turning them back; a 3MF's are in its `unit` (millimeter when
  absent; one the 3MF specification does not define is refused, as the viewer refuses it), made
  millimetres, and written `unit="millimeter"`. So a 10 mm cube is 10 mm in each, and 0.01 in a
  GLB's numbers. A part with no colour of its own is written in the writers' default grey, as a
  document's is.
- **STEP** (AP242, `export/step.py`): the assembly with instance and product names, colours per
  part and per painted face, material names and densities, element names on face, edge and
  vertex sub-shape labels. Read back through the engine's own reader, the instance tree, every
  name (on the same elements: the reader numbers edges and vertices in its own order), colours
  and materials' names and densities are the xbf's. Standard STEP surface rendering records
  carry an approximate diffuse/specular finish and transparency for parts and material-painted
  faces. Import converts that standard specular/gloss appearance back to metallic/roughness;
  it is an approximation based on the [Khronos specular/gloss conversion](https://github.com/KhronosGroup/glTF/tree/main/extensions/2.0/Archived/KHR_materials_pbrSpecularGlossiness), especially for third-party Phong materials. STEP does not retain the
  original advanced PBR properties, textures, emission, physical fields beyond name and density,
  mechanism, configurations, model key or provenance. Use XBF or GLB for full PBR looks. The writer's run-dependent choices are settled: the
  header's time stamp is `step.WRITTEN_STAMP` (the xbf's date); the colour presentations, which
  it keeps in a map keyed by shape, are put in the order of the shapes they style; the assembly
  occurrences, which it numbers on from every STEP the process wrote, are numbered from 1; and
  each record so renumbered is put on one line, as the writer broke it where its old numbers
  fell. A prototype is one product, and each of its usages a `NEXT_ASSEMBLY_USAGE_OCCURRENCE` of
  its own with the usage's name, placement and instance colour; OCCT's writer finds a usage by
  its shape and placement datum, so a prototype placed alike under two parents (a left and a
  right arm's shared parts) is placed apart while it is written and set back after. A part of
  several solids is styled solid by solid, as AP242 styles representation items: the engine's
  readers take one colour over every face as the part's. A build's document is written as its
  xbf reads back (written and read once, in memory), since a read moves placements by a last
  bit. So the same document is the same STEP in any process on any day, a build's or a cold
  read's of its xbf.
- **GLB**: one mesh per prototype (indexed in 16 bits up to 65,535 vertices, in 32 past them), the
  document's tree as nodes under one root named by the document, which turns its Z-up millimetres
  into glTF's Y-up metres: a node per sub-assembly, its components under it, each placed in its
  parent's frame (a node at its parent's place has no matrix), so Blender and any glTF reader show
  the sub-assemblies and every part stands where the document places it; every node named by its
  path below the root (`board/D44/housing`, its sub-assemblies `board` and `board/D44`), unique
  where the document's own paths are (two sub-assemblies both labelled `leg` give two `leg` nodes),
  and a part's name the one a flat file of an earlier release gave it (that file placed every part
  in the world under the root; a reader now walks the tree for a part's place, which is the same); a
  PBR material per
  look (a paint is a primitive of its own) with an extension for each part of the look past
  metallic-roughness (`KHR_materials_ior`, `_transmission`, `_volume`, `_clearcoat`,
  `_anisotropy`, `_emissive_strength`; a transmissive look `OPAQUE` at alpha 1 unless its PBR
  `opacity` fades it; **Materials**), every motion of the document an
  animation of the same name (below), and every `animation()` of its code, from a build or from
  the record an xbf carries (**Animations**); **3MF**: an object per prototype, a build item per
  placement, looks through the materials extension (base materials, `pbmetallic` display
  properties, painted triangles naming their own); **STL**: binary, every placed triangle.
  Their meshes are the process's one mesh cache's (`serve.MESHES`), the viewer's: a part the
  build meshed for the viewer is not meshed again for a GLB, nor the other way round. A GLB, an STL
  or a 3MF at an export's own tolerance or angle (**Mesh**) is meshed again for that file and says
  so: the GLB's `asset.extras.cad` holds `meshedWithin` (mm) and `angle` (degrees), each only where
  the export gave it, the STL's header ends `(meshed within 0.01 mm and 5 degrees)`, the 3MF's
  `Description` metadata reads `Meshed to within 0.01 mm and 5 degrees`. A GLB's `asset.generator`
  is `cad`. The file holds no document id or revision: those differ by source, and a GLB is the same
  bytes from an xbf, a held document or the build's worker.
- **DXF** (`export/dxf.py`): a planar document -- a model whose body returns a sketch, a face,
  wires or edges -- drawn by build123d's own `ExportDXF` (ezdxf), in millimetres, each edge
  where the document places it one entity, so a curve stays an ARC, CIRCLE, ELLIPSE or SPLINE.
  A document placing one part is the layer `CUT`; any other is a layer per part, named by its
  occurrence's name (`cut.label, bend.label = "CUT", "BEND"` in the compound returned), parts
  of one name sharing it; a layer of several shapes is one part of them all
  (`bd.Compound([a, b], label="ENGRAVE")`). A solid is refused (`tom.xbf is 3D`), and so is an edge with a point
  off z=0, by its element name. Layers are written in name order and edges in an order of
  their content (curve kind, sampled points, length), never the kernel's traversal, and
  ezdxf's provenance is pinned and its classes sorted: the same geometry is the same bytes in
  any process on any day, so a declared DXF is the bytes `cad xbf export flat.xbf flat.dxf`
  writes. The drawing checks run on the document before it is written -- units set, no
  zero-length or duplicate entity, every cut profile closed, something drawn; open geometry
  only on a layer its name's whole tokens make a bend, engrave or reference one -- and an
  error refuses the file, saying which. `export.dxf.validate_dxf_file` runs them on any DXF.
- **No option selects a part or a state**: a file of one part is that part's own
  model (a function returning it), and a posed file a model returning the assembly posed
  (`posed(arm(), "folded")`, `cad.build123d`). Snapshot's `--pose` is the picture's: ad
  hoc, never cached, never declared.

**Motions in a GLB.** Each motion (**Configuration sequences**) is baked into a glTF animation of its name:
translation and rotation channels for each node it moves, baked CUBICSPLINE over one set of
key times (`export/motion.py`) and written LINEAR (**GLB keys**). A sub-assembly whose every part is one
link's is keyed on its own node, so it moves as one and its parts stand still in it; every other moving
part on its own node; the topmost such node of each branch (`motion.chosen`). An `animation()` keys
alike: a sub-assembly whose every part the same references and link move, none of them scaled (a scale
is about a part's own origin), on its node. A node's keys are in its parent's frame, worked out from
the bake's place in the document's (`glb._local_rows`: the parent stands still in that clip, and the
map is linear, so the curve between two keys is the parent's of the bake's), so at every time every
part is where the bake puts it. The keys start at the motion's waypoints and the halfway point
between each two; at a key every moving placement is where forward kinematics through the
mechanism (its couplings included) puts it,
its in- and out-tangents the one-sided derivatives there, so a step's speed may jump at a
waypoint. A step is halved while at any eighth of it the Hermite strays from the true forward
kinematics by more than 1e-3 of the model's size (the diagonal of what the GLB places) in a
placement's origin or 1e-3 radian in its rotation, at most 4,097 keys. A moved node
stands by translation and rotation, every other by its matrix; nodes whose keys are the
same bytes (the parts of one link under one parent, each its own node) share one sampler, so a link's
motion is written once however many parts it carries; the animation's
`extras.cad` holds the duration and `"kind": "motion"` (an earlier release's file calls it
`extras.cadgen`, the duration alone; nothing the engine or the viewer runs reads either, a player
taking a clip's length from its keys). A clip is the motion once, and a player repeats it. STEP,
STL and 3MF ignore motions, and neither `export` nor `@glb` takes an argument for them. On the
corpus's motorbike (2,053 mm across, so a 2.05 mm tolerance), `steer` (a ±20° sweep of the head
tube and back over 4 s) bakes to 5 keys on 15 placements, within 1.26 mm and 2.1e-4 rad of
forward kinematics at eight points inside every step.

**GLB keys.** A bake keys a track where its curve needs it: a motion's every placement on the keys
its hardest one needs, an animation's eased channel CUBICSPLINE, three values a key. The GLB
writes each track that is not STEP as LINEAR keys, the fewest within `KEY_MM` (0.1 mm) and
`KEY_DEGREES` (0.1°) of the bake (`export/keys.py`), constants rather than options: a
tenth of a millimetre is under a pixel of a 1 m model filling a 4K screen. The bake's curve is
sampled densely (a CUBICSPLINE step as often as keeps its Hermite within 5% of the tolerance of
the chord between two samples, so a line that holds the samples holds the curve); from each kept
key the farthest candidate (a bake key, or a sample of a step its own two keys' line cannot hold)
whose line, lerped or for a rotation slerped as glTF interpolates LINEAR, holds every sample it
spans is kept, with the first and last keys, both keys of a jump (two keys under a millionth of
the clip apart) and two rotation keys never more than 120 degrees apart. A scale is held to the
millimetres its part moves (its change times the part's farthest point from its origin). A STEP
track (a hide) is written as baked, its jumps at the times it names. Distinct tracks are worked
out once, the same document gives the same bytes, and on the corpus's GLBs, their bakes rewritten
so and read at 240 Hz, every track stays within 0.0995 mm and 0.0997° of its bake while the animation keys shrink to 12-24% of
the bake's: juno 108.7 MB to 6.9, tom 98.5 to 18.7, w16 83.2 to 38.5, radial 78.9 to 44.2 (with the
samplers shared, above). A sparsely keyed eased bake (a small model's) can take more LINEAR keys
than it had CUBICSPLINE ones, each a third the bytes.

**File decorators require `out`.** `@xbf("XBF/arm.xbf")` declares the native document;
`@step("arm.step")`, `@glb("arm.glb")`, `@stl("arm.stl")`, `@threemf("arm.3mf")`
and `@dxf("arm.dxf")` declare translations. Relative paths are relative to the script.
There is no default decorator path. Beyond its path and optional `name=`, no file decorator
takes anything else: a model's material, colours, joints, the pose its joints connect its parts at, its
configurations, its motions and its animations are written in its body. Every declared file shows the model as
built: where its joints' `connect_to` placed the parts. A model that wants a second pose on
every build is a second model function with other joint values. A model with no `@xbf` writes
its derived files and nothing else.

**Every model that runs writes its files** (law 10). A child model -- one another model's body
calls, in its file or another -- writes the files it declares after its target's are written,
once per build, from its own document: the result its body returned, before its caller placed
or labelled it, its closure the one a build of its own script makes (its folder, the modules its
script imports). So its xbf is the one its own build writes, byte for byte, and the engine's cache
keeps its document as any (a later build of it takes that, **Build closure**); a file whose bytes are
unchanged is kept. A declared file is an export appended to the run: translated from the document
every time the model runs or is taken -- an xbf from the document's own bytes, serialised before any
export meshes its shapes -- compared with the file, and written only where it differs or is missing
(`atomic_replace.put`, the one writer `cad <type> export` writes its files with too), nothing remembered
of what was written: a declared file is what the code that last ran makes, whichever model ran it. A child called
twice is one model, written once; a child that is also a target of the build writes as the
target; a child run inside a replayed body writes as one its caller ran; one that ran before its
caller raised writes all the same. A child writes what its decorators declare. A model taken from its key ran nothing,
nor did its children: it writes its own declared files, and a child's are written when the child
itself runs or is taken. The target's report holds each child's under its identity
(`child_models`: its files, parts and timings), and a
child whose file cannot be written fails the build. A part is written free
(`document.unchecked`): OCCT marks a shape put in a compound as no longer free, which would
make a child's part, placed in its caller's assembly, other bytes than its own build's.

The xbf is saved first, then each derived file. Nothing of them is sent to a page: one serving
a declared file follows that file's bytes (**Document lifetime**).

**Functions** (`api`, behind each type's `cad.<type>.export`, `.snapshot` and `.inspect`; `serve`,
`status`, `stop`, `delete` and `server` only the CLI calls): one per command, each through the daemon. No function builds source text;
a shape made elsewhere is handed over, never built (`model(shape, name=...)`, **Shapes handed over**).
`export(source, *destinations)` a list of `Written`; `check(source, check)` a manufacturing check's report,
measured in the engine's checks processes (**Document types and integrations**); `snapshot(source, out, ...)` a `Drawn`, and `snapshot(job=PACKET, ...)` (with `source` in place of the packet's input, as `--job PACKET SRC`) a list of them, one verb with two input shapes, anything else refused as Python refuses a call; `inspect(doc)` what
the document holds and its build closure (`query="summary"`; `"structure"` the same with nothing measured, and with no
query the closure alone), `inspect(doc, ref)` an element's facts. Each takes a handle (what a model call
returns), a document id or a file path; `export` and `snapshot` take the decorated function too,
building it first. A type's function takes its own sources alone: `cad.model.*` a handle, an id or a
decorated function, every other type's a file of it (`cad.xbf.export("arm.xbf", ...)`). A handle exports and draws its document the same way (`.export()`,
`.snapshot()`); a `Model`'s `.build(verify=, profile=, daemon=)` is the debug seam, a `Report`: it
and its children, as declared.
