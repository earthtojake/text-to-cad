# Decisions

How text-to-cad is installed, run and updated, and why. Each entry says the decision, why it was
made, and what it costs. Read it before changing the install script, `cad setup`, the plugin's
manifests or the skills' setup text.

## Two layers, one direction of knowledge

**Decision.** text-to-cad is two layers. cad is the software: the `cad`, `cad-server` and
`cad-mcp` packages on PyPI and the `cad` command. The plugin is the skills, one manifest per agent
app and the lines that start the MCP server, on this repository's branches. The plugin knows cad:
its skills run `cad` commands and say how to install cad. cad knows nothing of skills, plugins or
agent apps: it never names them, installs, removes, updates or carries them, and does not depend on
them.

**Why.** Every agent app installs plugins its own way, and changes that way often. When cad wrote
plugin folders, edited app configs and ran app commands, every app change was a cad release, and a
cad bug could break an app's setup. With one direction, an app change touches the plugin and the
install script, never the software.

**What it costs.** cad cannot repair a broken plugin install or tell which app a person uses it
from. Two exceptions are allowed: the MCP server reads which app connected, to choose how to show a
model, and the viewer's "Open in" menu names apps. Nothing else in cad may name an app, a plugin or
a skill.

## cad says `cad`; the views may say text-to-cad

**Decision.** text-to-cad is the plugin's and the product's name. The command line, the server's
messages and the library call the software `cad`, and `cad-server` where a message names the package
to install. The web viewer and the CAD app may say text-to-cad (their titles, the update nudge):
they are where the person meets both layers.

**Why.** A message from cad that names text-to-cad points a person who uses cad alone at a plugin
they never installed, and ties cad's text to the plugin, which the first decision rules out.

**What it costs.** Two names for one project, and a test that holds cad's text to its own
(`tests/python/global/test_cad_calls_itself_cad.py`). Addresses (`texttocad.dev`, the repository),
the MCP ids `dev.texttocad/*` and the URDF namespace keep their spelling: they can never change.

## Versions are self-contained and sit side by side

**Decision.** Each release of cad is installed in its own folder, with its own code, server,
settings and store. Every command a skill runs names its release (`cad +X ...`), and `cad +X` runs
exactly release X, or says X is not installed. A new release copies settings and store once from
the newest older one; after that nothing moves between versions.

**Why.** A chat that started with one release keeps working while a newer one is installed beside
it, and a store's copy of the plugin can run a different release from a person's own. No release
has to understand another release's files or commands.

**What it costs.** Disk space, until an old version is cleaned up, and settings changed in one
version do not reach another. Recents entries and cached records written to an older version after
the newer one's one-time copy go when the cleanup removes it; files in a person's own project are
never touched.

## Who updates what

**Decision.** A plugin store (Codex's directory, claude.ai's) updates the copy it installed. The
agent updates a manual install. cad says only that a version exists, in one line after a command's
output: `A new version of cad is available: X -> Y`, with no command and no link, and only the
newest version installed on the computer says it. The skill holds the rest: at a session's start it
checks `cad +X --version`, and when `cad` reports a new version it tells the agent to "install the
new version of the plugin from https://github.com/earthtojake/text-to-cad", and then to tell the
person. The agent installs it; a cautious agent asks the person first. Nothing installs itself.

**Why.** cad cannot update a plugin without knowing the apps, which the first decision rules out.
The store already updates its copy, and the agent is already running commands for the person, with
the person watching. cad prints no command because the only command that updates a manual install,
the install script, installs the plugin into every agent app too: printing it would steer a person
who uses cad alone into the plugin. What installs a newer version is for whatever installed this one
to say, and for a manual install that is the skill. The skill links the repository rather than
quoting the command, so no copy of the plugin carries a download piped to a shell, which stores'
install scans flag.

**What it costs.** A computer whose agent never acts on the notice stays on its release, and a person
who uses cad alone learns that a version exists but not how to install it from cad. Besides the
notice, the only nudge is the viewer's (below).

## The viewer's update nudge

