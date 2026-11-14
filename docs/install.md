# Installing text-to-cad by hand

The install command in the [README](../README.md) sets up text-to-cad in every
agent app on your computer, and running it again updates them all:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh
```

On Windows, in PowerShell: `irm https://www.texttocad.dev/install.ps1 | iex`. It names
`www.texttocad.dev` because `texttocad.dev` redirects there with a 308, which Windows
PowerShell 5.1's `irm` does not follow. Run it the first time in a terminal of
its own (Windows Terminal or PowerShell), not in a Windows Store app's shell such
as the Claude desktop app's: Windows keeps what such an app's commands write under
`AppData` inside that app, uv's Python among it, where no terminal and no other
agent app finds it, so a first install there installs nothing and says so. Once
installed, updating from any app works.

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
   `uvx --no-config --managed-python --python 3.14 --refresh-package cad-server --refresh-package cad --from cad-server==0.11.11 cad setup`.
   Its first run downloads the release, and Python 3.14 for it.
3. Installs the release in a folder of its own in text-to-cad's state folder
   (`versions/<release>`), from uv's cache where it has it, and runs the rest from
   there. The folder holds the release's server and the CAD kernel models run in
   (OCP, build123d and what they need: about 240 MB to download, about 620 MB on
   disk), so your first model doesn't wait for it
   ([What a model runs in](#what-a-model-runs-in)). On Linux the CAD kernel needs the
   system's OpenGL library, `libGL.so.1` (the `libgl1` package on Debian and Ubuntu):
   without it, `cad doctor` reports the kernel as failing straight after the install.
   On a computer 0.8 was set up on, it first moves what 0.10 keeps of 0.8's state
   folder into its own, once: your telemetry answer and language, the documents' records
   and Recents, and 0.8's setup receipt
   ([Migrating from 0.8](migrations/migrating-0.8-to-0.10.md), item 5).
4. Finds your agent apps (Claude Code, Claude Desktop, Codex, Cursor,
   Grok Build and Gemini) and the copies of text-to-cad already in them, and prints
   its plan for each: add, update, remove a duplicate, or leave as it is.
5. Stops 0.8's server, where 0.8 is installed, with that installation's own
   `cadgen stop`, and says what it stopped: 0.10 never talks to anything of 0.8's itself.
   An app still running the 0.8 plugin goes on with 0.8 alone until it restarts (step 10
   lists the apps to restart); a 0.8 server it starts again keeps CAD's port (3245, or
   `CAD_ENGINE_PORT`), and the new release's serves on the next free port, and says so.
6. Writes the `cad` command (`~/.local/bin/cad`; on Windows
   `%USERPROFILE%\.local\bin\cad.exe`, with the Python it runs by beside it,
   `cad-launcher`). Every release is run through it
   ([Releases side by side](#releases-side-by-side)).
7. Moves your computer to this release (its default channel:
   [Releases side by side](#releases-side-by-side)). It copies what cannot be
   made again from the release it replaces: your settings (the telemetry and
   automatic-update choices among them), Recents, the documents' records, and the port
   and token of CAD's page links. A CAD server that is running finishes what it is doing
   (a build, an export), stops, and this release's takes its place on the same port, so
   every open page and card keeps its link and reloads itself. Where a plugin directory's
   copy is still on the release before, that release's server stays, and this release's
   serves on the next free port ([After an update](#after-an-update)). With none running,
   the next CAD session starts this release's. The release before is removed once no
   channel is on it and no work is in flight there, after what it wrote since is carried
   over. Should this step fail, nothing has changed, and no app is touched.
8. Writes the plugin, this release's, into a folder of text-to-cad's state folder
   (`plugin`), and points each app at that folder with the app's own commands
   ([What each app gets](#what-each-app-gets)), removing duplicate copies, among them
   one an earlier release installed from GitHub. A copy from a plugin directory
   (claude.ai's, Codex's) is that app's to deliver and update:
   it is kept, and that app gets nothing beside it; its line says how to switch to
   this release's (remove it in the app's own plugin manager, then run the install
   command again). So is one an administrator manages or claude.ai syncs in Claude
   Code, and one Cursor installed from a marketplace added in Cursor, which
   text-to-cad does not update ([Cursor](#cursor)). The agents without a plugin get the skills alone, copied from the folder
   through the Skills CLI ([Other Agents](#other-agents)). Claude gets the skills
   alone, no CAD server: the one releases through 0.11.10 wrote into Claude Desktop's
   config is taken out, the rest of the file kept and a `.bak` of it beside it, and so
   is a CAD server added to Claude Code with `claude mcp add`, for you or for one project.
9. Writes a receipt of everything it changed in text-to-cad's state folder. The
   receipt is also what lets this install update itself ([Updates](#updates)).
10. Says what each app has now, and ends with the apps to restart to load what it
    installed or updated ("Next, restart to load it:"). An agent whose skills folder lacks one of the skills it
    was given fails the run: its line says which, and the command exits 1.

It asks nothing on the way: it carries out the plan it prints, so a dry run is how
to see the plan before anything changes. Run it again to update: an app that is up
to date is left as it is. Options go after `sh -s --`:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh -s -- --dry-run            # print the plan, change nothing
curl -fsSL https://texttocad.dev/install.sh | sh -s -- --only claude,codex  # only these apps
curl -fsSL https://texttocad.dev/install.sh | sh -s -- --no-telemetry       # also turn telemetry off
curl -fsSL https://texttocad.dev/install.sh | sh -s -- --uninstall          # undo what the receipt records
curl -fsSL https://texttocad.dev/install.sh | sh -s -- --add X.Y.Z          # install release X.Y.Z alone
```

`--only` takes `claude`, `claude-desktop`, `codex`, `cursor`, `grok` and `gemini`, and
the Skills CLI's ids of the agents under [Other Agents](#other-agents) (`windsurf`,
`goose` and so on; `cad setup --help` lists them).
`--add X.Y.Z` installs that one release, and the `cad` command where it is missing,
and changes nothing else: no app, no other release, no setting. A skill asks for it
when the release its commands name is missing and cannot be installed from the
agent's shell. It works for 0.11.11 and later.

`--uninstall` runs `cad uninstall` in place of `cad setup`: it takes back what the
install command put on your computer. That is the copies of text-to-cad it gave your
apps (with no receipt, every copy of ours it finds), the plugin folder, the release
your computer runs and its server, the folders of releases before 0.11.11, and the
receipt. Your settings, Recents and documents' records stay: install again and the
release finds them, or a newer release takes them over. A copy from a plugin directory stays, with its release, its settings and its
Recents: its store delivered it. While one does, so does the `cad` command it runs,
and a line says which channel is still installed, on which release: its store's plugin
uses the command, and `cad uninstall --purge` removes it too. A chat an app still has
open with text-to-cad stops using it and says text-to-cad was uninstalled. Then restart
the apps the uninstall lists: a chat started in an app that still holds the plugin can
install text-to-cad again. Nothing is removed from under a program still running from
it: the release's folder stays with your data kept, the line says why (naming the
program where your system can tell), and the uninstall fails. On Windows, a `cad
uninstall` typed in a terminal runs from the release it removes, which Windows will not
delete while it runs: the line says so, and the rest is done. Delete the folder the line
names once that program, or that command, has ended, or install again, which uses it or
removes it.
A plugin directory's copy that the install command of a release through 0.11.10
replaced is not put back: install it from the directory again to get it back.
`--purge` with it removes everything: every release, a store's among them, and
text-to-cad's state and cache folders, your settings and Recents with them.
Asking for it is the yes: the install command passes `--yes` to `cad uninstall`. Run
`cad uninstall` yourself and it prints the same plan and asks before it changes
anything (`Take text-to-cad out as planned? (y/N)`); where nothing can ask (a script,
an agent), it changes nothing without `--yes`, and says the command with it.
`cad delete`, `cad doctor --prune` and `cad server --rotate-token` ask the same way.

The state folder is `~/Library/Application Support/cad` on macOS, `~/.local/state/cad`
on Linux and `%USERPROFILE%\.local\state\cad` on Windows; the cache folder is
`~/.cache/cad` (`%USERPROFILE%\.cache\cad` on Windows). Without `--purge`, the state
folder keeps a few small files that releases before 0.11.11 read, `settings.json`
among them. Neither touches uv or what uv keeps in its own cache.

`--version <release>` installs that release instead of the latest; a release from
before the install command has no `cad setup` to run. Going back to a release before
0.11.11 by hand, this way or any other, is not supported. To read the script before it
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
`~/.local/state/cad/plugin` on Linux and on Windows, where it is
`%USERPROFILE%\.local\state\cad\plugin`); `cad plugin` prints its path. It holds the plugin as the `latest` branch does
-- each app's manifest, its config for CAD's server, and the skills -- at the release
your computer runs, and is written again in place when an update moves your computer to
another release. Each app takes it the way it takes a local plugin:

| App | What it gets | After an update |
| --- | --- | --- |
| Claude Code | the skills: the folder added as a local catalog, `text-to-cad`, and its plugin installed, `text-to-cad@text-to-cad`; Claude Code reads the folder in place. The plugin starts no server for Claude Code, and a CAD server added with `claude mcp add` is removed. A copy from claude.ai's directory, or one an administrator manages or claude.ai syncs, is kept, and nothing is added beside it | its next session reads the new release; the update also refreshes the copy Claude Code keeps in its cache (`claude plugin update`), which Cursor and Grok Build may read |
| Codex | the same catalog and plugin; Codex copies the plugin when it is added. On a Mac, ChatGPT.app bundles Codex's command (`/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex`), so with that app installed Codex counts as present even with no `codex` command; with a `codex` command too (npm's, say), the install command uses the newer of the two. A copy from Codex's plugin directory, as Codex's own listing names it, is kept, and nothing is added beside it; one only Codex's plugin cache holds (Codex loads it only while you are signed in) gets this release's beside it, and a line says to remove one copy if the skills show twice | the update adds it again; a running Codex session keeps the copy it started with until you restart it |
| Gemini CLI | the folder linked as its extension (`gemini extensions link`) | nothing to do: it reads the folder in place |
| Cursor | the plugin loaded with Claude Code's, CAD's server included (Cursor reads its own manifest first); without Claude Code, a copy of the folder in its local plugins folder, `~/.cursor/plugins/local/text-to-cad`. A copy Cursor installed from a marketplace added in Cursor is kept, since Cursor has no command to uninstall it, and without Claude Code nothing is added beside it: uninstall it in Cursor, then run the install command again | the update copies the folder again |
| Grok Build | the plugin loaded with Claude Code's, CAD's server included (Grok reads its own manifest first); without Claude Code, the plugin from the `latest` branch | `grok plugin update text-to-cad`, without Claude Code |
| Claude Desktop | nothing: its Code tab runs Claude Code, which loads the plugin's skills. The CAD server releases through 0.11.10 wrote into its config is taken out | nothing to do |
| Other agents | the skills alone, copied from the folder by the Skills CLI | the update copies them again |

The folder and the copies move with each update, yours or an automatic one
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
3. Restart the app. The first time it starts CAD's server, text-to-cad installs its
   release (Claude starts none: there the first skill command does): a download, then the
   environment models run in ([What a model runs in](#what-a-model-runs-in)). That needs a
   network connection and takes from half a minute to a few minutes, which can be longer
   than the app waits for the server (Codex: 30 seconds). CAD's server then answers that it
   is still installing, and the chat that started it may have no CAD tools: start a new
   chat, or restart the app, once it has finished. An install that was interrupted resumes
   at the next start.

The plugin for your agent app brings the skills and CAD's viewer, a local server
(`cad-mcp`); Claude's brings the skills alone, and shows models in your browser. For an agent without a plugin, install the skills alone. Install
one or the other in an app, not both: two copies means every skill twice.

The runtime supports Python 3.13+; the launch commands use uv-managed Python 3.14.

The commands below take the `latest` branch: it holds the plugin alone and gets
each release once it is on PyPI. `main`, where development happens, installs too,
but can hold changes that aren't released yet. Each app names the branch in its
own way (`#latest`, `--ref latest`, `@latest` or `--branch latest`); leave it out
and the app installs `main`. The install command, run later, replaces a copy
installed this way with the plugin folder's ([What each app gets](#what-each-app-gets)).

Each app's heading also says how to update text-to-cad, and how to reinstall it:
remove it, then install it again. Updating the plugin updates CAD: the new
release is installed the first time one of its commands runs, and the skills and the
server share it. uv keeps what it downloaded in its own cache until you run
`uv cache prune`.

### Claude Code

The plugin gives Claude Code the skills alone: Claude gets no CAD server, in a
terminal or in Claude Desktop's Code tab.

```bash
claude plugin marketplace add earthtojake/text-to-cad#latest
claude plugin install text-to-cad@earthtojake
```

Asking it to show a model gives you a link that opens the model in your browser,
or in the desktop app's browser pane.

The copy from claude.ai's plugin directory carries the skills alone too. It runs the
release the directory last delivered, beside the install command's
([Releases side by side](#releases-side-by-side)), and the directory updates it. Where
the `cad` command is missing, its skills install it with uv rather than the install script;
for this release that is
`uvx --no-config --managed-python --python 3.14 --from cad-server==0.11.11 cad setup --add`. Copies
from it through 0.11.10 name CAD's server: when Claude
Code starts it, it offers no tools, since the Code tab refuses the calls its cards
make; set `CAD_MCP_CARDS=1` in the server's environment to keep them, for testing.

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

### Claude Desktop

text-to-cad sets up nothing in Claude Desktop: its Code tab runs Claude Code, which
loads the plugin's skills ([Claude Code](#claude-code)), and models open in your
browser. Its Chat tab gets no CAD server.

Releases through 0.11.10 added CAD's server to its config, as `cad` under
`mcpServers`. The install command, and every update, takes that entry out, keeps the
rest of the file as it was and a `.bak` of it beside it, and leaves a config it cannot
read alone. The server Claude Desktop runs keeps working until it next starts. To take
it out by hand, remove `cad` from `mcpServers` in its config (Settings > Developer >
Edit Config, or `~/Library/Application Support/Claude/claude_desktop_config.json` on a
Mac), then quit and reopen the app.

### Codex

```bash
codex plugin marketplace add earthtojake/text-to-cad --ref latest
codex plugin add text-to-cad@earthtojake
```

In the Codex app the plugin also brings the CAD viewer: **CAD** in the sidebar
(recent models, and Open), a **CAD** tab beside each thread that the agent
drives, and *Open with CAD* for model files.

Codex's plugin directory lists text-to-cad too, but for now its listing trails
the releases, so install it from the marketplace. The install command keeps a copy
from the directory, which the directory updates, and adds nothing beside it: to get
the release's instead, remove it in Codex's plugin manager, then run the install
command again. Installing from the directory alone also works, since the plugin's
server sets everything up on its first start. A copy from the directory runs the
release the directory last delivered, beside the install command's
([Releases side by side](#releases-side-by-side)). A copy from the directory and one from
the marketplace would load side by side: keep one.

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

Cursor can also install text-to-cad from a marketplace added in Cursor: a team
marketplace that imports this repository, or the repository added as one. Cursor keeps
that copy in its own app data, at the commit it fetched from the repository's default
branch. text-to-cad does not update that copy and does not know when Cursor will fetch
the repository again, so it can be many releases behind. A copy that old runs its own
release's commands (before 0.8 they were `cadgen` commands), and updating text-to-cad on
the same computer does not change it. Cursor has no command to uninstall it, so the
install command keeps it and adds nothing beside it. To get the current release in
Cursor, uninstall that copy in Cursor's plugin manager, then run the install command.

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

Grok Build reads its own manifest (`.grok-plugin/plugin.json`), which names CAD's
server, before Claude's, which names none. Grok shows tool results as text, so
asking it to show a model gives you a link that opens it in your browser.

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
Grok, it shows tool results as text, so asking it to show a model gives you a link
that opens it in your browser.

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
from the plugin folder's `skills` ([What each app gets](#what-each-app-gets)) with the
[Skills CLI](https://skills.sh), which needs Node (`npx`), into the skills folder it
keeps for each, in one command:
`npx --prefer-offline -y skills@latest add <plugin folder>/skills -g -a <agent> ... -s '*' -y --copy --json`.
It names each agent: it never does this for an app with a plugin, and moves a loose
copy of the skills out of such an app's skills folder. For GitHub Copilot, Amp,
Antigravity, Cline, Droid, Kilo Code, OpenCode and Zed, the Skills CLI copies them
into `~/.agents/skills`, never the agent's own folder (`~/.copilot/skills`,
`~/.factory/skills` and so on). All of them but Antigravity, whose documentation
names only its own folders, read it there, and so do Codex and Gemini CLI, which
list the skills beside their plugin's. Its receipt records which skills each agent got, from which
release; running it again, or an update, adds them again after a new release or when
one of them is gone, and `--uninstall` removes them.

For any other agent, install them with the Skills CLI yourself:

```bash
npx skills add earthtojake/text-to-cad#latest
```

The command asks which agents to install for, and where. To skip the questions,
name the agent and install for your user:
`npx skills add earthtojake/text-to-cad#latest -g -a <agent> -y`.

Each skill runs text-to-cad's server through the `cad` command, which the install command
writes (each skill's setup says so), so run it once. Without the plugin there is no CAD
server, so the skills open models in your browser.

**To update or reinstall, run the same command again**, then restart the app.
`add` re-fetches the package and overwrites what is already installed, so it both
refreshes existing skills and installs any skill added in a newer release.
`npx skills update` only refreshes skills already in your lockfile, so it silently
misses new ones — which matters here, because releases do add skills.

Neither command removes a skill that was retired upstream; drop one with
`npx skills remove <skill>` if you need to. The retired `cad-viewer` skill is
now covered by the CAD and robot-simulation skills, and the retired
`cad-mcp-setup` by the install command and this page. Remove old standalone
installs with `npx skills remove cad-viewer cad-mcp-setup`.

No plugin for your agent yet?
[Request one](https://github.com/earthtojake/text-to-cad/issues/new?title=Plugin%20request%3A%20).

## Updates

What the install command set up updates itself with every release that breaks nothing,
which needs nothing of you: fixes, additions, and new names for what a model imports with
the old names still working (a model that still uses an old name says so in a warning
naming the new one). Its version numbers follow [Semantic Versioning](https://semver.org),
so the number says which kind a release is: before 1.0, a patch release, like 0.11.0 to
0.11.1; from 1.0, a patch or minor release, like 1.4.2 to 1.4.3 or 1.5.0. Once an hour the
CAD server checks whether a newer release is out, and when it is one of those, it
installs it in the background at once. It then waits until text-to-cad has had nothing
to do for an hour (no command of any kind: no `cad` command, build, picture, export or
agent's tool call), so an update rarely lands while an agent is working. Then it moves your computer to the new release and
updates text-to-cad in every agent app on your computer, as the install command does.
Should an update fail, your computer stays on the release it ran, and that release is
not tried again by itself for a day; a newer one is tried when it comes out. With no
network nothing happens, and nothing waits.

A release that may break something never installs itself: before 1.0, a new minor or major
release, like 0.11 to 0.12; from 1.0, a new major release, like 1.5 to 2.0. It can rename a
command or change how a model is written (its migration guide says what), so it waits for
you. CAD shows its update button for it, and `cad update auto` says it is out; click the
button or run `cad update` when you are ready.

To turn automatic updates off, uncheck **Automatic updates** in the menu under CAD's
logo (on a CAD page in your browser or a CAD card), or run `cad update auto off`; `cad
update auto on` turns them back on, and `cad update auto` says whether they are on, when
the server last checked and when it checks next. The setting is one for every app on your
computer, and each update carries it to the new release. `CAD_UPDATE_CHECK=0` in the
server's environment turns the check off, and automatic updates with it.

With automatic updates off, or until one comes, CAD shows an update button when a
newer release is out: a blue icon first in its navbar and on its home, and in the
corner of a CAD card that has no navbar. Click it, and the update happens at once, with
no wait for a quiet hour. An app that shows CAD's replies as text gets a line with its
first reply instead, naming the install command.

Running the install command again does the same, and so does `cad update` in a
terminal: each acts at once, installs the newest release, updates every app, moves
your computer to it and lists the apps to restart. `cad update --dry-run` changes
nothing: it reads the version feed and says the release an update would install (or
that it would set this one up again, and why), then prints the plan. To update one app
by hand, run the update commands under its heading, then restart it.

An update writes the plugin folder again for the new release
([What each app gets](#what-each-app-gets)), with no network: Claude Code and Gemini
read it in place, and the apps that keep a copy of it (Codex, Cursor, the agents with
the skills alone) get it again. Should the new release fail before your computer has
moved to it, your computer stays on the release it ran, the release the update
downloaded stays for the next try, and the page you clicked in says the update failed.

An app the update could not give the new release's text to (most often because its
command was not on the server's `PATH`) keeps its copy of the release before. The
receipt records it, `cad doctor` names it and why, and the server tries again by
itself at most once a day, while nothing else is happening. `cad update`, run in a
terminal where the app's command is found, gives it the text now.

Only what the install command set up updates itself; the receipt it writes is what says
so. A copy from a plugin directory (claude.ai's, Codex's) is updated by its store: CAD
shows no update button or automatic-updates switch in its chats, and `cad update` there
says its store updates it. A copy Cursor installed from a marketplace added in Cursor
changes only when Cursor fetches the repository again, which text-to-cad does not control
([Cursor](#cursor)). On a computer where the install command never ran, `cad update` says there is
nothing to update and names the install command.

### After an update

- A CAD page open in your browser, or a CAD card, loses the server for about a second,
  then reloads into the new release at the same address. Links you shared keep working.
- Where the release before stays, because a plugin directory's copy is still on it or
  work was in flight there, its server keeps the address. A page that started the update
  goes to the new release's server at its own address, and a CAD card says "Updated to
  <release>. Start a new thread to use it."
- Where the release before takes a while to stop, the new release's server serves on
  another port meanwhile, and takes the old one too as the release before stops: a page
  open there reloads into it.
- After an update from 0.11.10, the new release's server serves the old port too where
  it is free, and `cad status` lists every port it serves. Where 0.11.10's server still
  held the old port, the new release's server takes it once that server stops.
- A Codex, Cursor, Gemini or Grok Build chat that was open when the update came says its
  CAD server is out of date: start a new chat. If a new chat says the same, run `cad update`,
  or for a plugin directory's copy update the plugin in the app it came from.
- A chat that was open in any app may say its commands are for the release before. Read
  the skill again; if it still names the release before, run `cad update` (with no release
  named), or for a plugin directory's copy update the plugin in the app it came from, then
  read the skill again or start a new chat.
- A copy of the plugin you installed yourself, with an app's own plugin commands rather
  than the install command, says the same until you update it in that app
  ([App by app](#app-by-app)), or until `cad update` replaces it with the install
  command's. `cad update` never changes a copy Cursor installed from a marketplace
  added in Cursor: it stays at the release Cursor last fetched.

### Releases side by side

Each release is installed in a folder of its own in text-to-cad's state folder
(`versions/<release>`), with its own settings, Recents and CAD server. Every command a
skill runs names the release it was written for (`cad +<release> ...`), and runs exactly
that release, installing it first if it is missing.

Who delivers a copy of text-to-cad is its channel. The copies the install command set up,
and a copy you installed yourself, share the default channel. A plugin directory's copy
is on a channel of its own (`claude` for claude.ai's, `codex` for Codex's), which only its
store moves. Each channel is on one release at a time, so two releases can be installed at
once: the default channel's and a store's, each with its own server. A `cad` command you
type with no release runs the default channel's release, and so do `cad status` and
`cad stop`: each acts on one release.

A release a channel has left is removed once no channel is on it and no work is in flight
there (an open page or an idle chat does not keep it), after what it wrote that the
channel's new release lacks (documents, Recents, settings) is carried over. The channel's
new release does that, by its server or its next update. A release installed and never
used by a channel, like an update waiting to run, is kept: `cad doctor --prune` removes
it, and an update that downloads a newer release removes the one it downloaded before.

Which release each channel is on is kept in a small file per channel. A command for a
channel whose file is there but cannot be read refuses to run, and nothing is removed
until it can be read. `cad doctor` says which file and why, and writes one that names no
release again, naming the newest release a channel has been on.

Each release keeps its own settings, and a new one starts with a copy of the settings
of the release it replaces. Turning telemetry off is the exception: a no, said through
any release, even an older one later, holds in every release on your computer.

Going back to a release before 0.11.11 by hand is not supported, and the install command refuses `--version` with one on a computer that runs
0.11.11 or later.

To find out a release is out, text-to-cad fetches `api.texttocad.dev/v1/versions` at
most once an hour: one anonymous request, with no ID, path or anything about you,
never in CI and only for what the install command set up.
`CAD_UPDATE_CHECK=0` turns it off. A click on the button reads the feed
again, for the newest release. With automatic updates off, the server reads the feed
only while a CAD page or card is open.

Updating from 0.8: [Migrating from 0.8 to 0.10](migrations/migrating-0.8-to-0.10.md) says
what 0.10 renames (the `cad` command, `CAD_*`, the folders, the packages) and what the
install command moves for you.

Updating from 0.8.0 or 0.8.1, whose engine runs until it is stopped:
[the migration guide](migrations/migrating-0.7-to-0.8.md#updating-from-080-or-081)
says what the install command and the new engine do with it.

A CAD project written for cadgen 0.7 needs porting to 0.8:
[the migration guide](migrations/migrating-0.7-to-0.8.md) takes one across, step by
step, and an agent with the CAD skill can follow it.

## Checking what your computer runs

Run `cad doctor`. It lists every release installed and every channel, with the release
each channel is on and when it was last used; the release the server runs; the plugin
folder's release; where each app's plugin comes from and its release; any app an update
could not reach, and why; and whether the CAD kernel loads.

`cad doctor --prune` removes what nothing needs: a channel no command has used for 30
days (its release's documents and Recents go to the default channel's release; where
that release is older, the channel's release goes with its settings and Recents, and the
plan says so), any release no channel is on, a release installed and never used, one
whose install was cut short, and what releases before 0.11.11 left behind; never a
release with work in flight, and never the settings and Recents `cad uninstall` kept. It prints exactly what it will remove first, and removes exactly that once you
say yes (`--yes` where it cannot ask). Nothing does this by itself.

`cad doctor` starts the CAD server if none is running. `cad doctor --no-server` does not,
and says whether one runs; `cad doctor --check` only reports, writing and starting nothing.

`cad status` reports only one server, and starts none: the release it runs, its workers and
what it serves. It does not list the releases on your computer.

## What a model runs in

The release the install command runs is text-to-cad's server (`cad-server`): the
`cad` command, the server of CAD's pages in your browser and the engine every build goes
through. Each app's CAD server is the smaller `cad-mcp`, which
reaches it. A model runs where the kernel is. `cad run` runs it exactly as `uv run` would -- the same
options and the same script header -- in an environment made with uv in the release's own folder
and kept: the library pinned at the server's release, with the integrations the script's
imports use (`import build123d`: `cad[build123d]`), on the server's Python, 3.14. The server's own
kernel processes run in the `cad[build123d]` one: exports, snapshots and the meshes the viewer
shows. That one is made when the release is installed; every other is made the first time
something needs it, and the run that needs it waits for it. A model run so imports what its
environment holds.
`cad[build123d]` is about 240 MB to download, and `cad[kicad]`, made the first time a board needs
it, about 100 MB. On disk, measured on an Apple silicon Mac, they take about 620 MB and 340 MB. A
script that imports Blender's `bpy` gets `cad[blender]`, whose environment is made on Python 3.13, the
one bpy is built for, which uv fetches: bpy 5.2.3 is about 260 MB to download on a Mac and 430 MB on
Linux, 730 MB on disk, and has no build for Intel Macs or Linux arm64.

A model that needs another package names it at the top of its script, in Python's inline
script metadata, and `cad run` installs it beside cad once, in an environment of its own that
the server keeps for the runs after:

```python
# /// script
# dependencies = ["pandas>=2"]
# ///
```

The header names the script's own packages; cad's integrations come from its imports, and a
header may name `cad[...]` to choose them itself. A header that pins cad to another release than
the server's is refused. `cad run --with pandas model.py` adds a package for one run (repeat
`--with`, or separate requirements with commas; a local folder or wheel works too, installed again
on the next run after an edit). A script with no header inside a Python project
(`pyproject.toml`) runs with the project's dependencies -- exactly its `uv.lock`'s where it has one
-- and reads the project's uv configuration and your shell's uv settings (a private index, say), as
`uv run` does. A requirement that cannot be installed
beside cad's own is refused in one line, with uv's reason. The environments go with their
release's folder when the release is removed.

To run models with a Python of your own instead, with the packages of your project's
environment, install the library with its kernel into it, at the server's release:
`pip install 'cad[build123d]==0.11.11'` (`cad requirement build123d` prints the exact
requirement; `pip install cad==0.11.11` is the library alone, and `import build123d` fails there). A script run with that Python (`python model.py`,
`uv run model.py`) is then built by a warm worker running that same Python: the model imports
your environment's packages, and an edit rebuilds only what it changed, as under `cad run`.
A release whose worker contract the server does not speak is refused in one line that says
which package to update, and to what release: the cad package in your environment, or
`cad-server`, by `cad update`. Another release of the same contract builds, and the run says
once which to update for the other's fixes.

## Windows 11: Smart App Control

The CAD kernel behind the `cad`, `engineering-drawing` and `robot-simulation`
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
