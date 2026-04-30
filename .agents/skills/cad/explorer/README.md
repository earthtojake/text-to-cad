# CAD Explorer

If you are modifying CAD Explorer, start here.

This folder contains the CAD Explorer web app. CAD Explorer is read-only with respect to files in the active CAD scan directory.

## Prompt Workflow

- CAD Explorer discovers displayable entries by scanning `EXPLORER_ROOT_DIR`, defaulting to the Vite process's current working directory when unset or empty, then loads package-local render assets and generated URDF/authored DXF XML/text from that tree.
- Prompt-ready `@cad[...]` refs are expected output from the workspace. The full grammar lives in [CAD prompt references](../references/prompt-refs.md).
- Common copied ref shapes include whole entries, occurrences, shape/face/edge/corner selectors, and grouped same-occurrence selectors, such as `@cad[<workspace-relative-cad-path>]`, `@cad[<workspace-relative-cad-path>#o1.2]`, `@cad[<workspace-relative-cad-path>#f12]`, and `@cad[<workspace-relative-cad-path>#o1.2.f12,f13,e7,v4]`.
- The path inside `@cad[...]` is relative to the Vite process's current working directory and omits `.step` or `.stp`.
- Assembly refs use generated assembly STEP topology, so face/edge/corner copy targets the assembly entry.
- Drawing tools and screenshots are communication aids, not source of truth.
- Agents interpreting `@cad[...]` refs should resolve them from source STEP data with `.agents/skills/cad/scripts/cadref/cli.py`, not against CAD Explorer assets.

## Data Model

- CAD Explorer discovers entries by scanning existing `.step`, `.stp`, `.stl`, `.3mf`, `.dxf`, and `.urdf` files. It does not inspect Python generators for discovery.
- STEP part entries load:
  - package-local `<cad-dir>/.../.<step-filename>/model.glb` for display
  - package-local `<cad-dir>/.../.<step-filename>/topology.json`
  - package-local `<cad-dir>/.../.<step-filename>/topology.bin`
- STEP assembly entries require package-local `<cad-dir>/.../.<step-filename>/model.glb`, load package-local `<cad-dir>/.../.<step-filename>/topology.json`, and read assembly composition from `assembly.root`. Generated Python assemblies link to scanned part GLBs; imported native STEP assemblies use `.<step-filename>/components/*.glb` URLs embedded in the topology composition.
- DXF entries load:
  - authored `<cad-dir>/.../*.dxf` directly
- STL entries load:
  - standalone or configured exported `<cad-dir>/.../*.stl` meshes directly
- 3MF entries load:
  - standalone or configured exported `<cad-dir>/.../*.3mf` meshes directly
- URDF entries load:
  - generated `<cad-dir>/.../*.urdf` XML directly
  - referenced URDF STL mesh filenames directly
  - optional package-local `<cad-dir>/.../.<urdf-filename>/explorer.json` metadata for defaults and poses
  - optional package-local `<cad-dir>/.../.<urdf-filename>/robot-motion/explorer.json` metadata for local motion server commands
- The CAD Explorer UI is in `components/CadExplorer.js`.
- The flat-pattern explorer UI is in `components/DxfExplorer.js`.
- The workspace UI is in `components/CadWorkspace.js`.

Do not hand-edit package-local generated CAD assets during normal CAD or CAD Explorer work.

## Persistence

- CAD Explorer persistence is browser-only and is owned by `lib/workbench/persistence.js`.
- URL query params are share state:
  - `?file=` selects the active CAD entry.
  - `?refs=` carries prompt references into the workspace.
  - `?resetPersistence=1` clears CAD Explorer browser state for the current origin, then removes itself from the URL before the app renders.
- `EXPLORER_DEFAULT_FILE` selects a default CAD entry when `?file=` is absent. Explicit `?file=` URLs are preserved when the file is missing so the workspace can show a missing-file screen.
- `sessionStorage` key `cad-explorer:workbench-session:v2` stores the scratch workspace in the canonical shape `{ version, global, tabs: { selectedKey, openOrder, byKey } }`.
- `localStorage` key `cad-explorer:workbench-global:v1` stores the global workspace state used across reloads, including search query, expanded directories, desktop/mobile sidebar and sheet states, and tool widths.
- `localStorage` key `cad-explorer:look-settings` stores visual look settings, `cad-explorer:workbench-glass-tone:v1` stores the workspace glass tone, and `cad-explorer-theme` stores the forced dark theme preference.
- `sessionStorage` key `cad-explorer:dxf-bend-overrides:v1` stores per-file DXF bend overrides for the active browser tab.
- Directory expansion no longer has a separate file-explorer storage key; it is part of workspace global state.
- React state updates immediately. Browser-storage writes are coalesced briefly and flushed on `pagehide`, `beforeunload`, and workspace unmount. If a write fails because storage is blocked or full, the workspace shows a status toast.

