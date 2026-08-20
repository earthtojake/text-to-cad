<div align="center">

<img src="assets/text-to-cad-demo.gif" alt="Demo of the CAD skill generating and previewing CAD geometry" width="100%">

<br>

<pre>
████████╗███████╗██╗  ██╗████████╗██████╗  ██████╗ █████╗ ██████╗ 
╚══██╔══╝██╔════╝╚██╗██╔╝╚══██╔══╝╚════██╗██╔════╝██╔══██╗██╔══██╗
   ██║   █████╗   ╚███╔╝    ██║    █████╔╝██║     ███████║██║  ██║
   ██║   ██╔══╝   ██╔██╗    ██║   ██╔═══╝ ██║     ██╔══██║██║  ██║
   ██║   ███████╗██╔╝ ██╗   ██║   ███████╗╚██████╗██║  ██║██████╔╝
   ╚═╝   ╚══════╝╚═╝  ╚═╝   ╚═╝   ╚══════╝ ╚═════╝╚═╝  ╚═╝╚═════╝ 
</pre>

A library of agent skills for CAD, CAE and CAM

[Docs](https://www.texttocad.dev)

[![Tests](https://img.shields.io/github/actions/workflow/status/earthtojake/text-to-cad/test.yml?branch=develop&style=for-the-badge&logo=githubactions&logoColor=white&label=Tests)](https://github.com/earthtojake/text-to-cad/actions/workflows/test.yml?query=branch%3Adevelop)
[![Join Discord](https://img.shields.io/badge/Discord-Join-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/5FGB9DwJYU)
[![GitHub stars](https://img.shields.io/github/stars/earthtojake/text-to-cad?style=for-the-badge&logo=github&label=Stars)](https://github.com/earthtojake/text-to-cad/stargazers)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](LICENSE)
[![Follow @earthtojake](https://img.shields.io/badge/Follow-%40earthtojake-000000?style=for-the-badge&logo=x)](https://x.com/earthtojake)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](skills/cad/requirements.txt)
[![STEP](https://img.shields.io/badge/STEP-Export-4A5568?style=for-the-badge)](skills/cad/SKILL.md)
[![STL](https://img.shields.io/badge/STL-Export-4A5568?style=for-the-badge)](skills/cad/SKILL.md)
[![3MF](https://img.shields.io/badge/3MF-Export-4A5568?style=for-the-badge)](skills/cad/SKILL.md)
[![URDF](https://img.shields.io/badge/URDF-Robots-6B46C1?style=for-the-badge)](skills/urdf/SKILL.md)
[![SDF](https://img.shields.io/badge/SDF-Simulation-6B46C1?style=for-the-badge)](skills/sdf/SKILL.md)
[![SRDF](https://img.shields.io/badge/SRDF-MoveIt2-6B46C1?style=for-the-badge)](skills/srdf/SKILL.md)

</div>

# text-to-cad

text-to-cad is a library of agent skills for generating, inspecting, sourcing,
slicing, and handing off CAD and robot-description artifacts from local project
files.

<table>
  <tr>
    <td width="33%">
      <a href="./assets/text-to-cad-demo.gif">
        <img src="./assets/text-to-cad-demo.gif" alt="CAD skill demo showing generated geometry in CAD Viewer" width="100%">
      </a>
      <a href="./skills/cad/SKILL.md"><strong>CAD</strong></a>
    </td>
    <td width="33%">
      <a href="./assets/urdf-demo.gif">
        <img src="./assets/urdf-demo.gif" alt="URDF skill demo showing robot description output in CAD Viewer" width="100%">
      </a>
      <a href="./skills/urdf/SKILL.md"><strong>URDF</strong></a>
    </td>
    <td width="33%">
      <a href="./assets/srdf-moveit2-demo.gif">
        <img src="./assets/srdf-moveit2-demo.gif" alt="SRDF MoveIt2 skill demo showing inverse kinematics in CAD Viewer" width="100%">
      </a>
      <a href="./skills/srdf/SKILL.md"><strong>SRDF / MoveIt2</strong></a>
    </td>
  </tr>
</table>

## 🧰 Skills

Install the library to give agents focused workflows for CAD, fabrication,
robot description files, simulation, and local review.

| Skill        | Summary                                                                                                                                            | Source                                              |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| CAD          | Creates and edits CAD models from plain-language or image requests, with STEP as the main output along with options to export to STL, 3MF and GLB. | [skills/cad](skills/cad/SKILL.md)                   |
| CAD Viewer   | Shows local browser previews for CAD and robot files.                                                                                     | [skills/cad-viewer](skills/cad-viewer/SKILL.md)     |
| step.parts   | Finds off-the-shelf STEP parts like screws, bearings, motors, and connectors.                                                                      | [skills/step-parts](skills/step-parts/SKILL.md)     |
| DXF          | Creates 2D DXF drawings like profiles, templates, gaskets, and cut layouts from Python sources or CAD geometry.                                    | [skills/dxf](skills/dxf/SKILL.md)                   |
| URDF         | Writes robot structure files with links, joints, limits, inertials, and meshes.                                                                    | [skills/urdf](skills/urdf/SKILL.md)                 |
| SRDF         | Adds MoveIt planning groups, end effectors, poses, and collision rules to a URDF.                                                                  | [skills/srdf](skills/srdf/SKILL.md)                 |
| SDF          | Creates simulator models and worlds with frames, physics, sensors, and lights.                                                                     | [skills/sdf](skills/sdf/SKILL.md)                   |
| SendCutSend  | Checks DXF and STEP files before upload to SendCutSend.                                                                                            | [skills/sendcutsend](skills/sendcutsend/SKILL.md)   |
| G-code       | Slices supported mesh files into validated, printer-profiled FDM `.gcode` with real slicer CLIs.                                                   | [skills/gcode](skills/gcode/SKILL.md)               |
| Bambu Labs   | Dry-runs, uploads, and cautiously starts local Bambu Lab print jobs from validated `.gcode`.                                                       | [skills/bambu-labs](skills/bambu-labs/SKILL.md)     |
| Implicit CAD | Creates browser-native implicit CAD models using GLSL signed-distance fields and CAD Viewer raymarch rendering. Experimental.                      | [skills/implicit-cad](skills/implicit-cad/SKILL.md) |

## 💻 Installation

For production use, install or clone from `main`; that branch contains the
generated skill outputs needed by provider installers.

### Skills

Install text-to-cad with the Skills CLI:

```bash
npx skills add earthtojake/text-to-cad
```

This is the preferred installation path. It installs the individual skills
directly for supported agents.

**Use the same command to update.** `add` re-fetches the package and overwrites
what is already installed, so it both refreshes existing skills and installs any
skill added in a newer release. `npx skills update` only refreshes skills already
in your lockfile, so it silently misses new ones — which matters here, because
releases do add skills.

Neither command removes a skill that was retired upstream; drop one with
`npx skills remove <skill>` if you need to.

(`npx skills install …` still works — it is an undocumented alias for `add`.)

### Plugins

Provider-native plugin installs are also available for Codex, Claude Code, and
Grok Build:

```bash
# Codex (requires Codex 0.142.0 or newer)
codex plugin marketplace add earthtojake/text-to-cad
codex plugin add cad@text-to-cad
```

Codex resolves this repository-root plugin only from 0.142.0 onward. On older
versions the plugin is skipped silently and never appears in `codex plugin list`;
upgrade with `npm install -g @openai/codex@latest`.

```bash
# Claude Code
claude plugin marketplace add earthtojake/text-to-cad
claude plugin install cad@text-to-cad
```

Grok Build uses the existing `.claude-plugin/marketplace.json`; there is no
separate Grok plugin manifest.

```bash
# Grok Build
grok plugin install earthtojake/text-to-cad --trust
grok plugin enable cad
```

Restart your agent if newly installed skills do not appear. For local
development, branch from `develop`, open PRs against `develop`, and use the symlink
workflow in [CONTRIBUTING.md](CONTRIBUTING.md).

## 🛠️ Contributing

Development happens from the `develop` branch; open PRs against `develop`, not `main`.
For local contribution workflow, skill linking, and validation guidance, see
[CONTRIBUTING.md](CONTRIBUTING.md).
