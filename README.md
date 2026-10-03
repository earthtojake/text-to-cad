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
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](packages/cadgen/pyproject.toml)
[![Node.js](https://img.shields.io/badge/Node.js-20+-5FA04E?style=for-the-badge&logo=nodedotjs&logoColor=white)](https://nodejs.org)

</div>

# text-to-cad

The text-to-cad plugin gives your agent local workflows for generating 3D models
as STEP, GLB, STL or 3MF files. It also does design for manufacturing checks,
generates engineering drawings, and connects to popular 3D printing, sheet metal
and CNC fabrication services.

It is supported by all popular agents that support plugins or the
[skills](https://skills.sh) framework, including Claude Code, Codex, Cursor,
Gemini and Grok.

## 💻 Install

### Ask your agent (recommended)

Send this message to your agent and it will install text-to-cad for you.

```text
Install text-to-cad from https://github.com/earthtojake/text-to-cad
```

**Agents installing text-to-cad:** check that uv is installed (`uv --version`; if
it is missing, point the user to [uv's installer](https://docs.astral.sh/uv/getting-started/installation/)).
Then run the commands under your app's heading below, or [Other Agents](#other-agents)
if it has none, and tell the user to restart the app.

Or install it yourself. The plugin for your agent app brings the skills and CAD's
viewer, a local server (`cadgen mcp`) that runs through
[uv](https://docs.astral.sh/uv/), which must be installed. For an agent without a
plugin, install the skills alone (see [Other Agents](#other-agents)). Install one
or the other in an app, not both: two copies means every skill twice. Restart your
agent if newly installed skills do not appear. Updating the plugin updates CAD: the
new release's cadgen is downloaded the first time it runs, and the skills and the
server share it. Earlier releases stay in uv's cache until you run `uv cache prune`.

### Claude Code

```bash
claude plugin marketplace add earthtojake/text-to-cad
claude plugin install text-to-cad@earthtojake
```

The plugin also starts CAD's server. Where Claude Code can show app views, CAD
shows models as viewer cards in the conversation; otherwise, as in a terminal,
asking it to show a model gives you a link that opens the model in the CAD
Viewer in your browser.

### Claude Desktop

CAD shows models in the chat: ask Claude to show one and it appears as a viewer
card you can orbit, add to your prompt, and open full size; Claude can read what
you selected and see what you see. It runs locally through
[uv](https://docs.astral.sh/uv/): add the server to Claude Desktop's config
(Settings > Developer > Edit Config), then restart the app. If Claude Desktop
cannot find `uvx`, give its full path (`which uvx`). The config pins a cadgen
release, and uvx keeps the version it first downloads: to update, change it to
the [latest release](https://pypi.org/project/cadgen/) and restart the app.

```json
{
  "mcpServers": {
    "cad": {
      "command": "uvx",
      "args": ["--no-config", "--managed-python", "--python", "3.13", "--from", "cadgen==0.7.11", "cadgen", "mcp"],
      "env": {"CADGEN_INSTALL_CHANNEL": "github"}
    }
  }
}
```

### Codex

```bash
codex plugin marketplace add earthtojake/text-to-cad
codex plugin add text-to-cad@earthtojake
```

Requires Codex 0.142.0 or newer: older versions skip this repository-root plugin
silently, and it never appears in `codex plugin list`. Upgrade with
`npm install -g @openai/codex@latest`.

In the Codex app the plugin also brings the CAD viewer: **CAD** in the sidebar
(recent models, and Open), a **CAD** tab beside each thread that the agent
drives, and *Open with CAD* for model files. It runs locally through
[uv](https://docs.astral.sh/uv/), which must be installed: after installing the plugin,
restart the app, and its first start downloads the pinned runtime. The plugin's
`$cad-setup` skill checks for uv and points you to its installer. To update, upgrade the `earthtojake` marketplace
(Plugins › Manage › Marketplace, or `codex plugin marketplace upgrade earthtojake`)
and restart the app: its first start downloads the new runtime. The marketplace was renamed from `text-to-cad`
to `earthtojake`; if you added it before, remove the old one first
(`codex plugin marketplace remove text-to-cad`).

### Cursor

```bash
git clone --depth 1 --branch plugin https://github.com/earthtojake/text-to-cad ~/.cursor/plugins/local/text-to-cad
```

Cursor reads `.cursor-plugin/plugin.json`: restart Cursor after cloning, and run
`git pull` in that folder to update. The `plugin` branch holds only the plugin,
one commit per release. Cursor also loads plugins installed with
Claude Code, so skip this if you installed the Claude Code plugin. Teams can
import the repository instead, under **Dashboard → Plugins & MCPs → Team
Marketplaces**.

### Grok Build

```bash
grok plugin install earthtojake/text-to-cad --trust
grok plugin enable text-to-cad
```

Grok Build reads the Claude plugin manifest, and also loads plugins installed
with Claude Code: install one or the other. Grok shows tool results as text, so
asking it to show a model gives you a CAD Viewer link.

### Gemini

```bash
gemini extensions install https://github.com/earthtojake/text-to-cad --consent --auto-update
```

Gemini installs the latest release as an extension, with the skills and CAD's
server, and keeps it up to date (`--auto-update`; `--consent` answers its security
prompt). `gemini extensions update text-to-cad` updates it now. Like Grok, it shows
tool results as text, so asking it to show a model gives you a CAD Viewer link.

### Other Agents

For an agent without plugin support: the skills give you everything you need for
core CAD workflows and let you view CAD files in a localhost web app. Install them
with the Skills CLI:

```bash
npx skills add earthtojake/text-to-cad
```

The command asks which agents to install for, and where. An agent installing
without a person at the prompts names itself, installs for the user, and skips the
questions: `npx skills add earthtojake/text-to-cad -g -a <agent> -y`.

The skills install from `main`, and each one runs cadgen through
[uv](https://docs.astral.sh/uv/) with the same pinned command the plugin's server
uses, so uv must be installed. Without the plugin there is no CAD server, so the
skills open models in the CAD Viewer in your browser.

**Use the same command to update.** `add` re-fetches the package and overwrites
what is already installed, so it both refreshes existing skills and installs any
skill added in a newer release. `npx skills update` only refreshes skills already
in your lockfile, so it silently misses new ones — which matters here, because
releases do add skills.

Neither command removes a skill that was retired upstream; drop one with
`npx skills remove <skill>` if you need to. The retired `cad-viewer` skill is
now covered by the CAD, DXF and robot-description skills, and `cad-mcp-setup`
became `cad-setup`; remove old standalone installs with
`npx skills remove cad-viewer cad-mcp-setup`.

No plugin for your agent yet?
[Request one](https://github.com/earthtojake/text-to-cad/issues/new?title=Plugin%20request%3A%20).

### Updates

When a newer release is out, text-to-cad says so once per release: a card in
CAD's viewer, where **Send to agent** posts "Update text-to-cad to 0.9.0 from
https://github.com/earthtojake/text-to-cad" to your chat, worded like the install
message (the browser viewer's card copies it instead), or a line in your agent's
command output. Your agent then follows the `cad-setup` skill's steps
for your app. Copies from a plugin directory or the Cursor Marketplace are
updated by their store, so they hear nothing unless the store falls far behind.

To find out, cadgen fetches `api.texttocad.dev/v1/versions` at most once a day:
one anonymous request, with no ID, path or anything about you, and never in CI.
`CADGEN_UPDATE_CHECK=0` turns it off.

### Usage analytics

The CAD app (the plugin's `cad` server) and the browser viewer (`cadgen viewer`) can send anonymous usage counts: a
random install ID, versions, where you installed it from, your OS and agent app, how often each CAD tool was
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

## 🛠️ Contributing

Branch from `main` and open PRs against `main`. For the local workflow, testing in
agent apps and validation, see [CONTRIBUTING.md](CONTRIBUTING.md).
