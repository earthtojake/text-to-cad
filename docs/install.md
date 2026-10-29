# Installing text-to-cad by hand

The install command in the [README](../README.md) sets up text-to-cad in every
agent app on your computer, and running it again updates them all:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh
```

On Windows, in PowerShell: `irm https://www.texttocad.dev/install.ps1 | iex`. It names
`www.texttocad.dev` because `texttocad.dev` redirects there with a 308, which Windows
PowerShell 5.1's `irm` does not follow.

This page is the long way round: what that command does, step by step, each agent
app's own commands to install, update or reinstall text-to-cad one app at a time,
and how [updates](#updates) reach you.

## What the install command does

It is a short script, served by texttocad.dev and attached to each
[release](https://github.com/earthtojake/text-to-cad/releases) with its SHA-256
checksum. It:

1. Finds [uv](https://docs.astral.sh/uv/), or installs it with uv's own installer.
2. Runs `cadgen setup` from the latest release, pinned, through uvx; for this
   release that is
   `uvx --no-config --managed-python --python 3.13 --from cadgen==0.8.3 cadgen setup`.
   Its first run downloads the release, and Python 3.13 for it.
3. Finds your agent apps (Claude Code, Claude Desktop's Chat tab, Codex, Cursor,
   Grok Build and Gemini) and the copies of text-to-cad already in them, and prints
   its plan for each: add, update, remove a duplicate, or leave as it is.
4. Stops an older cadgen's engine on CAD's port (3245, or `CADGEN_PORT`) once
   nothing is using it, through that engine's own `cadgen stop`, so the new
   release's engine can take the port.
5. Installs or updates text-to-cad in each app with the app's own commands, the
   ones below, and removes duplicate copies. A copy that a plugin store manages is
   reported, never removed. The agents without a plugin get the skills alone, through
   the Skills CLI ([Other Agents](#other-agents)). Each app's line that starts CAD's
   server names the release it was installed with, written once: from then on that
   release is a floor, not what runs.
6. Registers the release and makes it the one your computer runs: a small file in
   cadgen's state folder, `current`, names it, and each app's server, whatever
   release its line names, starts or attaches to the engine of the release `current`
   names. Then it registers the `cadgen` command (`~/.local/bin/cadgen`; on Windows
   `%USERPROFILE%\.local\bin\cadgen.cmd`), writes a receipt of everything it
   changed in cadgen's state folder, checks the result with `cadgen doctor`, and
   lists the apps to restart to load what it added for the first time.

It asks nothing on the way: it carries out the plan it prints, so a dry run is how
to see the plan before anything changes. Run it again to update: an app that is up
to date is left as it is. From then on it updates itself: within the hour of each
release, CAD's engine runs that release's `cadgen setup` for the same apps, and the
next thread or session an app starts runs it ([Updates](#updates)). Options go
after `sh -s --`:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh -s -- --dry-run            # print the plan, change nothing
curl -fsSL https://texttocad.dev/install.sh | sh -s -- --only claude,codex  # only these apps
curl -fsSL https://texttocad.dev/install.sh | sh -s -- --no-telemetry       # also turn telemetry off
curl -fsSL https://texttocad.dev/install.sh | sh -s -- --uninstall          # undo what the receipt records
```

`--only` takes `claude`, `claude-desktop`, `codex`, `cursor`, `grok` and `gemini`, and
the Skills CLI's ids of the agents under [Other Agents](#other-agents) (`windsurf`,
`goose` and so on; `cadgen setup --help` lists them).
`--uninstall` runs `cadgen uninstall` in place of `cadgen setup`: it takes back what
the receipt records, or, with no receipt, every copy of text-to-cad it finds but a
store's; `--purge` with it also removes cadgen's state and cache folders.
`--version <release>` installs that release instead of the latest, and makes it the
one your computer runs even when a newer one is installed. To read the
script before it runs, download it first, then run it:

```bash
curl -fsSL https://texttocad.dev/install.sh -o install.sh
sh install.sh --dry-run
```

On Windows, `irm https://www.texttocad.dev/install.ps1 -OutFile install.ps1` downloads
it, and `powershell -ExecutionPolicy Bypass -File install.ps1 --dry-run` runs it
with the same options.

## App by app

1. CAD runs through [uv](https://docs.astral.sh/uv/): check that it is installed
   (`uv --version`), and if it is missing, install it with
   [uv's installer](https://docs.astral.sh/uv/getting-started/installation/).
2. Run the commands under your agent app's heading below, or under
   [Other Agents](#other-agents) if it has none.
3. Restart the app. Its first start downloads CAD's runtime, so it needs a network
   connection.

The plugin for your agent app brings the skills and CAD's viewer, a local server
(`cadgen mcp`). For an agent without a plugin, install the skills alone. Install
one or the other in an app, not both: two copies means every skill twice.

The commands below take the `latest` branch: it holds the plugin alone and gets
each release once it is on PyPI. `main`, where development happens, installs too,
but can hold changes that aren't released yet. Each app names the branch in its
own way (`#latest`, `--ref latest`, `@latest` or `--branch latest`); leave it out
and the app installs `main`.

Each app's heading also says how to update text-to-cad, and how to reinstall it:
remove it, then install it again. Updating the plugin updates CAD: the new
release's engine is downloaded the first time it runs, and takes over from an
older one once nothing is using that one. Models run with `cadgen run model.py`,
which makes each project's Python environment with uv (the dependencies the project
declares, and the engine's own cadgen) and starts the engine when none is running;
nothing is installed in the project. The runtime supports Python 3.11 to 3.14, the
versions OCP and build123d publish for: the launch commands use uv-managed Python
3.13, and a project's environment uses the Python the project declares when it is one
of those, else the engine's. Earlier releases stay in uv's cache until you run
`uv cache prune`.

### Claude Code

Claude Desktop's Code tab uses this plugin. Its regular Chat tab needs separate
local MCP setup; Cowork uses the plugin's bundled MCP server.

```bash
claude plugin marketplace add earthtojake/text-to-cad#latest
claude plugin install text-to-cad@earthtojake
```

The plugin also starts CAD's server. Where Claude Code can show app views, CAD
shows models as viewer cards in the conversation; otherwise, as in a terminal,
asking it to show a model gives you a link that opens the model in the CAD
Viewer in your browser.

To update, run these, then restart Claude Code:

```bash
claude plugin marketplace update earthtojake
claude plugin update text-to-cad@earthtojake
```

To reinstall, remove it with these, then run the install commands again:

```bash
claude plugin uninstall text-to-cad@earthtojake
claude plugin marketplace remove earthtojake
```

### Claude Desktop: Chat tab

Use this setup for CAD in Claude Desktop's **Chat** tab. Claude Code and Cowork
use the plugin's bundled MCP server and do not need this separate configuration.

CAD shows models in the chat: ask Claude to show one and it appears as a viewer
card you can orbit, add to your prompt, and open full size; Claude can read what
you selected and see what you see. It runs locally through uv: add the server to
Claude Desktop's config (Settings > Developer > Edit Config), then restart the
app. If Claude Desktop cannot find `uvx`, give its full path (`which uvx`).

```json
{
  "mcpServers": {
    "cad": {
      "command": "uvx",
      "args": ["--no-config", "--managed-python", "--python", "3.13", "--from", "cadgen==0.8.3", "cadgen", "mcp"],
      "env": {"CADGEN_INSTALL_CHANNEL": "claude-desktop"}
    }
  }
}
```

The release in `args` is a floor: once your computer runs a newer one (the install
command, or its updates, `current` in cadgen's state folder), the server runs that
one instead, from its next start. Nothing in this config needs changing for an
update; to set up a computer the install command never did, name the
[latest release](https://pypi.org/project/cadgen/) there.

### Codex

```bash
codex plugin marketplace add earthtojake/text-to-cad --ref latest
codex plugin add text-to-cad@earthtojake
```

In the Codex app the plugin also brings the CAD viewer: **CAD** in the sidebar
(recent models, and Open), a **CAD** tab beside each thread that the agent
drives, and *Open with CAD* for model files.

Codex's plugin directory lists text-to-cad too, but for now its listing trails
the releases, so install it from the marketplace. A copy from the directory and
one from the marketplace would load side by side: keep one.

To update, upgrade the `earthtojake` marketplace (or use Plugins › Manage ›
Marketplace), then restart Codex:

```bash
codex plugin marketplace upgrade earthtojake
```

To reinstall, remove it with these, then run the install commands again:

```bash
codex plugin remove text-to-cad@earthtojake
codex plugin marketplace remove earthtojake
```

The marketplace was renamed from `text-to-cad` to `earthtojake`; if you added it
before, remove the old one first (`codex plugin marketplace remove text-to-cad`).

### Cursor

Cursor also loads the plugin installed with Claude Code. If the Claude Code plugin
is installed, Cursor already has text-to-cad: skip this.

```bash
git clone --depth 1 --branch latest https://github.com/earthtojake/text-to-cad ~/.cursor/plugins/local/text-to-cad
```

Cursor reads `.cursor-plugin/plugin.json`: restart Cursor after cloning. Teams
can import the repository instead, under **Dashboard → Plugins & MCPs → Team
Marketplaces**.

To update, pull the latest release, then restart Cursor:

```bash
git -C ~/.cursor/plugins/local/text-to-cad pull
```

To reinstall, delete the folder, then run the install command again:

```bash
rm -rf ~/.cursor/plugins/local/text-to-cad
```

### Grok Build

Grok Build also loads the plugin installed with Claude Code. If the Claude Code
plugin is installed, Grok Build already has text-to-cad: skip this.

```bash
grok plugin install earthtojake/text-to-cad@latest --trust
grok plugin enable text-to-cad
```

Grok Build reads the Claude plugin manifest. Grok shows tool results as text, so
asking it to show a model gives you a CAD Viewer link.

To update, run this, then restart Grok Build:

```bash
grok plugin update text-to-cad
```

To reinstall, remove it with this, then run the install commands again:

```bash
grok plugin uninstall text-to-cad
```

### Gemini

```bash
gemini extensions install https://github.com/earthtojake/text-to-cad --ref latest --consent --auto-update
```

Gemini installs the plugin as an extension, with the skills and CAD's server, and
keeps it up to date (`--auto-update`; `--consent` answers its security prompt). Like
Grok, it shows tool results as text, so asking it to show a model gives you a CAD
Viewer link.

To update now, run this, then restart Gemini:

```bash
gemini extensions update text-to-cad
```

To reinstall, remove it with this, then run the install command again:

```bash
gemini extensions uninstall text-to-cad
```

### Other Agents

For an agent without plugin support: the skills give you everything you need for
core CAD workflows and let you view CAD files in a localhost web app. The install
command gives them to the agents it knows when they are installed: GitHub Copilot
(VS Code's agent too), Windsurf, Cline, Amp, Antigravity, OpenClaw, Droid, Goose,
Kilo Code, Kiro CLI, Hermes Agent, OpenCode, Roo Code, Trae and Zed. It copies them
into each one's own skills folder with the [Skills CLI](https://skills.sh), which
needs Node (`npx`), in one command:
`npx -y skills@latest add earthtojake/text-to-cad#latest -g -a <agent> ... -s '*' -y --copy --json`.
It never does this for an app with a plugin, and moves a loose copy of the skills
out of such an app's skills folder. Cline and Zed keep skills in `~/.agents/skills`,
which Codex and Gemini CLI read too: there, those apps list the skills beside their
plugin's. Its receipt records which skills each agent got, from which release; running
it again adds them again after a new release or when one of them is gone, and
`--uninstall` removes them.

For any other agent, install them with the Skills CLI yourself:

```bash
npx skills add earthtojake/text-to-cad#latest
```

The command asks which agents to install for, and where. To skip the questions,
name the agent and install for your user:
`npx skills add earthtojake/text-to-cad#latest -g -a <agent> -y`.

Follow the skill's setup instructions to register cadgen. Run model scripts with
`cadgen run model.py`, which makes the project's Python environment and starts the
engine when none is running; to view files alone, start `cadgen server`. The skills
open models in the CAD Viewer in your browser.

**To update or reinstall, run the same command again**, then restart the app.
`add` re-fetches the package and overwrites what is already installed, so it both
refreshes existing skills and installs any skill added in a newer release.
`npx skills update` only refreshes skills already in your lockfile, so it silently
misses new ones — which matters here, because releases do add skills.

Neither command removes a skill that was retired upstream; drop one with
`npx skills remove <skill>` if you need to. The retired `cad-viewer` skill is
now covered by the CAD, DXF and robot-description skills, and the retired
`cad-mcp-setup` by the install command and this page. Remove old standalone
installs with `npx skills remove cad-viewer cad-mcp-setup`.

No plugin for your agent yet?
[Request one](https://github.com/earthtojake/text-to-cad/issues/new?title=Plugin%20request%3A%20).

## Updates

Once the install command has set your computer up, text-to-cad updates itself, and
there is nothing to restart or click.

CAD's engine checks for a newer release once an hour, starting a minute or two after
it starts. When there is one, it first downloads that release whole, CAD kernel
and all, which can take minutes on a slow connection; nothing changes until the
download is complete. Then it runs that release's `cadgen setup` for the same apps
the install command set up (the apps `--only` named, if it named any): that
refreshes the skills through each app's own plugin command, registers the release,
and makes it the one `current` names. No app's config is rewritten for it: the
release each app's server line names is the floor it was installed with, and each
app's server starts or attaches to the engine of the release `current` names. So the
next thread or session an app starts runs on the new release's engine; one already
running keeps the engine it started with, and is never changed under you. The engine of the release before steps aside
by itself once nothing is using it: no app holding it and nothing asked of it for
half a minute. With a CAD Viewer page open, it first starts the new release's
engine, and the page reloads on it. A release that fails to install is tried again
the next day, or whenever you ask.

A host can bring a newer release too: when an app updates its plugin by itself, its
server's floor moves past `current`, and that release becomes current the first
time it starts. A copy from a plugin directory or the Cursor Marketplace is updated
by its store, and Gemini's extension by Gemini; the update leaves those as they are.

CAD's blue update button, first in its navbar and on its home, shows only when there
is something for you to do: while the update is on its way, and once it is
installed, it stays out of sight. Could not install: what went wrong, and **Try
again**, which starts the update at once and shows it downloading and installing
until it is done. The card's **Manual installation** leads to the
[install instructions](https://www.texttocad.dev/install): the install command still
updates everything at once, whenever you run it. In an app that shows CAD's replies
as text, a line with its reply says when an update could not install, with the
command.
Where you installed text-to-cad another way, the button says a newer release is
out, its card shows the install command to copy, and its **Send to agent** posts
"Run `curl -fsSL https://texttocad.dev/install.sh | sh` to update text-to-cad to
0.9.0 (on Windows: `irm https://www.texttocad.dev/install.ps1 | iex`)" to your
chat: the command is the update; copies from a plugin directory or the Cursor
Marketplace never show it, since their store updates them, and neither does
Gemini's extension, which Gemini updates. `cadgen doctor` says where the update
stands, on its `update` line (`installed v0.9.0; new sessions run it` once it is in),
and which release your computer runs, on its `current` line.

To update one app by hand, run the update commands under its heading, then
restart it.

To find out, cadgen fetches `api.texttocad.dev/v1/versions` at most once an hour:
one anonymous request, with no ID, path or anything about you, never in CI. One
switch turns the check and the update off: `CADGEN_UPDATE_CHECK=0` in the
environment of the app that starts CAD's engine; then the install command is the
update.

The Python environments `cadgen run` makes for your projects follow the engine on
their own; a virtual environment you installed cadgen into yourself is yours to
update (`uv pip install -U cadgen`).

Updating from 0.8.0 or 0.8.1, whose engine never exits on its own: the install
command stops it. By hand, run `cadgen stop` once to stop it, then restart the app
([details](migrations/migrating-0.7-to-0.8.md#updating-from-080-or-081)).

A CAD project written for cadgen 0.7 needs porting to 0.8:
[the migration guide](migrations/migrating-0.7-to-0.8.md) takes one across, step by
step, and an agent with the CAD skill can follow it.

## Windows 11: Smart App Control

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
