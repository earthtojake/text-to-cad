# Decisions

How text-to-cad is installed, run and updated, and why. Each entry says the decision, why it was
made, and what it costs. Read it before changing the install script, cad's update, the plugin's
manifests or the skills' setup text.

## Two layers, one direction of knowledge

**Decision.** text-to-cad is two layers. cad is the software: the `cad` package on PyPI and the
`cad` command. The plugin is the skills, one manifest per agent app, and the lines that start the
server, on this repository's branches. The plugin knows cad: its skills run `cad` commands and say
how to install cad. cad knows nothing of skills or agent apps: it never names them, installs,
removes, updates or carries them, and does not depend on them. Of plugins it knows one command,
`cad plugin`, which runs the hosted install command.

**Why.** Every agent app installs plugins its own way, and changes that way often. When cad wrote
plugin folders, edited app configs and ran app commands, every app change was a cad release, and a
cad bug could break an app's setup. With one direction, an app change touches the plugin and the
install script, never the software.

**What it costs.** cad cannot repair a broken plugin install or tell which app a person uses it
from. Three exceptions are allowed: the MCP server reads which app connected, to choose how to show
a model; the viewer's "Open in" menu names apps; and `cad plugin` runs the hosted install command,
when asked (`cad plugin update`) and once where cad is newer than the release it last ended well for
and `cad plugin update auto` is on (below). Nothing else in cad may name an app, a plugin or a skill.

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
has one cad, installed globally with `uv tool install cad`, and one server, which it starts only
when asked (`cad server start`, or the CAD app an agent app starts). The CAD app's line runs cad from
uv's cache (`uvx ... cad@<VERSION> mcp`); where the computer has no global cad, that cad installs one
and uses its server, so no server runs from the cache. Its data lives in one folder per user.
No command names a version. `cad-server`, `cad-mcp` and `cadgen` stay on PyPI as empty aliases of
`cad`, so older installs that name them keep working.

**Why.** Earlier designs kept each release in its own folder, side by side, with every command
pinned to its release. That needed our own launcher, our own version machinery, data copied between
versions and a cleanup of old ones, and it confused people who saw two servers. One cad is what
every other command-line tool does.

**What it costs.** A chat that is open while cad updates meets the new release. Skills may be older
than cad, which the 30-day rule covers (below). A server started from uv's cache would never update
itself, which is why the CAD app's line installs cad first.

## uv's own commands

