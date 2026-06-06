# CAD Viewer Features

Load this only when a task needs Viewer file-support details or UI control guidance.

## Supported Files

- `.step`, `.stp`: STEP/STP review through hidden GLB sidecars; supports assembly trees, part hide/show, inspect/focus, face/edge/vertex/part selection, copied `#...` CAD references, display modes, clip planes, and optional STEP module parameters/animations when a sidecar module exists.
- `.stl`, `.3mf`, `.glb`: mesh viewing with orbit/pan/zoom, screenshots, appearance controls, and solid/wireframe display where available.
- `.dxf`: read-only flat-pattern viewing, plus plate thickness and bend direction/angle controls when bend preview data is available.
- `.gcode`: diagnostic toolpath preview; shows layer-colored extrusion ribbons, optional travel moves, visible-layer and detail controls, feature markers, movement stats, bounds, and parser warnings. It does not reslice, simulate firmware, or replace G-code validation.
- `.urdf`: robot link/mesh viewing with movable joint sliders, reset pose, and copied joint values.
- `.srdf`: linked-URDF viewing with planning groups, group-state presets, joint controls, and optional MoveIt2 IK/planning controls.
- `.sdf`: SDF model/world viewing with metadata, counts, warnings, and joint controls when available.

## Controls

- Navigation: left-drag to orbit, right/middle-drag to pan, wheel or pinch to zoom, and Arrow/WASD keys to orbit. Use the view sphere for top/bottom/front/back/left/right views; click its center for the default isometric view.
- File browser: toggle the left CAD Viewer sidebar, search files/ids/paths, expand folders, select entries, or switch files from the breadcrumb menus.
- Floating toolbar: `Select` copies STEP topology references, `Draw` opens annotation tools, `Select Pose` appears for robot target picking when available, `Open orbit preview` starts an auto-rotating preview, and the copy/download buttons capture screenshots.
- Drawing tools: freehand, line, arrow, expand, rectangle, circle, fill, erase, undo, redo, and clear.
- File sheet: open the right sheet for file-specific controls such as STEP tree/parameters, G-code layers/detail/travel, DXF thickness/bends, URDF/SRDF/SDF joints and metadata, plus display and appearance controls.
- Display/appearance: use the file sheet and theme menu for solid/wireframe mode, STEP clipping, surface colors, edge visibility/detail, highlight styling, backdrop, floor/grid, lighting, theme presets, and color mode.
