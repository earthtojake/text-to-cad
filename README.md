<div align="center">

<img src="apps/docs/public/brand/logo-texttocad-animated.svg" alt="text-to-cad" width="800">

Design physical products with AI.

[Website](https://www.texttocad.dev)

[![cad](https://img.shields.io/pypi/v/cad?style=flat&logo=pypi&logoColor=white&label=cad)](https://pypi.org/project/cad/)
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
   server into a document it holds in memory (its parts, names, colours, materials
   and joints) and the STEP, GLB, STL or 3MF files the script declares. The server keeps each
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

## ✨ Features

What your agent can design, check and make with text-to-cad.

- [**Parts and assemblies**](skills/cad/SKILL.md): Models written as Python scripts with build123d, exported as STEP, STL, 3MF or GLB, with joints and animations for mechanisms.
- [**Circuit boards**](skills/pcb/SKILL.md): KiCad schematics and boards, placed and routed, checked with ERC and DRC, reviewed before you order, and exported as fabrication files.
- [**Manufacturing checks**](skills/cad/SKILL.md#can-it-be-made): Whether a part can be machined, cut and bent, molded or 3D printed, measured against the process's rules, and what to change where it cannot.
- [**Engineering drawings**](skills/engineering-drawing/SKILL.md): Dimensioned PDF sheets projected from the part's geometry: views, hidden lines, centre marks, hole callouts and a title block.
- [**The CAD Viewer**](skills/cad/SKILL.md#show-the-model): Shows each model in your agent app or your browser and follows every rebuild. Measure, clip and explode it, or mark it up for your agent.
- [**Cut files**](skills/cad/references/2d-profiles-and-dxf.md): DXF profiles, gaskets and flat patterns with their bend lines, for laser and waterjet cutting.
- [**SendCutSend orders**](skills/sendcutsend/SKILL.md): Checks DXF and STEP files against SendCutSend's own guide, materials and services before you upload them.
- [**3D printing**](skills/print3d/SKILL.md): Slices a model to G-code with OrcaSlicer for your printer, and sends Bambu Lab prints to Bambu Connect or Bambu Studio.
- [**Robots and worlds**](skills/robot-simulation/SKILL.md): Robot and world descriptions for simulation and motion planning: URDF for ROS, SRDF for MoveIt and SDF for Gazebo.

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
