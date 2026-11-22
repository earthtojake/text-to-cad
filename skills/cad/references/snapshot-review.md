# Snapshots

Read this file when choosing visual checks for a model or a file the viewer opens. Which pictures a
change calls for is [Check each change](../SKILL.md#check-each-change); this file is what a
snapshot can draw.

## Contents

- [Display, camera and size](#display-camera-and-size)
- [Clipped views](#clipped-views)
- [Annotations and Quick Edit views](#annotations-and-quick-edit-views)
- [Mesh files, robots and drawings](#mesh-files-robots-and-drawings)

`cad <type> snapshot SRC OUT.png` draws SRC as the viewer draws it, rendered by OCCT, into a
PNG: one command, one picture. SRC is a model's id (the document the server holds, as it is:
nothing is built), a document file (`.xbf`, `.step`), a mesh (`.stl`, `.3mf`, `.glb`), a robot
(`.urdf`, `.srdf`) or a drawing (`.dxf`). A script is never a source, and SRC is a whole document,
never a ref into one (`$ID#bracket`): `--display '{"isolated": ["bracket"]}'` draws one part alone.

```bash
cad model snapshot "$ID" tmp/review.png
cad model snapshot "$ID" tmp/below_behind.png --camera 225:-30
cad model snapshot "$ID" tmp/top.png --display hidden-line --grid --camera top
```

With no flags a snapshot is the `solid` display from an orthographic isometric camera fitted to the
model, 1600x1200. It is always light, whatever theme the viewer is in. A value outside a flag's
vocabulary is refused by name before anything renders.

- **OUT is written exactly as given** and must end in `.png`; a folder (one that is there, or a
  path ending in `/`) gets `<SRC's stem>_<UTC time>.png`, which the command prints. A refused
  request and a failed render write nothing and leave an earlier picture where it was, so check
  the exit status before reading the file: 2 for a request refused before anything ran, 1 for a
  render that failed. `--json` prints what was drawn and its timings, or the failure as
  `{"ok": false, "error": ..., "reason": ...}` (`reason`: `usage`, `invalid_argument`,
  `wrong_type`, `not_found`).
- **A face the mesher left without triangles is drawn without it**, and one warning counts them
  and names the first parts. In your own model it is usually a sliver a Boolean left; in a
  vendor's STEP a few faces of a large assembly (a screw's tip) are common. Either way the picture
  is not the whole model where they are.

## Display, camera and size

`--display` takes one of the viewer's display modes: `solid` (shaded, with edge linework),
`shaded` (no edges), `parts` (each part its own colour), `xray` (translucent surfaces, hidden edges
visible), `hidden-line` (linework with occluded edges suppressed) and `wireframe` (edges only).
After a mode or alone, by commas (`hidden-line,exploded=0.6`, `solid,edges=feature`), it takes:

- `exploded=AMOUNT`: the parts moved apart as the viewer's explode moves them, 0 to 1;
- `edges=CLASS`: the edges of one class alone, `feature` (where faces meet at an angle), `tangent`
  (where they meet smoothly) or `seam` (where a face closes on itself). `edges=feature` draws no
  line along a loft's or a cylinder's seam, nor where a fillet meets its faces, which otherwise
  draw as lines across a smooth skin. It draws no silhouettes either, so a round part has no
  outline of its own.

It also takes the viewer's display object, inline or as a JSON file: `mode`, `grid`, `camera`
(`projection`: `orthographic` or `perspective`; `focalLength`), `clip`, `exploded`
(`{"enabled": true, "amount": 0.5}`), `edges` (`{"classes": ["feature", "seam"]}`: the classes
drawn), `hidden` and `isolated` ([below](#clipped-views)). `parts` and `exploded` are refused for a
document of one part.

`--grid` draws the measuring grid (red X and green Y axes) under the model.

`--preview` draws the viewer's preview in place of a display mode: the model lit in a studio (a
key light, softboxes, shadows on itself), in its materials, on a floor with its shadow, in
perspective. It is the picture for a person, and the one that shows form on a part of one colour: a
gloss-black shell, a white fairing. Review geometry in the display modes, where edges are drawn.
The first preview of a document takes some seconds longer than a mode. It is drawn by the same
renderer, not a path tracer: glass is a see-through tint, a polished metal reads lighter than the
viewer's, and nothing is reflected in the floor. A drawing, a board and a schematic have none.

`--camera` is a preset (`iso`, `front`, `back`, `left`, `right`, `top`, `bottom`), an
`azimuth:elevation` pair in degrees (`--camera 45:30`; `0:90` looks straight down), a camera
object (`preset`, `position`, `target`, `up`, `direction`, `zoom`, `orthographicHalfHeight`), or
`authored` ([below](#annotations-and-quick-edit-views)). Projection and focal length belong in
`display.camera`. The presets are the world's axes, Z up, not a part's own front: `front` looks
from -Y along +Y, `top` from +Z down, so a panel modelled lying flat (its face to +Z, as its DXF is
drawn) faces `top` and shows edge-on from `front`.

A camera object's lengths, an annotation's ink and `--measurements`' points are in the viewer's
scene coordinates: a document's and a GLB's millimetres, a robot's metres, a 3MF's declared unit.
`clip.at` alone is in the file's own unit, which for a GLB is metres.

`--width` and `--height` set the size in pixels, 16 to 8192. `--size-profile` names one instead:
`simple` 1200x900, `simple-square` 1024x1024, `diagnostic` and `labeled` 1600x1200 (the default),
`assembly` 1800x1200, `assembly-large` 1920x1440, `presentation` and `contact-sheet` 2400x1600,
`presentation-large` 2800x1800.

`--pose` draws a document's mechanism posed: a mechanism state's name, a configuration sequence
at a time of its clip (`walk@0.6`, the sequence's name and the seconds), or joint and coupling
values as JSON, a turn in degrees, a slide in millimetres
([reviewing motion](kinematics.md#reviewing-motion)). It is how the picture is drawn; a file of
the pose is a posed model ([exports](exports.md#posed-files-and-parts-on-their-own)).

A snapshot draws the mesh the viewer draws, which is right for a review and coarse for a close-up
of a large curved part (a faceted outline, uneven shading). For a still that needs a finer one,
export the model as a GLB at the tolerance wanted and draw that file:

```bash
cad model export "$ID" tmp/fine.glb --tolerance 0.02 --angle 3
cad glb snapshot tmp/fine.glb tmp/close.png --camera 35:20
```

## Clipped views

Clip reveals internal geometry: a shell, a bore, a cavity, a blind hole, a wall's
relation to a floor. `display.clip` takes `enabled`, `axis` (`x`, `y` or `z`, lower case), `at`
(the plane's coordinate on that axis, in the file's unit; the middle of the model when left out)
and `invert`; the cut is capped. Look straight at the cut:

```bash
cad model snapshot "$ID" tmp/cut.png --camera back --display '{"clip": {"enabled": true, "axis": "y", "at": 12.5}}'
```

Hide and isolate leave parts out, as the viewer's do: `display.hidden` is a list of
part refs (an occurrence's path: `lid`, `hand/finger.2`; an assembly hides every part
below it) the picture leaves out, `display.isolated` the parts it alone draws. A name
with `*`, `?` or `[` is a glob over every occurrence, matched against its label, its
numbered segment and its path written with either, so one entry leaves out a kind of
part wherever it is; a glob that matches nothing is refused.

```bash
cad model snapshot "$ID" tmp/inside.png --display '{"mode": "solid", "hidden": ["lid"]}'
cad model snapshot "$ID" tmp/frame.png --display '{"hidden": ["*skin*", "*/skin_screw"]}'   # the structure alone
```

## Annotations and Quick Edit views

A Quick Edit prompt carries a snapshot packet: inline JSON up to 1 KiB (save it to a
`.snapshot.json` first), or the path of a `.snapshot.json` in a folder of the server's under
`/tmp`. The prompt names files relative to your workspace, else from `~/`; `cad <type> snapshot`
reads either from the workspace. The packet holds:

- `input`: what the person looked at: a model's id, or a file's path;
- `jobs`: one per view they captured (the current view and each view they drew
  in), each with the view's `camera`, its `display` (the parts that view hid and isolated among
  it, as `hidden` and `isolated` refs) and an output `label`; a posed document's or a robot's
  carries its pose as `jointValues`;
- `annotation`: their ink, when they drew any. Each mark is in model coordinates,
  on the part it was drawn on, and its `touches` lists what it was drawn over, most
  first: faces and edges as refs where the viewer could name them, each with its
  part. Read those to know what a mark is about;
- `hidden` and `isolated`: with ink, the parts the view it was last drawn in hid
  and isolated, which `--annotation` leaves out of the picture unless `--display` says otherwise.

Draw the view a person drew their ink in, with the ink on the model:

```bash
cad model snapshot "$ID" tmp/quick_edit.png --annotation tmp/bracket.snapshot.json --camera authored
```

`--annotation FILE` takes the packet or an annotation file and draws each mark on its part,
wherever the picture places that part (posed or exploded). `--camera authored` draws exactly the
view the last mark was drawn in (no fit), at its size and projection unless other flags say
otherwise. Pass a job's `display` object as `--display` to draw in the person's mode with the
parts they hid left out, and its `jointValues` as `--pose`. A view without ink is drawn from its
`camera`, given as `--camera '<its JSON>'`. `--measurements` draws dimension lines of your own
over the model, a JSON list of `{start, end, label, color}` or a file of it.

`--job` replays the whole packet in one call (every view, each with its own camera, display and
pose, the ink over each) into the files its outputs name:

```bash
cad model snapshot --job tmp/bracket.snapshot.json
cad model snapshot --job tmp/bracket.snapshot.json "$ID"   # the same views, of the document as it is now
```

`--job` also takes a job (`{input, camera, display, preview, jointValues, output, outputs}`) or a
list of jobs, as a file or JSON, so one command draws many pictures. A job's `jointValues` takes
what `--pose` does, so a list of jobs is a sequence's frames. Its `outputs` are its pictures
(`path`, and `width`, `height`, `camera` of their own; a folder `path` takes a generated name). A
SRC given is drawn in place of every job's input, and any other flag overrides every job. Every
job is checked before anything renders, and a failure writes none of its pictures. A job's
`output` settings finish its pictures:

- `padding` (0 to 0.15 of the picture each side) and `tightFrame` frame a fitted camera; a view's
  own camera with `tightFrame` false, as the viewer writes every view, is drawn exactly;
- `transparent` draws on nothing, and `background` (a `#rrggbb`) on that flat colour in place of
  the pale default: a white or pearl part has no outline on it, so give one a dark one
  (`"output": {"background": "#2b2d31"}`);
- `renderScale` (1 to 3) supersamples, so edge lines read finer, and `sizeProfile` sizes an output
  that gives no size.

A preset or `azimuth:elevation` is fitted to what each picture shows, so two pictures of
different parts or poses are framed differently. For frames that must not move (a motion's
frames, a part alone beside the whole), draw one picture with `--json`, take the camera it
settled on from its report (`settledCamera`: `position`, `target`, `up` and, orthographic,
`orthographicHalfHeight`), and give it to every job as its `camera` with
`"output": {"tightFrame": false}`: it is drawn exactly, with no fit.

## Mesh files, robots and drawings

- **A mesh** (`.stl`, `.3mf`, `.glb`) takes every display mode, the grid, clip,
  an explode (a file of several parts) and annotations; `--pose` is refused: a
  mesh has no mechanism. A GLB is drawn at rest, its clips not played; its materials
  and base colour textures are drawn.
- **A robot** (`.urdf`, `.srdf`) is its links' visuals in their colours, faces
  alone as the viewer draws a robot (its meshes' folds only in the line modes), where the viewer
  opens it. `--pose` names an SRDF group state, or gives joint values over that
  pose: degrees for a turn and metres for a slide, though the file holds radians.
- **A drawing** (`.dxf`) is drawn whole from above in its pens on white paper. It takes the size
  flags, a plan-view `--camera`, `--annotation` and `--measurements`, and every other flag is
  refused by name ([see a drawing](2d-profiles-and-dxf.md#see-a-drawing)).
