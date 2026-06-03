---
name: cad-viewer
description: Start or reuse CAD Viewer and return review links for explicit CAD, implicit CAD, robot-description, and G-code files. Use when visually reviewing `.step`, `.stp`, `.implicit.js`, `.implicit.mjs`, `.glb`, `.stl`, `.3mf`, `.gcode`, `.dxf`, `.urdf`, `.srdf`, or `.sdf` files, especially when handed off from CAD, implicit-cad, G-code, URDF, SRDF, or SDF generation skills.
---

# CAD Viewer

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

Use this skill to open existing or newly generated CAD, implicit CAD,
robot-description, DXF, or plain FDM G-code files in CAD Viewer and hand back
live review links. The expected input is one or more explicit file paths.

## Start Viewer

Start or reuse one local CAD Viewer with `npm run agent:start`, then select
local files by URL. The launcher uses Vite dev mode when this skill's
`scripts/viewer` path is a development symlink, and the packaged `dist/` server
for production skill installs. Every Viewer link returned from this skill MUST
include `?dir=` with an absolute path. Set `?dir=` to the workspace-local
artifact root that owns the model files and related sidecars, usually the
project `models/` directory, such as `/Users/name/project/models`. This root
should be the shared directory containing STEP/STL/GLB/URDF/SRDF/SDF/G-code/DXF
files, not a relative path and not just the selected file's parent when a
broader model workspace root exists. The `?file=` value must be relative to
`?dir=`; choose a `?dir=` root that makes the relative `?file=` stable and
readable. The `agent:start` launcher
owns port selection: it starts from its requested or default port candidate,
checks the local CAD Viewer server registry, probes candidate ports with
`GET /__cad/server`, reuses a compatible live Viewer when found, or starts a new
Viewer on the first free port. When git is available, the launcher passes a
single `git` value derived from the worktree git dir and branch; a live Viewer
with a different `git` value is treated as another worktree or branch and
skipped. If either side has no `git` value, git is not used as a port reuse
condition.

If you need to inspect a running server manually, `GET /__cad/server` returns
JSON with `app: "cad-viewer"`, `dynamicRoot: true`, `serverApiVersion >= 2`,
`viewerVersion`, an optional `git` value, and the selected `port`. Treat a legacy
root-bound CAD Viewer without the dynamic-root fields as incompatible because
returned links must support absolute `?dir=` values and relative `?file=` values
inside that root.

Always start new local Viewer servers with `--shutdown-after 12h` so forgotten
review servers clean themselves up. Do not rely on a default shutdown; the
server stays alive until stopped unless this flag or `VIEWER_SERVER_LIFETIME_MS`
is set.

Do not manually choose or increment ports. Run `agent:start`, use the base URL
it prints, and append the requested absolute `?dir=` plus a `?file=` relative
to `?dir=`. Do not start a separate Viewer just to change
directories; the same local server can scan a new absolute `?dir=`.

Run from this skill directory:

```bash
npm --prefix scripts/viewer run agent:start -- --host 127.0.0.1 --shutdown-after 12h
```

Use the printed base URL and append query parameters:

```bash
http://127.0.0.1:<printed-port>/?dir=/absolute/workspace/models&file=path/to/model.step
```

Use the base URL printed by `agent:start`. If a non-Viewer process or another
worktree's Viewer occupies the candidate port, the launcher will continue to
the next port automatically. In sandboxed agent environments, local binding
failures such as `EPERM` or `EACCES` can be expected; rerun the same command
with the needed permission/escalation.

## Links

- Return the printed Viewer link for each requested file.
- If a compatible Viewer server is already running, reuse its port and vary the
  `?dir=`/`?file=` query only.
- ALWAYS include `?dir=<absolute-model-root>` on every returned Viewer link.
  This is mandatory for cad-viewer handoffs: do not omit it for convenience, do
  not use a relative path, and do not rely on the Viewer's session-storage
  `?dir=` fallback.
- Choose `?dir=` as the absolute workspace folder that contains the model
  artifacts, commonly `<repo>/models` or the consuming project's equivalent
  model directory.
- Include `file=<path>` for each requested file, one URL per file. The file path
  must be relative to `?dir=`. For directory-only review links, include
  `?dir=<absolute-root>` without `file=`.
- Do not stop an existing Viewer server unless the user asks.
- If Viewer startup fails, report the failure and continue with the owning skill's non-GUI validation or artifacts.

## References

- Read `references/development.md` when the user asks to modify, debug, or
  iterate on CAD Viewer source.
- Read `references/viewer-features.md` when you need supported file types, Viewer controls, or file-specific feature details.
- Read `references/moveit2-server.md` only when the user specifically needs optional SRDF MoveIt2 IK or path-planning controls.
