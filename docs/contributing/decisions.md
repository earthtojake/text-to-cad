# Decisions

How text-to-cad is installed, run and updated, and why. Each entry says the decision, why it was
made, and what it costs. Read it before changing the install script, `cad plugin install`, cad's
update, the plugin's manifests or the skills' setup text.

## Two layers, one direction of knowledge

**Decision.** text-to-cad is two layers. cad is the software: the `cad` package on PyPI and the
`cad` command. The plugin is the skills, one manifest per agent app, and the lines that start the
server, on this repository's branches. The plugin knows cad: its skills run `cad` commands and say
how to install cad. cad names agent apps, skills and plugins in exactly one place, the package
`cad_server/plugin/`: the table of apps, how the plugin is installed and updated in each, and which
older copies are ours to remove. Only the `cad plugin` command reaches it, as `cad_server/mcp/` is
the one place that knows the app hosting cad. Nothing else in cad names them, and cad carries no
skill and depends on none: `cad plugin install` fetches the plugin from the `latest` branch.

**Why.** Every agent app installs plugins its own way, and changes that way often, so what we know
of the apps has to live in one place. Through 0.11.13 that place was the hosted install script, and
cad knew no app at all: `cad plugin update` downloaded the script and ran it. That kept an app
change out of cad's releases, at three costs. A hosted script has no version: one copy serves every
release of cad, so it cannot be tested against the release that runs it. Its runs were not counted:
cad learned only whether the run after one of its own updates ended with exit status 0, so a row
that failed on every computer failed unseen. And cad ran it unattended, so whatever the website
served at that moment ran as the person, with nobody watching. In cad the table has a version, is
tested with the release it ships in, each run is counted (how many apps it found and how many failed,
naming an app only where it failed: which apps a computer has is never sent), and what runs unattended is
code the computer already installed. One package behind one command keeps the rest of cad free of
the apps: an app change is still one row.

**What it costs.** A fix to an app's row needs a release of cad, and reaches a computer only when
its cad updates. A cad that does not update (automatic updates off, a release installed by hand and
held, a cad that is no global install) keeps the table it shipped with, and its list of our skills'
names, while the `latest` branch it installs from carries the newest plugin. Two older exceptions stay: the MCP server reads which app
connected, to choose how to show a model, and the viewer's "Open in" menu names apps. Nothing else
in cad may name an app, a plugin or a skill, or import the package
(`tests/python/global/test_cad_names_no_skill_or_plugin.py`, `test_host_neutral_packages.py`).

## cad says `cad`; the views may say text-to-cad

**Decision.** text-to-cad is the plugin's and the product's name. The command line, the server's
messages and the library call the software `cad`. The web viewer and the CAD app may say
text-to-cad in their titles: they are where the person meets both layers. So may the one package
that installs the plugin (`cad_server/plugin/`): the plugin is named text-to-cad in every app.

**Why.** A message from cad that names text-to-cad points a person who uses cad alone at a plugin
they never installed, and ties cad's text to the plugin outside the one place the first decision
gives it.

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
asks PyPI: `cad update`, the install command (which installs cad where there is none and, run by a
person, runs `cad update` on the one that is there), the skills' line and the CAD app's line.

**Why.** The hour keeps automatic updates from spreading a release the moment it is out, and a hold
stops them without a new release. The upgrade names a range, never an exact version, because an
exact version makes uv skip the tool in a person's own `uv tool upgrade cad`. Someone who asks for an
update wants the newest now, not the feed's hour-old answer.

**What it costs.** A hold is a brake, not a wall: it stops automatic updates only on computers
already on the feed's release, since an update the feed starts takes PyPI's newest of the major. A
person who runs the install command gets PyPI's newest of their major at once, a release minutes old
or held back included, as a fresh install always did. To pull a bad release from everyone, yank it
on PyPI. With no answer from the feed, no automatic update starts.

## A major version never installs itself