**Decision.** cad is installed, updated and removed with its installer's own commands: `uv tool
install cad`, `uv tool install --upgrade "cad>=<installed>,<<next major>"` (what cad's update runs),
`uv tool install --upgrade "cad>=<installed>"` (what `cad update --major` runs) and `uv tool uninstall cad`. cad has no
installer, uninstaller or launcher of its own.

**Why.** uv already installs a tool in place, replaces it on update, and removes it cleanly. Code of
our own that did the same was how earlier releases got into trouble.

**What it costs.** We take uv's behaviour as it is, its bugs included: on Windows, uv cannot remove a
running `cad.exe`, so cad's update renames each one aside first and puts a copy back, and tries again
if uv still fails; and when an install fails after it has started, uv removes the tool, so cad's update
puts the release it ran back.

## One line installs cad

**Decision.** `uv tool install cad`, with no flags, is the one way we tell anyone to install cad,
and it never changes. Every skill's Setup block runs it where `cad` is missing, does not run, or is
older than the first release installed this way; cad updates itself, so no skill updates it. No skill runs the
install command. cad runs on Python 3.11 and newer, with no upper bound.

**Why.** A skill deals with cad alone: the install command changes every agent app on the computer,
which is the person's call, not an agent's. A line with no flags works on whatever Python uv picks,
and leaves a person's own `uv tool upgrade cad` working.

**What it costs.** uv chooses the Python, so cad cannot count on one: where the server's Python is
newer than the CAD kernel's builds, the kernel's environment is made on an older Python uv fetches.
An upper bound on Python would make a resolver on a newer Python fall back to an old release with no
`cad` command, so there is none. The `cad` name and that line are fixed for good.

## The feed says when

**Decision.** The version feed, `api.texttocad.dev/v1/releases`, names the newest release, `latest`,
once it has been on PyPI for an hour, and the newest such release of each major version, `lines`; we
can hold a release back from it. cad's automatic update
begins when the feed names a release of its own major newer than its own, or, where the feed names
none of its major while its `latest` is of a higher major, all the same (bounded by its tries), and
then runs the installer's own upgrade inside that major, which installs PyPI's newest of the major. Everything else
asks PyPI: `cad update`, the install command, the skills' line and the CAD app's line.

**Why.** The hour keeps automatic updates from spreading a release the moment it is out, and a hold
stops them without a new release. The upgrade names a range, never an exact version, because an
exact version makes uv skip the tool in a person's own `uv tool upgrade cad`. Someone who asks for an
update wants the newest now, not the feed's hour-old answer.

**What it costs.** A hold is a brake, not a wall: it stops automatic updates only on computers
already on the feed's release, since an update the feed starts takes PyPI's newest of the major. To
pull a bad release from everyone, yank it on PyPI. With no answer from the feed, no automatic update
starts.

## A major version never installs itself

**Decision.** cad installs by itself any newer release with the same major version number as its
own, a patch and a minor alike; a release of a higher major never arrives by itself. A person asks for
it: `cad update --major`, which `cad update` and `cad doctor` name, with the migration guides, when
one is out. The automatic update and a typed `cad update` run the installer's upgrade bounded to the
installed major, `uv tool install --upgrade "cad>=<installed>,<<next major>"` (pipx: `pipx upgrade cad
--pip-args=...` with the same range), worked out from the installed release each time; the helper
accepts only a release of that major, never an older one. The CAD app's line installs the newest of its
own major where a computer has no cad, and never over a `cad` of a higher major. This is cad's own
update; the hosted install command is not bounded by major, and cad runs it by itself too (the
plugin's catch-up after cad got newer, and the bridge from 0.10.0 to 0.11.11): it installs the newest
plugin of all, and, where cad is missing or does not start, PyPI's newest `cad` of all. No higher
major exists yet; CONTRIBUTING's "Before the first release of a higher major" lists what changes
first.

**Why.** The bound lives in the updater a computer already has: a computer that sleeps for months
wakes with the updater of the release it has, so the rule has to be in the first release of this
updater, and in the commands it runs, not in a feed that can change. uv's own version range does it:
the upgrade moves up, never past the bound and, with the floor, never down; it is safe to repeat; and
uv keeps the range, so a person's own `uv tool upgrade cad` stays inside the major too.
`uv tool install --upgrade "cad>=<installed>"` crosses it, the floor alone in its place, and never
moves down (measured on uv 0.11.25, a yanked installed release included). A minor that breaks installs itself because
text-to-cad is in beta: below 1.0 a break bumps the minor, comes with a migration guide, and the skills
tell the person when cad is a version ahead of them.

**What it costs.** A person on an old major stays there until they run `cad update --major`, and gets
no fixes made only in a later major. A minor that breaks reaches everyone by itself. Before pipx 1.18,
pipx keeps no range, so there a person's own `pipx upgrade cad` takes the newest of all; from 1.18 it
keeps the last upgrade's, so `cad update --major` passes a floor alone to replace it.

## Who updates which copy

**Decision.** cad and the plugin update separately. A global install of cad updates itself, inside
its major version, on by default (`cad update auto off` stops it): when the feed names a newer release
of its major, as the server starts, after a failed start, or once nothing has run for a minute, a
helper outside cad's environment stops the server, runs the installer's upgrade and starts the server
again. `cad update` updates cad now, inside its major (`--major`: the newest of all), with or without a
server running and with automatic updates off too, and touches nothing else. A cad that is not a global
install, such as one installed with pip into a project's own Python, never updates itself.

The plugin is the install command's. Run by a person, or by cad (`cad plugin update`), it puts the
newest plugin in every app it finds. Wherever cad is there, it turns on `cad plugin update auto`, which
is off until then, so a computer whose runs keep failing still has the plugin kept: where cad is newer
than the release the install command last ended well for, cad's server runs it once. cad keeps that
release in a small record of its state folder, written when the command ends with exit status 0 and
when the switch is turned on by a run that is ending well (a run ending badly tells cad so, and writes
none); a run that fails writes none. The rule asks what cad is, not how it got there, so a typed `cad update` or `uv
tool upgrade cad` by hand brings the plugin along as cad's own update does, with one mechanism. A run
cad's server began is stopped, with all it started, after 15 minutes (in a Windows session where `taskkill`
is refused, only the install command's own process is ended; what it started may run on). A failed run is tried again an
hour or more later: at most three runs for one release. A plugin
store (Codex's directory, Claude's) updates the copy it installed.

**Why.** People install and forget, and they should get our fixes without being asked. Nothing of
ours asks a person to update: in blind tests, agents would not install without the person's say-so,
and a prompt the person must act on is one most people ignore. A command does what it says: `cad
update` updates cad, and only the install command, which the person ran, changes their apps. The
install command is the one place that knows the apps, so cad hands it the plugin's update rather than
learning the apps itself.

**What it costs.** Where the install command ran, cad runs a script from our website unattended:
[SECURITY.md](../../SECURITY.md) says so. A store's copy of the skills lags cad by however long its
store takes.

## Forward only

**Decision.** Nothing installs a release older than the one installed: not the install command, not
cad's update. An older starter never replaces a newer running server; it joins it. There is no
automatic way back after an update.

**Why.** A way back is machinery that must work on every computer when something has already gone
wrong. Holding the release back, yanking it on PyPI and shipping a fix is simpler and reaches
everyone. The one exception is an update that failed and left no `cad`: the release that ran is put
back.

**What it costs.** A bad release stays on the computers that took it until the next one. A person
who wants an older release installs it by hand, with automatic updates off
([docs/install.md](../install.md)).

## The 30-day rule

**Decision.** A command the skills used keeps working for at least 30 days after the skills stop
using it, hidden if need be. CI checks each release against the skill text of every release in the
last 30 days. Apart from that, a command, option or tool may change or go in any release.

**Why.** cad moves to the newest release of its major on every computer, while a store's copy of the skills can
lag by weeks. The rule keeps those skills working; the test keeps the rule.

**What it costs.** An old spelling lives on for a month after the skills drop it. A person's own
scripts that run `cad` commands are not covered and may need changes after an update. A model's
Python imports and a person's data are not covered by this rule either: they keep law 15's tiers 2
and 3 (`packages/cad/README.md`).

## The install script is the one place that knows every app

**Decision.** `scripts/install/install.py`, behind `install.sh` and `install.ps1`, takes no options,
carries no cad version and has one behaviour, whether a person or cad runs it. It makes sure uv is
there (an old uv that cannot update itself gets a newer one beside it), installs cad only where none
is installed or the one there does not start, installs or updates the plugin in each app it finds
with that app's own command, removes our own older copies, puts cad's folder on the PATH with uv's
own `uv tool update-shell`, and turns on `cad plugin update auto`, telling cad whether its run ended
well. It never
updates a cad that works,
never stops to ask the person anything, and starts no server. Its table of apps is the only list of
apps and of past layouts in the repository.

**Why.** Knowledge of the apps, and of every layout a past release left on a computer, has to live
somewhere. In one hosted script, a correction reaches every computer the next time it runs, with no
release of cad. One behaviour means one thing to test, and running it again is how a broken install
is repaired. cad updates itself, so the script has no reason to.

**What it costs.** The script is long, and many of its rows follow vendor documentation we cannot
run here. A row that is wrong fails for that app alone.

## The bridge for 0.10.0 to 0.11.11

**Decision.** Releases 0.10.0 to 0.11.11 shipped an updater of their own, which installs a newer
release the old way and runs its hidden `cad setup --engine-update`. The new cad then runs the
hosted install command once, which installs cad as a uv tool, installs the plugin and turns
`cad plugin update auto` on. A computer whose apps got text-to-cad only from a plugin store gets the new cad
alone: running the install command there would put our plugin in apps the person never asked us
into. There, and where the install command failed before it installed cad, the new cad installs
itself with uv, and that cad updates itself from then on. Where the new cad arrived by the uv line
on a computer the install command set up before, cad runs the install command once. The code that
does this is kept apart and marked, so that a later release deletes it in one change.

**Why.** That updater cannot be changed, and it is the only way those computers reach the new
design without a person doing anything.

**What it costs.** A few commands stay for those releases: `cad setup --engine-update`; plain
`cad setup`, which a `cad update` typed on those releases runs; and the hidden short forms
`cad status` and `cad stop` their skill text uses.

## Old releases are carried through the newest 0.11

**Decision.** The old address of the version feed, `api.texttocad.dev/v1/versions`, which every
release from 0.7.12 to 0.11.11 reads, is frozen: it names the newest release below 0.12.0, in the shape
it always had (`latest` alone), under the feed's hour and holds. The releases from 0.11.12 on read
their own address, `api.texttocad.dev/v1/releases`, which names the newest release and the newest of
each major version. A computer on an old release reaches the newest 0.11.x, whose bridge brings it onto
the design that updates itself, and that cad goes on from there.

**Why.** Releases 0.11.0 to 0.11.11 install by themselves exactly the release the feed names, but only a
patch of their own minor: the day the feed named 0.12.0, every computer on 0.11.x would stop updating by
itself. Releases 0.10.0 to 0.10.4 install what it names on a click, with no rule on the number. The
newest 0.11.x carries the bridge, and nothing shipped can be changed to read anything else.

**What it costs.** The last 0.11.x must stay on PyPI, with its bridge, for as long as old computers
run. No old computer ever installs 0.12 or later directly: it always goes
through the newest 0.11.x first. Two addresses are kept by the service, and the old one never changes.

## No version left behind

**Decision.** As many past releases as reasonable can reach the latest. Releases 0.10.0 to 0.11.11
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
to another app by hand is offered no tools either, whatever the app says it supports.

**Why.** Inline cards are small and scroll away with the chat; only Codex's tab is a proper view. Of the
other apps, Cursor shows cards inline only, Claude Code's cards are broken, and nothing else is verified.
Apps claim support they do not have, and their support changes between versions, so the server trusts
what was checked in the real app rather than what an app declares.

**What it costs.** Cursor loses its working card and shows a model in its browser instead. Where
nothing has started the server, a command that needs it tells the agent to run `cad server start`; in
an app that sandboxes the agent's shell, that needs one approval.

**Adding an app back.** Verify its CAD view in the real app first. Then add its manifest's server entry
and its name to the server's rule (`cad_server/mcp/host.py`), in one change.

## No hooks, no pre-approved tools

**Decision.** No manifest of ours declares a hook, and no skill declares `allowed-tools`. Nothing
starts cad's server when a session opens: `cad server start` starts it, which a command that finds no
server tells the agent to run (`the cad server is not running: run cad server start`), or `cad mcp`,
Codex's server line. Every copy of the plugin, the one a person installs by hand and each listing's,
carries the same skills, byte for byte. No released version ever had either: both were added on
2026-11-16 and taken out before the next release shipped.

**Why.** The copy people install by hand should be the same skills a listing carries, and Claude's
plugin directory refuses hooks and `allowed-tools` from an organization it has not verified. The hooks
had only tests of their declaration, and failed wherever cad was missing or old. `allowed-tools`
pre-approves a command only during the turn that loads the skill, and made Claude Code ask before
loading the skill at all. Current Claude Code terminal sessions start in auto mode, where routine
commands are not asked.

**What it costs.** In Claude Code's manual permission mode each new `cad` command asks once, and the
first command of a session may be told to start the server.

## No Skills CLI route

**Decision.** The install script and the guide never use the Skills CLI (`npx skills`). Agents
without a plugin command get the skills copied into their own skills folder.

**Why.** The Skills CLI wrote one shared folder, `~/.agents/skills`, that several apps read beside
their own plugin, so people saw every skill twice. Each agent's own folder is read by that agent
alone.

**What it costs.** An agent that reads only the shared folder, such as Zed, has no route.

## Inside a Windows app's package, say so

**Decision.** Inside a Windows packaged app (the Claude desktop app, Codex's Store app), Windows can
keep what uv writes under AppData in a private copy only that app sees. We do not work around it.
Where uv cannot set up Python there, `install.ps1` prints one line: run the install command once from
PowerShell opened from the Start menu. `cad server start` and `cad doctor` name a uv folder in an
app's private copy, say why it matters, and say to delete it in File Explorer; cad never deletes it.

**Why.** No tool we found works around it from inside someone else's package: a way out of the
package is reported to fail inside these apps, and uv, pip and CPython document the problem and stop.
Detecting and saying what to do is what they do. The lines say File Explorer because a delete from
inside the app does not reach the folder: `Remove-Item` on that path, run inside the package,
reported the folder gone and left every file, and the same delete from outside the app removed it
(both measured).

**What it costs.** On such a computer a person may have to run one command or delete one folder by
hand.
