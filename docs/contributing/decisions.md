# Decisions

How text-to-cad is installed, run and updated, and why. Each entry says the decision, why it was made
and what it costs. Read it before changing the install script, `cad plugin install`, cad's update, the
plugin's manifests or the skills' setup text. How each is carried out is
[How a release reaches a computer](releases.md#how-a-release-reaches-a-computer) and, by module, the
server README's [cad's own update](../../packages/cad/src/cad_server/README.md#cads-own-update).

The decisions, by what they govern:

- **The two layers**: two layers, one direction of knowledge; cad says `cad`
- **Installing**: one cad per computer; uv's own commands; one line installs cad; the install command
  gets cad and hands the apps to it; no Skills CLI route; inside a Windows app's package
- **Updating**: the feed says when; a major version never installs itself; who updates which copy;
  forward only; the 30-day rule
- **Past releases**: the bridge for 0.10.0 to 0.11.11; old releases are carried through the newest
  0.11; no version left behind
- **The plugin**: browser first; no hooks, no pre-approved tools

## Two layers, one direction of knowledge

**Decision.** text-to-cad is two layers. cad is the software: the `cad` package on PyPI and the
`cad` command. The plugin is the skills, one manifest per agent app and the line that starts the
server, on this repository's branches. The plugin knows cad: its skills run `cad` commands and say
how to install cad. cad names agent apps, skills and the plugin in exactly one place, the package
`cad_server/plugin/`: the table of apps, how the plugin is installed and updated in each, and which
older copies are ours to remove. Only the `cad plugin` command reaches it. cad carries no skill and
depends on none: `cad plugin install` fetches the plugin from the `latest` branch.

**Why.** Every agent app installs plugins its own way, and changes that way often, so what we know of
the apps lives in one place. A hosted script has no version: one copy serves every release of cad,
so it cannot be tested against the release that runs it; its runs went uncounted, so a row that
failed on every computer failed unseen; and cad ran it unattended, whatever the website served at
that moment. In cad the table has a version, is tested with the release it ships in, and each run is
counted (how many apps it found and how many failed, naming an app only where it failed: which apps a
computer has is never sent); what runs unattended is code the computer already installed. One package
behind one command keeps the rest of cad free of the apps: an app change is still one row.

**What it costs.** A fix to an app's row needs a release of cad, and reaches a computer only when its
cad updates. A cad that does not update (automatic updates off, a release held by hand, a cad that is
no global install) keeps its table, and its list of our skills' names, while `latest` carries the
newest plugin. Two other exceptions are allowed: the server reads which app it serves, to choose how
to show a model and to say in telemetry where a count came from; and the viewer's "Open in" menu
names apps. Nothing else in cad names an app, a plugin or a skill, or imports the package
(`tests/python/global/test_cad_names_no_skill_or_plugin.py`, `test_host_neutral_packages.py`).

## cad says `cad`; the views may say text-to-cad

**Decision.** text-to-cad is the plugin's and the product's name. The command line, the server's
messages and the library call the software `cad`. The web viewer and the CAD app may say
text-to-cad in their titles: they are where the person meets both layers. So may the one package that
installs the plugin (`cad_server/plugin/`): the plugin is named text-to-cad in every app.

**Why.** A message from cad that names text-to-cad points a person who uses cad alone at a plugin
they never installed, and ties cad's text to the plugin outside the one place the first decision gives
it.

**What it costs.** Two names for one project, and a test that holds cad's text to its own
(`tests/python/global/test_cad_calls_itself_cad.py`). Addresses (`texttocad.dev`, the repository),
the MCP ids `dev.texttocad/*` and the URDF namespace keep their spelling: they can never change.

## One cad per computer

**Decision.** One package, `cad`, holds the library, the `cad` command and the server. A computer
has one cad, installed globally with `uv tool install cad`, and one server, which it starts only
when asked (`cad server start`, or the CAD app an agent app starts). The CAD app's line runs cad from
uv's cache (`uvx ... cad@<VERSION> mcp`); where the computer has no global cad, that cad installs one
and uses its server, so no server runs from the cache. Its data lives in one folder per user. No
command a skill runs names a version. `cad-server`, `cad-mcp` and `cadgen` stay on PyPI as empty
aliases of `cad`, so older installs that name them keep working.

**Why.** A release per folder, side by side, with every command pinned to its release, needs a
launcher and version machinery of our own, data copied between versions and a cleanup of old ones,
and shows people two servers. One cad is what every other command-line tool does.

**What it costs.** A chat that is open while cad updates meets the new release. Skills may be older
than cad, which [the 30-day rule](#the-30-day-rule) covers. A server started from uv's cache would
never update itself, which is why the CAD app's line installs cad first.

## uv's own commands

**Decision.** cad is installed, updated and removed with its installer's own commands: `uv tool
install cad`, `uv tool install --upgrade "cad>=<installed>,<<next major>"` (what cad's update runs),
`uv tool install --upgrade "cad>=<installed>"` (what `cad update --major` runs) and `uv tool
uninstall cad`. cad has no installer, uninstaller or launcher of its own.

**Why.** uv already installs a tool in place, replaces it on update and removes it cleanly. Code of
our own that did the same is where earlier releases failed.

**What it costs.** We take uv's behaviour as it is, its bugs included: on Windows, uv cannot remove a
running `cad.exe`, so cad's update renames each one aside first and puts a copy back, and tries again
if uv still fails; and when an install fails after it has started, uv removes the tool, so cad's
update puts the release it ran back.

## One line installs cad

**Decision.** `uv tool install cad`, with no flags, is the one way we tell anyone to install cad,
and it never changes. Every skill's Setup block runs it where `cad` is missing or older than 0.11.12,
the first release installed this way
([The shared blocks](writing-a-skill.md#the-shared-blocks), held by
`tests/python/global/test_skill_requirements.py`); cad updates itself, so no skill updates it. No
skill runs the install command. cad's `requires-python` has a floor and no upper bound.

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
can hold a release back from it ([The version feed](releases.md#the-version-feed)). cad's automatic
update begins when the feed names a newer release of its own major, and then runs the installer's own
upgrade inside that major, which installs PyPI's newest of the major. Everything else asks PyPI:
`cad update`, the install command (which installs cad where there is none and, run by a person, runs
`cad update` on the one there), the skills' line and the CAD app's line.

**Why.** The hour keeps automatic updates from spreading a release the moment it is out, and a hold
stops them without a new release. The upgrade names a range, never an exact version, because an
exact version makes uv skip the tool in a person's own `uv tool upgrade cad`. Someone who asks for an
update wants the newest now, not the feed's hour-old answer.

**What it costs.** A hold is a brake, not a wall: it stops automatic updates only on computers
already on the feed's release, since an update the feed starts takes PyPI's newest of the major. A
person who runs the install command gets PyPI's newest of their major at once, a release minutes old or
held back included, as a fresh install does. To pull a bad release from everyone, yank it on PyPI.
With no answer from the feed, no automatic update starts.

## A major version never installs itself

**Decision.** cad installs by itself any newer release with the same major version number as its
own, a patch and a minor alike; a release of a higher major never arrives by itself. A person asks
for it: `cad update --major`, which `cad update` and `cad doctor` name, with the migration guides,
when one is out. The automatic update and a typed `cad update` run the installer's upgrade bounded to
the installed major ([uv's own commands](#uvs-own-commands)). The CAD app's line installs the newest
of its own major where a computer has no cad, and never over a `cad` of a higher major. The bound is
cad's own update's, and the install command's when a person runs it on a cad that is there: it runs
that cad's `cad update`. Two things have none. The plugin: `cad plugin install` takes it from
`latest`, the newest of all, whatever major the cad that runs it is. And the hosted install command
where it has no working cad to ask: it installs PyPI's newest `cad` of all where cad is missing or does
not start, and where the cad there has no `cad plugin install` (0.11.12 and 0.11.13) runs the newest
release's from uv's cache, `uv tool run ... cad@latest plugin install`. Those two releases and
[the bridge](#the-bridge-for-0100-to-01111) run it by themselves. No higher major exists yet;
[Before the first release of a higher major](releases.md#before-the-first-release-of-a-higher-major)
lists what changes first.

**Why.** The bound lives in the updater a computer already has: a computer that sleeps for months
wakes with the updater of the release it has, so the rule has to be in the first release of this
updater, and in the commands it runs, not in a feed that can change. uv's own version range does it:
the upgrade moves up, never past the bound and, with the floor, never down; it is safe to repeat; and
uv keeps the range, so a person's own `uv tool upgrade cad` stays inside the major too. The floor
alone, in the range's place, crosses a major and never moves down (measured on uv 0.11.25, a yanked
installed release included). A minor that breaks installs itself because text-to-cad is in beta:
below 1.0 a break bumps the minor, comes with a migration guide, and the skills tell the person when
cad is a version ahead of them.

**What it costs.** A person on an old major stays there until they run `cad update --major`, and gets
no fixes made only in a later major. A minor that breaks reaches everyone by itself. Before pipx 1.18,
pipx keeps no range, so there a person's own `pipx upgrade cad` takes the newest of all; from 1.18 it
keeps the last upgrade's, so `cad update --major` passes a floor alone to replace it.

## Who updates which copy

**Decision.** cad and the plugin update separately. A global install of cad updates itself, inside
its major version, on by default (`cad update auto off` stops it). `cad update` updates cad now,
inside its major (`--major`: the newest of all), with or without a server running and with automatic
updates off too, and touches nothing else. A cad that is not a global install, such as one installed
with pip into a project's own Python, never updates itself.

The plugin is `cad plugin install`'s, the one command that installs it: in every agent app it finds,
the plugin installed or updated with that app's own command, then our older copies there removed, and
nothing else. It never runs the hosted install command and never changes `cad plugin update auto`.
`cad plugin update` is its hidden second name, the one 0.11.12 and 0.11.13 gave the run, kept for
their skills and scripts. The plugin is up to date for a release only where every app found went well:
a run keeps cad's release only where no app it found failed (none found counts) and the cad that ran
it is the computer's global install. A run where one app failed still exits 0, but keeps no release;
a run of a cad from anywhere else, such as the newest release from uv's cache, does the work and keeps
none, since its release may be of a major the installed cad never reaches.

The switch is off until the install command a person ran turns it on, as its last step, with the
installed cad's own `cad plugin update auto on`; where the plugin's step went badly, that call says
so (`CAD_INSTALL_FAILED=1`, read the same way by 0.11.12 and 0.11.13) and no release is kept. Where
cad is newer than the release the plugin is up to date for, or a run of the global install that went
badly left its release owed one, cad's server runs `cad plugin install` once, a minute after it
starts at the earliest and never while a run is going: the install command that just updated cad, and
so restarted the server, does the work in that minute. The rule asks what cad is, not how it got
there, so a typed `cad update` or `uv tool upgrade cad` by hand brings the plugin along as cad's own
update does. A server's run, named by `CAD_PLUGIN_SERVER_RUN`, has 15 minutes: each command it runs
is stopped when they are up, with all it started, and no further app is begun; a run still going a
minute past them, because a step never came back, is ended by a thread of its own, counted as
stopped, which frees its lock. A failed run, and one where any app failed, is tried again an hour or
more later: three runs at most for one release. 0.11.12 and 0.11.13 name their server's run
`CAD_INSTALL_ATTEMPT`, which everything their hosted install command starts inherits, so the install
command takes both names out of every cad command it starts. A plugin store (Codex's directory,
Claude's) updates the copy it installed.

No path loops. The install command runs `cad update` (a person's run alone), `cad plugin install` and
`cad plugin update auto on`, never `cad plugin update` alone (on 0.11.12 and 0.11.13 that runs the
install command) nor `cad setup`; `cad plugin install` runs each app's own commands and nothing of
ours; the switch keeps a setting and runs nothing; `cad update` runs neither. The only way back to the
install command is an older release's server, bounded as above
(`tests/python/global/test_no_install_loops.py`).

One run at a time. A run holds a lock in cad's state folder from its start to its end, and tries for
it for two seconds first. A second run waits; one a server began runs nothing and is tried again as a
failed run is, and a server begins none while the lock is held, spending none of its tries. cad's own
update holds while a run is going: the automatic update begins none, and a typed `cad update` is
refused in one line.

**Why.** People install and forget, and they should get our fixes without being asked. Nothing of
ours asks a person to update: in blind tests, agents would not install without the person's say-so,
and a prompt the person must act on is one most people ignore. A command does what it says: `cad
update` updates cad, `cad plugin install` installs the plugin, and only the install command, which the
person runs to have text-to-cad, opts them in to the plugin following cad. The plugin's update is the
code of the installed cad, the release that was tested, and nothing is fetched from our website to
run it. Two runs can meet (the server that starts after the install command updated cad), hence the
lock; cad's update replaces the files a run is reading, hence the hold; a run that hung for good
would hold the lock for as long as its process lived, hence the hard stop. A run where one app failed
keeps no release, or the server would not try that app again until the next release.

**What it costs.** The plugin's install is only as new as the cad that runs it (the first decision).
Released 0.11.12 and 0.11.13 still download the hosted install command and run it unattended, as their
`cad plugin update` and after their own update, and so does the bridge:
[SECURITY.md](../../SECURITY.md) says so, and nothing shipped later can change them. A typed `cad
update` during a run fails and has to be typed again. An app that fails for good costs up to three
background runs a release, each running every app found again. The hard stop cannot end a process
none of whose threads runs (one a signal stopped). A store's copy of the skills lags cad by however
long its store takes.

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
([Staying on an older release](../install.md#staying-on-an-older-release)).

## The 30-day rule

**Decision.** A command the skills used keeps working for at least 30 days after the skills stop
using it, hidden if need be. No test holds it: the change that removes a command says which
releases' skills typed it and who may still be following them. Apart from that, a command, option
or tool may change or go in any release.

**Why.** cad moves to the newest release of its major on every computer, while a store's copy of the
skills can lag by weeks. The rule keeps those skills working. A test once replayed every command
of the last 30 days' skills against the command line; it was removed, because it measured the 30
days back from the newest release tag and so held a removal the owner had decided on until some
later release was cut.

**What it costs.** An old spelling lives on for a month after the skills drop it. A person's own
scripts that run `cad` commands are not covered and may need changes after an update. A model's
Python imports and a person's data are not covered by this rule either: they keep tiers 2 and 3 of
[law 14](../../packages/cad/README.md#the-design-laws).

## The install command gets cad, and hands the apps to it

**Decision.** `scripts/install/install.py`, behind `install.sh` and `install.ps1`, takes no options,
carries no cad version and knows no agent app ([scripts/README.md](../../scripts/README.md),
`install/`, lists what it does). It makes sure uv is there, installs cad only where none is installed
or the one there does not start, and puts the folder of a cad it installed on the PATH with uv's own
`uv tool update-shell`. Where a person ran it and a cad that starts was there, it runs that cad's own
`cad update`, inside its major, and says what came of it in one line; run by cad, it updates no cad.
Then it hands over: that cad's `cad plugin install` does everything in the agent apps. Where the cad
there has no such command (0.11.12 and 0.11.13), or cad could not be installed, the newest release's
runs instead, once, from uv's cache (`uv tool run ... cad@latest plugin install`), keeping no release.
It never stops to ask the person anything, and starts no server. A run that fails where no working
cad can count it sends one anonymous report of the stage that failed
([What it sends](../install.md#what-it-sends)); a run cad started says nothing of it, and sends one
only where cad's settings show the person was told what cad sends. The docs site serves the script,
so a production deploy of the site is refused until PyPI's newest cad has `cad plugin install`
(`scripts/release/newest_cad.py`). cad's table of apps (`cad_server/plugin/apps.py`) is the only
list of apps and of past layouts in the repository.

**Why.** What is left in the script is what cannot be in cad: there is no cad yet, or the one there
does not start. A person who runs the install command is asking for the newest of everything, so it
updates cad as well as the plugin; run by cad, it has no reason to, since cad updates itself. One
behaviour for the apps means one thing to test (`tests/python/global/test_install_script.py`), and
running it again is how a broken install is repaired. A failure before any cad runs was one nobody
saw; a report of the stage is the least that shows it, sent only once a person was told. The script
goes live with the site and hands over to PyPI's newest cad, so served before the release that
carries the command, every install would fail: the deploy asks first.

**What it costs.** The script still has no version: one copy must work with each release that has
`cad plugin install` and, through `cad@latest`, with the two that do not. Those two and the bridge
run it unattended, so what they read of it never changes: no options, exit status 0 only where the
run ended well, and the report it writes where `CAD_INSTALL_REPORT` names a file. The bridge reads
that report, never the exit status. The bridge of 0.11.12 to 0.11.14, with cad installed, takes a
run for a failed one only where a value of its `apps` says `failed`; so where the plugin's step
ended non-zero and named no app as failed, the script writes `"plugin": "failed"` there itself, and
that bridge runs it again later. A later release's takes a run that installed cad as done, and
leaves a `failed` there to the plugin's retry (the bridge, below).
While PyPI's newest cad has no `cad plugin install`, nothing of `main` can be deployed to the
production site, a fix to a page included: only a preview. A person's run updates a working cad at
once from PyPI, under neither the feed's hour nor a hold. cad's table is long, and many of its rows
follow vendor documentation we cannot run here; a row that is wrong fails for that app alone, until a
release of cad corrects it.

## The bridge for 0.10.0 to 0.11.11

**Decision.** Releases 0.10.0 to 0.11.11 shipped an updater of their own, which installs a newer
release the old way and runs its hidden `cad setup --engine-update`. The new cad then runs the
hosted install command once, which installs cad as a uv tool, hands the apps to that cad's `cad
plugin install` and turns `cad plugin update auto` on. A computer whose apps got text-to-cad only
from a plugin store gets the new cad alone: running the install command there would put our plugin
in apps the person never asked us into. There, and where the install command failed before it
installed cad, the new cad installs itself with uv, and that cad updates itself from then on. Where
the new cad arrived by the uv line on a computer the install command set up before, cad runs the
install command once. The code that does this is kept apart and marked (`cad_server/cli/setup.py`),
so that a later release deletes it in one change.

The bridge's run of the install command is done once its report says cad is installed, whatever the
apps' steps did. Where one failed (an app's, or the plugin's step as a whole), that is left to the
plugin's ordinary retry (who updates which copy, above): the computer is marked as owed a run for
the release, and the retry, held back while the bridge's run is owed, then runs `cad plugin install`
at most three times for the release, an hour or more apart, and three more with each newer cad. Only
a run that did not install cad (its cad step failed, it wrote no report, or it could not start) is
run again: an hour later at a server's start, then once a day, at most 30 times in 30 days. Until
0.11.14 an app's failure kept the run failed, and so retrying, too.

**Why.** That updater cannot be changed, and it is the only way those computers reach the new design
without a person doing anything. The run is there to bring a computer onto that design: cad
installed globally, its updates on, the plugin's switch on. Once cad is installed that is done, and
an app that fails is the failure any computer can meet, which cad already retries one way, bounded
for each release. Kept failed for it, the run ran every app again each day for up to 30 days, held
the ordinary retry back the while, and was counted as failed where cad was installed; and some apps
fail for reasons no run of ours can fix: an app release that fails every git install by itself, or
one nobody is signed in to.

**What it costs.** A few commands stay for those releases: `cad setup --engine-update`; plain
`cad setup`, which a `cad update` typed on those releases runs; and the hidden short forms `cad status`
and `cad stop` their skill text uses. An app that fails in the bridge's run gets three tries a
release, not one a day: one that would come right by itself within the month waits for the next
release of cad, or for a person's `cad plugin install`. The bridge's run is counted as done where an
app failed; the app is counted by the run of `cad plugin install` that met it, as any run's apps
are.

## Old releases are carried through the newest 0.11

**Decision.** The old address of the version feed, `api.texttocad.dev/v1/versions`, which every
release from 0.7.12 to 0.11.11 reads, is frozen: it names the newest release below 0.12.0, in the shape
it always had (`latest` alone), under the feed's hour and holds. The releases from 0.11.12 on read
their own address, `/v1/releases` ([The feed says when](#the-feed-says-when)). A computer on an old
release reaches the newest 0.11.x, whose bridge brings it onto the design that updates itself, and
that cad goes on from there.

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
addresses can never change, and whatever else changes must bring the earlier releases along
([What must stay the same](releases.md#what-must-stay-the-same); the paths to check a change
against are [No version left behind](releases.md#no-version-left-behind)).

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

**Decision.** No manifest of ours declares a hook, and no skill declares `allowed-tools`
(`tests/python/global/test_plugin_manifests.py`, `test_skill_requirements.py`). Nothing starts cad's
server when a session opens: `cad server start` starts it, which a command that finds no server tells
the agent to run (`the cad server is not running: run cad server start`), or `cad mcp`, Codex's
server line. Every copy of the plugin, the one a person installs by hand and each listing's, carries
the same skills, byte for byte (`test_plugin_branch.py`).

**Why.** The copy people install by hand should be the same skills a listing carries, and Claude's
plugin directory refuses hooks and `allowed-tools` from an organization it has not verified. A hook
fails wherever cad is missing or old, and only its declaration can be tested. `allowed-tools`
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
inside the app does not reach the folder: `Remove-Item` there reported the folder gone and left every
file, and the same delete from outside the app removed it (both measured).

**What it costs.** On such a computer a person may have to run one command or delete one folder by
hand.
