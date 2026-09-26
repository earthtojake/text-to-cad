# CAD Viewer Features

Load this only when a task needs Viewer file-support details or UI control guidance.

## Supported Files

- `.step`, `.stp`: STEP/STP review through the document's tree in the store (compiled from the file's bytes on open when missing); supports assembly trees, part hide/show, inspect/focus, face/edge/part selection, copied `#...` CAD references, display modes, clip planes, and a live Position section (named poses and joint sliders) when the model's sidecar declares kinematics, plus animation clips through the Animate tool when it declares animation.
- `.stl`, `.3mf`, `.glb`: mesh viewing with orbit/pan/zoom, screenshots, and the Display tool's shading modes. Measure is not offered — it is a STEP-only tool that snaps to B-rep topology, which a mesh has none of. A plain GLB's `COLOR_0` vertex colors render as source colors, exactly like authored material colors; a GLB carrying embedded animation plays it through the Animate tool, not a tab of its own, and looks the same at rest and while animating: a GLB is always drawn as its own glTF scene, wearing the viewer's surface finish outside Render mode (keeping its colors, maps and opacity) and its authored finish in Render mode.
- `.dxf`: read-only 2D drawing viewing — a straight render of the sheet, with no 3D view and no flat pattern. The server flattens the drawing to 2D primitives per request (text outlined, dimensions exploded, hatches filled, blocks placed) and the viewer paints them; no render artifact exists for a `.dxf`, so generated and imported drawings alike render straight from their own bytes.
- `.urdf`: robot link/mesh viewing with movable joint sliders, and reset pose.
- `.srdf`: paired-URDF viewing with planning groups, group-state presets, and joint controls.
- `.sdf`: SDF model/world viewing with metadata, counts, and joint controls when available.

## Navigation and tools

- Orbit by dragging; right-drag or Shift-drag pans. Wheel, pinch or middle-drag
  zooms, two fingers pan, and Arrow/WASD keys orbit the viewer that has focus or
  the pointer. The bottom-right cube (hidden below 720px and in fullscreen)
  changes direction without resetting zoom. Opening or reloading a file fits the
  model; the camera is never saved.
- The top-left toolbar shows only the tools the file supports (an unavailable
  tool is absent, not greyed). STEP starts in Select and offers Draw, Measure,
  Explode (two or more parts), Clip, Position when it has kinematics, Animate when
  it has routines, and Display. Robots start in Select and may offer Position.
  Meshes offer Display; animated GLBs also offer Animate. DXF uses a 2D canvas:
  drag to pan, wheel/pinch to zoom, double-click to fit.
- A corner triangle means options, an ordinary dropdown under the button that
  may overlap the panels below. First press selects; another press opens it.
  Select chooses its mode, Measure snapping, Animate Routine, Speed and Loop.
- STEP Select modes: All (pointer icon), Parts (assemblies only), Faces, Edges;
  the Select button shows the mode's icon. Edge chain and Tangent faces are
  checkboxes below them, independent of the mode and each other (Tangent faces
  applies under All/Faces, Edge chain under All/Edges; otherwise disabled, kept).
  The mode shapes the Features tree: All is your own expansion; Parts shows every
  part, none expandable; Faces/Edges expand everything and load each part's
  topology as its row scrolls into view. Outside All the tree cannot be expanded
  or collapsed.
- One tool owns picking. Leaving Select clears selection; leaving Draw clears
  drawings. Position edits persist. Animate sets Position values aside while it
  plays; leaving it stops playback and gives them back. Animate's Routine, Speed
  and Loop survive leaving it and Position edits. Completed measurements
  remain until their panel's X or main tool button clears them; unfinished picks
  are canceled when leaving Measure.
- Explode and Clip open neutral panels in the tool stack. Editing applies the
  effect; nonzero effects persist across tools. X or pressing the tool again
  resets/removes it. Unused zero-value panels disappear when selecting another
  tool, or when the pointer is released after a drag back to zero — never
  mid-drag. Explode uses a
  percentage; Clip uses an axis, Flip and one cut-percentage slider over the
  original model bounding box. 0% means no effect.
