---
name: cad-viewer
description: Start CAD Viewer and return review links for CAD and robot-description files. Use when visually reviewing `.step`, `.stp`, `.glb`, `.stl`, `.3mf`, `.dxf`, `.urdf`, `.srdf`, or `.sdf` files, especially when handed off from CAD, URDF, SRDF, or SDF generation skills.
---

# CAD Viewer

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review. If the user asks to
modify, debug, or iterate on CAD Viewer source itself, that is the repository's
work, not this skill's — this skill runs the Viewer, it is not where you edit it.

Use this skill to open existing or newly generated CAD,
robot-description, or DXF files in CAD Viewer and hand back live review links. The expected input is one or more explicit file paths.

## Setup

The Viewer is part of `cadgen`: install this skill's `requirements.txt` into a
Python >= 3.11 and the `cadgen` command carries the server and the prebuilt
client. There is nothing else to install and no Node at run time.

```bash
python -m pip install -r requirements.txt
```

`cadgen doctor <this skill's directory>` confirms the installed cadgen matches
the version this skill was published against.

## Start Viewer

Launching is unconditional: the command below always ends with the URL of a
live Viewer for the launch directory. If one is already running for that
directory with the same Viewer code on disk (the reuse key is
realpath(directory) x an identity token — the cadgen version salted with the
Viewer files' newest mtime, so an upgraded Viewer never hands back a stale
instance), its URL is returned (`"action": "reused"`);
otherwise a new server starts on the first free port from `3245` upward
(`"action": "started"`). Never pick or reason about ports — read the URL the
command prints. Each instance serves ONE directory — the directory it is
launched from — fixed for the life of the process. There is no flag for it:
the cwd IS the served directory.

> The base port `3245` is `0xCAD` — "CAD" in hexadecimal.

```bash
cd /absolute/project/models && cadgen viewer --host 127.0.0.1 --json
```

(`cadgen` must be the one installed from this skill's `requirements.txt`. If it
is not on `PATH`, `python -m cadgen.viewer` with that interpreter is the same
launcher.)

**Choose the launch directory deliberately — it is the whole ballgame.** The
cwd decides what the catalog SCANS (a project root drags in `node_modules`,
`.git` and build output) and it is the instance REUSE key, so launching from
wherever you happen to be can hand back a Viewer serving somewhere else. `cd`
to the directory the user thinks of as their model workspace — usually the
project's `models/` directory — and launch from there. Never launch from
inside this skill's directory: that serves the skill, not the models.

Flags: `--json` prints the machine-readable last stdout line
(`{"url", "port", "action": "started"|"reused"}`) — always pass it and take the
URL from there. `--new` forces a fresh instance instead of reusing. An
explicit `--port <n>` is strict — "this port or fail" — and disables
both reuse and rolling. `cadgen viewer --help` lists the rest.

## URL shape

The page is the bare origin, and `file=` selects one artifact inside the served root:

```text
http://127.0.0.1:3245/?file=gripper/STEP/gear_rack_gripper.step
```

The `file=` value is relative to the served directory. Nothing about the
directory appears in the URL, so the same link means different files under
different instances — the root is the server's, not the link's.

**The launch directory is the workspace, not the file's folder.** The Viewer
scans it recursively, so the file browser lists every model beneath it and the
user can switch files without a new link. Launch from the directory the user
thinks of as their model workspace — typically the project's `models/`
directory, or the nearest common parent of the files you were asked to review —
and put the rest of the path in `file=`. Launching from the artifact's own deep
folder (`cd .../models/gripper/STEP`, `?file=gear_rack_gripper.step`) opens
the same model but hides the rest of the project, which is almost never what
the user wants.

Port collisions are not your problem: the launcher rolls to a free port and the
URL it prints is the truth. In sandboxed agent environments, local binding
failures such as `EPERM`/`EACCES` can still occur; rerun with the needed
permission/escalation.

`cadgen viewer list` shows every running instance with the directory it
serves; `cadgen viewer stop --port <n>` ends one. (Both run from anywhere —
only launching cares about the cwd.)
To review a directory outside the current root, just `cd` there and launch
again — reuse-or-start makes the second launch cheap and correct.

## Generation is the CAD skill's job; documents compile in the Viewer

The Viewer is a static visualization tool: it renders artifacts that already
exist. Generated models must be built first by running their model script (see
the CAD skill); the Viewer never runs a script and never learns whether a
document has one.

A `.step`/`.stp` document's status in the Viewer is one of four, decided from
the file's bytes and the store alone: **not compiled** (the store has no tree
for these bytes — the Viewer offers to compile, and compiles on open),
**compiling · <phase> n/total** (a job in cadgen's build pool is producing a
tree whose outputs include this document — the Viewer's own compile, a
`python model.py` in a terminal, or a parent's child build alike),
**rendered**, or **failed** (the last job for it failed; the message is shown).
A compile is a job submitted to the same pool every cadgen door uses, so
progress and errors come back as data. There is no "stale vs source" state:
whether a document is behind its script is `cadgen store why`'s question, not
the Viewer's. When an agent is doing the work there is nothing to run first:
just use the file and return the link.

## Links

- Before returning any link, resolve `<directory>/<file>` and confirm it
  exists. Pass the `.step`/`.stp` artifact itself — generated and imported
  alike. The catalog lists artifacts and names them exactly as they read on
  disk: `moonwatch.step` is `moonwatch.step` in the tab, the breadcrumb, the
  catalog row and the file picker, whether it was generated or imported.
  The Viewer never learns whether a document was generated: its status is
  artifact-side only (not compiled / compiling / rendered / failed), and the
  model script is not shown anywhere in the UI. A generated model's document
  must already exist (run the model script); a document the store has no tree
  for is compiled from its bytes on open. If the resolved path is missing, do
  not return the link; report the problem and point to the correct path.
- Return one Viewer URL per requested file.
- Start the Viewer once and pick one workspace root for the session. Every link is
  the same origin plus `?file=<path relative to that root>`, so all of them share one
  browsable catalog. An artifact outside that root needs its own Viewer — launch
  again with that root (reuse-or-start makes this idempotent); a link alone cannot
  reach it.
- For directory-only review links, return the origin without `?file=`.
- Do not stop an existing Viewer server unless the user asks.
- If Viewer startup fails, report the failure and continue with the owning skill's non-GUI validation or artifacts.

## References

- Read `references/viewer-features.md` when you need supported file types, Viewer controls, or file-specific feature details.
