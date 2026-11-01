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
2. Runs `cad setup` from the latest release, pinned, through uvx; for this
   release that is
   `uvx --no-config --managed-python --python 3.14 --refresh-package cad-server --refresh-package cad --from cad-server==0.10.0 cad setup`.
   Its first run downloads the release, and Python 3.14 for it.
3. Installs the release in a folder of its own in text-to-cad's state folder
   (`releases/<release>`), from uv's cache where it has it, and runs the rest from
   there. On a computer 0.8 was set up on, it then moves what 0.10 keeps of 0.8's state
   folder into its own, once: your telemetry answer and language, the installations'
   records, the page token, the documents' records and Recents
   ([Migrating from 0.8](migrations/migrating-0.8-to-0.10.md), item 5).
4. Finds your agent apps (Claude Code, Claude Desktop's Chat tab, Codex, Cursor,
   Grok Build and Gemini) and the copies of text-to-cad already in them, and prints
   its plan for each: add, update, remove a duplicate, or leave as it is.
5. Stops the server of a release from before 0.10 (0.8's cadgen) on CAD's port
   (3245, or `CAD_ENGINE_PORT`) when nothing is using it, through that installation's
   own `cadgen stop`. One still in use (an app session open on it, a page watching it, a
   build) is left running, and the plan says how to stop it.
6. Registers the release and writes the `cad` command (`~/.local/bin/cad`; on
   Windows `%USERPROFILE%\.local\bin\cad.cmd`), as the CAD server does when it
   starts.
7. Makes the CAD kernel environment, once: the release with its CAD kernel (OCP,
   build123d and what they need, about 220 MB the first time) on the same Python,
   in text-to-cad's cache folder ([What a model runs in](#what-a-model-runs-in)), so the
   first model builds without a download.
8. Writes the plugin, this release's, into a folder of text-to-cad's state folder
   (`plugin`), and points each app at that folder with the app's own commands
   ([What each app gets](#what-each-app-gets)), removing duplicate copies, among them
   one an earlier release installed from GitHub. A copy from a plugin directory
   (claude.ai's, Codex's) is a duplicate too: running the install command asks for
   this release, so it is removed with the app's own command and this release's
   installed in its place. A copy the app has no command of yours to remove (one an
   administrator manages or claude.ai syncs in Claude Code, the Cursor Marketplace's)
   is reported and kept, and that app gets nothing beside it. The agents without a
   plugin get the skills alone, copied from the folder through the Skills CLI
   ([Other Agents](#other-agents)). Claude Desktop's config gets CAD's server for this
   release, with a `.bak` of the file kept beside it.
9. Writes a receipt of everything it changed in text-to-cad's state folder.
10. Moves your computer's CAD server to this release: a running server finishes
    what it is doing (a build, an export), stops, and this release's takes its place
    on the same port, so every open page and card keeps its link and reloads itself;
    should it not start, the release before comes back. With none running, the next
    CAD session starts this release's.
11. Says what each app has now, and lists the apps to restart to load what it
    installed or updated.

It asks nothing on the way: it carries out the plan it prints, so a dry run is how
to see the plan before anything changes. Run it again to update: an app that is up
to date is left as it is. Options go after `sh -s --`:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh -s -- --dry-run            # print the plan, change nothing
curl -fsSL https://texttocad.dev/install.sh | sh -s -- --only claude,codex  # only these apps
curl -fsSL https://texttocad.dev/install.sh | sh -s -- --no-telemetry       # also turn telemetry off
curl -fsSL https://texttocad.dev/install.sh | sh -s -- --uninstall          # undo what the receipt records
```

`--only` takes `claude`, `claude-desktop`, `codex`, `cursor`, `grok` and `gemini`, and
the Skills CLI's ids of the agents under [Other Agents](#other-agents) (`windsurf`,
`goose` and so on; `cad setup --help` lists them).
`--uninstall` runs `cad uninstall` in place of `cad setup`: it takes back what
the receipt records, or, with no receipt, every copy of text-to-cad it finds but a
store's, removes the `cad` command and stops the server. A plugin directory's copy that
the install command replaced is not put back: install it from the directory again to
get it back. `--purge` with it also removes text-to-cad's state and cache folders.
`--version <release>` installs that release instead of the latest; a release from
before the install command has no `cad setup` to run. To read the script before it
runs, download it first, then run it:

```bash
curl -fsSL https://texttocad.dev/install.sh -o install.sh
sh install.sh --dry-run
```

On Windows, `irm https://www.texttocad.dev/install.ps1 -OutFile install.ps1` downloads
it, and `powershell -ExecutionPolicy Bypass -File install.ps1 --dry-run` runs it
with the same options.

## What each app gets

The install command gives every app the same plugin, from one folder on your computer
that the release writes: `plugin` in text-to-cad's state folder
(`~/Library/Application Support/cad/plugin` on macOS,
`~/.local/state/cad/plugin` on Linux, `%LOCALAPPDATA%\cad-state\plugin` on
Windows); `cad plugin` prints its path. It holds the plugin as the `latest` branch does
-- each app's manifest, its config for CAD's server, and the skills -- at the release
your computer runs, and is written again in place when an update moves your computer to
another release. Each app takes it the way it takes a local plugin:

| App | What it gets | After an update |
| --- | --- | --- |
| Claude Code | the folder added as a local catalog, `texttocad`, and its plugin installed, `text-to-cad@texttocad`; Claude Code reads the folder in place. A copy from claude.ai's directory is uninstalled first (`claude plugin uninstall`); one an administrator manages, or claude.ai syncs, is kept, and nothing is added beside it | its next session reads the new release; the update also refreshes the copy Claude Code keeps in its cache (`claude plugin update`), which Cursor and Grok Build may read |
| Codex | the same catalog and plugin; Codex copies the plugin when it is added. A copy from Codex's plugin directory is removed first (`codex plugin remove`), its catalog kept | the update adds it again; a running Codex session keeps the copy it started with until you restart it |
| Gemini CLI | the folder linked as its extension (`gemini extensions link`) | nothing to do: it reads the folder in place |
| Cursor | the plugin loaded with Claude Code's; without Claude Code, a copy of the folder in its local plugins folder, `~/.cursor/plugins/local/text-to-cad`. A copy from the Cursor Marketplace is kept, since Cursor has no command to uninstall it, and without Claude Code nothing is added beside it: uninstall it in Cursor, then run the install command again | the update copies the folder again |
| Grok Build | the plugin loaded with Claude Code's; without Claude Code, the plugin from the `latest` branch | `grok plugin update text-to-cad`, without Claude Code |
| Claude Desktop (Chat tab) | CAD's server in its config, run by your own `uvx` at its full path | the update moves the server to the new release |
| Other agents | the skills alone, copied from the folder by the Skills CLI | the update copies them again |

Nothing of it updates by itself: the folder and the copies move when you update
([Updates](#updates)). Leave the folder where it is: Claude Code and Gemini read it in
place. `cad doctor` says where each app's plugin comes from, and writes the folder
again if it is gone. The install command with `--uninstall` takes all of it out, the
folder too.

## App by app

1. CAD runs through [uv](https://docs.astral.sh/uv/): check that it is installed
   (`uv --version`), and if it is missing, install it with
   [uv's installer](https://docs.astral.sh/uv/getting-started/installation/).
2. Run the commands under your agent app's heading below, or under
   [Other Agents](#other-agents) if it has none.
3. Restart the app. Its first start downloads CAD's runtime and makes the environment
   models run in ([What a model runs in](#what-a-model-runs-in)), so it needs a network
   connection.

The plugin for your agent app brings the skills and CAD's viewer, a local server
(`cad-mcp`). For an agent without a plugin, install the skills alone. Install
one or the other in an app, not both: two copies means every skill twice.

The runtime supports Python 3.14+; the launch commands use uv-managed Python 3.14.

The commands below take the `latest` branch: it holds the plugin alone and gets
each release once it is on PyPI. `main`, where development happens, installs too,
but can hold changes that aren't released yet. Each app names the branch in its
own way (`#latest`, `--ref latest`, `@latest` or `--branch latest`); leave it out
and the app installs `main`. The install command, run later, replaces a copy
installed this way with the plugin folder's ([What each app gets](#what-each-app-gets)).

Each app's heading also says how to update text-to-cad, and how to reinstall it:
remove it, then install it again. Updating the plugin updates CAD: the new
release is downloaded the first time it runs, and the skills and the
server share it. Earlier releases stay in uv's cache until you run `uv cache prune`.

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
      "args": ["--no-config", "--managed-python", "--python", "3.14", "--from", "cad-mcp==0.10.0", "cad-mcp"],
      "env": {"CAD_INSTALL_CHANNEL": "claude-desktop"}
    }
  }
}
```

The config pins a release in `args`, and uvx keeps the version it first
downloads. To update, change that version to the
[latest release](https://pypi.org/project/cad-mcp/), then restart Claude Desktop.
The install command writes this entry, with uvx's full path, and moves its release
to the new one each time it updates.

### Codex

```bash
codex plugin marketplace add earthtojake/text-to-cad --ref latest
codex plugin add text-to-cad@earthtojake
```

In the Codex app the plugin also brings the CAD viewer: **CAD** in the sidebar
(recent models, and Open), a **CAD** tab beside each thread that the agent
drives, and *Open with CAD* for model files.

Codex's plugin directory lists text-to-cad too, but for now its listing trails
the releases, so install it from the marketplace. The install command replaces a
copy from the directory with the release's; installing from the directory alone
also works, since the plugin's server sets everything up on its first start. A copy
from the directory and one from the marketplace would load side by side: keep one.

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
gemini extensions install https://github.com/earthtojake/text-to-cad --ref latest --consent
```

Gemini installs the plugin as an extension, with the skills and CAD's server
(`--consent` answers its security prompt). Like
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
from the plugin folder's `skills` ([What each app gets](#what-each-app-gets)) into each
one's own skills folder with the [Skills CLI](https://skills.sh), which needs Node
(`npx`), in one command:
`npx --prefer-offline -y skills@latest add <plugin folder>/skills -g -a <agent> ... -s '*' -y --copy --json`.
It names each agent: it never does this for an app with a plugin, and moves a loose
copy of the skills out of such an app's skills folder. Cline and Zed keep skills in
`~/.agents/skills`, which Codex and Gemini CLI read too: there, those apps list the
skills beside their plugin's. Its receipt records which skills each agent got, from which
release; running it again, or an update, adds them again after a new release or when
one of them is gone, and `--uninstall` removes them.

For any other agent, install them with the Skills CLI yourself:

```bash
npx skills add earthtojake/text-to-cad#latest
```

The command asks which agents to install for, and where. To skip the questions,
name the agent and install for your user:
`npx skills add earthtojake/text-to-cad#latest -g -a <agent> -y`.

Each skill runs text-to-cad's server through the `cad` command, pinned to the skill's
release, which a run of `cad doctor` through uvx registers once (each skill's setup guide
gives it), so uv must be installed. Without the plugin there is no CAD server, so the
skills open models in the CAD Viewer in your browser.

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

When a newer release is out, CAD shows an update button: a blue icon first in its
navbar and on its home, and in the corner of a CAD card that has no navbar. Click
it, and the server installs the release, updates text-to-cad in every agent app on
your computer as the install command does, and restarts on the new release; the
page or the card reloads itself once the server is back. An app that shows CAD's
replies as text gets a line with its first reply instead, naming the install
command. Nothing updates until you ask.

Running the install command again does the same, and so does `cad update` in a
terminal: each installs the newest release, updates every app, moves the server to
it and lists the apps to restart. To update one app by hand, run the update
commands under its heading, then restart it.

An update writes the plugin folder again for the new release
([What each app gets](#what-each-app-gets)), with no network: Claude Code and Gemini
read it in place, and the apps that keep a copy of it (Codex, Cursor, the agents with
the skills alone) get it again. Should the new release's server not start, the release
before comes back, and its plugin and Claude Desktop's server with it; the CAD Viewer page
you clicked in says the update failed, and offers it again.

Your computer runs one CAD server, the current release's, whatever release each
app's plugin names: an app whose plugin is behind or ahead uses that server all the
same. An app runs its updated plugin from the session it starts after the update.
Each release is kept in a folder of its own in text-to-cad's state folder
(`releases/<release>`): the one before the current stays, to go back to should the
new one not start, and older ones go at the next update. `cad doctor` says
which releases are there, which one is current, the release the server runs, the
plugin folder's, and where each app's plugin comes from and its release.

Copies from a plugin directory or the Cursor Marketplace are not told of a release
from the feed, since their store updates their plugin. Once the store has moved an
app's plugin ahead of your server, the button shows for them too, and moves the
server to it.

To find out a release is out, text-to-cad fetches `api.texttocad.dev/v1/versions` at
most once an hour: one anonymous request, with no ID, path or anything about you,
never in CI and never for a copy that something else updates.
`CAD_UPDATE_CHECK=0` turns it off. An app whose plugin already runs a newer
release says so too, with no request at all. A click on the button reads the feed
again, for the newest release.

Updating from 0.8: [Migrating from 0.8 to 0.10](migrations/migrating-0.8-to-0.10.md) says
what 0.10 renames (the `cad` command, `CAD_*`, the folders, the packages) and what the
install command moves for you.

Updating from 0.8.0 or 0.8.1, whose engine runs until it is stopped:
[the migration guide](migrations/migrating-0.7-to-0.8.md#updating-from-080-or-081)
says what the install command and the new engine do with it.

A CAD project written for cadgen 0.7 needs porting to 0.8:
[the migration guide](migrations/migrating-0.7-to-0.8.md) takes one across, step by
step, and an agent with the CAD skill can follow it.

## What a model runs in

The release the install command runs is text-to-cad's server (`cad-server`): the
`cad` command, the CAD Viewer's server and the engine every build goes through, without
the CAD kernel. Each app's CAD server is the smaller `cad-mcp`, which
reaches it. A model runs where the kernel is: in one environment the server makes with uv
in its cache folder and keeps, the library with its kernel (`cad[build123d]`) on the
server's Python, 3.14. Every model runs there, and so do the server's own kernel
processes: exports, snapshots and the meshes the viewer shows. The install command makes
it; otherwise the server makes it as it starts, in the background (with a plugin alone,
the first start of an app's CAD app), and a first model or view waits for it. A model
imports what that environment holds: the library (`cad`), build123d and what they bring.

To run models with a Python of your own instead, install the library with its kernel
into it: `pip install 'cad[build123d]==0.10.0'` (`pip install cad==0.10.0` is the library alone,
and `import build123d` fails there). That environment is then the one models run in.

## Windows 11: Smart App Control

The CAD kernel behind the `cad`, `dxf`, `urdf`, `srdf` and `sdf`
skills is `OCP`, OpenCascade's Python binding, and its wheel ships an unsigned
native module. Windows 11's Smart App Control blocks unsigned native code, so
on a machine where it is on (the default on a fresh install) every `cad`
command and `import build123d` fails with
`ImportError: DLL load failed while importing OCP`, and Event Viewer records
the refusal as Event ID 3077 under CodeIntegrity › Operational. `cad doctor`
names this when it sees it.

Smart App Control has no per-app exception. Either turn it off (Settings ›
Privacy & security › Windows Security › App & browser control › Smart App
Control settings; once off it can only be turned back on by reinstalling
Windows) or run the CAD skills under WSL, where it does not apply. The wheel
is built by the cadquery-ocp project, so signing it is not something this
repository can do.
