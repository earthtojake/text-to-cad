# Snapshots

Read this file when choosing visual checks for a model or a file the viewer opens.

This is the catalogue of what a snapshot can draw. Take one only when no viewer is open or you must
see something the person has not asked about, then one picture from one angle; with a viewer open,
report the run and stop ([Pictures](../SKILL.md#pictures)).

## Contents

- [Views](#views)
- [Choosing views](#choosing-views)
- [Display, camera and size](#display-camera-and-size)
- [Clipped views](#clipped-views)
- [Annotations and Quick Edit views](#annotations-and-quick-edit-views)
- [Mesh files, robots and drawings](#mesh-files-robots-and-drawings)
- [Output paths](#output-paths)
- [Targeted additions](#targeted-additions)
- [Diagnostic review](#diagnostic-review)

`cadgen snapshot SRC OUT.png` draws SRC as the CAD Viewer draws it, rendered by OCCT,
into a PNG. SRC is a model's id (the `id:` line its run printed: drawn from the document
the engine holds, as it is, and nothing is built), a document file (`.xbf`, `.step`), a
mesh (`.stl`, `.3mf`, `.glb`), a robot (`.urdf`, `.sdf`, `.srdf`) or a drawing (`.dxf`). A
script is never a source. Nothing is written but OUT.

```bash
cadgen snapshot "$ID" tmp/review.png
cadgen snapshot "$ID" tmp/review.png --display hidden-line --grid --camera top
cadgen snapshot "$ID" tmp/review.png --preview
```

A face the mesher left without triangles is drawn without it and named in a
warning, with its part. It is usually a sliver a boolean left: the picture is then
not the whole model.

## Views

Skip saved snapshots only when no visible geometry was created or updated, or no valid artifact exists:

- pure format/export requests where geometry is unchanged
- source changes that do not alter visible geometry
- inspection-only tasks (for example direct measurement questions) that create or update nothing
- a failed run, before a valid document exists

When skipping, report the reason and the deterministic evidence that still ran.

Do not loop on snapshots. Rerender only when a source repair changed visible geometry or when a specific visual finding needs confirmation.

## Choosing views

Choose views that expose the features being checked; each command draws one. One
may be enough; add an opposing view for hidden exterior features, an orthographic
side view for a pattern or silhouette, or a clipped view for internal geometry. No
fixed set of views proves every face or feature is correct.

```bash
cadgen snapshot "$ID" tmp/iso.png
cadgen snapshot "$ID" tmp/below_behind.png --camera 225:-30
cadgen snapshot "$ID" tmp/top.png --camera top
cadgen snapshot "$ID" tmp/front.png --camera front
```

With no flags a snapshot is the `solid` display, Light appearance, an orthographic
isometric camera fitted to the model, 1600x1200.

## Display, camera and size

`--display` takes one of the viewer's six display modes, each at its own defaults:
`solid` (shaded, with edge linework), `shaded` (no edges), `parts` (each part its own
colour), `xray` (translucent surfaces, hidden edges visible), `hidden-line`
(linework with occluded edges suppressed) and `wireframe` (edges only). It also takes
`exploded=AMOUNT` (the parts moved apart as the viewer's Explode moves them, 0 to 1),
alone or after a mode (`hidden-line,exploded=0.6`), or the viewer's display object,
inline or as a JSON file: `mode`, `grid`, `appearance` (`light` or `dark`), `camera`
(`projection`: `orthographic` or `perspective`; `focalLength`), `clip` and `exploded`
(`{"enabled": true, "amount": 0.5}`). `parts` and `exploded` are refused for a
document of one part. Unknown keys and out-of-range values are refused.

`--grid` draws the measuring grid (red X and green Y axes) under the model.
`--preview` draws Preview's photographic look instead of a mode.

`--camera` is a preset (`iso`, `front`, `back`, `left`, `right`, `top`, `bottom`),
an `azimuth:elevation` pair in degrees, a camera object (`position`, `target`, `up`,
`direction`, `zoom`, `orthographicHalfHeight`), or `authored` (below). Projection and
focal length belong in `display.camera`.

`--size-profile` is one of exactly these names; anything else is refused with this
list:

| Profile | Size |
| --- | --- |
| `simple` | 1200x900 |
| `simple-square` | 1024x1024 |
| `diagnostic` (default), `labeled` | 1600x1200 |
| `assembly` | 1800x1200 |
| `assembly-large` | 1920x1440 |
| `presentation`, `contact-sheet` | 2400x1600 |
| `presentation-large` | 2800x1800 |

`--width` and `--height` set the size in pixels instead, up to 8192.

`--pose` draws a document's mechanism posed: a mechanism state's name, or joint and
coupling values as JSON ([reviewing motion](kinematics.md#reviewing-motion)). It is how
the picture is drawn; a file of the pose is a posed model
([exports](exports.md#posed-files-and-parts-on-their-own)).

`--json` prints what was drawn and each stage's milliseconds as one JSON object,
and a failure as `{"ok": false, "error": ...}` on stdout, with exit status 1.

## Clipped views

Clip reveals internal geometry: a shell, a bore, a cavity, a blind hole, a wall's
relation to a floor. `display.clip` takes `enabled`, `axis` (`x`, `y` or `z`), `at`
(the plane's coordinate on that axis, in the file's own unit: a document's
millimetres) and `invert`; the cut is capped. Look straight at the cut:

```bash
cadgen snapshot "$ID" tmp/cut.png --camera back --display '{"clip": {"enabled": true, "axis": "y", "at": 12.5}}'
```

Hide and isolate leave parts out, as the viewer's do: `display.hidden` is a list of
part refs (an occurrence's path: `lid`, `hand/finger.2`; an assembly hides every part
below it) the picture leaves out, `display.isolated` the parts it alone draws. A Quick
Edit packet given to `--annotation` carries the person's own, which `--display` may
override:

```bash
cadgen snapshot "$ID" tmp/inside.png --display '{"mode": "solid", "hidden": ["lid"]}'
```

## Annotations and Quick Edit views

A Quick Edit prompt carries a snapshot packet: inline JSON up to 1 KiB, or the
absolute path of a `.snapshot.json`. Save inline JSON to a temporary
`.snapshot.json` first. The packet holds:

- `input`: what the person looked at: a model's id, or a file's absolute path;
- `jobs`: one per view they captured (the current view and each view they drew
  in), each with the view's `camera`, its `display` and an output `label`; a posed
  document's or a robot's carries its pose as `jointValues`. A document's display
  names the parts that view hid and isolated, as `hidden` and `isolated` refs;
- `annotation`: their ink, when they drew any. Each mark is in model coordinates,
  on the part it was drawn on, and its `touches` lists what it was drawn over, most
  first: faces and edges as refs where the viewer could name them, each with its
  part. Read those to know what a mark is about;
- `hidden` and `isolated`: with ink, the parts the view it was last drawn in hid
  and isolated, which `--annotation` leaves out of the picture;
- `measurements`: Measure's dimensions, when they took any.

Draw the view a person drew their ink in, with the ink on the model:

```bash
cadgen snapshot "$ID" tmp/quick_edit.png --annotation tmp/bracket.snapshot.json --camera authored
```

`--annotation FILE` draws the ink over the model, each mark on its part wherever the
picture places that part (posed or exploded); it takes the packet or an annotation
file. `--camera authored` draws exactly the view the last mark was drawn in (no fit),
at its size and projection unless other flags say otherwise. Pass the job's
`display` object as `--display` to draw in the person's mode with the parts they
hid left out, a job's
`jointValues` as `--pose`, and the packet's `measurements` list (as a file, or inline
JSON) as `--measurements` to draw the dimensions. A view without ink is drawn from
its `camera`, given as `--camera '<its JSON>'`.

Replay the whole packet in one call -- every view, each with its own camera,
display, hidden and isolated parts and pose, the ink and the dimensions over each --
into the files its outputs name:

```bash
cadgen snapshot --job tmp/bracket.snapshot.json
cadgen snapshot --job tmp/bracket.snapshot.json "$ID"   # the same views, of the document as it is now
```

`--job` takes a packet, a job (`{input, camera, display, jointValues, outputs, ...}`)
or a list of jobs, as a file or JSON; a job's `outputs` are its pictures (`path`, and
`width`, `height`, `camera` of their own; a folder `path` takes a generated name).
A SRC given is drawn in place of every job's input, and any other flag overrides
every job. A job's `output` settings finish its pictures: `padding` (0 to 0.15 of
the picture each side) and `tightFrame` frame a fitted camera (a view's own camera
with `tightFrame` false, as the viewer writes every view, is drawn exactly),
`transparent` draws on nothing, `renderScale` (1 to 3) supersamples -- OCCT's edge
lines stay one pixel of the larger picture, so they read finer -- and `sizeProfile`
sizes an output that gives no size. Every job is checked before anything renders,
and a failure writes none of its pictures, leaving existing ones unchanged. `--json` prints each picture's report.

Inspect supplied annotations before editing. A view without annotations is optional
context: render it only when useful to the request. After an edit, run the script and
draw the same view again to see the change from where the person looked, with their ink
still on it.

## Mesh files, robots and drawings

- **A mesh** (`.stl`, `.3mf`, `.glb`) takes every display mode, the grid, clip,
  Explode (a file of several parts), Preview and annotations; `--pose` is refused: a
  mesh has no mechanism. A GLB is drawn at rest, its clips not played; its materials
  and base colour textures are drawn.
- **A robot** (`.urdf`, `.sdf`, `.srdf`) is its links' visuals, each link one colour
  of the Parts palette, where the viewer opens it. `--pose` names an SRDF group state
  or gives joint values (degrees, metres) over that pose.
- **A drawing** (`.dxf`) is drawn whole from above in its pens, as the viewer's
  drawing pane draws it. It takes `--display` with `appearance` alone (`--display dark`,
  or `{"appearance": "dark"}`), and the size flags; every other flag is refused by name.

## Output paths

OUT is written exactly as given, relative to the working directory, and must end in
`.png`; a folder instead (one that is there, or a path ending in `/`) gets a
generated name inside it, `<SRC's stem>_<UTC time>.png` (an id for a model:
`tmp/stills/0dc50a92-a21f-5895-a245-ebdeb5352f3b_20261023T233930Z.png`),
which the command prints. Check the command's exit status before reading it: a refused request
(an unknown key or value, a pose out of range, a flag the input cannot take) and a
failed render write nothing, and leave a file an earlier run wrote where it
was. Reuse one name while iterating (`tmp/review.png`), or name before and after
images when both are needed for a comparison.

## Targeted additions

Add views only when the brief or a failure mode calls for them:

- reference-image reproduction: one snapshot from the reference image's viewpoint for side-by-side comparison
- a clipped view with a camera facing the cut: shell, bore, internal cavity, passage, blind hole, enclosure, or wall/floor relationship ([clipped views](#clipped-views))
- `--display xray`: translucent surfaces with hidden edges visible
- `--display hidden-line`: line-focused review with occluded edges suppressed
- `--display wireframe`: edge-only review for internal overlap or interference
- `--display exploded=0.6`: an assembly's parts apart, to see what is inside
- `--grid`: a measuring grid under the model, for reading size and placement at a glance
- `--pose`: each mechanism state that matters, for an articulated model

## Diagnostic review

Visual review is diagnostic, not authoritative. Convert every visual concern into a follow-up geometry check before using it as a validation claim:

- hole pattern appears asymmetric -> measure hole centers and compare offsets
- lid, child part, or occurrence appears offset -> inspect placements and mating deltas
- gusset, boss, standoff, rib, or plate may be floating -> inspect solid count, labels, connectivity, contact, or relevant distances
- cavity, bore, or blind hole looks wrong -> review a clipped view, then measure wall thickness, depth, or through-condition
- repeated pattern looks uneven -> measure pattern centers, angular spacing, or placements

Final reports name what the snapshots showed, or the documented skip reason, and which deterministic checks support any visual finding. The PNGs are for your review; the user sees the model in the viewer, so attach one only when they ask for an image.
