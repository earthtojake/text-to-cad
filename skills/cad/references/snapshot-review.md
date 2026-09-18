# Snapshot review

Read this file when choosing visual checks for saved STEP/STP or mesh outputs.
Use `cadgen step snapshot` for STEP, or the corresponding `stl`, `3mf` or `glb`
snapshot command for meshes (see [mesh exports](supported-exports.md)). The
CAD topology, selection, section and motion controls below apply to STEP.

## Policy

Every created or visibly updated part or assembly gets at least one reviewed
PNG snapshot of its STEP, or its mesh when no STEP is declared. Passing geometry
checks does not waive this visual review. Use the format's snapshot command.
For a STEP pose or clip frame, pass `--kinematics` and/or
`--animation CLIP --time SECONDS`. A motion review may additionally need video;
see [kinematics](kinematics.md#reviewing-motion).

Skip saved snapshots only when no visible geometry was created or updated, or no valid artifact exists:

- pure format/export requests where geometry is unchanged
- source changes that do not alter visible geometry
- inspection-only tasks (for example direct measurement questions) that create or update nothing
- failed Python or STEP generation before a valid artifact exists

When skipping, report the reason and the deterministic evidence that still ran.

Do not loop on snapshots. Rerender only when a source repair changed visible geometry or when a specific visual finding needs confirmation.

## Packet sizing

Choose views that expose the features being checked. One may be enough;
add an opposing view for hidden exterior features, an orthographic view for
a pattern or silhouette, or a section for internal geometry. No fixed set of
views proves every face or feature is correct.

## Small packet

For example, a four-view comparison can use one JSON job:

```json
{
  "input": "models/part.step",
  "mode": "view",
  "outputs": [
    { "path": "/tmp/render/iso.png", "camera": "iso" },
    { "path": "/tmp/render/iso_opposite.png", "camera": { "direction": [-1, 1, -0.8] } },
    { "path": "/tmp/render/top_ortho.png", "camera": "top" },
    { "path": "/tmp/render/front_ortho.png", "camera": "front" }
  ],
  "output": { "viewLabels": true, "padding": 0.12, "sizeProfile": "diagnostic" }
}
```

Use only the views relevant to the design. Opposed isometric views reveal more
exterior faces, but neither they nor orthographic views reveal all occluded geometry.

Set `input` to the primary STEP/STP artifact using a relative or absolute path (documents only — a `.py` model script is refused: run it first, then snapshot the STEP it wrote). The snapshot CLI derives its internal render root from that input path. With no `render` key it uses deterministic light CAD lighting, an orthographic isometric camera and normal shaded-with-edges display, with grid and axis guides disabled for still evidence. Labeled/section views default to 1600x1200 when dimensions are omitted. Use `output.sizeProfile: "assembly"` or `"assembly-large"` for complex assemblies that need 1800x1200 or 1920x1440. For CAD review packets, use still-image render modes `view` and `section`; set `display.mode` to `shaded_edges`, `transparent`, `hidden_edges`, `hidden_lines_removed`, or `wireframe` when the visual check benefits from explicit CAD linework. For shaded surfaces with no CAD linework set `display.mode: "shaded"` (or `"unshaded"`). `display.edges` carries the viewer's edge styling settings for modes that draw linework.

An explicit `render` envelope opts into the photographic scene and supports `view` mode only. The compact form is `{}`; the full shape is `{"studio":...,"quality":...,"exposure":...,"lighting":...,"backdrop":...,"camera":...}`. Studio is `light` or `dark`; the CLI uses Light when omitted. Quality is `preview` or `final` and defaults to final. Exposure is a finite number from -5 to 5. Lighting accepts `rotation` (-180..180 degrees), `size` (0.25..3 relative softbox scale), and `fill` (0..1 ratio). Backdrop accepts a hex `color`, boolean `transparent` and `ground` controls, and `groundPlacement` — `lowest` (the default: the floor sits at the model minimum, so geometry below the document origin is not veiled by it) or `origin` (pin the plane to the document's own Z=0), moving neither geometry nor lighting. The envelope camera owns projection, `focalLength` (20..200 mm), and `orthographicHalfHeight`, a positive finite world-space half-height that preserves orthographic scale. Top-level camera and display settings belong to normal CAD and cannot be combined with Render; a packet output's camera remains an explicit per-image override. `--render` accepts `light`, `dark`, inline JSON, or a JSON file.

Use `--focus '#o1.2' ...` to emphasize specific part or subassembly occurrence refs in normal CAD snapshots — in `view` renders the focused refs keep full opacity while the rest of the assembly is ghosted in place (framing and context are preserved); in `section` mode focus isolates the refs entirely. Use `--hide '#o1.2' ...` to omit parts from normal CAD snapshots. Do not combine focus and hide in the same snapshot command or job. These filters accept occurrence refs only, not face, edge, vertex, or shape selectors. Selection cannot be combined with Render. Kinematics, animation frames and animation sequences all compose with the photographic scene; a robot's `--joint-values` does not.

For close macro views in normal CAD, a JSON job can set `quality.tessellation` to
`{"chordTolerance": 0.0005, "angleTolerance": 0.10}`. Chord tolerance is
relative to each component's bounding diagonal; angle tolerance is radians.
These positive numeric overrides retessellate the exact STEP surfaces and use
separate shared-cache entries. They do not change the STEP geometry or a model's
declared mesh-export tolerances. Use them only when visible faceting needs finer
sampling; lower tolerances cost more memory and render time. `chordTolerance`
must be at least `0.00001` and `angleTolerance` at least `0.005` — finer than
that exhausts the renderer instead of improving the image, and the job is
refused. The largest named still profile is `presentation-large` (2800×1800).
Existing mesh documents cannot be retessellated this way. Render cannot be combined with
this top-level CAD sampling request; its `preview` or `final` quality selects the photographic LOD.

Scene setup, output capture and geometric sampling are separate closed objects.
`render` is the Render envelope described above. `output` supports `sizeProfile`,
`padding`, `paddingPercent`, `viewLabels`, `tightFrame`, `transparent`, and
`renderScale`. Normal-CAD `quality` supports `tessellation`. Scene units use the top-level
`scale` (`cad` or `urdf`). Unknown keys are refused, so a misspelling cannot
render the wrong thing quietly.

### Flags and job keys

A JSON job's keys are the flags without their dashes, and the job is the only
place some shapes exist. `--animation CLIP --time SECONDS` is ONE request, so a
job carries it as one `animation` object — `time` is not a top-level job key:

```json
{
  "input": "models/arm.step",
  "kinematics": "open",
  "animation": { "clip": "demo", "time": 2.0 },
  "outputs": [{ "path": "/tmp/render/demo_t2.png", "camera": "iso" }]
}
```

`clip` names a clip embedded in the document sidecar's animation and is required;
`time` is seconds, finite and >= 0, defaulting to 0. A bare clip name is the
FLAG's spelling, not the job's: `"animation": "demo"` is refused, as is any key
the job does not support — the error lists the supported set.

A `"video"` object beside it renders the clip's SPAN into the `.mp4` or `.gif`
the single output names, instead of one frame: `{"fps": 30, "seconds": <what is
left of the clip>, "start": 0, "quality": "review", "loop": true}`, every key
optional and every other key refused. It needs `animation`, refuses an
`animation.time`, refuses a `start` past the end of the clip, and needs ffmpeg
installed. See `kinematics.md`, "Rendering the whole clip".

In a JSON job these two flags are the one exception to "job key = flag name without dashes": they nest under a job-level `selection` object, and a top-level `"hide"` or `"focus"` is rejected as an unknown key. Selection applies to the whole job, not to one output — to hide or focus parts for a single view, give that view its own job in a `jobs` array.

```json
{
  "input": "STEP/assembly.step",
  "mode": "view",
  "selection": { "hide": ["#o1.3", "#o1.4"] },
  "outputs": [{ "path": "tmp/render/without_covers.png", "camera": "iso" }]
}
```

`"selection": { "focus": ["#o1.2"] }` is the `--focus` form. Every other flag keeps the plain rule (`--kinematics` → `"kinematics"`, `--animation CLIP --time S` → `"animation": {"clip": ..., "time": ...}`).

## Output paths

Name the file and you get that file:

```bash
cadgen step snapshot STEP/bracket.step tmp/review.png
# then Read tmp/review.png
```

OUT (and an output's `path` in a JSON packet) is written exactly as given,
relative to the working directory. Check the command's exit before reading:
invalid request combinations leave an existing file untouched; after request
validation, the target is cleared and successful output is written atomically.
Reuse `tmp/review.png` during iteration, or name before/after images when both
are needed for comparison.

Pass a directory (`tmp/` as OUT, or an output `path` that is one) only when the name does not matter: a timestamped name is generated inside it, and that is the one case where you read the path from the `saved snapshot:` line.

## Targeted additions

Add views only when the brief or a failure mode calls for them:

- reference-image reproduction: one snapshot from the reference image's viewpoint for side-by-side comparison
- `section`: shell, bore, internal cavity, passage, blind hole, enclosure, or wall/floor relationship
- `display.mode: "shaded_edges"`: shaded CAD view with explicit edge linework
- `display.mode: "shaded"`: shaded material view without edge overlay
- `display.mode: "transparent"`: overlap, collision, enclosure readability, or hidden contact checks when transparency adds information and wireframe is too noisy
- `display.mode: "hidden_edges"`: opaque shaded context with hidden/occluded CAD edges visible through solids
- `display.mode: "hidden_lines_removed"`: line-focused review where hidden/occluded edges should be suppressed
- `display.mode: "wireframe"`: internal overlap, hidden interference, or assembly collision suspicion when full triangle wire is useful
- labeled or annotated review: use supported CAD Viewer refs, selections, screenshots, or GUI review links

Exploded or labeled review is an intent, not a render mode. Satisfy it through supported CAD Viewer mechanisms, supported JSON job settings, or the GUI link.

## Diagnostic review

Visual review is diagnostic, not authoritative. Convert every visual concern into a follow-up geometry check before using it as a validation claim:

- hole pattern appears asymmetric -> measure hole centers and compare offsets
- lid, child part, or occurrence appears offset -> inspect frames and mating deltas
- gusset, boss, standoff, rib, or plate may be floating -> inspect solid count, labels, connectivity, contact, or relevant distances
- cavity, bore, or blind hole looks wrong -> run section review, then measure wall thickness, depth, or through-condition
- repeated pattern looks uneven -> measure pattern centers, angular spacing, or occurrence frames

Final reports should include the generated snapshot PNGs or the documented skip reason, and state which deterministic checks support any visual finding.
