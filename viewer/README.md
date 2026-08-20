# CAD Viewer

CAD Viewer is a browser workbench for inspecting CAD files,
robot-description files, and generated CAD artifacts from a URL-selected local
directory or hosted catalog. It is built for engineering review loops where you
need to open a model quickly, understand the source tree, copy stable `#...`
CAD references, and verify generated assets without leaving the browser.

## Features

- Scans the local directory named by the URL's path and mirrors its folder
  structure in the sidebar.
- Opens `.step`, `.stp`, `.stl`, `.3mf`, `.glb`, `.dxf`, `.urdf`, `.srdf`,
  and `.sdf` entries.
- Uses hidden STEP GLB/topology sidecars for assembly structure, face/edge
  picking, copied CAD references, and STEP parameter controls.
- Previews mesh files, DXF flat patterns, URDF/SDF robots, and SRDF group
  states in one app shell.
- Runs against either a local filesystem backend or hosted Vercel Blob storage.
- Can regenerate STEP GLB/topology artifacts and generated-DXF drawing
  packages when the CAD Python runtime is
  available.
- Provides optional MoveIt2 websocket controls for SRDF IK and planning.

## Quick Start

Run these commands from this directory:

```bash
npm install
npm run test
npm run build
```

For local development, start the dev server and then pass a local directory and
directory-relative file path in the URL:

```bash
npm run dev -- --host 127.0.0.1
```

Open the URL printed by Vite. A Viewer URL's PATH is the absolute directory to
open, exactly as in a `file://` URL, and `?file=` selects one artifact within it:

```text
http://127.0.0.1:3245/path/to/root?file=assemblies/robot-arm/robot-arm.step
```

The bare origin names no directory and falls back to the server's cwd. One Viewer
serves any folder — change the path, no restart.

Use `npm run dev` for iterating on the client/backend (HMR), and `npm run start`
to serve the built `dist/` bundle via the Python backend (the production path the
`cad-viewer` skill uses). Both listen on `--port`, defaulting to `3245`, and both
exit with an error when that port is taken rather than reusing a running Viewer or
rolling onto another port. Local dev and production servers stay running unless
`VIEWER_SERVER_LIFETIME_MS` is set or production `serve` is started with
`--shutdown-after <duration>`.

Install the local Python artifact package when iterating on local STEP
regeneration:

```bash
python -m pip install -r requirements.txt
```

Agent handoff links from the cad-viewer skill must use an absolute directory as
the URL path, with `?file=` relative to it. The URL is the only source of truth —
there is no stored fallback, so the same URL always shows the same thing.

## Project Layout

- `src/client/`: React app, browser state, styling, and viewer + workbench UI.
- `src/client/components/`: top-level CAD, DXF, workbench, and shadcn-style UI
  components.
- `src/client/workbench/`: selection, persistence, file-sheet, alert, motion,
  and reference helpers that are not React components.
- `src/client/ui/`: viewer-owned browser utilities such as clipboard, color
  scheme, class merging, and DOM helpers.
- `src/shared/`: config helpers shared by the client and the launchers.
- `server_py/`: the Python backend — local filesystem CAD API (`/__cad/*`),
  artifact generation, and the production static server for `dist/`.
- `scripts/`: developer and runtime launchers, the test runner, and the
  end-to-end sweeps.
- `docs/`: workflow reference docs for backend storage, browser persistence,
  render types, settings UI, and MoveIt2.
- `moveit2_server/`: optional Python websocket backend for SRDF controls.
- `packages/cadjs`, `packages/implicitjs`, `packages/cadgen`: the shared
  runtimes this app depends on. Keep reusable parsing, rendering, sidecar,
  selector, topology, implicit shader, snapshot, and export logic in these
  packages rather than in `src/`.

`packages/*` is a symlinked development layout inside the text-to-cad workbench
and a real vendored copy in a standalone checkout; every path in this app is
written to work either way.

## Common Commands

```bash
npm run dev          # Vite dev server (HMR) + local CAD API middleware — use for iteration
npm run build        # Production frontend build (writes dist/)
npm run start        # Prod launcher: serve the built dist/ + CAD API on 3245 (or --port)
npm run serve        # Low-level raw Python backend (what `start` spawns)
npm run test         # Discover and run all JS tests
```

`npm run test` uses `scripts/run-tests.mjs`, which discovers
`*.test.js` and `*.test.mjs` under `src/` and `scripts/`. To run specific tests:

```bash
node scripts/run-tests.mjs src/client/workbench/sidebar.test.js
node scripts/run-tests.mjs src/shared/viewerConfig.test.mjs
```

Python backend tests run separately:

```bash
python -m unittest discover -s server_py/tests -t .
```

## Runtime Configuration

Important environment variables:

- `VIEWER_DEFAULT_FILE`: directory-relative file opened when `?file=` is absent.
- `VIEWER_SERVER_LIFETIME_MS`: optional server lifetime in milliseconds for
  local dev and production servers. When unset, there is no automatic shutdown.
- `VIEWER_GITHUB_URL`: optional top-bar GitHub link target. When set, the
  version label links to the matching GitHub release tag. For GitHub-hosted
  repositories, the Viewer also checks the latest release and lightly marks the
  version label when a newer release is available.
- `VIEWER_DISCORD_URL`: optional top-bar Discord community link target.
- `VIEWER_ALLOWED_HOSTS`: extra hostnames accepted by local Vite dev and
  production servers.
- `VIEWER_MOVEIT2_WS_URL`: optional websocket URL for SRDF MoveIt2 controls.
- `VIEWER_CAD_PYTHON`: optional Python executable for local STEP/DXF artifact regeneration.
- `VIEWER_CAD_PYTHONPATH` / `CAD_PYTHONPATH`: optional Python source path for
  the `cadgen` package.

`VIEWER_LOCAL_ROOT_DIR` and `VIEWER_LOCAL_WORKSPACE_ROOT` are removed for local
filesystem viewing. Setting either variable is a hard startup error; the URL's
path names the directory instead.

Production builds contain the frontend and initial catalog module only. CAD
assets are served by the local backend and are not copied into `dist/`.

## Reference Docs

- [Settings UI guidelines](./docs/settings-ui.md): the mandatory row grammar,
  spacing, and control standards for file-sheet and theme settings panels.
- [Backend storage](./docs/backend.md): local filesystem backend contracts.
- [Browser storage](./docs/storage.md): URL, `localStorage`, and
  `sessionStorage` ownership.
- [MoveIt2 server](./docs/moveit2-server.md): optional SRDF websocket backend.
- [`cadjs` render pipeline](./packages/cadjs/docs/render-pipeline.md): shared
  render APIs used by the viewer, docs, and snapshot runtime.
- [`implicitjs` runtime](./packages/implicitjs/README.md): shared implicit CAD
  model, shader render, snapshot, and export APIs.

## Verification

Run the focused viewer checks before handing off viewer changes:

```bash
npm run test
npm run build
```

For UI behavior changes, also run `npm run dev -- --host 127.0.0.1`, open the
printed URL with `/absolute/root?file=path/to/model.step`, and check that the app
renders, selection works, and the browser console is clean.
