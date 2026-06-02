<div align="center">

<img src="assets/text-to-cad-demo.gif" alt="Demo of the CAD skill generating and previewing CAD geometry" width="100%">

<br>

<pre>
 ██████╗ █████╗ ██████╗       ███████╗██╗  ██╗██╗██╗     ██╗     ███████╗
██╔════╝██╔══██╗██╔══██╗      ██╔════╝██║ ██╔╝██║██║     ██║     ██╔════╝
██║     ███████║██║  ██║      ███████╗█████╔╝ ██║██║     ██║     ███████╗
██║     ██╔══██║██║  ██║      ╚════██║██╔═██╗ ██║██║     ██║     ╚════██║
╚██████╗██║  ██║██████╔╝      ███████║██║  ██╗██║███████╗███████╗███████║
 ╚═════╝╚═╝  ╚═╝╚═════╝       ╚══════╝╚═╝  ╚═╝╚═╝╚══════╝╚══════╝╚══════╝
</pre>

A skills library for CAD, robotics, and hardware design agents

[Docs](https://www.cadskills.xyz) | [Demo](https://demo.cadskills.xyz)

[![GitHub stars](https://img.shields.io/github/stars/earthtojake/text-to-cad?style=for-the-badge&logo=github&label=Stars)](https://github.com/earthtojake/text-to-cad/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/earthtojake/text-to-cad?style=for-the-badge&logo=github&label=Forks)](https://github.com/earthtojake/text-to-cad/network/members)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](LICENSE)
[![Follow @earthtojake](https://img.shields.io/badge/Follow-%40earthtojake-000000?style=for-the-badge&logo=x)](https://x.com/earthtojake)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](skills/cad/requirements.txt)
[![build123d](https://img.shields.io/badge/build123d-CAD-00A676?style=for-the-badge)](https://github.com/gumyr/build123d)
[![OCP](https://img.shields.io/badge/OCP-OpenCascade-2F80ED?style=for-the-badge)](skills/cad/requirements.txt)
[![STEP](https://img.shields.io/badge/STEP-Export-4A5568?style=for-the-badge)](skills/cad/SKILL.md)
[![STL](https://img.shields.io/badge/STL-Export-4A5568?style=for-the-badge)](skills/cad/SKILL.md)
[![3MF](https://img.shields.io/badge/3MF-Export-4A5568?style=for-the-badge)](skills/cad/SKILL.md)
[![URDF](https://img.shields.io/badge/URDF-Robots-6B46C1?style=for-the-badge)](skills/urdf/SKILL.md)
[![SDF](https://img.shields.io/badge/SDF-Simulation-6B46C1?style=for-the-badge)](skills/sdf/SKILL.md)
[![SRDF](https://img.shields.io/badge/SRDF-MoveIt2-6B46C1?style=for-the-badge)](skills/srdf/SKILL.md)

</div>

# CAD Skills

CAD Skills is a library of agent skills for generating, inspecting, sourcing,
slicing, and handing off CAD and robot-description artifacts from local project
files.

## 🧰 Skills

Install the library to give agents focused workflows for CAD, fabrication,
robot description files, simulation, and local review.

| Skill        | Summary                                                                                                                                            | Source                                              |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| CAD          | Creates and edits CAD models from plain-language or image requests, with STEP as the main output along with options to export to STL, 3MF and GLB. | [skills/cad](skills/cad/SKILL.md)                   |
| CAD Viewer   | Shows local browser previews for CAD, G-code, and robot files.                                                                                     | [skills/cad-viewer](skills/cad-viewer/SKILL.md)     |
| step.parts   | Finds off-the-shelf STEP parts like screws, bearings, motors, and connectors.                                                                      | [skills/step-parts](skills/step-parts/SKILL.md)     |
| URDF         | Writes robot structure files with links, joints, limits, inertials, and meshes.                                                                    | [skills/urdf](skills/urdf/SKILL.md)                 |
| SRDF         | Adds MoveIt planning groups, end effectors, poses, and collision rules to a URDF.                                                                  | [skills/srdf](skills/srdf/SKILL.md)                 |
| SDF          | Creates simulator models and worlds with frames, physics, sensors, and lights.                                                                     | [skills/sdf](skills/sdf/SKILL.md)                   |
| SendCutSend  | Checks DXF and STEP files before upload to SendCutSend.                                                                                            | [skills/sendcutsend](skills/sendcutsend/SKILL.md)   |
| G-code       | Slices supported mesh files into validated, printer-profiled FDM `.gcode` with real slicer CLIs.                                                   | [skills/gcode](skills/gcode/SKILL.md)               |
| Bambu Labs   | Dry-runs, uploads, and cautiously starts local Bambu Lab print jobs from validated `.gcode`.                                                       | [skills/bambu-labs](skills/bambu-labs/SKILL.md)     |
| Implicit CAD | Creates browser-native implicit CAD models using GLSL signed-distance fields and CAD Viewer raymarch rendering. Experimental.                      | [skills/implicit-cad](skills/implicit-cad/SKILL.md) |

## 💻 Installation

For production use, install or clone from `main`; that branch contains the
generated skill/plugin outputs needed by provider installers.

### Skills

Install CAD Skills with the Skills CLI:

```bash
npx skills install earthtojake/text-to-cad
```

This is the preferred installation path. It installs the individual skills
directly for supported agents.

### Plugins

Provider-native plugin installs are also available for Codex and Claude Code:

```bash
# Codex
codex plugin marketplace add earthtojake/text-to-cad
codex plugin add cad@text-to-cad
```

```bash
# Claude Code
claude plugin marketplace add earthtojake/text-to-cad
claude plugin install cad@text-to-cad
```

Restart your agent if newly installed skills do not appear. For local
development, branch from `develop`, open PRs against `develop`, and use the symlink
workflow in [CONTRIBUTING.md](CONTRIBUTING.md).

## 📸 Screenshots

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

## 🧪 Benchmarks

The repo stores heavyweight assets in `assets/**` and `benchmarks/**` through Git LFS and excludes those trees from default LFS pulls so lightweight clones do not fetch GIF assets. Benchmark markdown remains normal Git for readable diffs. To hydrate only the benchmark assets locally, run:

```bash
git lfs pull --include="benchmarks/**"
```

<table>
  <thead>
    <tr>
      <th>#</th>
      <th>Target</th>
      <th>Prompt</th>
      <th>Output</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>1</td>
      <td><a href="benchmarks/01-rectangular-calibration-block.md">Rectangular calibration block with four holes</a></td>
      <td>Create a centered 100 x 60 x 20 mm block with four 8 mm vertical through-holes. Add only a 2 mm chamfer on the top outer perimeter.</td>
      <td><img src="benchmarks/benchmark_01_rectangular_calibration_block.gif" alt="Rectangular calibration block orbit gif" width="220"></td>
    </tr>
    <tr>
      <td>2</td>
      <td><a href="benchmarks/02-circular-flange.md">Circular flange with bolt-hole pattern</a></td>
      <td>Create an 80 mm diameter, 10 mm thick circular flange with a 30 mm central through-bore. Add six 6 mm through-holes on a 60 mm bolt circle and fillet the outside circular edges.</td>
      <td><img src="benchmarks/benchmark_02_circular_flange.gif" alt="Circular flange orbit gif" width="220"></td>
    </tr>
    <tr>
      <td>3</td>
      <td><a href="benchmarks/03-l-bracket.md">L-bracket with gussets and two hole directions</a></td>
      <td>Create an L-bracket from a base plate and rear vertical plate. Add vertical base holes, horizontal back-plate holes, two triangular gussets, and a filleted base/back transition.</td>
      <td><img src="benchmarks/benchmark_03_l_bracket.gif" alt="L-bracket orbit gif" width="220"></td>
    </tr>
    <tr>
      <td>4</td>
      <td><a href="benchmarks/04-stepped-shaft-keyway.md">Stepped shaft with keyway</a></td>
      <td>Create a 120 mm shaft along X with 20/30/20 mm diameter stepped sections. Add end chamfers and a shallow rectangular keyway on top of the middle section.</td>
      <td><img src="benchmarks/benchmark_04_stepped_shaft_keyway.gif" alt="Stepped shaft orbit gif" width="220"></td>
    </tr>
    <tr>
      <td>5</td>
      <td><a href="benchmarks/05-open-top-electronics-enclosure.md">Open-top electronics enclosure with bosses</a></td>
      <td>Create a hollow open-top enclosure with 3 mm walls and floor. Add four internal standoffs with centered blind holes and 2 mm outside vertical corner fillets.</td>
      <td><img src="benchmarks/benchmark_05_open_top_electronics_enclosure.gif" alt="Open-top electronics enclosure orbit gif" width="220"></td>
    </tr>
    <tr>
      <td>6</td>
      <td><a href="benchmarks/06-clevis-bracket-lightening-cutouts.md">Aerospace-style clevis bracket with lightening cutouts</a></td>
      <td>Create a symmetric clevis bracket with a base plate, two rounded lugs, base mounting holes, and a horizontal lug bore. Add triangular lightening cutouts, reinforcing ribs, and rounded transitions.</td>
      <td><img src="benchmarks/benchmark_06_clevis_bracket_lightening_cutouts.gif" alt="Clevis bracket orbit gif" width="220"></td>
    </tr>
    <tr>
      <td>7</td>
      <td><a href="benchmarks/07-radial-engine-cylinder.md">Radial-engine-style cylinder with cooling fins</a></td>
      <td>Create a vertical engine-cylinder form with a central barrel, 12 cooling fins, a base flange, and a top cap. Add a 35 degree angled spark-plug boss with a coaxial through-hole.</td>
      <td><img src="benchmarks/benchmark_07_radial_engine_cylinder.gif" alt="Radial-engine-style cylinder orbit gif" width="220"></td>
    </tr>
    <tr>
      <td>8</td>
      <td><a href="benchmarks/08-centrifugal-impeller.md">Centrifugal impeller with backward-curved blades</a></td>
      <td>Create a centrifugal impeller with a backplate, hub, and through-bore. Add 12 fused backward-curved blades sweeping about 45 degrees from root to tip.</td>
      <td><img src="benchmarks/benchmark_08_centrifugal_impeller.gif" alt="Centrifugal impeller orbit gif" width="220"></td>
    </tr>
    <tr>
      <td>9</td>
      <td><a href="benchmarks/09-spiral-staircase.md">Spiral staircase with helical handrail</a></td>
      <td>Create a miniature spiral staircase with a central column, base disk, and 20 rising wedge treads. Add a one-revolution helical handrail and vertical balusters at the tread outer ends.</td>
      <td><img src="benchmarks/benchmark_09_spiral_staircase.gif" alt="Spiral staircase orbit gif" width="220"></td>
    </tr>
    <tr>
      <td>10</td>
      <td><a href="benchmarks/10-planetary-gear-stage.md">Simplified planetary gear stage</a></td>
      <td>Create a flat planetary gear assembly with separate sun, planet, ring, carrier, and pin bodies. Use simplified trapezoidal teeth and place three planets around the sun on a 42 mm radius circle.</td>
      <td><img src="benchmarks/benchmark_10_planetary_gear_stage.gif" alt="Planetary gear stage orbit gif" width="220"></td>
    </tr>
  </tbody>
</table>

## 🛠️ Contributing

Development happens from the `develop` branch; open PRs against `develop`, not `main`.
For local contribution workflow, skill linking, and validation guidance, see
[CONTRIBUTING.md](CONTRIBUTING.md).
