# The viewer and the snapshot

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

The viewer and its document reads share the daemon's HTTP listener. The page
reads its document's kind's routes (`/api/v1/documents/<kind>/<id>/structure`, `parts/<key>`) and
waits on `/api/v1/documents/<id>/version`; dispatch calls the engine's own reads directly, in process
(`/api/doc/<id>...`, `serve.py`'s, which binds no listener of its own: the engine's reads are served
only through the daemon's).
XBF/STEP loading, the DXF pane's drawing (`drawing_payload.py`) and geometry facts run in child processes. A launcher starts or reuses the
engine's one page, prints its authenticated URL -- a file's page, `/<id>`, for each file it names,
else the home's -- and exits. A library server made without the daemon's listener (a render
process's) binds nothing and is read in process.

**The look.** The regular display modes draw a document as OCCT's PBR raster draws it, one frozen
record (`render/look.py`) that the OCCT prototype (`render/occt.py`, its finishes and light in
`render/finish.py`) draws by too: one white directional key at radiance 4 travelling
(-0.35, 0.55, -1), and one environment lighting every surface at 0.5, the viewer's neutral studio
baked as a 512 x 256 Radiance image beside the record (`render/studio.hdr`); no ambient term, fill,
shadow, exposure or tone curve: the sum is clamped and sRGB-encoded. Every surface answers that
light as OCCT's PBR program does (the record's `brdf`, `occt`): single scattering, Schlick-GGX
geometry, OCCT's split-sum table, the roughness as given, no anisotropy, which the viewer draws in
place of three's own physical model (the bundled `@cad/core`'s `lib/viewer/surfaceBrdf.js`),
its environment prefiltered as OCCT bakes it (`lib/viewer/ggxEnvironment.js`: each roughness the
image convolved with that roughness's GGX lobe, the diffuse light OCCT's nine spherical harmonics
of the irradiance). A part without a material,
and every fill (Parts), wears a plain dielectric finish (roughness 0.5) over its colour, linear,
squared, which keeps the saturated colours of OCCT's old Phong look. A part with a material wears
its finish in Solid and Shaded on both renderers, its colour as authored, reflecting that
environment; the snapshot keeps faces of the same colour but different materials apart for XBF,
STEP, GLB and 3MF. X-ray draws a material in the plain finish. What OCCT's raster has no term for it
approximates (`render/finish.py`): a clear coat eases the base's roughness toward the coat's,
OCCT drops anisotropy, and transmission is opacity over the colour tinted
by the transmission colour.
Edges are unlit in their class's ink, 1 px; X-ray's faces are lit at 0.22 opacity, Hidden line's
are the backdrop's colour. A face that writes depth steps back a hair in the depth test, so the
edges on it win; a see-through one (a translucent part's, X-ray's), which writes none, steps a
hair forward (`render/occt.py`'s `SEE_THROUGH_OFFSET`), so lying on an opaque face it is in front
of it at every pixel, never in shards along the two faces' triangles: the viewer's rule (the
bundled `@cad/core`'s `lib/viewer/surfaceLook.js`). The engine serves the record as
`GET /api/v1/look` and its image as `GET /api/v1/look/environment`; the page reads both once per
engine, beside the document, and the document's scene brings them as its own lighting and surface
rule (the bundled `@cad/core`'s `lib/xbf/xbfLook.js`), which the viewer's viewport and the snapshot
page put up in place of the theme's. Preview is drawn as any file's is.

`cad <type> snapshot` writes PNG images with OCCT, and no video. `--preview` (a job's `"preview": true`,
`snapshot(preview=True)`) draws the viewer's Preview in place of a display mode, by the same raster: the
model in its materials under the viewer's rig (`photographicStudioRig.js`: its key from the same direction
at the same strength, shadowing the model, and the look's `studio.hdr` -- the viewer's room and softboxes --
at full strength as the image-based light), in perspective unless the display says otherwise, in the
viewer's studio (its backdrop sweep, its floor at the model's lowest point, the floor's shadow baked as the
viewer bakes it), and tone-mapped as the viewer tone-maps (three's Neutral: OCCT's raster has no tone
mapping, so the model is drawn alone on black and on white, its cover and colour read from the two, and
what the curve changes laid over the model's pixels -- `occt.Scene._tone`; the studio, drawn in the
viewer's finished colours, is untouched, and a camera under the floor, which sees the model through it,
takes the share of that change the floor lets through). It is not the viewer's picture pixel for pixel, and no browser
draws it: a frame holds no light past 1, so a highlight comes out the tone a full white does; there is no
ambient occlusion and no reflection in the floor; glass is drawn at its preview alpha; and OCCT's baked
reflections read lighter on a polished metal. The first Preview of a document bakes its light (seconds).

`cad <type> snapshot` draws a document as the viewer does. The engine serves and meshes it (the
daemon's meshes, or with `daemon=False` a server of this process), and OCCT draws it from those meshes
(`render/`, below), in the look the viewer resolves for the same display settings. Every snapshot is
light -- a 3D document on the look's flat backdrop (`#f0f4f9`; the shaded studio sweep is Preview's,
drawn only when asked for), a drawing's white paper, a board's and a schematic's light colours --
whatever theme the viewer is in or the view it replays was seen in: a snapshot is a tool for an agent,
and dark is the harder to read, so no flag, tool argument or packet names a theme. A mesh file
passed through a worker's export request still uses its render reader, preserving textures,
feature edges and file units; its export source holds no B-rep to mesh. `--display` takes
a mode (`solid`, `shaded`, `parts`, `xray`, `hidden-line`, `wireframe`), `exploded=A` (the parts
moved apart as the viewer's Explode moves them, by an amount from 0 to 1; with a mode,
`hidden-line,exploded=0.6`), or the display object (a drawing takes none: `mode`, `grid`, `camera`,
`clip`: `{"enabled", "axis", "at", "invert", "partColors"}`,
its `at` in the file's unit as the viewer reads it -- a document's millimetres, a robot's or a GLB's
metres, a 3MF's declared unit (`render/clip.py`); `exploded`: `{"enabled", "amount"}`, 0.5
unless given; `hidden` and `isolated`: lists of part refs, an occurrence's path in the refs
grammar, which every look -- Preview, X-ray, Explode, Clip -- leaves out or alone draws, as the
viewer's hide and isolate do, and which a Quick Edit packet given to `--annotation` carries; a
robot's parts are named by the viewer's visual ids too, `link:v1` (`link:v1/object/0` one object of
it); a ref that names nothing is refused by name), each key and value checked as the viewer checks its
display settings (`clip.axis` is `x`, `y` or `z`, `clip.at` a number) and anything else refused by
name, never left out of the picture; `--json` reports what was drawn
and each stage's milliseconds (`serveMs`, `meshMs`, `sceneMs` when a scene is made, `presentMs`,
`frameMs`, `drawMs`, `renderMs`, `totalMs`; a file no document: `readMs` its reader, `openMs` its
render process opening it). `parts` and `exploded` for a document that places one
part are refused by name before anything renders, the document named as its file is, or a model's by
its own name (the picture of a document no file holds is drawn under a name made from OUT, which no
refusal says). `--camera` is a preset, an `azimuth:elevation` pair, a camera object or `authored`: an
object's `preset` (a preset or a pair), `position`, `target`, `up`, `direction`, `zoom`,
`orthographicHalfHeight` and `name` are checked as the viewer checks a camera, its lens (`projection`,
`focalLength`) is the display's (`display.camera`), and a view straight down or up with no `up` has +Y
up the picture, as `top` and `bottom` do. SRC is a whole document: one that names something inside a
document (`ID#bracket`, `arm.step#arm/face 3`) is refused, saying how to draw a part alone
(`display.isolated`). `--annotation FILE` draws the viewer's annotation over the
model -- each mark on the part it was drawn on, wherever the picture places that part -- from an
annotation file or the Quick Edit packet that carries one (the `.snapshot.json` the viewer writes),
and `--measurements FILE` Measure's dimensions (`[{start, end, label, color}]`). A camera object's
lengths (`position`, `target`, `orthographicHalfHeight`), a measurement's points and the ink are in
the viewer's scene coordinates, as a Quick Edit packet carries them -- a document's and a GLB's
millimetres, a robot's metres, a 3MF's declared unit (the structure's `millimetresPerSceneUnit`;
`clip.at` alone is in the file's unit, a GLB's metres) -- and a still draws them in its millimetres
(`render/occt.py` `camera_in_millimetres`, `measure`, `annotate`). A mark names the
view it was drawn in by label alone (`"view": "view 1"`); the view itself -- its camera
(`position`, `target`, `up`, `orthographicHalfHeight`, the snapshot's own camera object), size and
projection -- is a job of the packet. `--camera authored` draws the picture from the view of the
last mark, exactly (no fit), at its size and projection unless the flags say otherwise: from the
packet given as `--annotation`, else the newest packet beside the annotation file that draws this
document; with none, it is refused by name. A face the mesher left without triangles is named in a
warning. Nothing is written but OUT. OUT may be a folder -- one that is there, or a path ending in a
separator -- and the picture is then `<SRC's stem>_<UTC time>.png` in it (a model's name for a model,
`snapshot.picture_path`), the path the verb prints and reports (`output`).

**A job.** `--job PACKET` replays a whole Quick Edit packet -- or a job file in its words: a job, a list
of jobs, or `{"input", "jobs": [...], "annotation", "measurements"}` -- in one call
(`snapshot.job_pictures`, `api.snapshot(job=)`), on the machinery above: each job is a view, drawn with
its own `camera` (an output's own `camera` over it), its `display` (its `hidden` and `isolated` parts
among it; the packet's top-level copies are `--annotation`'s), its pose (`jointValues`, as `--pose`
takes it), and -- a robot's -- the visuals its `selection.hide` names by the viewer's ids
(`link:v1`, each robot instance carrying its visual's), the packet's ink and dimensions over each
(a job's own `annotation` and `measurements` over the packet's); and each of its `outputs` (`path`,
`width`, `height`, `camera`, `label`) is a picture written at its path (a folder takes
`<stem>[_j<m>][_<n>]_<UTC time>.png`, the job's and the output's place where there are several). A
job's `output` settings finish its pictures: `padding` (0 to 0.15 of the picture each side, 0.04
unless given) and `tightFrame` (true unless given: the fit on every drawn vertex, else on the drawn
parts' box) frame a fitted camera, and a view's own camera -- a position, a target and, orthographic,
a half height -- with `tightFrame` false is drawn exactly, as the viewer writes every view
(`padding` 0, `tightFrame` false); `transparent` draws on nothing (OCCT's backdrop is a fill it draws
whole, so the picture is drawn on black and on white and each pixel's coverage read from the two,
in linear light: `service.matte`; Preview keeps its floor and its shadow, the sweep gone);
`renderScale` (1 to 3) draws the picture that many times its size and brings it down, each pixel
the mean of those it covers (`service.picture`): what the engine draws in pixels -- ink, words,
Measure, the grid -- is as heavy against the picture at any scale, while OCCT's GL lines (edges, a
drawing's hairlines) stay one pixel of the larger frame and read finer: OCCT's core profile draws no
line wider than a pixel, and this is that, not a bug; `sizeProfile` sizes an output that gives no
size. SRC, given, is drawn in place of every job's input, and a flag given overrides every job: the
display, the grid, the camera, the pose, the ink, the dimensions, the size of every
output; an OUT is refused. Every job is checked before anything renders (an unknown key, a setting
out of range, two outputs at one path, a file that is not there: refused by name, every file left as
it was), and a picture that fails writes none of the job's: every picture is staged beside its
output and moved into place only when all are drawn, and a failed snapshot leaves every existing picture as it was. Through the daemon each picture is a frame
of the file's warm render process; `daemon=False` serves each file once for all its pictures.
`--json` prints `{"ok": true, "pictures": [what each drew]}`.

**Native KiCad stills.** A `.kicad_pcb` is a file source, with no XCAF document or model worker.
`formats/kicad/plot.py` builds the plot payload from the board and its sibling project, its pours KiCad's
refill of a copy (`formats/kicad/poured.py`: the server's `_internal/boards.refill`, kicode in the
environment of `cad[kicad]`), kept by the bytes it reads (`poured.key`) in the engine's memory
(`viewer/plots.py`) and gzipped in the document cache beside the board's document,
`<cache>/documents/<its id>/kicad/<key>/` (with its DRC and its kept exports, `_internal/boards.py`; a
`cad delete` of the board deletes them with it), which a board's snapshot is drawn from too
(`renders.py` keeps it before the render process reads it; a payload drawn as saved says why in
`pours` and in the snapshot's warnings). `render/board.py` paints the same layer primitives
with Pillow in sheet millimetres, including top/bottom mirroring, Display presets, saved
plan cameras, annotation and measurements. Its render-service handle holds only a path; no
board plot or parsed model is persisted. It refuses Preview, pose and transparent output.
Viewing a board needs no KiCad installed: its first plot fetches kicode, the `kicad` integration's, for the
refill (`_internal/boards.refills`: `CAD_KICAD_REFILL=0` plots the pours as saved, fetching nothing), and
KiCad's own CLI (kicode's) performs DRC and exports.
A `.kicad_sch` is drawn the same way, one sheet a picture: `formats/kicad/schematic_plot.py` rereads
the hierarchy from its project's root and builds the page the display names (`{sheet, border, title}`: the
root, `/`, unless it names another; KiCad's default title block on unless `title` is false; the page's
edge and the drawing sheet's frame off unless `border`), and `render/schematic.py`
paints it in KiCad's light schematic colours, framed on what the page draws
(the title block with the rest, the whole page with its border on) or through a plan camera. Its handle watches every sheet file of
the hierarchy, so an edit to any sheet draws anew. It refuses Preview, pose, transparent output and
references; KiCad's own CLI (kicode's) performs ERC and the exports.

**The OCCT stills.** A document is drawn by OCCT's own OpenGL renderer from the engine's meshes
(`render/`): one presentation per part and look, each
instance a connected object of it; the modes, the camera fit, clip, grid and Preview are the
page's, Explode is the viewer's layout ported to Python (held to the viewer by one golden its own
scene made), and the annotation's ink and the measurements are drawn over the picture. Through the daemon, a served document a snapshot asks
for gets a render process of its own, started on its first picture and holding the document --
each part's buffer from the daemon's one mesh cache (nothing meshed again), its OCCT shapes, a
scene and its presentations on a hidden OpenGL context: a picture of it is a frame of that
process, answered as PNG bytes that the verb writes to OUT (tom: about a tenth of a second). A
picture of a version the process does not hold -- a model built again, a file rewritten -- sends
it that version first, with the buffers of the parts it lacks: the parts it shares with the last
keep their shapes, the new ones are made, and its scene is made again. It goes
with the daemon, and after a picture that leaves it over the workers' memory cap it says so
(`retired`) and exits. `daemon=False`, and a model's own document in its worker, draw in that
process. The context is a hidden window: Cocoa on macOS, a hidden window on Windows, and on Linux an
X server's -- the OCP wheels draw through GLX alone, so there is no context without one. A Linux
still draws on its request's `DISPLAY`, else on the engine's ([display.py](../display.py)): a render
process (`Service.draws`) is started with it, and a model's worker is told it with the export that draws
(`worker.told_display`) -- the daemon's own `DISPLAY` and `XAUTHORITY`, else an Xvfb's the daemon starts
at the first picture where `Xvfb` is on PATH (a cookie of its own, which only this user can read) and
stops with it;
where none can be made the engine fails the picture (`snapshot.NO_GL`). The caller then draws it itself where it
can (`snapshot.drawable_here`: the kernel in its process and a context it makes, on its own `DISPLAY`), saying so
on stderr -- a held document's picture from an xbf the engine exports to a temporary folder --; a `cad` command
that carries no kernel but has a display (`xvfb-run cad urdf snapshot ...`) runs the same snapshot in the
installation's base from its own process, which draws it so (`cli._drawn_elsewhere`); and with neither the
snapshot fails, naming what to install. Nothing is written but OUT.

`SRC` may also be a file the viewer opens that is no document, each read by its reader
(`formats/`) and drawn by OCCT in the same look, through the daemon by a render process of its own
per file (read again when a file it read changes) or with `daemon=False` in this process:

- **A mesh file** (`.stl`, `.3mf`, `.glb`) becomes a structure and part buffers as a document's are,
  so the modes, the camera fit, the grid, clip, Explode and the annotation are a
  document's. Each mesh carries the viewer's normals (creased at 30 degrees up to 10,000
  triangles, else flat) and its feature edges (three's `EdgesGeometry` at 16 degrees: the folds,
  the open rims), which Solid and the line modes draw. An STL is one part in the look's fill, its
  numbers millimetres; a 3MF is its objects placed by its build in its unit, each triangle in its
  colour group's or base material's colour (a slicer's generated default is none), a base
  material's `pbmetallic` its finish; a GLB is read by OCCT's glTF reader into an XCAF document --
  its node tree, its meshes, each primitive's material (with the extensions the engine writes:
  IOR, transmission, clear coat, anisotropy, emissive strength) and its base colour texture,
  drawn on its texture coordinates in the lit looks. `--pose` is refused: a mesh has no
  mechanism.
- **A robot** (`.urdf`, `.srdf`) is its link visuals' meshes (STL, 3MF and GLB files, a
  `package://NAME/...` one in the ROS package the description is in: the nearest folder above it
  named NAME or holding a `package.xml` that names it, as the viewer finds it too; a
  box, cylinder or sphere made and meshed by the kernel), each in its colour. Solid and
  Parts draw its faces alone, as the viewer draws a robot: a link mesh's edges are its triangles'
  folds, which along a thin curved part (a cable's wires, tessellated at the engine's angle) are
  lines a pixel apart that hide its colour; the line modes draw them. A URDF (and an SRDF's group states over it) is read
  once, in the engine (`urdf_source.py`, into the one
  articulation of `robot_model.py`: every link's frame at rest, its visuals, its joints with their
  mimics and four-bars, its named poses), and the viewer's payload (the server's
  `robot_payload.py`) and the stills (`formats/robot.py`) are two views of that read, each
  translating shapes and units and deciding what it can draw; where the two have always read a
  detail differently, each consumer's `Dialect` keeps its own (its words for a refusal, among
  them). The stills place the links by forward kinematics held to a golden its own code made
  (mimic joints and four-bar linkages followed, the linkage solved as `fourBarCoupling.js` solves
  it) where the viewer opens the robot -- every control at zero, an SRDF's `home`
  group state over that. `--pose` names an SRDF group state (`group/name`, or a name one group
  has), or gives joint values (degrees, metres) over the opening pose; an unknown joint, a joint
  that is no control and a value past its limits are refused by name.
