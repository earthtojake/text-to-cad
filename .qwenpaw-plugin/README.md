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
| `engineering-drawing` | Projects a dimensioned PDF drawing from the part: orthographic views, hole callouts, notes and a title block on ISO sheets. |
| `dxf`      | Generates and validates 2D DXF drawings from Python sources or CAD geometry.                    |
| `urdf`     | Authors and validates URDF robot descriptions.                                                  |
| `srdf`     | Adds MoveIt2 planning groups, end effectors, poses, and collision rules to a URDF.              |
| `sdf`      | Authors SDFormat models and worlds for simulators.                                              |
| `dfam-check` | Measures mesh printability per process (FDM, SLS, SLA/DLP, metal PBF, MJF).                   |
| `dfm`      | Reviews manufacturability per process: sheet-metal bends, machining access, molding draft and undercuts. |
| `gcode`    | Slices mesh files into validated, printer-profiled FDM G-code with real slicer CLIs.            |
| `bambu-labs` | Dry-runs, uploads, and cautiously starts local Bambu Lab print jobs from validated G-code.    |
| `sendcutsend` | Checks DXF and STEP files before uploading a SendCutSend order.                              |

Skills are enabled by default on all channels in every workspace. The plugin
itself ships no tools: each skill's `requirements.txt` names the `cadgen`
distribution it runs on, and the skill instructs the agent to install it on
first use (`python -m pip install -r requirements.txt`).

## Install

The package carries no second copy of the skills: it resolves a `skills/` tree
when it loads, so name one in QwenPaw's own config (`~/.qwenpaw/config.json`;
the `plugins` map is keyed by plugin id):

```json
{ "plugins": { "cad": { "skills_dir": "/path/to/text-to-cad/skills" } } }
```

Plugin operations require QwenPaw to be offline. Install from the clone:

```bash
qwenpaw plugin install /path/to/text-to-cad/.qwenpaw-plugin
```

Then start QwenPaw (`qwenpaw app`). On startup the plugin copies every skill
into each workspace's `skills/` directory, so the CAD skills appear under
**Workspace → Skills** alongside QwenPaw's built-ins.

Installing while the app is running hot-loads the plugin before the config
above reaches it, so the skills appear on the next start rather than
immediately: only the boot path (`load_all_plugins`) hands a plugin its
`plugins.<id>` config.

No checkout to point at? Generate the bundled copy and the plugin resolves it
with no config involved:

```bash
cd /path/to/text-to-cad
rsync -a --delete --exclude '__pycache__' --exclude '.DS_Store' \
  skills/ .qwenpaw-plugin/skills/
zip -r text-to-cad-qwenpaw.zip .qwenpaw-plugin
qwenpaw plugin install text-to-cad-qwenpaw.zip
```

That copy is gitignored, and a ZIP install needs it: an archive of this
directory carries nothing else.

## Verify

```bash
qwenpaw plugin list
```

shows `text-to-cad` as installed; the workspace skill page lists every skill in
the table above as enabled.

## Requirements

- QwenPaw 2.1.1 through 2.x (`qwenpaw_version` in `plugin.json`). The loader
  requires `>=min` AND `<max` and disables the plugin with no error when either
  fails, so the `max` of 2.99.0 is load-bearing: it covers every 2.x release,
  and it has to be revisited before a QwenPaw 3 ships or this plugin stops
  loading in silence.
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
└── skills/       # optional generated copy (gitignored) — never edit in place
```

`_resolve_skills_dir()` picks the tree to provision from, in order: the
`skills_dir` this plugin's config names, then a generated copy here, then the
checkout's `skills/` beside the package. `/cad-setup` prints which one won. A
configured path that does not resolve is an error and stops resolution:
falling through would let a moved checkout keep being served by a copy nobody
updated, which is the failure this whole ordering exists to avoid.

Two shapes are deliberately not used.

*A symlink* (`skills -> ../skills`) would need no config, but it only survives
because the loader's `shutil.copytree` dereferences by default — and the ZIP
route breaks that: `_safe_extract_zip` extracts with `zipfile.extractall`,
which recreates no links, so the member lands as a text file containing
`../skills`, no tree resolves, and the plugin registers nothing with one log
line. QwenPaw also treats links in skill content as an input to reject rather
than a feature to enable: it refuses a linked skill source, scans for links
inside one, and rejects symlink members in a skill ZIP outright.

*A committed copy* is what this directory used to ship — 102 files, and a
second tree to keep in step. It now stays out of the repository for the same
reason `packages/cadgen/_runtime` does: regenerable from source, so the source
is the only thing reviewed.