- Select individual faces/edges in the viewport even when Features groups them.
  In an assembly, the first face/edge press on a part loads that part's faces
  and picks under the pointer; the part lights on hover until then.
  Shift-click adds to the selection (Shift, Ctrl or Cmd in a tree). Double-click
  a component/subassembly, or its row's hover Isolate button (left of the eye),
  to isolate; double-click away, the lit Isolate or the isolation bar's Exit
  leaves. Double-click a face/edge to copy its file-prefixed reference; it
  stays selected. STEP context menus offer Zoom to Fit (the whole model, current
  angle) and Zoom to Selection.
- Copy Reference/References appears only for a usable selection. Copy Drawing
  appears only with ink. The platform copy shortcut performs the same action
  unless a text field owns input. Copies complete silently.

## Tool stack and display

The navbar's only panel toggle is the file explorer; a CAD file's controls are
panels in the tool stack under the toolbar, shown by their tool, and no pick or
tool opens, closes or switches the explorer. Under Select: Features (STEP) or
Links (robots) — the filter box is its top row — then, with a selection, the
Reference, then STEP Issues or SDF metadata. Under Position: the Position panel.
Under Display or Draw: that tool's panel, first. Kept Measure results, Explode
and Clip follow. All panels share one width (190px default, 160px minimum, up to
half the viewer; drag or arrow-key the handle right of the stack; remembered
across files) and never extend past the viewer: the tree scrolls first, then
details panels; the Reference holds about eight rows before scrolling. On mobile
(below 720px) the same stack applies, the tree taking at most 40% of it; the file
explorer is a floating sheet. The file explorer column is 200px minimum and
closes only when dragged below half of that.

The Reference panel's header names the reference (a label, else part and kind,
e.g. "base · face 3"; its ID is a row) with an X to clear; with several selected
the header is a picker with "i/N" and the rows show the chosen one only.

Position has a full-width Pose dropdown with Default and named poses, a Reset
beside its label, then joint sliders/value inputs. Edits apply immediately and
survive tool changes. Reset restores authored defaults, including SRDF home.
Filters match model/link names; link filters also match joint names. File names
retain their on-disk suffixes.

Display is a toolbar tool whose panel leads the stack: Mode, Appearance and
Projection; Surfaces; then optional Edges, Grid / Axes, Lighting, Background and
Floor. Plus enables a section with defaults; minus disables it. There is no
extra Enabled checkbox. Color and choice popups close before the panel does.
Mode presets are Solid, Render, X-ray, Hidden line and Wireframe where supported.
Render defaults to perspective; other presets to orthographic. Meshes and robots
offer Solid/Render without STEP topology effects. Manual changes show Custom.
Reset restores the selected preset and clears Clip/Explode, without reframing
and preserving pose and app appearance. Preset changes preserve applied model
effects. Pressing Display again or Escape returns to the default tool; clicking
the model does not close it.

## Fullscreen and host actions

Fullscreen is a transparent top-right scene button, separate from Animate. It
fills the area below the navbar, hides the file explorer, tool stack, cube and
editor tools, and
starts orbit. Pointer movement reveals Exit, a separate Orbit menu, animation
settings when clips exist, and a playbar (or an orbit play/pause). Controls share
one idle timeout. Picks, Draw, Measure, Position and Explode/Clip are suspended,
not discarded. Escape closes menus first, then exits. Exit restores the regular
camera, explorer and tool panels.

The navbar's camera action captures the viewport. The web viewer's local backend
can write a PNG to its machine's clipboard; desktop delivers to its composer.
File actions offer path copying and, when supported by the host, Reveal in Finder,
Explorer or a file manager. Native reveal/clipboard operate on the server machine
when accessing a viewer remotely, not automatically on the remote device.

Copied CAD references include a file identifier and canonical selector. Generated
models may use a bare stem; other files retain their suffix. Resolve that identifier
against the viewer's served root before using it as a filesystem path. Bare
`#...` selectors remain valid when the model is already known.
