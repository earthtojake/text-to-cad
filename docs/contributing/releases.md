# Releases

How a release is made, what it may change, how it reaches a computer and how the install branches are
written. Read it before bumping `VERSION`, touching a release workflow or the install branches, or
deciding whether a change breaks anything. AGENTS.md has the short rules;
[Decisions](decisions.md) has the reasons behind install and update.

A pull request that changes `VERSION` is a release: merging it starts `Publish Release`, which
uploads the release's four projects to PyPI and only then moves the branches installers follow, so
`VERSION`, the stamped versions, the Git tag, the PyPI wheels and the GitHub Release all describe one
commit. Every other pull request leaves `VERSION` alone and keeps the stamps valid: `Test`'s `static`
job checks `VERSION`, the derived metadata and the stamped versions apart from the code tests, so
those still run when one is wrong.

- What a release may change: [Build artifacts live in the wheel, never in git](#build-artifacts-live-in-the-wheel-never-in-git),
  [Versions a release cannot take](#versions-a-release-cannot-take),
  [Which number a release bumps](#which-number-a-release-bumps),
  [How a release reaches a computer](#how-a-release-reaches-a-computer),
  [What must stay the same](#what-must-stay-the-same),
  [No version left behind](#no-version-left-behind),
  [Before the first release of a higher major](#before-the-first-release-of-a-higher-major)
- Making one: [Shipping a release](#shipping-a-release),
  [Submitting the plugin to OpenAI](#submitting-the-plugin-to-openai),
  [Resuming and republishing](#resuming-and-republishing),
  [Rehearsing on `build-test`](#rehearsing-on-build-test),
  [Local and manual fallbacks](#local-and-manual-fallbacks),
  [Redeploying the docs site](#redeploying-the-docs-site)
- What it stands on: [The install branches](#the-install-branches),
  [The version feed](#the-version-feed), [Repository settings](#repository-settings)

## Build artifacts live in the wheel, never in git

`main` is source. Everything the server serves that is not Python (the CAD Viewer client under
`cad_server/_runtime/viewer`, the CAD app page under `_runtime/mcp`) is gitignored and built by
`scripts/bundle/bundle.sh`, because a committed bundle can drift from the source that claims to
produce it. What a release builds, and where it goes:

- **The wheel and sdist** of `cad`, and of its empty aliases `cad-server`, `cad-mcp` and `cadgen`:
  to PyPI, where uv installs them from. `cad`'s are also attached to the GitHub Release, the
  provenance copy of what shipped.
- **The plugin alone**: onto the branches installers and stores follow, `latest`, `claude-plugin`
  and `codex-plugin` ([The install branches](#the-install-branches)).
- **The plugin ZIP**, `cad-openai-plugin-<version>.zip`, in the layout OpenAI's portal takes: to the
  GitHub Release ([Submitting the plugin to OpenAI](#submitting-the-plugin-to-openai)).
- **The pages' source maps**: to PostHog and the GitHub Release.
- **The docs site**, deployed from the release commit.

## Versions a release cannot take

The PyPI project `cad` was transferred to this project on 2026-10-31, and its previous owner had
published these versions: `0.8.0`, `0.8.1`, `0.8.2`, `0.8.3`, `0.8.4`, `0.8.5`, `0.9.0`, `0.9.1`, `0.9.5`, `0.9.6`, `0.9.7`, `0.9.8`, `0.9.9.1`, `0.9.9.3`, `1.0`, `1.0.1`, `1.0.2`, `1.0.3`, `1.0.4`, `1.1.1`, `1.1.2`.
PyPI never accepts a filename again, yanked or deleted or not, and `VERSION` is one number for every
distribution, so no release can carry any of them, nor 1.0.0: a trailing `.0` is insignificant to
PyPI. `scripts/release/unavailable-versions.txt` is the machine-checked list. `check-version.sh` and
`bump-version.sh` (which `Prepare Release` runs) refuse a `VERSION` on it, and
`tests/python/global/test_unavailable_versions.py` keeps this list identical to the file. So
`bump-version.sh major` from a version below 1.0, which computes 1.0.0, is refused: the first release
of that major is named as an exact version that is free.

Every file of those releases is yanked on PyPI, and must stay so: uv and cad's own update skip a
yanked release, and nothing else keeps a computer from taking the previous owner's 1.x for a higher
major of ours.

## Which number a release bumps

Releases follow [Semantic Versioning](https://semver.org): `VERSION` is `MAJOR.MINOR.PATCH`, and the
part a release bumps says what it asks of the people who update to it. A breaking change bumps the
*breaking slot*: the major from 1.0 and, below 1.0, which the standard leaves to the project, the
minor. Nothing else declares a break, no flag in any config.

| | Below 1.0 (`0.y.z`) | From 1.0 (`x.y.z`) |
| --- | --- | --- |
| A breaking change | the minor: `0.11.4` to `0.12.0` | the major: `1.4.2` to `2.0.0` |
| An addition, or a deprecation (a rename that keeps the old name working) | the patch: `0.11.4` to `0.11.5` | the minor: `1.4.2` to `1.5.0` |
| A fix | the patch | the patch: `1.4.2` to `1.4.3` |

Choose the bump by what the release asks of people, not by its size. When in doubt, it is the
breaking slot. The release to 1.0 bumps the major.

**What breaks.** [Law 14](../../packages/cad/README.md#the-design-laws) ("Compatibility, by who pays
for a break") sorts what a release can change into four tiers and says what compatibility each keeps;
it is the one statement of them. This table says which slot a change in each tier takes. The list in
[What must stay the same](#what-must-stay-the-same) is outside every slot.

| Law 14's tier | Breaks nothing: the patch below 1.0, the minor or patch from 1.0 | Breaking: the breaking slot, with a migration guide |
| --- | --- | --- |
| 1. What an agent reads each session: the skills, the `cad` command's verbs and options, the CAD tools | any change, in any release, once no skill text of the last 30 days uses what it removes | nothing: the 30-day rule keeps what released skills use |
| 2. The library's public imports | an addition; a rename or a move whose earlier spelling stays an alias of the same object, its interface unchanged (a deprecation, which bumps the minor from 1.0) | the alias's removal; a change to a name's contract (what it takes or returns), including a spelling kept by something that is not the same object with the same interface |
| 3. A person's data | a new form, with the previous shipped release's read and migrated on first touch | a release that cannot read what the previous shipped release wrote, or reads it as meaning something else |
| 4. Protocols where two releases meet while both run | an addition within a number; a new number whose newer side keeps answering the previous one | a new number whose newer side stops answering the previous one |

- **Tier 1 is the 30-day rule.** A `cad` command, an option, a `--json` key, an exit status, an MCP
  tool or its arguments that the skills of any release in the last 30 days use keeps working, hidden
  if need be: cad moves to the newest release of its major on every computer, and a store's copy of
  the skills can be weeks older. `tests/python/global/test_released_commands_still_parse.py` puts
  every `cad` command those skills type through today's command line (commands and options, not
  keys, statuses or tools). Past the window it may change or go in any release, a hard cutover and
  not a breaking change. A person's own script that runs `cad` commands may need an edit after an
  update; the release notes say what changed.
- **Tier 2 changes in two steps, and only the second breaks.** The rename keeps the earlier spelling
  an alias of the same object for a release at least, so no script stops working: the non-breaking
  slot, and no guide (its warning names the new spelling, and `cad._internal.aliases` pins the
  table). It is listed in a migration guide when a breaking release next writes one, at the latest
  the release that removes it, where it must be. The removal, a release or more later, takes the
  breaking slot.
- **In tier 4 the number is the protocol's, not the release's.** A new one makes the release
  breaking only where the newer side stops answering the previous number, which the law decides case
  by case. The worker contract keeps no window, so a new worker contract always does.

**Migration guides.** A breaking change comes with a migration guide under `docs/migrations/`, which
says what to change. A release that does not bump the breaking slot breaks nothing, so it adds no
guide: `Test`'s version check refuses one there (`version_breaks_nothing` in
`scripts/release/release-tags.sh`). An existing guide may be corrected or extended in any release.

**Which releases install themselves.** cad installs by itself every newer release of the major it is
on, a patch and a minor alike, and never a release of a higher major, which a person asks for with
`cad update --major`. So below 1.0 a minor that breaks reaches every computer by itself, with its
migration guide: text-to-cad is in beta, and the skills tell the person when cad is a version ahead
of them. The release to 1.0, and every major after it, waits for the person. The two rules are not
one (`version_installs_itself`, `version_breaks_nothing`): from 1.0 a minor installs itself and must
break nothing; below 1.0 a minor installs itself and may break.

## How a release reaches a computer

- **cad updates itself, inside its major.** A global install (`uv tool install cad`) does, on by
  default; `cad update auto off` stops it. Its server reads the version feed about once an hour and,
  when the feed names a newer release of its major, runs the installer's own upgrade bounded to that
  major: `uv tool install --upgrade "cad>=<installed>,<<next major>"`, PyPI's newest of the major
  (pipx: `pipx upgrade cad --pip-args=...`, the same range). uv keeps the range, so a person's own
  `uv tool upgrade cad` stays inside the major too. A typed `cad update` does the same at once, asking
  PyPI instead of the feed, and names a higher major where one is out. Nothing installs an older
  release.
- **A major is crossed only when a person asks**: `cad update --major` installs PyPI's newest of all
  (`uv tool install --upgrade "cad>=<installed>"`), and the automatic update goes on inside the new
  major. Bounded to a major is what cad runs of its own: its update, automatic and typed, and its
  install of itself, by the plugin's server line where a computer has no cad and by the bridge
  (`tool_install`: `cad<N>`, never over a `cad` of a higher major). Not bounded is the hosted install
  command, which cad also runs by itself (the plugin's catch-up below, and the bridge): it installs
  the plugin from `latest`, the newest of all, and, where cad is missing or does not start, PyPI's
  newest `cad` of all. [Before the first release of a higher
  major](#before-the-first-release-of-a-higher-major) is what must change first.
- **The plugin follows cad.** Where `cad plugin update auto` is on (the install command turns it on
  wherever cad is there) and cad is newer than the release the install command last ended well for,
  cad's server runs `cad plugin update`, the hosted install command, once, however cad got newer. The
  run is stopped, with all it started, after 15 minutes, and a failed one is tried again an hour or
  more later: at most three runs for one release. `cad update` itself never runs it.
- **The version feed says when.** It names a release an hour after it is on PyPI, unless the project
  holds it back ([The version feed](#the-version-feed)).
- **A plugin store** (Codex's directory, claude.ai's) updates the copy it installed. Its skills may
  be older than cad, which the 30-day rule covers.
- **Releases 0.10.0 to 0.11.11** are carried over once by their own updater
  ([No version left behind](#no-version-left-behind)).

The mechanism, module by module, is the server README's
[cad's own update](../../packages/cad/src/cad_server/README.md#cads-own-update); the reasons are in
[Decisions](decisions.md).

## What must stay the same

Everything else may change in any release. These may not, because past releases, their skills and
the agents running them reach for them, and nothing shipped later can change what they reach for:

1. **`texttocad.dev/install.sh` and `www.texttocad.dev/install.ps1`, run with no options.** Past
   releases' skills and documents name them, and cad runs them (`cad plugin update`, the plugin's
   catch-up after an update, the bridge). The Windows line names `www.` because Windows PowerShell 5.1
   does not follow the redirect from `texttocad.dev`.
2. **The version feed's two addresses.** `api.texttocad.dev/v1/versions`, with its `latest` field
   alone, naming the newest release below 0.12.0: every release from 0.7.12 to 0.11.11 reads it to
   learn of a newer one, and 0.11.x installs by itself only a patch of its own minor, so it is frozen
   and never names 0.12.0 or later
   ([Decisions](decisions.md#old-releases-are-carried-through-the-newest-011)). And
   `api.texttocad.dev/v1/releases`, with its `latest` and its `lines` (the newest release of each
   major), which every release from 0.11.12 on reads.
3. **`uv tool install cad`, with no flags, as the one line that installs cad.** Every skill's Setup
   block runs it, and the docs give it, so the newest `cad` on PyPI must install a working `cad`
   command on any Python from the floor up. `requires-python` takes no upper bound: with one, a
   resolver on a newer Python would fall back to an older release that has none, and that release has
   no `cad` command.
4. **The telemetry address, accepting what older releases send.** They keep sending as long as they
   run ([The version feed](#the-version-feed)).
5. **Every release on PyPI, under all four names.** Codex's plugin line runs `cad@<VERSION>` through
   uvx, and the updaters of 0.10.0 to 0.11.11 ask PyPI for `cad-server` by name: a release removed
   there breaks every copy that names it.
6. **The hidden `cad setup --engine-update`.** The updaters of 0.10.0 to 0.11.11 call it.
7. **The repository's address answering, with its `latest`, `claude-plugin` and `codex-plugin`
   branches and a README that tells an agent how to install.** Installs, apps and stores follow the
   branches by name, and the viewers of 0.7 and 0.8 send agents to the README. GitHub keeps an old
   address answering (web links, and `git clone`, `fetch` and `push`) after a rename or a move to an
   organisation, until a repository is made at the old address again; whether a renamed branch
   redirects is not known, so the three branch names are held fixed.

**Everything else follows one rule: a new release carries the old ones, and an old release never
needs to know a new one.** A name, a place or a layout may change in any release, on the condition
that the release that changes it brings along every computer an earlier one is on, by its own code or
by the install script. Two things that look fixed are instances of the rule:

- **The names `text-to-cad` (the plugin) and `earthtojake` (the catalog).** They are words in our
  own manifests, not GitHub's: moving the repository changes neither. A new name is carried by the
  install script, which removes the copies under the old one, as it does for four older names; a copy
  the script never runs on stays under the old name.
- **Where cad keeps its data** (one folder per user). A later release may move it, carrying the old
  folder along.

## No version left behind

As many past releases as reasonable can reach the latest one, by two paths:

- **0.10.0 to 0.11.11** update through their own updater, which installs the release `/v1/versions`
  names the old way and runs its hidden `cad setup --engine-update`. The new cad's server then moves
  the computer onto a global cad that updates itself: by the hosted install command, run once, where
  our install command set that computer up before, and by installing cad with uv itself elsewhere, or
  where that run installed no cad. This is the bridge (`cad_server/cli/setup.py`, kept apart to be
  deleted in one change once those releases are gone;
  [Decisions](decisions.md#the-bridge-for-0100-to-01111)). A known gap: its last step (`setup.once`,
  the install command run once) has no deadline, so a run that hangs lives on, and a later catch-up
  can run beside it.
- **Older releases** reach the latest when a person or an agent runs the install command. The script
  removes what each past layout left in the agent apps (`scripts/install/install.py`: each app's
  `handler` in `APPS`, and `remove_loose_skills`).

Check a change to the install script, to cad's update or to the list above against both paths before
it ships.

## Before the first release of a higher major

No higher major exists today, and none of this is done. Before the first one ships:

- **Its number is chosen by hand**: `bump-version.sh major` computes 1.0.0, which is on the list of
  [versions a release cannot take](#versions-a-release-cannot-take).
- **The hosted install command keeps an arriving computer inside its major** unless a person asked
  for more. Today it installs PyPI's newest `cad` of all where cad is missing or does not start. It
  is fetched at every run, so it can ask the `cad` that is there for its release and bound its
  install.
- **The plugin catch-up does not move a plugin across a major.** Today the install command installs
  the plugin from `latest`, the newest of all, whatever major the `cad` on the computer is.
- **The newest release below 0.12.0**, the stepping stone through which 0.10.0 to 0.11.11 computers
  arrive (`/v1/versions`), is checked against the same rule: its bridge runs the install command.
- **The previous owner's releases of `cad` on PyPI** (0.8.0 to 1.1.2, every file yanked) stay yanked:
  uv and cad skip a yanked release, and nothing else keeps them out.

## Shipping a release

Merging a pull request that changes `VERSION` releases it: `Publish Release`
(`release-publish.yml`) runs on that merge. Installers never take `main` as the plugin. They follow
the `latest` branch ([The install branches](#the-install-branches)), which `Publish Release` moves
only once PyPI serves the release's wheels. A mention of the release must never reach anything an
installer tracks before PyPI has its wheel: whoever updated in between would get a server that
cannot start.

The steps, for whoever ships one:

1. **Choose the bump**, by [Which number a release bumps](#which-number-a-release-bumps). If the
   request for a release names none, ask, and do not assume one.
2. **Add the What's new entry**, if the release has significant user-facing features: its minor
   version's line in `packages/ui/src/whats-new/notes.js` and its words in all five locale files.
   User-facing features only, at most three items, each a bold title and one or two sentences: it is
   the dialog the CAD Viewer and the CAD app's tabs show once after an update, and `notes.test.mjs`
   holds the shape. A release with nothing a person would notice adds none.
3. **Make the release pull request**, [one of two ways](#making-the-release-pull-request).
4. **Wait for its checks.** A `VERSION` change runs every `Test` job
   ([a full run](testing.md#a-full-run)), so the release is tested whole, Windows included, before it
   can merge, and its version check (`static`) says what merging it releases, or
   [refuses it](#what-the-version-check-refuses).
5. **Merge it** once everything is green, on the user's explicit word. That is the release:
   [`Publish Release`](#what-publish-release-does) runs on the merge commit.
6. **Afterwards**: if the release sends a new telemetry schema, check that `Deploy API` succeeded
   ([The version feed](#the-version-feed)); upload the plugin ZIP to OpenAI
   ([Submitting the plugin to OpenAI](#submitting-the-plugin-to-openai)); and if the run stopped,
   [resume it](#resuming-and-republishing).

### Making the release pull request

**Its own pull request**, to release what `main` already has: dispatch `Prepare Release`
(`release-prepare.yml`).

```bash
gh workflow run release-prepare.yml --ref main -f bump=patch     # or minor, major; -f set_version=X.Y.Z
```

It runs `bump-version.sh` on a fresh `release/X.Y.Z` branch from `main` and opens that pull request
with `PREPARE_RELEASE_TOKEN`: a pull request the workflow's own token opens starts no workflows, so
no check would ever run on it. It never merges anything. `-f dry_run=true` shows the version changes
and opens nothing.

**On the pull request that should carry it**, a feature branch whose merge should be the release:

```bash
git fetch origin && git merge origin/main      # the bump is relative to main's VERSION
scripts/release/bump-version.sh patch           # or minor, major, or an exact X.Y.Z
```

`bump-version.sh` sets `VERSION` past `main`'s and stamps the derived metadata and every mention of
the release's own (`sync-version.mjs`: package, plugin and lockfile versions, the four
`pyproject.toml`s and the aliases' `cad==` pins, Codex's server line, `cad@<VERSION>`, and the
release each skill's Setup block names). The install script carries no version. The bump works from
`main`'s version, not the branch's: running it twice changes nothing, running it again after `main`
moves moves the bump with it, and it refuses a branch that does not contain `main` yet, whose stamps
would conflict.

**When two pull requests bump at once**, the first merged wins. The other then conflicts on the
stamps if it bumped differently (take `main`'s side and run `bump-version.sh` again), or quietly
stops changing `VERSION` if it bumped the same way: its version check then says it releases nothing,
so bump again to release it.

### What the version check refuses

The pull request's version check, in `static` (`check-version.sh`, `sync-version.mjs --check`,
`check-pr-version.sh`), refuses:

- a bump from a fork: releases come from branches of this repository only, so a contributor's pull
  request can never start one;
- a version that is not past the target branch's and the latest release tag's, or that is on the list
  of [versions a release cannot take](#versions-a-release-cannot-take);
- a release that breaks nothing (below 1.0 a patch; from 1.0 a patch or a minor) and adds a migration
  guide under `docs/migrations/`, though a change to one already there passes
  ([Which number a release bumps](#which-number-a-release-bumps));
- a release that changes more than 300 files: GitHub matches a push's paths against its first 300
  changed files only, so `Publish Release` might never start. Release such a change after it merges,
  from its own pull request;
- stamps out of step with `VERSION`.

### What `Publish Release` does

On the merge commit, in this order:

1. **Gate.** `check-version.sh` and `sync-version.mjs --check`, and `VERSION` must be past the latest
   release tag, in either spelling: `scripts/release/release-tags.sh` is the one place that knows
   `v0.5.0` and the bare `0.4.28` before it, and it compares versions, not tag strings. On `main` the
   install branches' deploy key and the PostHog settings must be set
   ([Repository settings](#repository-settings)), so a release that could not finish stops before
   the PyPI upload.
2. **Tested?** Every `Test` run records the tree it tested (`tested-<tree>-<scope>`), and
   `scripts/github-workflows/tested_tree.py` looks for the record of a completed, successful `Test`
   run of this repository (never a fork's) that ran every job on exactly this tree: the pull
   request's own, since `main` merges only an up-to-date pull request. Found, nothing is tested
   again. Not found, the workflow calls `test.yml` with `full` on the release commit and publishes
   only if every job passes. No untested tree is published either way.
3. **Build.** First what a store could refuse, from the untouched release commit:
   `scripts/release/plugin_zip.py` builds the plugin ZIP and checks it against the portal's package
   rules (kept as the workflow artifact `cad-openai-plugin-<version>`), and
   `scripts/release/plugin_branch.py --check` does the same for the three copies the install
   branches get. A package a store would refuse stops the release before anything irreversible. Then:
   - `bundle.sh --clean`, which is where the server's whole runtime comes into existence, Viewer
     client and CAD app alike, because the release commit carries none of it. Its `CAD_RELEASE` names
     the version, so the Viewer and the CAD app show `v<VERSION>` where every other build shows
     `v<VERSION>-dev.<commit>` (`@cad/ui/build-id`);
   - `check-builds.sh`;
   - the pages' source maps, which the bundle builds and the wheel leaves out, gathered by
     `scripts/release/sourcemaps.py`: every chunk a crash on the CAD Viewer or the CAD app can name,
     by the debug id its build stamped on it, with its map. A page whose maps PostHog could not use
     stops the release here;
   - the wheel-contents check (`check-wheel-contents.sh`);
   - `python -m build` of the release's four projects into one folder: `cad`, and its empty aliases
     `cad-server`, `cad-mcp` and `cadgen`, a wheel and an sdist each, and nothing else or at any
     other version.
4. **Install test.** The `cad`, `cad-server` and `cad-mcp` wheels together into a fresh venv
   (`cad --help`, `cad viewer --help`, `cad-mcp --help`, `cad doctor`), then
   `scripts/test/test-installed.sh --wheels <the built folder>`, then an `unzip -l` assertion that
   the `cad` wheel about to ship really holds `_runtime/viewer` and `_runtime/mcp`. The distributions
   are kept as a workflow artifact (`dist-<version>`).

   Every step from here is irreversible and runs on `main` only.

5. **Source maps, then PyPI.** The maps go to PostHog first (`posthog-cli sourcemap upload`,
   pinned), so that no install can crash with a map PostHog lacks. Each is filed under its chunk's
   debug id, which the chunk's text and its map decide together (`@cad/core/chunk-ids`): one id names
   one map in every page and version, so no page's or version's map overwrites another's, and a later
   release that ships the same chunk and map uploads it once. Then the `pypi` job uploads the four
   projects, the only job that may mint a PyPI token ([Repository settings](#repository-settings)),
   in the order of `PROJECTS` in `scripts/release/pypi_release.py`: `cad` first, since each alias
   pins it at its own release; then `cad-server` and `cad-mcp` in one upload (neither requires the
   other); then `cadgen`, whose index the version feed reads. Each step is listed by PyPI's simple
   index, which uv resolves a pin through, before the next goes up (`--wait`: usually seconds). The
   job uploads only what PyPI does not hold yet, so a resumed release uploads nothing twice; what
   PyPI already holds is downloaded and checked against PyPI's sha256 for the GitHub Release to
   attach; and a file PyPI holds that the run did not build stops the release.
6. **Install branches**, the first step of the tag's job (one runner for both, so a busy queue costs
   the release one wait, not two). `plugin_branch.py` commits the plugin alone onto `latest`,
   `claude-plugin` and `codex-plugin` (the last, the ZIP's files), in one atomic push. Only now does
   an installer see the version.
7. **Announce.** The `v<VERSION>` tag and the GitHub Release, with these assets: `cad`'s wheel and
   sdist as PyPI serves them (the `pypi` job's artifact, `dist-<version>-released`; the aliases' are
   empty, and PyPI keeps them), the plugin ZIP, the source maps
   (`text-to-cad-sourcemaps-<version>.zip`, to upload a version's maps again) and the one-line
   installer, `install.sh`, `install.ps1` and `install.py`, with their `SHA256SUMS`. PyPI stays the
   install channel; the release page is the provenance copy. The installer files are this release's
   copies, kept for the record, and install no particular release: run from anywhere, `install.sh`
   and `install.ps1` download the newest `install.py` from texttocad.dev (`Deploy Docs` serves it),
   which installs the newest release. Then `Deploy Docs`, whose header names the release: it starts
   once the tag's job ends, and runs where the branches moved though the tag failed. Nothing here
   touches the version feed, which reads PyPI itself and names the release once it has been there
   for an hour ([The version feed](#the-version-feed)).

`main` has the new version from the merge on, a few minutes before PyPI has the wheels. Only an
install of `main` itself sees that: a command that names no branch, and a marketplace added in
Cursor, should Cursor fetch the repository in those minutes.

## Submitting the plugin to OpenAI

The plugin directory shared by ChatGPT and Codex takes plugins only through the web portal at
<https://platform.openai.com/plugins>. OpenAI documents no API or CLI for uploading, submitting or
publishing, so CD cannot do it and no secret is involved. What CD does is build the file to upload:
each GitHub Release carries `cad-openai-plugin-<version>.zip`.

For each release, a person with the access below:

1. Downloads `cad-openai-plugin-<version>.zip` from the release page.
2. On the Plugins page, opens the text-to-cad plugin, selects **Upload plugin to make changes**, and
   uploads the ZIP. The first submission uses **Upload new or existing plugin** instead.
3. Resolves the automated findings, selects **Submit for review**, and completes the policy
   attestations.
4. After approval, selects **Publish plugin**.

OpenAI's directory lists text-to-cad twice: an old listing still at 0.7.10, and the
[current one](https://chatgpt.com/plugins/plugins_6ac32e7e1a74819193e1edd581a99966?open_in_app).
Until OpenAI merges them, upload each release's ZIP to both, so the old listing's users move to the
current release too.

One-time setup, in the OpenAI Platform organization that owns the plugin: complete individual or
business verification under <https://platform.openai.com/settings/organization/general>. Submitting
needs an organization owner, or a member granted **Apps Management Write** (`api.apps.write`).

**The ZIP.** It holds the plugin at the archive's root, each folder with an entry of its own, which
the portal needs to find a plugin there: `.codex-plugin/` (manifest and icons), `skills/`, `LICENSE`,
and every file the manifest points at. The portal requires `mcpServers` to resolve to a root
`.mcp.json`, so the repository's `codex.mcp.json` is archived under that name, as it is
(`uvx ... cad@<VERSION> mcp`, Codex's `startup_timeout_sec`, no environment), and the archived
manifest points there.

`python3 scripts/release/plugin_zip.py --check` runs the release's checks locally; `--out PATH` also
writes the ZIP. `tests/python/global/test_plugin_zip.py` runs them on every pull request. They are
the portal's documented package rules
([submission errors](https://developers.openai.com/plugins/deploy/submission-errors)), with the
final-submission listing limits, such as 30 characters for the name and subtitle. A missing
`interface.logo` or `interface.composerIcon` is a warning, not an error, but the portal refuses the
upload without them. The portal's own skill and policy scans still run after upload.

## Resuming and republishing

A run that stopped (say the upload went through and the branches' push failed) is finished by
dispatching it:

```bash
gh workflow run release-publish.yml --ref main            # or -f publish=false for a draft
```

- It publishes the commit on `main` that last moved `VERSION`, the release commit and not whatever
  merged after it, if that version has no tag yet. A version whose tag exists skips at the gate.
- The release commit holds the pull request's tested tree, so its record is found and nothing is
  tested again. A run that tested a commit itself records it inside its own run, which does not
  count, so a resume of one tests again.
- A dispatch uses the workflow file on `main`, so a fix to `release-publish.yml` itself applies to
  the resume. A fix anywhere else in the tree ships with a new bump, since the resume builds the
  release commit as it was.
- The PyPI upload is idempotent, and a push of the install branches that changes nothing is a no-op.
- A failed docs deploy is redeployed on its own
  ([Redeploying the docs site](#redeploying-the-docs-site)).
- A run that pushed the tag and failed before the GitHub Release is not resumed this way, since the
  gate skips it: finish it with `publish-github-release.sh`
  ([Local and manual fallbacks](#local-and-manual-fallbacks)).

## Rehearsing on `build-test`

`build-test` is a long-lived branch whose only job is to run `Publish Release` without side effects:
there it builds and installs, uploads and pushes nothing, and prints what it would have uploaded,
deployed and tagged (`publish-github-release.sh --dry-run`). To rehearse a release, reset the branch,
open a bump against it, and merge that:

```bash
git push --force origin main:build-test     # build-test is throwaway; a past rehearsal leaves it ahead
gh workflow run release-prepare.yml --ref main -f bump=patch -f target=build-test
```

Or bump a branch of `build-test` by hand (`bump-version.sh patch --base origin/build-test`) and open
its pull request against `build-test`. The gate compares the rehearsal's `VERSION` against the
repository's real tags, exactly as `main` would: a rehearsal bump passes the gate and exercises
everything. A rehearsal consumes that version number on `build-test` only; `main` and the tags are
untouched, so the real release re-uses it.

## Local and manual fallbacks

To check a bump locally the way the gate and the version check will:

```bash
git fetch --tags origin
scripts/release/check-version.sh --incremented-from "refs/tags/$(source scripts/release/release-tags.sh && latest_release_tag)"
node scripts/release/sync-version.mjs --check
```

After bundling, `scripts/release/check-wheel-contents.sh` builds from a clean temporary package copy
and verifies that every bundled runtime file is present with identical bytes, with no obsolete
assets left in the wheel. It leaves the checkout's build scratch untouched. Set `CAD_WHEEL_OUT_DIR`
and `CAD_KEEP_WHEEL=1` to keep that checked wheel for an installed smoke test.

`scripts/release/publish-github-release.sh` is the manual fallback for the tag and GitHub Release
step, run on the release commit. It creates and pushes the tag where it is missing, then creates the
GitHub Release with each `--asset` attached; a release that exists gains those files, or has them
replaced. The files are the run's artifacts (`dist-<version>-released`, `cad-openai-plugin-<version>`,
`sourcemaps-<version>`) and the installer scripts with their `SHA256SUMS`. Unlike `Publish Release`,
the script creates a draft unless `--publish` is passed; `--dry-run` prints what it would do.

## Redeploying the docs site

`Deploy Docs` (`.github/workflows/deploy-docs.yml`) redeploys without a release, from a ref that
defaults to `main`:

```bash
gh workflow run deploy-docs.yml -f ref=main
gh workflow run deploy-docs.yml -f ref=v0.5.0  # a past release: its tag
```

`Deploy API` (`.github/workflows/deploy-api.yml`) deploys `api.texttocad.dev` on every change to
`apps/api` on `main`, and redeploys `main` on dispatch (`gh workflow run deploy-api.yml`). It follows
no release.

## The install branches

Installers clone a branch and take its tree as the plugin. On `main` that tree is the monorepo: a
Claude Code install copied all of it into its plugin cache and ran an npm install of the workspace,
1 GB per install, and claude.ai's directory would hold its workflows, lockfile and binaries for a
reviewer. `main` also names a release from the merge on, before PyPI has the wheel. So installers
follow branches only `Publish Release` writes, once the release is on PyPI: one commit per release
whose tree is only the plugin (`scripts/release/plugin_branch.py`). A release whose plugin did not
change adds no commit. There are three copies:

- **`latest`**, the newest release, which the documented install commands name. Every app's manifest
  (`.claude-plugin/plugin.json` and `icon.png`, `.cursor-plugin/plugin.json`,
  `.grok-plugin/plugin.json`, `gemini-extension.json`, `.codex-plugin/`, `.antigravity-plugin/`,
  `.kimi-plugin/`, `.devin-plugin/`, `.muse-plugin/`), `codex.mcp.json` (the one MCP config: browser
  first, only Codex gets the CAD server), the marketplace catalogs (Claude's, which Codex reads too,
  and Muse's), each listing the plugin at the branch's root, `skills/`, `LICENSE` and `README.md`,
  each README link to a file outside the tree pointed at the release commit on GitHub. No root
  `plugin.json` (the Agent Plugins standard's) and no root `mcp.json`: Codex reads a folder with the
  first as an Agent Plugin, whose server comes from the second alone, and never reads
  `codex.mcp.json` ([apps/mcp/README.md](../../apps/mcp/README.md), "Which config Codex reads").
- **`claude-plugin`**, which claude.ai's directory listing tracks: the skills alone.
  `.claude-plugin/plugin.json` (naming no MCP server and no hooks) and `icon.png`, `skills/`,
  `LICENSE` and `README.md`, and nothing another app reads. From an organization it has not
  verified, the directory refuses an MCP server that runs on the user's computer, and every file
  type but Markdown, text, JSON, YAML and PNG, JPEG, GIF, WebP or ICO images. So the builder checks
  each file of this copy against that rule and fails `--check`, and with it the release's "Check the
  plugin trees" step, on any other: a program or anything starting with `#!`, text that is not UTF-8
  or holds a NUL byte, a `hooks.json`, `.mcp.json`, `.lsp.json` or `monitors.json`, a package
  manager's configuration, or anything in `.claude-plugin/` but `plugin.json` and images. A
  `LICENSE` with no extension counts as text. No skill is left out to pass: a refused file anywhere
  in `skills/` fails the build, so a skill ships no script, and what one would script is a `cad`
  command.
- **`codex-plugin`**, for Codex's plugin directory: exactly the files of the ZIP a person uploads to
  OpenAI's portal, from the one function that builds that ZIP (`plugin_zip.build`), so the branch
  and the ZIP cannot differ.

A store's copy (`claude-plugin`, `codex-plugin` and the ZIP) is delivered and updated by its store.
Every copy holds `main`'s skills byte for byte, so the same Setup block: it installs cad by uv's
line, `uv tool install cad`, and no skill names our install command. No copy names our install
script or pipes a download to a shell anywhere (`plugin_zip.text_errors` and
`plugin_branch.PIPE_TO_SHELL`, which fail the build): the directory flags `curl ... | sh` as an
install-time risk. No skill pre-approves a tool (`allowed-tools`), which the directory refuses from
an organization it has not verified, and no manifest of ours declares a hook. No copy names a store
in its commands.

What each built copy changes from `main`'s text, each change a strict substitution that fails the
build when what it replaces is not there exactly once:

| | `latest` | `codex-plugin` and the OpenAI ZIP | `claude-plugin` |
| --- | --- | --- | --- |
| Skills | as `main` | as `main` | as `main` |
| Codex's server line | as `main`: `uvx ... cad@<VERSION> mcp` in `codex.mcp.json` | the same, in `.mcp.json` | none: no MCP config |
| README's install section | uv's line and one paragraph, in place of the Quickstart's one-liners | no README | the same as `latest` |
| `.claude-plugin/plugin.json` | as `main` | not shipped | without `documentationUrl`, `privacyPolicyUrl`, `supportUrl` and `termsOfServiceUrl`, which the directory's validation does not know; the README links the same pages |

**Installs always work from `main`; `latest` is the preferred install.** A command that names no
branch installs `main` as it is, so `main` keeps every manifest, the MCP config and the marketplace
catalogs at its root, its catalogs list the plugin at `./`, and nothing on `main` points an
installer at another branch. Development installs (`scripts/install/dev_install.py`) rely on that
too. The documented commands name `latest` where the app can name a branch, because it is the plugin
alone and never ahead of PyPI; Devin, Antigravity and Factory Droid have no branch syntax and
install `main` (Droid appends a `#ref` to the catalog's name).
`tests/python/global/test_plugin_manifests.py` holds both halves of the rule. Every copy is built
and checked by `test_plugin_branch.py` and `test_plugin_zip.py` on every pull request and again
before each release (`plugin_branch.py --check`), the directory's against claude.ai's file rules
(<https://claude.com/docs/plugins/pre-submission-checklist>).

`CAD_INSTALL_CHANNEL` and `CAD_AUTO_UPDATED`, which the configs of 0.11.11 and earlier set, are no
longer written and are ignored where an older copy still sets them.

Two branches stay as they are on purpose. `plugin`, which Cursor installs cloned before `latest`
existed, is no longer written: it stays at 0.7.14 until it is deleted. And claude.ai's listing stays
on `claude-plugin`: the portal refuses a tracked-branch change while a reviewer has the plugin, and
moving it to `latest` would hand the directory every other app's manifest and MCP config, which it
refuses from an organization it has not verified.

## The version feed

`api.texttocad.dev` (`apps/api`; its [README](../../apps/api/README.md) is the full account) serves
the feed at two addresses, both from one read of PyPI:

- `/v1/releases` names `latest`, the newest release that has been on PyPI for at least an hour and is
  not held back, and `lines`, the newest such release of each major version. Releases from 0.11.12
  on read it (`cad_server/updates.py`, at most once an hour).
- `/v1/versions` names `latest` alone and, under the same rules, the newest such release below
  0.12.0. Releases 0.7.12 to 0.11.11 read it, and 0.10.0 to 0.11.11 install the release it names, so
  the newest 0.11.x carries them over.

What a release depends on:

- **Nothing in a release touches the feed.** It reads the index of `cadgen`, the last of the four
  projects a release uploads, so a release it names is installable under every name. Its edge keeps
  an answer five minutes.
- **It says when, not what.** cad's automatic update begins when the feed names a release of the
  installed major newer than the one installed, and also where it names none of the installed major
  while its `latest` is of a higher one (bounded by its tries); either way the update installs PyPI's
  newest of the installed major. The install command, `cad update`, the plugin's server line and the
  skills' `uv tool install cad` read no feed: they take PyPI's newest (`cad update` and the server
  line, of the installed major).
- **So a hold is a brake, not a wall.** Holding a release back (`CAD_HELD_RELEASES`, an environment
  variable of the Vercel project, then `gh workflow run deploy-api.yml --ref main`:
  [Holding a release](../../apps/api/README.md#holding-a-release)) stops automatic updates only on
  computers already on the feed's release. To pull a release from everyone, yank it on PyPI.
- **A new telemetry schema ships with its receiver.** Telemetry passes through the same API to
  PostHog. A release that sends a new schema carries the receiver that reads it, deployed by its
  merge (`Deploy API`, on every change to `apps/api` on `main`; it needs the project's PostHog
  settings in Vercel, which `/v1/health` checks). Until that deploy is live, the receiver answers
  the new schema's batches "try later" (503) and the senders keep them, so check that `Deploy API`
  succeeded after the merge.

## Repository settings

What the workflows count on, in GitHub's, PyPI's and Vercel's settings and not in the tree:

- **`main`** requires a pull request with one status check, `CI`
  ([the gate](testing.md#the-gate): every `Test` job that ran passed), from GitHub Actions as its
  source, strict (up to date with `main`); squash merges only, a linear history, no force pushes and
  no deletions. A job its selection skips passes the gate, so a prose pull request merges on `static`
  and `CI`. The other side of one required check: a pull request that removes a job from `test.yml`,
  or from `CI`'s `needs`, still merges green, where a removed required job would block. So review a
  change to `test.yml`, `ci_gate.py` or the selector as a change to what protects `main`
  (`test_ci_workspace_selection.py` holds that `CI` needs every job). Strict up-to-date is what makes
  a merged tree the tree its pull request's run tested, so the push's run and `Publish Release` find
  that run's record and test nothing again; a merge that is not up to date is still tested, by both.
- **`build-test`** is protected too: a push there runs `Publish Release`, and its irreversible steps
  are skipped by the workflow, not by who may push. Its required check should be `CI` alone, as
  `main`'s. In November 2026 it still required nine job names `test.yml` no longer has
  (`Version Check`, `cadgen (Linux)` and the rest), which no run reports: until that is changed, only
  an administrator can merge a rehearsal's pull request.
- **`PREPARE_RELEASE_TOKEN`** is a personal access token, so that the release pull requests
  `Prepare Release` opens start their checks. It needs Contents and Pull requests write on this
  repository; nothing merges with it, so it need not be an admin's.
- **PyPI is published to from one place.** The `pypi` job runs in the GitHub environment `release`,
  whose deployment branches are `main` alone, and the trusted publisher of each of the four projects
  on PyPI (`cad`, `cad-server`, `cad-mcp`, and the deprecated alias `cadgen`) names this repository,
  `release-publish.yml` and that environment, so no run on another branch (or a workflow changed on
  one) can mint a token PyPI takes. A project PyPI does not have yet takes a pending publisher, the
  same three names, before its first release. No other job asks for `id-token`.
- **The install branches**, `latest`, `claude-plugin` and `codex-plugin`, have two rulesets.
  `Install branches` refuses their deletion and any force push, from anyone.
  `Install branches: release only` lets only a deploy key update them, so `Publish Release` is their
  only writer: it pushes them with its own write deploy key, whose private half is the
  `INSTALL_BRANCHES_KEY` secret, and anyone else's push is refused, an admin's or an agent's with an
  admin's credentials included. GitHub allows no exception for the workflow's own token on a personal
  account's repository. The gate stops a release on `main` that lacks the secret, before the PyPI
  upload. To replace the key, add a new write deploy key, set the secret to its private half, then
  delete the old key. A deploy key cannot be limited to some branches: its write access is to the
  whole repository, and the rulesets are what keep everyone else off the install branches (the
  deploy key is their one bypass). A new install branch needs both rulesets extended to it before
  its first release, the owner's change once in the repository's settings: without it the branch is
  not protected, though the release's push still succeeds.
- **The source map upload** needs three more secrets, which the gate checks the same way:
  `POSTHOG_CLI_API_KEY`, a PostHog personal API key scoped to the telemetry project with
  `error_tracking:write` alone (not the receiver's, which lives in Vercel); `POSTHOG_CLI_PROJECT_ID`;
  and `POSTHOG_CLI_HOST` (`https://us.posthog.com` or `https://eu.posthog.com`).
- **Tags.** Keep the tag ruleset, `Release tags`: no deletion or update of a tag
  `v[0-9]*.[0-9]*.[0-9]*` or of the bare form before 0.5.0. Keep immutable releases too, where the
  setting is on: v0.11.13 was published without it.
- **Dependabot** (`.github/dependabot.yml`) opens weekly pull requests, one grouped per ecosystem
  for minor and patch bumps, labelled `dependencies` so they land in the release notes' Maintenance
  category.

`main`'s history before 0.5.0 (commit `3eb1f9b8a`, 2026-09-04) is of a generated publish tree; the
source history of that time is the branch `history/0.5.0-source`.
