<div align="center">

<img src="apps/docs/public/brand/logo-texttocad-animated.svg" alt="text-to-cad" width="800">

Design physical products with AI.

[Website](https://www.texttocad.dev) · [Docs](https://www.texttocad.dev/docs)

[![cad](https://img.shields.io/pypi/v/cad?style=flat&logo=pypi&logoColor=white&label=cad)](https://pypi.org/project/cad/)
[![Tests](https://img.shields.io/github/actions/workflow/status/earthtojake/text-to-cad/test.yml?branch=main&style=flat&logo=githubactions&logoColor=white&label=Tests)](https://github.com/earthtojake/text-to-cad/actions/workflows/test.yml?query=branch%3Amain)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue?style=flat)](LICENSE)

[![Join Discord](https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white)](https://discord.gg/5FGB9DwJYU)
[![Follow @earthtojake](https://img.shields.io/badge/Follow-%40earthtojake-000000?style=flat&logo=x)](https://x.com/earthtojake)
[![Sponsor](https://img.shields.io/badge/Sponsor-%E2%9D%A4-EA4AAA?style=flat&logo=githubsponsors&logoColor=white)](https://github.com/sponsors/earthtojake)

</div>

# text-to-cad

## 🚀 Quickstart

macOS and Linux:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh
```

Windows, in PowerShell:

```powershell
irm https://www.texttocad.dev/install.ps1 | iex
```

It installs uv if it is missing, then `cad`, the command text-to-cad runs on, then
the plugin in each agent app it finds on your computer, with that app's own command
(Kimi Code you install by hand), and turns on automatic updates.

Then ask your agent for a part or an assembly: it writes the model as a Python
script, runs it to build the model and shows it in the viewer.

It works in Claude Code, Codex, Cursor, Gemini CLI, Grok Build, Antigravity,
Devin CLI, Factory Droid, GitHub Copilot CLI, Kimi Code, Muse, Pi, Qwen Code, Amp,
Cline, Goose, Hermes Agent, Kilo Code, Kiro CLI, OpenClaw, OpenCode, Roo Code,
Trae and Windsurf.

Installing by hand, app by app, updating and removing: [docs/install.md](docs/install.md)

## ✨ Features

The text-to-cad plugin gives your agent local workflows to generate 3D models as STEP, GLB, STL or 3MF files, check them for manufacturing, draw them, and connect to 3D printing, sheet metal and CNC services. It works with any agent that supports plugins or skills.

- [**Parts and assemblies**](skills/cad/SKILL.md): Models written as Python scripts with [build123d](https://github.com/gumyr/build123d) and [OpenCASCADE](https://github.com/Open-Cascade-SAS/OCCT), exported as STEP, STL, 3MF or GLB, and as [DXF profiles and flat patterns](skills/cad/references/2d-profiles-and-dxf.md) for laser and waterjet cutting, with joints and animations for mechanisms, and shown live in the viewer.
- [**Circuit boards**](skills/pcb/SKILL.md): KiCad schematics and boards, placed and routed, checked with ERC and DRC, reviewed before you order, and exported as fabrication files.
- [**Manufacturing checks**](skills/cad/SKILL.md#can-it-be-made): Whether a part can be machined, cut and bent, molded or 3D printed, measured against the process's rules, and what to change where it cannot.
- [**Stress checks**](skills/fea/SKILL.md): Whether a part or an assembly of bonded parts holds under its loads, solved with CalculiX: each part's peak stress, safety factor and how far it moves, drawn on the model.
- [**Engineering drawings**](skills/engineering-drawing/SKILL.md): Dimensioned PDF sheets projected from the part's geometry: views, hidden lines, centre marks, hole callouts and a title block.
- [**Renders**](skills/render/SKILL.md): Photoreal stills, turntables and films of a model with Blender, lit and framed in a Python script and run on the GPU, with a quick draft before each final.
- [**Fabrication services**](skills/sendcutsend/SKILL.md): [Checks DXF and STEP files against SendCutSend's guide](skills/sendcutsend/SKILL.md) before you upload them, and [slices 3D prints](skills/print3d/SKILL.md) with OrcaSlicer and sends them to Bambu Connect or Bambu Studio.
- [**Robotics and simulation**](skills/robot-simulation/SKILL.md): Robot and world descriptions for simulation and motion planning: URDF for ROS, SRDF for MoveIt and MJCF for MuJoCo.

## 🌐 Community

Projects built on top of text-to-cad, and projects that text-to-cad uses.

- **Studio**: A community app by @amywork777: an open-source desktop CAD app for mechanical engineers, built on text-to-cad, for Mac and Windows. You describe a part to the agent, and the 3D model, drawings, stress check and versions sit beside the chat, where you can also edit the model by hand. [Website](https://texttocad.studio) · [GitHub](https://github.com/amywork777/studio)
- **build123d**: The Python CAD library text-to-cad's models are written in: parts and assemblies as code, with sketches, features and joints, built on OpenCASCADE. [Docs](https://build123d.readthedocs.io) · [GitHub](https://github.com/gumyr/build123d)
- **OpenCASCADE**: The open-source geometry kernel under build123d: it builds the solids and reads and writes the STEP files. [Website](https://dev.opencascade.org) · [GitHub](https://github.com/Open-Cascade-SAS/OCCT)
- **kicode**: KiCad's command line, kicad-cli, and its Python client, KiPy, in one Python package: the headless KiCad that text-to-cad's circuit boards run on, with nothing else of KiCad installed. Unofficial: not made or supported by the KiCad project. [PyPI](https://pypi.org/project/kicode/) · [GitHub](https://github.com/earthtojake/kicode)

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
  anywhere. [CONTRIBUTING.md](CONTRIBUTING.md) has the local setup, how to
  test in the agent apps, and the guidance for agents working in the repository.

By default, text-to-cad sends usage stats and crash reports, tagged with a random
ID and never including your files, paths or prompts. The
[privacy policy](https://www.texttocad.dev/privacy-policy) says what is sent and
how to turn it off, and the [terms of service](https://www.texttocad.dev/terms-of-service)
govern using text-to-cad.
