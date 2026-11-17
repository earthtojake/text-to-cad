# Decisions

How text-to-cad is installed, run and updated, and why. Each entry says the decision, why it was
made, and what it costs. Read it before changing the install script, cad's update, the plugin's
manifests or the skills' setup text.

## Two layers, one direction of knowledge

**Decision.** text-to-cad is two layers. cad is the software: the `cad` package on PyPI and the
`cad` command. The plugin is the skills, one manifest per agent app, and the lines that start the
server, on this repository's branches. The plugin knows cad: its skills run `cad` commands and say
how to install cad. cad knows nothing of skills, plugins or agent apps: it never names them,
installs, removes, updates or carries them, and does not depend on them.

**Why.** Every agent app installs plugins its own way, and changes that way often. When cad wrote
plugin folders, edited app configs and ran app commands, every app change was a cad release, and a
cad bug could break an app's setup. With one direction, an app change touches the plugin and the
install script, never the software.

**What it costs.** cad cannot repair a broken plugin install or tell which app a person uses it
from. Three exceptions are allowed: the MCP server reads which app connected, to choose how to show
a model; the viewer's "Open in" menu names apps; and, after cad updates itself, it runs the hosted
install command once, where that command set the computer up (below). Nothing else in cad may name
an app, a plugin or a skill.

## cad says `cad`; the views may say text-to-cad

**Decision.** text-to-cad is the plugin's and the product's name. The command line, the server's
messages and the library call the software `cad`. The web viewer and the CAD app may say
text-to-cad in their titles: they are where the person meets both layers.

**Why.** A message from cad that names text-to-cad points a person who uses cad alone at a plugin
they never installed, and ties cad's text to the plugin, which the first decision rules out.

**What it costs.** Two names for one project, and a test that holds cad's text to its own
(`tests/python/global/test_cad_calls_itself_cad.py`). Addresses (`texttocad.dev`, the repository),
the MCP ids `dev.texttocad/*` and the URDF namespace keep their spelling: they can never change.

## One cad per computer

**Decision.** One package, `cad`, holds the library, the `cad` command and the server. A computer
has one cad, installed as a uv tool, and one server, which it starts only when asked
(`cad server start`, or the CAD app an agent app starts). Its data lives in one folder per user.
No command names a version. `cad-server`, `cad-mcp` and `cadgen` stay on PyPI as empty aliases of
`cad`, so older installs that name them keep working.

**Why.** Earlier designs kept each release in its own folder, side by side, with every command
pinned to its release. That needed our own launcher, our own version machinery, data copied between
versions and a cleanup of old ones, and it confused people who saw two servers. One cad is what
every other command-line tool does.

**What it costs.** A chat that is open while cad updates meets the new release. Skills may be older
than cad, which the 30-day rule covers (below).

## uv's own commands

**Decision.** cad is installed, updated and removed with uv's own commands:
`uv tool install --managed-python --python 3.14 cad==X` and `uv tool uninstall cad`. cad has no
installer, uninstaller or launcher of its own.

**Why.** uv already installs a tool in place, replaces it on update, and removes it cleanly. Code of
our own that did the same was how earlier releases got into trouble.

**What it costs.** We take uv's behaviour as it is, its bugs included: on Windows, uv can fail to
replace a running `cad.exe`, so cad's update tries again; and when an install fails after it has
started, uv removes the tool, so cad's update puts the release it ran back.

## The feed is the pointer

**Decision.** The version feed, `api.texttocad.dev/v1/versions`, names one release, `latest`. The
install command installs exactly that release, and so does cad's own update. The feed names a
release only once it has been on PyPI for an hour, and we can hold a release back from it.

**Why.** One pointer we control is the brake on every computer at once. The hour gives us time to
see a bad release before it spreads; holding it back stops it without a new release.

**What it costs.** A release reaches computers an hour or more after it is published. With no
answer from the feed, cad's update does nothing, and the install command installs PyPI's newest
release instead. A plugin store's skills install cad from PyPI directly, so a bad release must also
be yanked on PyPI to be pulled everywhere.

## Who updates which copy

**Decision.** cad updates itself, where automatic updates are on. They are off by default. The
install command turns them on, and so does a plugin store's skill, with `cad auto-update on`. With
them on, the server checks the feed when it starts and about once an hour; when a newer release is
listed and nothing is running, a helper stops the server, installs the release with uv and starts the
server again. Then, where the install command set the computer up, cad runs that command once more
in an update mode, which updates only the copies of our plugin still in the apps. A plugin store
(Codex's directory, Claude's) updates the copy it installed. A cad that is not a uv tool, such as one
installed with pip into a project's own Python, never updates itself.

**Why.** People install and forget, and they should get our fixes without being asked. Nothing of
ours asks a person to update: in blind tests, agents would not install without the person's say-so,
and a prompt the person must act on is one most people ignore. The install command is the one place
that knows the apps, so cad hands it the plugin's update rather than learning the apps itself.

