# Mesh

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

One tolerance for everything the engine holds and draws, configurable nowhere: a linear deflection of
`(Lx + Ly + Lz) / 300 * 0.25` of the part's own bounding box (0.25 %, half
FreeCAD's default Deviation of 0.5 %, so a large arc's outline is not drawn
in corners) and FreeCAD's angular deflection of 28.5 degrees, both absolute,
with the kernel's face parallelism on, through `IMeshTools_Parameters` with
`EnableControlSurfaceDeflectionAllSurfaces` set (analytic faces held to the
deflection; every other knob stays at its default). `BRepMesh_IncrementalMesh`
is used as it is: no check before it, no second pass, no finer retry, no other
tessellator. A face it leaves without triangles is left out and named: the
part's structure lists it under `unmeshed` (ordinals) with a verdict under
`unmeshedCheck` -- the mesher's own status first (`GetStatusFlags` of the
part's mesh), then `BRepCheck_Analyzer`'s on that face ("BRepMesh:
SelfIntersectingWire; BRepCheck: valid") -- and the rest of the part is drawn.
A part is meshed from its binary shape bytes read into a fresh shape, so its
mesh is a function of those bytes alone. Those are its read-back bytes, the
bytes its document holds of it. A build's live part is written and read once to
get them, as saving its document does. A part read from a document (the served
document, `cad <type> export`) is written as it was read. So a worker, the
server and an export all mesh one geometry key from the same bytes.
The geometry key is the digest of those bytes (`document.geometry_key`), so a
reader makes a part's key again from the part it read, and takes the key the file
names for it only when the two agree (`document.Loaded`). Where one part naming a
key does not make it, the parts naming it are keyed apart, by the key and their
own keys together (a placement's look kept apart is such a copy, and keeps one key
with its first). The daemon's caches are shared by every document it serves, so a
file never lends its part another document's key, and never its mesh or facts.

A GLB, an STL or a 3MF export may give its own tolerance instead: `cad model export ID part.stl
--tolerance 0.01`, `export(doc, "part.3mf", tolerance=0.01)`, `@glb("part.glb", tolerance=0.01)`. It is
an absolute ceiling on the linear deflection in millimetres, at least 0.001 (`export.MIN_TOLERANCE`),
the angle unchanged: for a print whose fits are finer than a quarter per cent of the part (an 85 mm
tube is 47 segments round at the engine's tolerance, its facets 0.095 mm deep; 205 and 0.005 mm at
0.01), or a picture whose curves are. Each part is meshed at the finer of its own deflection and the ceiling, so a tolerance never
makes a part coarser than the viewer draws it -- most of a robot's parts are under 60 mm across,
where a quarter per cent is already finer than 0.05 mm, and meshed coarser their faces were seen to
lose triangles. An explicit tolerance also sets `ForceFaceDeflection`, so loose edge tolerances do
not override the requested face deflection. It is meshed for that file alone and never cached, so the
viewer, the snapshot and every other export keep the engine's mesh; the file says what it was meshed to
(**Translation formats**). The same export may give an angle beside it or alone (`--angle 5`, `angle=5`,
on the decorators too): a ceiling on the angular deflection in degrees, from 1 to 28.5
(`export.MIN_ANGLE`, `export.MAX_ANGLE`), so a file is never coarser than the viewer's mesh, for small
radii a linear deflection never reaches (a cylinder of 10 mm radius and 40 long is 152 triangles at
the engine's pair and 572 at 5 degrees). It is the mesher's own angle, set on each edge's polygon: a doubly curved face's
triangles can stand a little further apart (a sphere's normals up to 7 degrees at 5). Each is
refused by name for any other kind and for a mesh file's source, whose triangles are the file's. Since
which faces the mesher leaves without triangles changes with either, the export names each part it
left faces of, and how many. The cost is the triangles: a tenth of the deflection is about three times the
segments round a curve and ten times the triangles of a doubly curved face, on the large parts
alone. Measured on 2026-11-03 on a 600-part robot arm (a 439 MB STEP), a whole-assembly STL at
0.01 mm was 1.33 million triangles against 1.02 million, 66 MB against 51, in about the same 30 s
and 0.8 GB.

Every edge has a class read from the B-rep: 1 feature (two faces at an angle),
2 tangent (two faces meeting at least G1), 3 seam (a face closing on itself),
5 boundary (one face), 6 non-manifold (more than two). Degenerate edges are left
out.

Inspection and the build delta measure bounds without tessellation or changing the shape.
For free-form faces, `kernel.bounds.optimal_box` measures native distances from the boundary
to six finite support planes outside the kernel's conservative box. It copies topology before
collecting faces and loose edges/vertices, so neither solid containment nor input flags affect
the measurement. This avoids OCCT 8's spline-grid
refinement missing symmetric extrema (`BRepBndLib.AddOptimal`); analytic surfaces and
shapes without faces still use `AddOptimal`. A failed distance measurement is an error.

What the kernel measures of an element is asked for, never extracted ahead:
`GET /api/v1/documents/<kind>/<id>/parts/<key>/faces/<ordinal>` (`serve.py`'s
`/api/doc/<id>/part/<key>/face/<ordinal>`, as `cad <type> inspect` asks it through the door) is its
area, centroid, surface type, exact bounding box and `BRepCheck` verdict (and a round face's radii), and
whether the part's tessellation has it (`meshed`: null while the part is not meshed --
an inspection meshes nothing);
`.../edge/<ordinal>` its length, curve type, class, faces and endpoints (and a
circle's radius and sweep); `.../vertex/<ordinal>` its position;
`.../groups` how a pick of one face or edge grows, as a STEP's selector table
says: each face's tangent group (faces joined across tangent edges of one
solid) and each edge's chain (edges that run on through a shared vertex). An element of a model's document also answers `made_by`: the element's name, the feature that made
it (its name's last step), that feature's operation, the function, file and line
of its call, and, for a name that folds its derivation, the derivation spelled
out. It comes from the trace of the worker that built the document, asked over
the worker's pipe (a `where` request, answered by the worker's reading thread,
during a build too) and never from a file: a document served cold, with no live
worker that built it (for example, after a daemon restart), answers
`made_by: null`, and so does an element the served version names otherwise than
that worker's last build. The line is the call's in the run that named the part. A file's
element -- a model's declared xbf among them -- answers no `made_by`: a file names no model,
whichever run wrote it.
`cad xbf inspect DOC REF` serves the document on demand and resolves `REF` (**References**):
an element answers its facts and, of a model's document, `made_by`, with its canonical `ref`, its occurrence's `path`
(`hand/finger.2`), its part, key, kind, ordinal and name, its points (centroid, position,
endpoints, box) placed where that occurrence stands; a part or an assembly answers what it
weighs: each part's volume, measured on its solids (its facts, below), times its material's
density, summed -- `{ref, parts, volume (mm³), mass (kg, null when no part has a material),
unweighed (the parts without one, by path)}`, and for one part its path, material and density. Where
the model declares a mass or point masses (`mass`, `point_mass`), they weigh as its robot description
weighs them (`weights.py`, the description's **Mass** over the engine's volumes, every part measured,
since a declared mass scales its solids together), and `declared` says which is which: `{mass, declared,
computed (kg: the solids below no declared mass, at their densities), masses (each declared node's name,
path and grams), pointMasses (each part's, by name, in grams), scaled (the parts scaled to a declared
mass)}`, or `{mass: null, refused}` in the description's words.
A ref of several selectors answers a list. A ref that names nothing, or several things where
it names one, is refused by name (exit 2). Without a REF it serves the document the same way and
summarises it before its closure (`api._summary`, `query="summary"`): its state (`model_info`'s, with
`cached` when the engine's cache holds it at its revision; `file` for a file's document), its parts,
its bounds (each part's box beside its volume placed where its occurrences stand), its
volume, its materials and their masses (`declared`, as a ref's: as the robot description weighs a
declared mass and point masses), its joints, mechanism states, configuration sequences and
animations (the structure's `animations`: each name and duration), and a model's declared files.
`query="structure"` (`--query structure`) is the same without its bounds, volume and masses, and
measures nothing: the lists alone.

**What an inspection costs.** It meshes nothing: it reads the structure through the engine's door
(`Server.read`), which sends no part to the mesher, where a page's read sends every part not held
yet, as it is about to ask for them all. What it measures of a part as a whole -- its volume, its
solids, how many of them are inside out (`inverted`) and its box in its own frame (`mesh.measured`)
-- are the part's facts, kept by its geometry
key beside its tessellation (`serve.FactCache`), under the same memory budget and evicted after the
tessellations (**Document lifetime**), and written nowhere: a memo of them beside the document or
in the cache folder would be a derived file (law 2), and the cache holds a document's bytes alone.
They are measured once, whichever document or version holds the part, so an edit measures only
the parts whose key it changed. `GET /api/v1/documents/<kind>/<id>/measure` (`?keys=K,...` for some;
the engine's `/api/doc/<id>/volumes`) answers every part's at once, and `.../parts/<key>/volume`
one part's: the parts no one measured yet go to the pool together, in batches of about a megabyte of shape bytes (`serve.FACT_BYTES`: a light document is one
job, a heavy one spread over the pool a page warmed, else over two processes at most,
`serve.FACT_PROCESSES_COLD`, so an inspection with no page open starts no more), each in the pool's
queue for facts, which a free process takes before any mesh waiting (**The engine server and its
workers**). A summary that finds a part's facts missing waits for them: no figure is guessed. Its
`measure` count is the engine's: the door's read of the facts, asked with `progress`, says each
part's as it comes in -- the ones held at once, the rest as the pool answers their batches -- ahead
of its answer. Measuring is lazy: a document is measured when an inspection first asks for its
facts (a summary, a part's or an assembly's ref), and a build of a document no inspection has asked
of reads nothing, measures nothing and starts no pool process. Once one has asked, the document is
an inspected one (`Server.inspected`, in memory: an engine started afresh measures it again at its
next inspection), and each later build of it is read at its new version once the build's worker has
settled (free for half a second with no request waiting for it, `daemon.MEASURE_IDLE`: a program
calling its models one after another sends its next build within milliseconds, so those calls do
not wait on that read), its parts whose geometry key changed measured then, in the facts queue
ahead of meshes (`Server.measure_later`), so the inspection after the edit finds them. The command
parses the ref and places what it names in its own process with no kernel: the element-name grammar
it reads is `refs.ELEMENT_NAME`.
