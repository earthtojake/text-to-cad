# CAD Viewer Features

Load this only when a task needs Viewer file-support details or UI control guidance.

## Supported Files

- `.step`, `.stp`: STEP/STP review through the document's tree in the store (compiled from the file's bytes on open when missing); supports assembly trees, part hide/show, inspect/focus, face/edge/vertex/part selection, copied `#...` CAD references, display modes, clip planes, and live pose sliders and animation clips when the model's sidecar declares kinematics or animation.
- `.stl`, `.3mf`, `.glb`: mesh viewing with orbit/pan/zoom, screenshots, and the Display tab's shading modes. Measure snaps to triangle vertices only (two clicks, distance in mm) — not STEP faces/edges. A plain GLB's `COLOR_0` vertex colors render as source colors, exactly like authored material colors; a GLB carrying embedded animation gets an Animation tab of its own.
- `.dxf`: read-only 3D flat-pattern viewing. The drawing file is parsed directly and rendered client-side — no render artifact exists for a `.dxf`, so generated and imported drawings alike render straight from their own bytes.
- `.urdf`: robot link/mesh viewing with movable joint sliders, reset pose, and copied joint values.
- `.srdf`: paired-URDF viewing with planning groups, group-state presets, and joint controls.
- `.sdf`: SDF model/world viewing with metadata, counts, warnings, and joint controls when available.

## Controls

- Navigation: left-drag to orbit, right/middle-drag to pan, wheel or pinch to zoom, and Arrow/WASD keys to orbit. Use the view sphere for top/bottom/front/back/left/right views; click its center for the default isometric view.
- File browser: toggle the left CAD Viewer sidebar, search files/ids/paths, expand folders, select entries, or switch files from the breadcrumb menus.
- File names read exactly as they do on disk. The tab title, breadcrumb, catalog rows and the file picker all show the artifact's own basename and its own path — `moonwatch.step`, never the `moonwatch.py` that generated it. The Viewer never learns whether a document was generated: its status badge is one of not compiled / compiling / rendered / failed, decided from the file's bytes, the store and the build pool's job ledger, and no part of the UI names or opens a model script. (Copied topology references are the one exception, and a deliberate one: see the bare-stem rule below.)
- Floating toolbar: `Select` copies STEP topology references, `Pan` drags the camera, `Measure` picks measurement points (only offered where the view can measure — a robot description has no Measure button), `Draw` opens annotation tools, `Play`/`Pause` appears when the model has animation clips, and `Copy screenshot` puts a viewport capture on the clipboard — screenshots are clipboard-only; nothing downloads. DXF drawings get their own 2D/3D view pill beside the toolbar. The toolbar's rightmost `Fullscreen` button hands the model the whole window and auto-rotates it; the toolbar there keeps playback, capture and an `Exit fullscreen` button, and auto-hides until the pointer reaches it.
- File context menu (file browser rows and the breadcrumb): `Reveal in Explorer View` highlights the entry in the file browser, and the copy items hand out references to the file — `Copy Filename`, `Copy Path` (absolute), `Copy Relative Path` (relative to the served directory), and `Copy Link`, which copies the viewer deep link for the entry (the bare origin plus `?file=<root-relative path>`, byte-identical to the URL the app itself lands on). There is no download and no native file-manager reveal; paths and links are how bytes leave the Viewer.
- Drawing tools: freehand, line, arrow, expand, rectangle, circle, fill, erase, undo, redo, and clear.
- File sheet: open the right sheet for file-specific tabs. In Inspect, STEP files get Tree and Reference, then a Kinematics tab when the document's sidecar declares kinematics, an Animation tab when that sidecar embeds animation — its load errors (a syntax error, an export the renderer does not know) and any clip target the compiled tree does not carry are reported in that tab — then Measure and Display. In Kinematics, a DOF that exactly one coupling gears is marked "driven by <coupling>": its slider shows the effective value and drags the coupling, so sliding one member of a gear train turns the whole train. In Animation, the "Clip" dropdown lists the model's authored clips and nothing else, opening on the first one; the section header's switch turns animation off, which idles the transport so the model holds the Kinematics tab's pose, and Play turns it back on. URDF/SRDF/SDF files get joints (and an SDF tab for SDF metadata) plus Display. Mesh files show a Measure tab for vertex-to-vertex distance plus Display. DXF drawings get Material, Bends when the drawing has bend lines, and Layers when it uses layers.
- Viewing mode: the navbar's viewing-mode dropdown switches the whole workspace between `Inspect` and `Render`. Inspect is the CAD view — the Display tab's shading modes, inspection colors, guides, edges and clip. Render is the photographic view, and it replaces the Inspect settings tabs with `Studio` (setup, camera, lighting, backdrop) and `Materials`; Kinematics and Animation stay available in both. There is no theme sidebar and no theme preset list: scene settings live in these tabs.
- Copied references carry their file: the Viewer prefixes every copied ref with the shortest
  path suffix that names that file uniquely (`bracket#o1.2.f1`, or
  `lyra/STEP/palm.step#o1.3` where a filename is not unique), so a ref pasted into a prompt
  still says which model it belongs to. A generated model shows as a bare stem — the common
  case, so it gets the shortest name — while everything else keeps its suffix (`bracket.step`,
  `plate.stl`, `plate.3mf`). That means a bare stem is NOT a literal path suffix, so resolving
  one back to a file means expanding it; the CAD skill's
  `references/inspection-and-validation.md` documents the split-and-expand steps. Bare `#...`
  refs remain valid everywhere.
- Tutorial tips: the first time a selection produces a copyable reference — a component, a subassembly, or a face/edge — a one-shot tip above the "Copy #…" button explains that references can be pasted into prompts to edit specific parts. Only its X closes it; clicking away, Escape, and reloads leave it to reappear on the next selection, and once dismissed it never returns. Append `?resetTips=1` to a Viewer URL to clear the record and re-arm every tip; the param applies once and is stripped from the address bar.
- Display tab: a "View" subsection holding the "Mode" dropdown (Shaded with edges / Shaded / X-Ray / Hidden / Lines / Flat / Wire) and the Exploded slider, then Camera (projection), Inspection colors, Guides (grid, origin axes), Edges, and Clip.
- Exploded view: one percentage slider — 0% is assembled, and any higher value pulls the assembly apart. It is disabled for a document with fewer than two explodable parts.
- Clip: a Flip toggle and X/Y/Z position sliders, always visible — a slider at 0 means no cut on that axis.
