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

Start or reuse one local CAD Viewer with `npm run agent:start`, passing the
absolute artifact directory as `--dir`. The `agent:start` launcher owns port
selection, compatible-server reuse, directory activation, and the `?dir=` query
parameter. It activates reused servers through the Viewer's lightweight
directory activation API, without requiring agents to probe ports or trigger
catalog scans manually. Use the Viewer URL printed by `agent:start` as-is, then
add only a `file=` query value for the artifact you want to review.

Choose `--dir` as the absolute directory that contains the model
artifacts and sidecars, commonly `<repo>/models` or the consuming project's
equivalent model directory. The `file=` value must be relative to that `--dir`.
Do not manually choose ports, probe servers, rewrite `?dir=`, or start a
separate Viewer just to change directories.

Always start new local Viewer servers with `--shutdown-after 12h` so forgotten
review servers clean themselves up. Do not rely on a default shutdown; the
server stays alive until stopped unless this flag or `VIEWER_SERVER_LIFETIME_MS`
is set.

Run from this skill directory:

```bash
npm --prefix scripts/viewer run agent:start -- --host 127.0.0.1 --dir <absolute-model-root> --shutdown-after 12h
```

Use the printed Viewer URL and append `file=`:

```bash
http://127.0.0.1:<printed-port>/?dir=/absolute/project/models&file=path/to/model.step
```

If a non-Viewer process or another worktree's Viewer occupies the candidate
port, the launcher will continue automatically. In sandboxed agent environments,
local binding or probe failures such as `EPERM` or `EACCES` can be expected;
rerun the same command with the needed permission/escalation.

## Links

- Return one Viewer URL per requested file.
- Start/reuse the Viewer once per absolute directory `--dir`, then append
  `file=<path>` for each requested file. The file path must be relative to
  `--dir`.
- For directory-only review links, return the URL printed by `agent:start`
  without adding `file=`.
- Do not stop an existing Viewer server unless the user asks.
- If Viewer startup fails, report the failure and continue with the owning skill's non-GUI validation or artifacts.

## References

- Read `references/development.md` when the user asks to modify, debug, or
  iterate on CAD Viewer source.
- Read `references/viewer-features.md` when you need supported file types, Viewer controls, or file-specific feature details.
- Read `references/moveit2-server.md` only when the user specifically needs optional SRDF MoveIt2 IK or path-planning controls.