**What it costs.** cad runs a script from our website unattended on computers where the install
command ran: [SECURITY.md](../../SECURITY.md) says so. A store's copy of the skills lags cad by
however long its store takes.

## Forward only

**Decision.** Nothing installs a release older than the one installed: not the install command, not
cad's update. An older starter never replaces a newer running server; it joins it. There is no
automatic way back after an update.

**Why.** A way back is machinery that must work on every computer when something has already gone
wrong. Holding the release back in the feed and shipping a fix is simpler and reaches everyone.

**What it costs.** A bad release stays on the computers that took it until the next one. A person
who wants an older release installs it by hand, with automatic updates off
([docs/install.md](../install.md)).

## The 30-day rule

**Decision.** A command the skills used keeps working for at least 30 days after the skills stop
using it, hidden if need be. CI checks each release against the skill text of every release in the
last 30 days. Apart from that, a command, option or tool may change or go in any release.

**Why.** cad moves to the newest release on every computer, while a store's copy of the skills can
lag by weeks. The rule keeps those skills working; the test keeps the rule.

**What it costs.** An old spelling lives on for a month after the skills drop it. A person's own
scripts that run `cad` commands are not covered and may need changes after an update. A model's
Python imports and a person's data are not covered by this rule either: they keep law 15's tiers 2
and 3 (`packages/cad/README.md`).

## The install script is the one place that knows every app

**Decision.** `scripts/install/install.py`, behind `install.sh` and `install.ps1`, takes no options
and carries no cad version. It makes sure uv is there, installs cad at the feed's release, installs
or updates the plugin in each app it finds with that app's own command, removes our own older
copies, and turns automatic updates on. It starts no server. Its table of apps is the only list of
apps and of past layouts in the repository.

**Why.** Knowledge of the apps, and of every layout a past release left on a computer, has to live
somewhere. In one hosted script, a correction reaches every computer the next time it runs, with no
release of cad.

**What it costs.** The script is long, and many of its rows follow vendor documentation we cannot
run here. A row that is wrong fails for that app alone.

## The bridge for 0.10.0 to 0.11.10

**Decision.** Releases 0.10.0 to 0.11.10 shipped an updater of their own, which installs a newer
release the old way and runs its hidden `cad setup --engine-update`. The new cad then runs the
hosted install command once, which installs cad as a uv tool, installs the plugin and turns
automatic updates on. A computer whose apps got text-to-cad only from a plugin store gets the new cad
alone: running the install command there would put our plugin in apps the person never asked us
into. The code that does this is kept apart and marked, so that a later release deletes it in one
change.

**Why.** That updater cannot be changed, and it is the only way those computers reach the new
design without a person doing anything.

**What it costs.** A few commands stay for those releases: `cad setup --engine-update`; plain
`cad setup`, which a `cad update` typed on those releases runs; and the hidden short forms
`cad status` and `cad stop` their skill text uses.

## No version left behind

**Decision.** As many past releases as reasonable can reach the latest. Releases 0.10.0 to 0.11.10
get there through the bridge. Older ones get there when a person or an agent runs the install
command, which removes what they left behind. The install command, a README that says how to install
and the version feed stay where they are, because old releases point people and agents at them.

**Why.** People install and forget. A release that strands its users leaves them with bugs we have
fixed and a support load we cannot see.

**What it costs.** The install script carries the cleanup of every past layout, a few addresses can
never change, and whatever else changes must bring the earlier releases along (CONTRIBUTING, "What
must stay the same").

## Browser first: the MCP server only where its view is verified

**Decision.** The CAD MCP server ships to, and offers tools to, one app: Codex, where the CAD tab is
verified as solid. Only Codex's manifest names the server. Every other app gets the skills alone, and
its agent shows a model in the app's own browser or by a link, as the skills say. A server someone adds
to another app by hand is offered no tools either, whatever the app says it supports. Copies of the
plugin we install in Claude Code and Cursor start cad's server when a session starts.

**Why.** Inline cards are small and scroll away with the chat; only Codex's tab is a proper view. Of the
other apps, Cursor shows cards inline only, Claude Code's cards are broken, and nothing else is verified.
Apps claim support they do not have, and their support changes between versions, so the server trusts
what was checked in the real app rather than what an app declares.

**What it costs.** Cursor loses its working card and shows a model in its browser instead. Where
nothing has started the server, the skills have the agent run `cad server start`; in an app that
sandboxes the agent's shell, that needs one approval.

**Adding an app back.** Verify its CAD view in the real app first. Then add its manifest's server entry
and its name to the server's rule (`cad_server/mcp/host.py`), in one change.

## No Skills CLI route

**Decision.** The install script and the guide never use the Skills CLI (`npx skills`). Agents
without a plugin command get the skills copied into their own skills folder.

**Why.** The Skills CLI wrote one shared folder, `~/.agents/skills`, that several apps read beside
their own plugin, so people saw every skill twice. Each agent's own folder is read by that agent
alone.

**What it costs.** An agent that reads only the shared folder, such as Zed, has no route.
