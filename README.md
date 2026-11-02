<div align="center">

<img src="apps/docs/public/brand/logo-texttocad-animated.svg" alt="text-to-cad" width="800">

Design physical products with AI.

[Website](https://www.texttocad.dev)

[![cad-server](https://img.shields.io/pypi/v/cad-server?style=flat&logo=pypi&logoColor=white&label=cad-server)](https://pypi.org/project/cad-server/)
[![Tests](https://img.shields.io/github/actions/workflow/status/earthtojake/text-to-cad/test.yml?branch=main&style=flat&logo=githubactions&logoColor=white&label=Tests)](https://github.com/earthtojake/text-to-cad/actions/workflows/test.yml?query=branch%3Amain)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue?style=flat)](LICENSE)

[![Join Discord](https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white)](https://discord.gg/5FGB9DwJYU)
[![Follow @earthtojake](https://img.shields.io/badge/Follow-%40earthtojake-000000?style=flat&logo=x)](https://x.com/earthtojake)
[![Sponsor](https://img.shields.io/badge/Sponsor-%E2%9D%A4-EA4AAA?style=flat&logo=githubsponsors&logoColor=white)](https://github.com/sponsors/earthtojake)

</div>

# text-to-cad

The text-to-cad plugin gives your agent local workflows for generating 3D models
as STEP, GLB, STL or 3MF files. It also does design for manufacturing checks,
generates engineering drawings, and connects to popular 3D printing, sheet metal
and CNC fabrication services.

It is supported by all popular agents that support plugins or the
[skills](https://skills.sh) framework, including Claude Code, Codex, Cursor,
Gemini and Grok.

### How it works

1. Your agent writes each model as a Python script with [build123d](https://github.com/gumyr/build123d), built on [Open CASCADE](https://dev.opencascade.org).
2. Running the script, `python model.py`, builds the model with text-to-cad's
   server into an `.xbf` document (its parts, names, colours, materials and joints)
   and the STEP, GLB, STL or 3MF files the script declares. The server keeps each
   model's work in memory, so an edit rebuilds only what it changed.
3. The CAD viewer shows the model in your agent app or your browser, and follows
   every rebuild.

## 🚀 Quickstart

macOS and Linux:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh
```

Windows, in PowerShell:

```powershell
irm https://www.texttocad.dev/install.ps1 | iex
```

It installs uv if it is missing, then sets up text-to-cad in every agent app on
your computer with each app's own commands (the plugin, which brings the skills
and CAD's MCP server, or for an agent without a plugin the skills alone),
registers the `cad` command, and moves CAD's server to the new release. Run
it again to update everything, or click CAD's update button when it shows one; it
lists the apps to restart.

Then ask your agent for a part or an assembly: it writes the model as a Python
script, runs it to build the model and shows it in the CAD viewer.

Installing by hand, app by app, and updates: [docs/install.md](docs/install.md)

## 🧰 Skills

Install the library to give agents focused workflows for CAD, fabrication,
robot description files, simulation, and local review.

| Skill        | Summary                                                                                                                                            | Source                                              |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| CAD          | Creates and edits CAD models from plain-language or image requests as Python scripts, built into XBF documents with STEP, STL, 3MF and GLB exports. | [skills/cad](skills/cad/SKILL.md)                   |
| step.parts   | Finds off-the-shelf STEP parts like screws, bearings, motors, and connectors.                                                                      | [skills/step-parts](skills/step-parts/SKILL.md)     |
| Engineering Drawing | Dimensioned engineering drawings from a part, as a PDF: views, hidden lines, dimensions, hole callouts, title block. | [skills/engineering-drawing](skills/engineering-drawing/SKILL.md) |
| DXF          | Creates 2D DXF drawings like profiles, templates, gaskets, and cut layouts from Python sources or CAD geometry.                                    | [skills/dxf](skills/dxf/SKILL.md)                   |
| URDF         | Writes robot structure files with links, joints, limits, inertials, and meshes.                                                                    | [skills/urdf](skills/urdf/SKILL.md)                 |
| SRDF         | Adds MoveIt planning groups, end effectors, poses, and collision rules to a URDF.                                                                  | [skills/srdf](skills/srdf/SKILL.md)                 |
| SDF          | Creates simulator models and worlds with frames, physics, sensors, and lights.                                                                     | [skills/sdf](skills/sdf/SKILL.md)                   |
| SendCutSend  | Checks DXF and STEP files before upload to SendCutSend.                                                                                            | [skills/sendcutsend](skills/sendcutsend/SKILL.md)   |
| DfAM Check   | Measures mesh printability per process: wall thickness, overhangs, support volume, and build orientation.                                          | [skills/dfam-check](skills/dfam-check/SKILL.md)     |
| DFM | Reviews a part for sheet metal, CNC machining, or injection molding, with measured evidence and the cited rule behind every finding; measures draft, undercuts and projected area from a mesh. | [skills/dfm](skills/dfm/SKILL.md) |
| G-code       | Slices models into printer-ready G-code with OrcaSlicer, using your own printer presets.                                                           | [skills/gcode](skills/gcode/SKILL.md)               |
| Bambu Labs   | Sends prints to Bambu Lab printers through Bambu Connect, Bambu Lab's official app, or Bambu Studio.                                               | [skills/bambu-labs](skills/bambu-labs/SKILL.md)     |

## 🛠️ Contributing

text-to-cad is MIT-licensed and built in the open.

- **Bugs and plugin requests**: [open an issue](https://github.com/earthtojake/text-to-cad/issues/new).
  A bug report with the model script and the output of `cad doctor` is the
  fastest to fix, and an agent app without a plugin gets one on request. A
  security problem is reported privately, as [SECURITY.md](SECURITY.md) says.
- **Questions, ideas and what you made**: the [Discord](https://discord.gg/5FGB9DwJYU).
  Say what the skills got wrong, too: that is what improves them.
- **Code, skills and models**: a new skill (a fabrication service, a printer, a
  CAD workflow) goes in `skills/`, an example model in `models/`, and fixes
  anywhere. [CONTRIBUTING.md](CONTRIBUTING.md) has the local setup and how to
  test in the agent apps; an agent working in the repository starts at
  [AGENTS.md](AGENTS.md).

By default, text-to-cad sends usage stats and crash reports, tagged with a random
ID and never including your files, paths or prompts. The
[privacy policy](https://www.texttocad.dev/privacy-policy) says what is sent and
how to turn it off.


<a href="https://trendshift.io/repositories/26559"><img src="https://trendshift.io/api/badge/repositories/26559" alt="earthtojake/text-to-cad | Trendshift" width="250" height="55"></a>
