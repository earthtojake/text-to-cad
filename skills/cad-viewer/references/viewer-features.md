# CAD Viewer Features

Load this only when a task needs Viewer file-support details or UI control guidance.

## Supported Files

- `.step`, `.stp`: STEP/STP review through hidden GLB sidecars; supports assembly trees, part hide/show, inspect/focus, face/edge/vertex/part selection, copied `#...` CAD references, display modes, clip planes, and optional STEP module parameters/animations when a sidecar module exists.
- `.stl`, `.3mf`, `.glb`: mesh viewing with orbit/pan/zoom, screenshots, theme controls, and solid/wireframe display where available. Measure snaps to triangle vertices only (two clicks, distance in mm) — not STEP faces/edges.
- `.dxf`: read-only 3D flat-pattern viewing. The extruded pattern is baked into the drawing's `__cadgen__` render package on first open (thickness and bend state are producer-owned bake settings, not live controls), so both generated `.dxf.py` drawings and imported `.dxf` files render through the same mesh path as everything else.
- `.implicit.js`, `.implicit.mjs`: implicit-CAD models raymarched on the GPU from their own GLSL — no bake, nothing cached to go stale. Parameters, animations and raymarch graphics settings are live viewport controls; `export --stl/--3mf/--glb` meshes on demand for exchange.
- `.urdf`: robot link/mesh viewing with movable joint sliders, reset pose, and copied joint values.
- `.srdf`: paired-URDF viewing with planning groups, group-state presets, joint controls, and optional MoveIt2 IK/planning controls.
- `.sdf`: SDF model/world viewing with metadata, counts, warnings, and joint controls when available.

## Controls

- Navigation: left-drag to orbit, right/middle-drag to pan, wheel or pinch to zoom, and Arrow/WASD keys to orbit. Use the view sphere for top/bottom/front/back/left/right views; click its center for the default isometric view.
- File browser: toggle the left CAD Viewer sidebar, search files/ids/paths, expand folders, select entries, or switch files from the breadcrumb menus.
- Floating toolbar: `Select` copies STEP topology references, `Draw` opens annotation tools, `Select Pose` appears for robot target picking when available, `Open orbit preview` starts an auto-rotating preview, and the copy/download buttons capture screenshots.
- Drawing tools: freehand, line, arrow, expand, rectangle, circle, fill, erase, undo, redo, and clear.
- File sheet: open the right sheet for file-specific controls such as STEP tree/parameters, implicit parameters/animation/graphics, URDF/SRDF/SDF joints and metadata, plus the Display tab. Mesh files show a Measure tab for vertex-to-vertex distance. DXF drawings have material/bend controls.
- Display vs theme: the file sheet's Display tab holds per-file view state (display mode, clip, exploded view); the navbar theme button opens the theme sidebar, holding the global, persistent theme — preset, surface colors, backdrop, floor/grid, lighting, and color mode.
- Theme sidebar: a "Preset" dropdown (System, then the built-in presets, each with a two-box swatch showing its backdrop and default part colour) followed by the settings groups. Presets are read-only and there is only one custom theme: editing any setting writes it into that single custom slot and the dropdown reads "Custom", and picking a preset again is how you reset. Custom is a state, not a list entry — you leave it by choosing a preset. There is no save, restore, rename, or delete.
- Sidebars: the file sheet and the theme sidebar are mutually exclusive. Each navbar button toggles its own sidebar; opening one replaces the other, and closing one leaves nothing open.
- Copied references carry their file: the Viewer prefixes every copied ref with the shortest
  path suffix that names that file uniquely (`bracket#o1.2.f1`, or
  `starship/super_heavy#o1.3` where a filename is not unique), so a ref pasted into a prompt
  still says which model it belongs to. A `.step.py` generator shows as a bare stem — the common
  case, so it gets the shortest name — while everything else keeps its suffix (`bracket.step`,
  `plate.stl`, `plate.3mf`). That means a bare stem is NOT a literal path suffix, so resolving
  one back to a file means expanding it; the CAD skill's
  `references/inspection-and-validation.md` documents the split-and-expand steps. Bare `#...`
  refs remain valid everywhere.
- Tutorial tips: the first time a selection produces a copyable reference — a component, a subassembly, or a face/edge — a one-shot tip above the "Copy #…" button explains that references can be pasted into prompts to edit specific parts. Only its X closes it; clicking away, Escape, and reloads leave it to reappear on the next selection, and once dismissed it never returns. Append `?resetTips=1` to a Viewer URL to clear the record and re-arm every tip; the param applies once and is stripped from the address bar.
- Display tab: a "Mode" dropdown (solid/rendered/x-ray/hidden/lines/flat/wire), then Clip and Exploded as subsections of the same tab.
- Clip: X/Y/Z position sliders plus Flip and Reset, always visible — an offset of 0 means no cut.
- Exploded view: a switch beside the "Exploded" subheading pulls an assembly apart (it moves the Amount scrub to/from zero) and reveals an Amount scrub, an Automatic/Custom layout switch, a Direction dropdown (Auto/X/Y/Z/Radial), Reverse, Spread, Detail, Order, explode-line, and Reset controls, where Custom lets you edit per-part moves.
