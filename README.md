<div align="center">

<img src="apps/docs/public/brand/logo-texttocad.png" alt="text-to-cad" width="800">

Give your agent CAD superpowers.

[Docs](https://www.texttocad.dev)

[![GitHub stars](https://img.shields.io/github/stars/earthtojake/text-to-cad?style=for-the-badge&logo=github&label=Stars)](https://github.com/earthtojake/text-to-cad/stargazers)
[![skills.sh](https://skills.sh/b/earthtojake/text-to-cad?style=for-the-badge)](https://skills.sh/earthtojake/text-to-cad)
[![Follow @earthtojake](https://img.shields.io/badge/Follow-%40earthtojake-000000?style=for-the-badge&logo=x)](https://x.com/earthtojake)
[![Join Discord](https://img.shields.io/badge/Discord-Join-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/5FGB9DwJYU)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](LICENSE)
[![Tests](https://img.shields.io/github/actions/workflow/status/earthtojake/text-to-cad/test.yml?branch=main&style=for-the-badge&logo=githubactions&logoColor=white&label=Tests)](https://github.com/earthtojake/text-to-cad/actions/workflows/test.yml?query=branch%3Amain)
[![cadgen](https://img.shields.io/pypi/v/cadgen?style=for-the-badge&logo=pypi&logoColor=white&label=cadgen)](https://pypi.org/project/cadgen/)
[![build123d](https://img.shields.io/badge/build123d-0.11-2F6FB0?style=for-the-badge)](https://github.com/gumyr/build123d)
[![Open CASCADE](https://img.shields.io/badge/Open%20CASCADE-7.9-E2001A?style=for-the-badge)](https://dev.opencascade.org)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](skills/cad/requirements.txt)
[![Node.js](https://img.shields.io/badge/Node.js-20+-5FA04E?style=for-the-badge&logo=nodedotjs&logoColor=white)](https://nodejs.org)

</div>

# text-to-cad

text-to-cad is a library of agent skills for generating, inspecting, sourcing,
slicing, and handing off CAD and robot-description artifacts from local project
files.

## 🧰 Skills

Install the library to give agents focused workflows for CAD, fabrication,
robot description files, simulation, and local review.

| Skill        | Summary                                                                                                                                            | Source                                              |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| CAD          | Creates and edits CAD models from plain-language or image requests, with STEP as the main output along with options to export to STL, 3MF and GLB. | [skills/cad](skills/cad/SKILL.md)                   |
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

## 💻 Installation

Install or clone from `main`: it is the source tree, and every skill's
`requirements.txt` pins the `cadgen` release it was published with. (`models/`,
the fixture corpus, is not needed to use the skills.)

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
`npx skills remove <skill>` if you need to. The retired `cad-viewer` skill is
now covered by the CAD, DXF and robot-description skills; remove old standalone
installs with `npx skills remove cad-viewer`.

(`npx skills install …` still works — it is an undocumented alias for `add`.)

### Plugins

Provider-native plugin installs are also available for Codex, Claude Code,
Cursor and Grok Build. Each installs from `main`, whose root carries every
host's manifest. The `plugin` branch is the same plugin without the rest of the
repository, updated on each release; the plugin directories follow it.

```bash
# Codex (requires Codex 0.142.0 or newer)
codex plugin marketplace add earthtojake/text-to-cad
codex plugin add text-to-cad@earthtojake
```

Codex resolves this repository-root plugin only from 0.142.0 onward. On older
versions the plugin is skipped silently and never appears in `codex plugin list`;
upgrade with `npm install -g @openai/codex@latest`.

In the Codex app the plugin also brings the CAD viewer: **CAD** in the sidebar
(recent models, and Open), a **CAD** tab beside each thread that the agent
drives, and *Open with CAD* for model files. It runs locally through
[uv](https://docs.astral.sh/uv/), which must be installed: after installing the plugin,
restart the app, and its first start downloads the pinned runtime. The plugin's
`$cad-mcp-setup` skill checks for uv and points you to its installer. To update, upgrade the `earthtojake` marketplace
(Plugins › Manage › Marketplace, or `codex plugin marketplace upgrade earthtojake`)
and restart the app: its first start downloads the new runtime. The marketplace was renamed from `text-to-cad`
to `earthtojake`; if you added it before, remove the old one first
(`codex plugin marketplace remove text-to-cad`).

```bash
# Claude Code
claude plugin marketplace add earthtojake/text-to-cad
claude plugin install text-to-cad@earthtojake
```

In Claude Code, the plugin also starts CAD's server. Where Claude Code can show
app views, CAD shows models as viewer cards in the conversation; otherwise, as
in a terminal, asking it to show a model gives you a link that opens the model
in the CAD Viewer in your browser.

In Claude Desktop, CAD shows models in the chat: ask Claude to show one and it
appears as a viewer card you can orbit, add to your prompt, and open full size;
Claude can read what you selected and see what you see. It runs locally through
[uv](https://docs.astral.sh/uv/): add the server to Claude Desktop's config
(Settings > Developer > Edit Config), then restart the app. If Claude Desktop
cannot find `uvx`, give its full path (`which uvx`). The config pins a cadgen
release, and uvx keeps the version it first downloads: to update, change it to
the [latest release](https://pypi.org/project/cadgen/) and restart the app.

```json
{
  "mcpServers": {
    "cad": { "command": "uvx", "args": ["--no-config", "--from", "cadgen==0.7.11", "cadgen", "mcp"] }
  }
}
```

```bash
# Cursor
git clone --depth 1 https://github.com/earthtojake/text-to-cad ~/.cursor/plugins/local/text-to-cad
```

Cursor reads `.cursor-plugin/plugin.json`: restart Cursor after cloning, and
`git pull` in that folder to update. Add `--branch plugin` to clone only the
plugin. Teams can instead import the repository under **Dashboard → Plugins &
MCPs → Team Marketplaces**. Like the other plugins it starts CAD's server, which
runs locally through [uv](https://docs.astral.sh/uv/).

Grok Build reads the Claude plugin manifest; there is no separate Grok plugin
manifest. Append `@plugin` to the source to install only the plugin.

```bash
# Grok Build
grok plugin install earthtojake/text-to-cad --trust
grok plugin enable text-to-cad
```

Restart your agent if newly installed skills do not appear. For local
development, branch from `main`, open PRs against `main`, and follow
[CONTRIBUTING.md](CONTRIBUTING.md).

### Usage analytics

The CAD app (the plugin's `cad` server) and the browser viewer (`cadgen viewer`) can send anonymous usage counts: a
random install ID, versions, your OS and agent app, how often each CAD tool was
called and views were used, and a one-way code and the format of each distinct
file shown (to count files, not identify them). Our server also counts installs
per country, from each request's IP address, as weekly and monthly totals only.
Never file names, paths, contents or prompts. It is off until you allow it
in either app's one-time prompt (one answer counts for both); change it later with
**Share anonymous usage data** in either app's Settings, `uvx cadgen analytics on|off`, or by asking your agent to
turn it off. `DO_NOT_TRACK=1` keeps it off. See the
[privacy policy](https://www.texttocad.dev/privacy-policy).

### Windows 11: Smart App Control

The CAD kernel behind the `cad`, `dxf`, `urdf`, `srdf` and `sdf`
skills is `OCP`, OpenCascade's Python binding, and its wheel ships an unsigned
native module. Windows 11's Smart App Control blocks unsigned native code, so
on a machine where it is on (the default on a fresh install) every `cadgen`
command and `import build123d` fails with
`ImportError: DLL load failed while importing OCP`, and Event Viewer records
the refusal as Event ID 3077 under CodeIntegrity › Operational. `cadgen doctor`
names this when it sees it.

Smart App Control has no per-app exception. Either turn it off (Settings ›
Privacy & security › Windows Security › App & browser control › Smart App
Control settings; once off it can only be turned back on by reinstalling
Windows) or run the CAD skills under WSL, where it does not apply. The wheel
is built by the cadquery-ocp project, so signing it is not something this
repository can do.

## 🛠️ Contributing

Branch from `main` and open PRs against `main`.
For local contribution workflow, skill linking, and validation guidance, see
[CONTRIBUTING.md](CONTRIBUTING.md).