**Decision.** The web viewer and the CAD app show a small blue button, last in the navbar, only
while the server's version check knows a newer release and its version is the newest installed.
Pressed, it opens a popover saying a new version of the text-to-cad plugin is available, with a
ready prompt for the person's agent: `A new version of the text-to-cad plugin is available (vY).
Update it from https://github.com/earthtojake/text-to-cad`. The CAD app sends it to the chat where
the host takes messages; otherwise, and in the web viewer, the person copies it. The nudge is the
one place the software tells a person, rather than an agent, that a new version exists, and all
it does is hand them that prompt: nothing in the page or the server installs, downloads or restarts
anything. Only the default channel gets the nudge: a CAD app session a store's launcher opened is
never shown it, and the web viewer shows it only where the default channel (a command or a session
with no store's name) has used that version, which the version records once, in a marker file beside
its last use.

**Why.** A skill cannot make an agent install without the person's say-so: in blind tests, agents
told to install "without asking" refused. The person has to agree, and the viewer is where they
are looking and can opt in by pressing, so they are given an easy way to say it. This is a
deliberate, small exception to "a viewer knows nothing about versions", and the one piece of the
cad packages' text that names the text-to-cad plugin, because the plugin and cad are updated
together.

**What it costs.** The page reads one more field from its server and carries one more control and
popover, in five languages. The web viewer cannot tell who opened it, so on a computer where both
the default channel and a store's copy use a version, a person who opened the page from the store's
copy is shown the nudge too, and an agent that follows it updates the default channel's copy. A
computer with store copies alone never sees it. The prompt names the repository's address, which can
never change.

## The install script is the one place that knows every app

**Decision.** `scripts/install/install.py`, behind `install.sh` and `install.ps1`, takes no options.
It installs the newest cad, removes what past releases left behind, and installs or updates the
plugin in each app it finds with that app's own command. Its table of apps is the only list of apps
and of past layouts in the repository.

**Why.** Knowledge of the apps, and of every layout a past release left on a computer, has to live
somewhere. In one hosted script, a correction reaches every computer the next time someone runs it,
with no release of cad.

**What it costs.** The script is long, and many of its rows follow vendor documentation we cannot
run here. A row that is wrong fails for that app alone.

## The one exception: `cad setup --engine-update`

**Decision.** `cad setup` takes one hidden option, `--engine-update`. It sets up the release, hands
over from the layout of earlier releases, and starts the hosted install script once, in the
background, once the site's script is this release's or later (it waits up to about an hour).

**Why.** Releases 0.10.0 to 0.11.10 shipped an updater that installs a newer release and runs its
`cad setup --engine-update`. That call is the only way those computers reach the new install model
without a person doing anything. It is kept for as long as those releases are in use, and is left
out of help and documents.

**What it costs.** One place where cad starts the script that knows the apps. It is the only one.

## No version left behind

**Decision.** As many past releases as reasonable can reach the latest. Releases 0.10.0 to 0.11.10
get there through their own updater and `--engine-update`. Older ones get there when a person or
an agent runs the install command, which removes what they left behind. The install command, the
README's Quickstart and the version feed stay where they are, because old releases point people and
agents at them.

**Why.** People install and forget. A release that strands its users leaves them with bugs we have
fixed and a support load we cannot see.

**What it costs.** The install script carries the cleanup of every past layout, and a few addresses
and names can never change (CONTRIBUTING, "What must stay the same").

## Built to move quickly

**Decision.** A command, option or tool may change or go in any release. Removing one is not a
breaking change, and leaves no alias or shim behind. Only the short list in CONTRIBUTING, "What
must stay the same", is fixed.

**Why.** Every command a skill runs names its release, so a skill never meets another release's
commands. The project ships often, and every fixed surface is code that has to be kept working
forever.

**What it costs.** A person's own scripts that run `cad` commands may need changes after an update.
A model's Python imports and a person's data are not covered by this: they keep law 15's tiers 2
and 3 (`packages/cad/README.md`).

## Browser first: the MCP server only where its view is verified

**Decision.** The CAD MCP server ships to, and offers tools to, one app: Codex, where the CAD tab is
verified as solid. Only Codex's manifest names the server. Every other app gets the skills alone, and
its agent shows a model in the app's own browser or by a link, as the skills say. A server someone adds
to another app by hand is offered no tools either, whatever the app says it supports. `cad setup`, which
always runs outside a sandbox, leaves its version's server running, so a later session's sandboxed
`cad` command finds it.

**Why.** Inline cards are small and scroll away with the chat; only Codex's tab is a proper view. Of the
other apps, Cursor shows cards inline only, Claude Code's cards are broken, and nothing else is verified.
Apps claim support they do not have, and their support changes between versions, so the server trusts
what was checked in the real app rather than what an app declares.

**What it costs.** Cursor loses its working card and shows a model in its browser instead. With no CAD
program in most apps, nothing starts cad's server for an agent: after the computer restarts, the first
`cad` command in an app that sandboxes the agent's shell needs one approval to start the server, unless
the app has the CAD program (Codex), which starts it.

**Adding an app back.** Verify its CAD view in the real app first. Then add its manifest's server entry
and its name to the server's rule (`cad_server/mcp/host.py`), in one change.

## No Skills CLI route

**Decision.** The install script and the guide never use the Skills CLI (`npx skills`). Agents
without a plugin command get the skills copied into their own skills folder.

**Why.** The Skills CLI wrote one shared folder, `~/.agents/skills`, that several apps read beside
their own plugin, so people saw every skill twice. Each agent's own folder is read by that agent
alone.

**What it costs.** An agent that reads only the shared folder, such as Zed, has no route.