**Decision.** cad installs by itself any newer release with the same major version number as its
own, a patch and a minor alike; a release of a higher major never arrives by itself. A person asks for
it: `cad update --major`, which `cad update` and `cad doctor` name, with the migration guides, when
one is out. The automatic update and a typed `cad update` run the installer's upgrade bounded to the
installed major, `uv tool install --upgrade "cad>=<installed>,<<next major>"` (pipx: `pipx upgrade cad
--pip-args=...` with the same range), worked out from the installed release each time; the helper
accepts only a release of that major, never an older one. The CAD app's line installs the newest of its
own major where a computer has no cad, and never over a `cad` of a higher major. This is cad's own
update, and the install command's when a person runs it on a cad that is there: it runs that cad's
`cad update`. Two things are not bounded by major. The plugin: `cad plugin install` and `cad plugin
update` take it from `latest`, the newest of all, whatever major the cad that runs them is. And the
hosted install command where it has no working cad to ask: it installs PyPI's newest `cad` of all
where cad is missing or does not start, and where the cad there has no `cad plugin install` (0.11.12
and 0.11.13) it runs the newest release's from uv's cache, `uv tool run ... cad@latest plugin
install`. Those two releases and the bridge from 0.10.0 to 0.11.11 run it by themselves. No higher
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

The plugin is `cad plugin install`'s: for every agent app it finds, the plugin installed or updated
with that app's own command, then our older copies there removed. `cad plugin update` is the same
run, and neither downloads or runs the hosted install command. As its last step a run turns on `cad
plugin update auto`, which is off until then, and keeps cad's release as the one the plugin is up to
date for only where it ended well and the cad that ran it is the computer's global install. A run
in which every app it found failed turns the switch on and keeps none, so a computer whose runs
keep failing still has the plugin kept: where cad is newer than the release the plugin is up to
date for, cad's server runs `cad plugin update` once. A run of a cad from anywhere else, such as
the newest release from uv's cache (`uv tool run cad@latest`, below), does the work, turns the
switch on and keeps none too: its release is not the installed cad's, and may be of a major that
cad never reaches, so kept, the installed cad's server would never catch up again. cad keeps that
release in a small record of its state folder, written when `cad plugin update` ends with exit
status 0 and when the switch is turned on by a run that ended well. The rule asks what cad is, not
how it got there, so a typed `cad update` or `uv tool upgrade cad` by hand brings the plugin along
as cad's own update does, with one mechanism. A run cad's server began has 15 minutes: each command
it runs is stopped when they are up, with all it started, and no further app is begun (in a Windows
session where `taskkill` is refused, only the command's own process is ended; what it started may
run on). That much is asked between the run's steps, so the run also carries a hard stop: where a
step never comes back and the run has not ended a minute past its 15, a thread of its own closes
its record as a stopped run's, counts it as stopped and ends the process there and then, which
frees its lock. A failed run is tried again an hour or more later: at most three runs for one
release. A plugin store (Codex's directory, Claude's) updates the copy it installed.

One run at a time. A run holds a lock in cad's state folder from its start to its end. A second run
waits for it; one a server began does not wait, runs nothing, and is tried again as a failed run
is. Either tries for the lock for two seconds before it takes it as another run's: whether a run is
going can only be asked by trying for the lock, so a server that asks holds it for an instant. cad's
own update holds while a run is going: the automatic update begins none, and a typed `cad update`
is refused in one line.

The install command, which a person runs, gets cad and hands over to it (below). It no longer
carries the plugin's install: it runs the installed cad's `cad plugin install`.

**Why.** People install and forget, and they should get our fixes without being asked. Nothing of
ours asks a person to update: in blind tests, agents would not install without the person's say-so,
and a prompt the person must act on is one most people ignore. A command does what it says: `cad
update` updates cad, and only a command the person ran themselves (the install command, `cad plugin
install`) first changes their apps. The plugin's update is the code of the cad that is installed,
so it is the release that was tested, and nothing is fetched from our website to run it. The lock
is there because two runs can meet: after a person's install command updated cad, the server that
starts may begin its own run at the moment that command goes on to the plugin. cad's update holds
because it replaces the files of the environment a run is reading. The hard stop is there because
the lock holds back cad's own update and every run that waits: a run that hung for good would hold
them for as long as its process lived.

**What it costs.** The plugin's install is only as new as the cad that runs it: a correction to an
app's row waits for a release, and for that computer's update (the first decision). Released 0.11.12
and 0.11.13 still download the hosted install command and run it unattended, as their `cad plugin
update` and after their own update, and so does the bridge for 0.10.0 to 0.11.11:
[SECURITY.md](../../SECURITY.md) says so. Nothing shipped later can change those two releases: they
stop only when their computers have updated. A typed `cad update` during a run fails and has to be
typed again. The hard stop cannot end a process no thread of which runs at all (one a signal
stopped). A store's copy of the skills lags cad by
however long its store takes.

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