- **A drawing** (`.dxf`) is drawn as the viewer's DXF pane draws it: from above, fitted with its
  16 px margin, lines, arcs, polylines, splines, ellipses, solids, solid hatches, blocks and
  dimensions one pixel wide in their pens (ACI 7 the look's ink), words set in the platform's UI
  face, on the light theme's white paper (`render/look.py`'s `DRAWING`); it takes no display. Its
  camera is a plan view, the window a Quick Edit view of it names (`render/drawing.py`'s
  `plan_view`: `{position, target, up, orthographicHalfHeight}` looking straight down at the sheet,
  +Y up), drawn as that window -- given as `--camera`, as `authored` (the view the ink was last
  drawn in), or as a job's view; `--annotation`'s ink lies on the sheet in drawing coordinates,
  painted as the pane paints it (`paint_ink`: strokes round-capped as wide as the viewer drew them
  against its height, areas filled, a text mark's words filling its box), and `--measurements`
  Measure's dimensions over it. Every other flag is refused by name; what it does not draw
  (points, hatch patterns, images) is named in a warning.

`SRC` may be a document's id too: it is drawn from the document the worker holding it has,
served by a server of the worker's over its one mesh cache, whether or not the model declares an
xbf, and nothing is built. From Python, `cad.snapshot(handle, ...)` and `handle.snapshot(...)`
draw the document a model call returned, by its id, as it is held; `cad.snapshot(model, ...)`
with the decorated function itself builds it first, writing what the model declares (law 10), and
the snapshot nothing but OUT. A picture is never a declaration: no
decorator and no build flag draws one.
