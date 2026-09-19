# text-to-cad for QwenPaw

A [QwenPaw](https://qwenpaw.agentscope.io) plugin that installs the
[text-to-cad](https://github.com/earthtojake/text-to-cad) skill library — CAD,
robotics, fabrication, and local review workflows — into every QwenPaw
workspace.

## What it provides

| Skill      | What it does                                                                                    |
| ---------- | ----------------------------------------------------------------------------------------------- |
| `cad`      | Creates, edits, and validates parametric CAD models; STEP default, STL/3MF/GLB exports.         |
| `cad-viewer` | Opens a local browser preview (CAD Viewer) for CAD, robot-description, and DXF files.         |
| `step-parts` | Finds off-the-shelf STEP parts (screws, bearings, motors, connectors) on step.parts.          |
| `dxf`      | Generates and validates 2D DXF drawings from Python sources or CAD geometry.                    |
| `urdf`     | Authors and validates URDF robot descriptions.                                                  |
| `srdf`     | Adds MoveIt2 planning groups, end effectors, poses, and collision rules to a URDF.              |
| `sdf`      | Authors SDFormat models and worlds for simulators.                                              |
| `dfam-check` | Measures mesh printability per process (FDM, SLS, SLA/DLP, metal PBF, MJF).                   |
| `gcode`    | Slices mesh files into validated, printer-profiled FDM G-code with real slicer CLIs.            |
| `bambu-labs` | Dry-runs, uploads, and cautiously starts local Bambu Lab print jobs from validated G-code.    |
| `sendcutsend` | Checks DXF and STEP files before uploading a SendCutSend order.                              |

Skills are enabled by default on all channels in every workspace. The plugin
itself ships no tools: each skill's `requirements.txt` names the `cadgen`
distribution it runs on, and the skill instructs the agent to install it on
first use (`python -m pip install -r requirements.txt`).

## Install

Plugin operations require QwenPaw to be offline.

From a clone of this repository:

```bash
qwenpaw plugin install /path/to/text-to-cad/.qwenpaw-plugin
```

Or from a ZIP of the plugin directory:

```bash
cd /path/to/text-to-cad
zip -r text-to-cad-qwenpaw.zip .qwenpaw-plugin
qwenpaw plugin install text-to-cad-qwenpaw.zip
```

Then start QwenPaw (`qwenpaw app`). On startup the plugin copies every skill
into each workspace's `skills/` directory, so the CAD skills appear under
**Workspace → Skills** alongside QwenPaw's built-ins.

## Verify

```bash
qwenpaw plugin list
```

shows `text-to-cad` as installed; the workspace skill page lists the eleven
skills above as enabled.

## Requirements

- QwenPaw 2.1.1 or newer (`qwenpaw_version.min` in `plugin.json`; the loader
  checks `>=min` and disables the plugin otherwise).
- Per skill, at runtime: Python ≥ 3.11 and the `cadgen` distribution from
  PyPI (the agent installs it from the skill's `requirements.txt`). `cad`
  rendering additionally needs a Chromium browser
  (`python -m playwright install chromium`).

## Preflight: /cad-setup

Run `/cad-setup` in any workspace chat to check the runtime before first use:

- whether the `cadgen` distribution is installed (and its version);
- each cadgen-pinned skill's `requirements.txt` pin, verified with
  `cadgen doctor` (exit 3 = mismatch, and the command prints the fix);
- viewer instances and the warm daemon, so background processes are visible.

A one-line pointer to `/cad-setup` is injected into the system prompt, so the
agent knows the check exists without reading a skill.

## Fabrication opt-in

`bambu-labs` and `sendcutsend` reach real machines (starting LAN prints,
uploading parts for manufacture), so the plugin provisions them **disabled**
the first time it fills a workspace; enable them per workspace in
**Workspace → Skills** when you want them. The once-only gate is marked by a
`.text-to-cad-provisioned` file in each workspace: after the first provision,
your own enable/disable choices always win.

## Files

```
.qwenpaw-plugin/
├── plugin.json   # Manifest: id "cad", type "general"
├── plugin.py     # Entry point: skill provider, /cad-setup, fabrication gate
├── README.md     # This file
└── skills/       # GENERATED copy of the canonical skills/ — do not edit
```

The QwenPaw loader installs a plugin by copying this directory, so the skill
tree travels inside it. `skills/` here is generated from the repository's
canonical `skills/` (what every other installer ships):

```bash
rsync -a --delete --exclude '__pycache__' --exclude '.DS_Store' \
  skills/ .qwenpaw-plugin/skills/
```

`tests/python/global/test_qwenpaw_plugin.py` fails when the copy drifts from
the canonical tree. The release PR stamps the version into `plugin.json`
alongside the other plugin manifests via `scripts/release/sync-version.mjs`.