## The install command gets cad, and hands the apps to it

**Decision.** `scripts/install/install.py`, behind `install.sh` and `install.ps1`, takes no options,
carries no cad version and knows no agent app. It makes sure uv is there (an old uv that cannot
update itself gets a newer one beside it), installs cad only where none is installed or the one
there does not start, and puts the folder of a cad it installed on the PATH with uv's own `uv tool
update-shell`. Where a person ran it and a cad that starts was there already, it runs that cad's own
`cad update`, which stays inside its major; run by cad, it updates no cad. Then it hands over: that
cad's `cad plugin install` does everything in the agent apps. Where the cad there has no such
command (0.11.12 and 0.11.13), or cad could not be installed, the newest release's runs instead,
once, from uv's cache (`uv tool run ... cad@latest plugin install`), which keeps no release as the
one the plugin is up to date for: that is the installed cad's to say. It never stops to ask the
person anything and starts no server. A run that fails where no working cad can count it sends one
anonymous report of the stage that failed ([docs/install.md](../install.md#what-it-sends)); a run
cad started says nothing of it, and sends one only where cad's settings show the person was told
what cad sends. The docs site serves the script, so a production deploy of the site is refused
until PyPI's newest cad has `cad plugin install` (`scripts/release/newest_cad.py`). cad's
table of apps (`cad_server/plugin/apps.py`) is the only list of apps and of past layouts in the
repository.

**Why.** What is left in the script is what cannot be in cad: there is no cad yet, or the one there
does not start. Everything else has a version in cad (the first decision). A person who runs the
install command is asking for the newest of everything, so it updates cad as well as the plugin:
before, it never updated a cad that worked, and a person who ran it to fix something kept the old
cad until its next automatic update. Run by cad it has no reason to: cad updates itself. One
behaviour for the apps means one thing to test, and running it again is how a broken install is
repaired. A failure before any cad runs was one nobody saw; a report of the stage is the least that
shows it, and it is never sent before a person was told: a run cad started has no reader for the
line that says so. The script goes live with the site and hands over to PyPI's newest cad, so
served before the release that carries the command, every install would fail: the deploy asks
first.

**What it costs.** The script still has no version, and one copy serves every cad: it must work with
each release that has `cad plugin install` and, through `cad@latest`, with the two that do not.
Those two and the bridge still run it unattended, so what they read of it can never change: no
options, exit status 0 only where the run ended well, and the report it writes where
`CAD_INSTALL_REPORT` names a file. The bridge reads that report and never the exit status, and with
cad installed takes a run for a failed one only where a value of its `apps` says `failed`; so where
the plugin's step ended non-zero and named no app as failed, the script writes `"plugin": "failed"`
there itself, and the bridge runs it again later. And while PyPI's newest cad has no `cad plugin
install`, nothing of `main` can be deployed to the production site, a fix to a page included: only a
preview. A person's run updates a working cad at once from PyPI, under neither the feed's hour nor a
hold, as a fresh install does (the feed's decision). And cad's table is long, with many rows that
follow vendor documentation we cannot run here. A row that is wrong fails for that app alone, until
a release of cad corrects it.

## The bridge for 0.10.0 to 0.11.11

**Decision.** Releases 0.10.0 to 0.11.11 shipped an updater of their own, which installs a newer
release the old way and runs its hidden `cad setup --engine-update`. The new cad then runs the
hosted install command once, which installs cad as a uv tool and hands the apps to that cad's `cad
plugin install`, which installs the plugin and turns `cad plugin update auto` on. A computer whose apps got text-to-cad only from a plugin store gets the new cad
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
command, which installs cad and has it remove what they left behind. The install command, a README
that says how to install and the version feed stay where they are, because old releases point
people and agents at them.

**Why.** People install and forget. A release that strands its users leaves them with bugs we have
fixed and a support load we cannot see.

**What it costs.** cad carries the cleanup of every past layout in the agent apps
(`cad_server/plugin/`), the install script that of the `cad` command 0.10.0 to 0.11.11 wrote, a few
addresses can never change, and whatever else changes must bring the earlier releases along (CONTRIBUTING, "What
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

**Decision.** `cad plugin install` and the guide never use the Skills CLI (`npx skills`). Agents
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
