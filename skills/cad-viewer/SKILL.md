---
name: cad-viewer
description: Start CAD Viewer and return review links for explicit CAD, implicit CAD, and robot-description files. Use when visually reviewing `.step`, `.stp`, `.implicit.js`, `.implicit.mjs`, `.glb`, `.stl`, `.3mf`, `.dxf`, `.urdf`, `.srdf`, or `.sdf` files, especially when handed off from CAD, implicit-cad, URDF, SRDF, or SDF generation skills.
---

# CAD Viewer

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review. If the user asks to
modify, debug, or iterate on CAD Viewer source itself, clone that repository and
work there — this installed skill runtime runs the Viewer, it is not where you
edit it.

Use this skill to open existing or newly generated CAD, implicit CAD,
robot-description, or DXF files in CAD Viewer and hand back live review links. The expected input is one or more explicit file paths.

## Start Viewer

Start one local CAD Viewer with `npm run start`. It serves the prebuilt Viewer
bundle plus the CAD API on a single fixed port (`3245`). It is NOT started
against a directory — a URL names the directory, so one Viewer serves any folder.

> The default port `3245` is `0xCAD` — "CAD" in hexadecimal.

Run from this skill directory:

```bash
npm --prefix scripts/viewer run start -- --host 127.0.0.1
```

## URL shape

A Viewer URL's **path is the absolute directory**, exactly as in a `file://` URL,
and `file=` selects one artifact inside it:

```text
http://127.0.0.1:3245/absolute/project/models?file=mechanisms/lift_table.step.py
```

**Always build the path from an absolute directory.** The Viewer runs from an
arbitrary working directory — usually wherever the skill happens to be installed,
not the model directory — so a relative path resolves against the wrong place.
The `file=` value is relative to that directory.

**On Windows the drive goes in the path, after the URL's leading slash**, with
forward slashes: `D:\project\models` is `http://127.0.0.1:3245/D:/project/models`.
The launcher prints this form already; build it the same way by hand.

**The path is the workspace, not the file's folder.** The Viewer scans it
recursively, so the file browser lists every model beneath it and the user can
switch files without a new link. Pick the directory the user thinks of as their
model workspace — typically the project's `models/` directory, or the nearest
common parent of the files you were asked to review — and put the rest of the
path in `file=`. Naming the artifact's own deep folder
(`.../models/step/mechanisms?file=lift_table.step.py`) opens the same model but hides
the rest of the project, which is almost never what the user wants.

If port `3245` is already in use, the launcher exits with an error rather than
rolling to another port; rerun with an explicit free port, `--port <n>`, and use
the URL it prints. In sandboxed agent environments, local binding failures such
as `EPERM`/`EACCES` can be expected; rerun with the needed permission/escalation.

Add `--json` to also print a machine-readable result as the last stdout line
beginning with `{` (`{"url": ..., "port": ..., "action": "start"}`). The printed
URL points at the launch directory; replace its path to review any other folder.

## Links

- Before returning any link, resolve `<directory>/<file>` and confirm it
  exists. For a **generated** model pass the generator source (`<name>.step.py`)
  — that is what the catalog itself lists, the backend resolves it directly and
  builds the render artifacts on demand, and no `.step` file needs to exist. It
  is also the only form that carries a `params` sidecar, because a same-stem
  `<name>.step.py` shadows `<name>.step` anyway. For an **imported** STEP with no
  generator, pass the `.step`/`.stp` itself. If the resolved path is missing, do
  not return the link; report the problem and point to the correct path.
- Return one Viewer URL per requested file.
- Start the Viewer once and pick one workspace root for the session. Every link
  is that same absolute root plus `?file=<path relative to it>`, so all of them
  share one browsable catalog. Only use a second root for an artifact that lives
  outside the first.
- For directory-only review links, return the directory URL without `?file=`.
- Do not stop an existing Viewer server unless the user asks.
- If Viewer startup fails, report the failure and continue with the owning skill's non-GUI validation or artifacts.

## References

- Read `references/viewer-features.md` when you need supported file types, Viewer controls, or file-specific feature details.
- Read `references/moveit2-server.md` only when the user specifically needs optional SRDF MoveIt2 IK or path-planning controls.
