---
name: cad-viewer
description: Start or reuse CAD Viewer and return review links for explicit CAD, robot-description, and G-code files. Use when visually reviewing `.step`, `.stp`, `.glb`, `.stl`, `.3mf`, `.gcode`, `.dxf`, `.urdf`, `.srdf`, or `.sdf` files, especially when handed off from CAD, G-code, URDF, SRDF, or SDF generation skills.
---

# CAD Viewer

Release version: `0.1.12`.
Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

Use this skill to open existing or newly generated CAD, robot-description, DXF, or plain FDM G-code files in CAD Viewer and hand back live review links. The expected input is one or more explicit file paths.

## Start Viewer

Start or reuse one packaged CAD Viewer server with `npm run serve`, then select
local files by URL. Every Viewer link returned from this skill MUST include
`?dir=` with an absolute path. Set `?dir=` to the workspace-local artifact root
that owns the model files and related sidecars, usually the project `models/`
directory, such as `/Users/name/project/models`. This root should be the shared
directory containing STEP/STL/GLB/URDF/SRDF/SDF/G-code/DXF files, not a relative
path and not just the selected file's parent when a broader model workspace root
exists. Always begin at port `4178`.

Probe each candidate port with `GET /__cad/server`. If the response is JSON
with `app: "cad-viewer"`, `dynamicRoot: true`, and `serverApiVersion >= 2`,
reuse that base URL. The response also includes `viewerVersion` for sanity
checking the running build. If the response is a legacy root-bound CAD Viewer
without those fields, treat it as incompatible and try the next port because
returned links must use absolute `?dir=` and `?file=` values. If the port is
occupied by something else, increment the port and probe again. If the port is
closed, start the packaged server on that port.

Legacy fixed-root startup flags and old local root environment variables have
been removed. Do not use fixed-root startup configuration; use absolute `?dir=`
links instead.

Always start new local Viewer servers with `--shutdown-after 12h` so forgotten
review servers clean themselves up. Do not rely on a default shutdown; the
server stays alive until stopped unless this flag or `VIEWER_SERVER_LIFETIME_MS`
is set.

If the user has a Viewer URL open, treat that port as the first reuse candidate.
Return a URL on that same port whenever it can serve the requested absolute
`?dir=`/`?file=`. Do not start a separate Viewer just to change directories;
the same local server can scan a new absolute `?dir=`.

Run from this skill directory:

```bash
npm --prefix scripts/viewer run serve -- --host 127.0.0.1 --port 4178 --shutdown-after 12h
```

Use the printed base URL and append query parameters:

```bash
http://127.0.0.1:4178/?dir=/absolute/workspace/models&file=/absolute/workspace/models/path/to/model.step
```

If a non-Viewer process occupies the candidate port, rerun `serve` with the next
available `--port <number>`. In sandboxed agent environments, local binding
failures such as `EPERM` or `EACCES` can be expected; rerun the same command
with the needed permission/escalation.

## Claude Preview

When running in Claude Code Desktop, check the workspace `.claude/launch.json`.
If it does not already contain a CAD Viewer preview configuration, add one and
preserve every existing configuration. The preview config should start this
packaged Viewer, use the same selected port as the returned links, and keep
`autoPort: false` so Claude does not silently move the Viewer to a different
port. Use an absolute path to this skill's `scripts/viewer` directory in
`npm --prefix`, or set the preview `cwd` to this skill directory before running
the same `npm --prefix scripts/viewer run serve -- --host 127.0.0.1 --port
<port> --shutdown-after 12h` command.

Example configuration entry:

```json
{
  "name": "cad-viewer",
  "runtimeExecutable": "npm",
  "runtimeArgs": [
    "--prefix",
    "/absolute/path/to/cad-viewer/scripts/viewer",
    "run",
    "serve",
    "--",
    "--host",
    "127.0.0.1",
    "--port",
    "4178",
    "--shutdown-after",
    "12h"
  ],
  "port": 4178,
  "autoPort": false
}
```

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
- Include `file=<absolute-file>` for each requested file, one URL per file. For
  directory-only review links, include `?dir=<absolute-root>` without `file=`.
- Return file-only links with no `?dir=` only when the user explicitly asks to
  test the Viewer's no-directory/file-only mode.
- Do not stop an existing Viewer server unless the user asks.
- If Viewer startup fails, report the failure and continue with the owning skill's non-GUI validation or artifacts.

## References

- Read `references/development.md` when the user asks to modify, debug, or
  iterate on CAD Viewer source.
- Read `references/viewer-features.md` when you need supported file types, Viewer controls, or file-specific feature details.
- Read `references/moveit2-server.md` only when the user specifically needs optional SRDF MoveIt2 IK or path-planning controls.
