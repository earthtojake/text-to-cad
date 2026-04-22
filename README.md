<div align="center">

# ⚙ Open Source Text to CAD Harness ⚙

An open source harness for generating 3D models with your favorite coding agent

<img src="assets/text-to-cad-demo.gif" alt="Demo of the text-to-cad harness generating and previewing CAD geometry" width="100%">

[![GitHub stars](https://img.shields.io/github/stars/earthtojake/text-to-cad?style=for-the-badge&logo=github&label=Stars)](https://github.com/earthtojake/text-to-cad/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/earthtojake/text-to-cad?style=for-the-badge&logo=github&label=Forks)](https://github.com/earthtojake/text-to-cad/network/members)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](LICENSE)
[![Follow @soft_servo](https://img.shields.io/badge/Follow-%40soft__servo-000000?style=for-the-badge&logo=x)](https://x.com/soft_servo)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](requirements-cad.txt)
[![build123d](https://img.shields.io/badge/build123d-CAD-00A676?style=for-the-badge)](https://github.com/gumyr/build123d)
[![OCP](https://img.shields.io/badge/OCP-OpenCascade-2F80ED?style=for-the-badge)](requirements-cad.txt)
[![STEP](https://img.shields.io/badge/STEP-Export-4A5568?style=for-the-badge)](skills/cad/SKILL.md)
[![STL](https://img.shields.io/badge/STL-Export-4A5568?style=for-the-badge)](skills/cad/SKILL.md)
[![URDF](https://img.shields.io/badge/URDF-Robots-6B46C1?style=for-the-badge)](skills/urdf/SKILL.md)
[![Node.js](https://img.shields.io/badge/Node.js-Viewer-339933?style=for-the-badge&logo=node.js&logoColor=white)](viewer/package.json)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=111111)](viewer/package.json)
[![Vite](https://img.shields.io/badge/Vite-7-646CFF?style=for-the-badge&logo=vite&logoColor=white)](viewer/package.json)

</div>

## ✨ Features

- **Generate** - Create source-controlled CAD models with coding agents like Codex and Claude Code.
- **Export** - Produce STEP, STL, DXF, GLB, topology data, and URDF robot descriptions.
- **Browse** - Inspect generated geometry in a local CAD Explorer viewer.
- **Reference** - Copy stable `@cad[...]` references so agents can make precise follow-up edits.
- **Review** - Render quick snapshots for fast checks during an iteration loop.
- **Reproduce** - Edit source files first, then regenerate explicit targets.
- **Local** - Run the harness and viewer locally with no backend to host.

## 🔁 Workflow

1. **Describe** - Tell your agent about the part, assembly, fixture, robot, or mechanism you want.
2. **Edit** - Let your coding agent update CAD source files under `models/`.
3. **Regenerate** - Create explicit STEP, STL, DXF, GLB, or URDF targets.
4. **Inspect** - Open the CAD Explorer viewer to review the generated model.
5. **Reference** - Copy `@cad[...]` handles when you want geometry-aware edits.
6. **Commit** - Save the source and generated artifacts together once the model is ready.

## 🚀 Quick Start

Clone the repo:

```bash
git clone https://github.com/earthtojake/text-to-cad.git
cd text-to-cad
```

Install Python CAD dependencies:

```bash
python3.11 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/pip install -r requirements-cad.txt
```

Install viewer dependencies:

```bash
cd viewer
npm install
```

Run the local CAD Explorer:

```bash
npm run dev
```

Then open [http://localhost:4178](http://localhost:4178).