## Runtime

- `npm run dev` starts `vite dev`, scans `EXPLORER_ROOT_DIR` relative to the Vite process's current working directory, and updates the workspace when matching CAD files or per-STEP CAD Explorer assets are added, changed, or removed.
- `EXPLORER_DEFAULT_FILE` can be set to a scan-root-relative file path, including extension, to open that entry by default when the URL has no `?file=`.
- `EXPLORER_GITHUB_URL` sets the top-bar GitHub button target and defaults to `https://github.com/earthtojake/text-to-cad`.
- URDF CAD Explorer defaults and poses load from `.<urdf>/explorer.json`. In local Vite dev only, IK and path-planning controls load from optional `.<urdf>/robot-motion/explorer.json` and use a separately started local motion websocket server. Vite never starts Python or ROS.
- In local Vite dev, the browser connects to `EXPLORER_ROBOT_MOTION_WS_URL` when set, otherwise `ws://127.0.0.1:8765/ws`; `?motionWs=` can override the websocket URL for a single browser session. Production builds disable motion server connections.
- Start the motion server with `.agents/skills/robot-motion/scripts/run-motion-server.sh`. Plain URDF entries never contact the motion server.
- `npm run build` scans `EXPLORER_ROOT_DIR`, defaulting to the Vite process's current working directory when unset or empty, and bakes that scan into the static app.
- Production builds read `EXPLORER_DEFAULT_FILE`, `EXPLORER_GITHUB_URL`, `EXPLORER_ROOT_DIR`, and `EXPLORER_WORKSPACE_ROOT` at build time. If the build command runs from `.agents/skills/cad/explorer`, CAD Explorer falls back to the containing workspace root; set `EXPLORER_WORKSPACE_ROOT=/path/to/workspace` explicitly when your deployment builds from a different directory layout.
- `npm run build:app` runs an isolated verification build for CAD Explorer-only changes.
- Regenerate CAD assets outside the CAD Explorer package before these commands when CAD assets need to change.

## Hot Reload

- Real-time dev updates come from the Vite CAD catalog endpoint and websocket events, not browser polling.
- When external tools add, remove, or update `.step`, `.stp`, `.stl`, `.3mf`, `.dxf`, `.urdf`, `.<step-filename>/*.glb`, `.<step-filename>/topology.json`, `.<step-filename>/topology.bin`, or URDF CAD Explorer metadata files under an active scan directory, Vite asks the client to rescan and remount the workspace.

## UX Contract

- STEP part and assembly entries expose face/edge/corner picking from selector proxy geometry.
- Shape and occurrence refs are exposed through inspector state, not a separate canvas pick mode.
- DXF entries are read-only flat-pattern views.
- URDF entries are read-only robot views with joint sliders; entries with robot-motion metadata and a live local motion server may expose pose solving or path-planning controls. They do not expose picking, refs, or drawing tools.
- File pickers use canonical suffix labels: STEP parts and assemblies show `.step`, STL entries show `.stl`, 3MF entries show `.3mf`, URDF entries show `.urdf`, and DXF entries show `.dxf`.
- The workspace selects one file at a time. Per-file view, reference, drawing, and tool state is still restored from the existing session `tabs` state when a file is selected again.
- Sidebar grouping follows the exact directory structure under the active scan directory, not hardcoded part/assembly roots.

## Verification For CAD Explorer Changes

- For pure CAD Explorer changes, run `cd .agents/skills/cad/explorer && npm run build:app`.
- Run `cd .agents/skills/cad/explorer && npm run test:node` when the change touches explorer logic, parsing, persistence, catalog scanning, selectors, or kinematics.
- Run `npm --prefix .agents/skills/cad/explorer exec vite -- build --config .agents/skills/cad/explorer/vite.config.mjs` from the workspace you want to scan when you need the normal production `dist/` output for the current generated CAD snapshot.
- If the change depends on fresh CAD-derived assets, regenerate the affected entries separately with `.agents/skills/cad/scripts/gen_step_part/cli.py`, `.agents/skills/cad/scripts/gen_step_assembly/cli.py`, `.agents/skills/cad/scripts/gen_dxf/cli.py`, or `.agents/skills/urdf/scripts/gen_urdf/cli.py` before explorer verification.
- For render-contract changes, inspect the relevant package-local `.<step-filename>/model.glb`, `.<step-filename>/topology.json`, `.<step-filename>/topology.bin`, native assembly `.<step-filename>/components/*.glb` meshes, visible `.stl`, visible `.3mf`, visible `.dxf`, or visible `.urdf` files.

## Run

From the workspace root:

```bash
npm --prefix .agents/skills/cad/explorer install
npm --prefix .agents/skills/cad/explorer run dev:ensure
```

Then open:

- `http://localhost:4178`
