# Releases

How a release is made, what it may change, how it reaches a computer and how the install branches are
written. Read this before bumping `VERSION`, touching a release workflow or the install branches, or
deciding whether a change breaks anything. The short rules are in the repository's agent guidance; the
reasons behind install and update are in [Decisions](decisions.md).

A pull request that changes `VERSION` is a release: merging it starts `Publish
Release`, which uploads the release's four projects to PyPI and only then moves the branches
installers follow, so the canonical repo version, the stamped versions, the Git tag,
the PyPI wheels and the GitHub Release all describe one commit. Normal
development PRs leave `VERSION` alone. A PR that touches release state must keep
`VERSION`, the derived metadata and the stamped versions valid; `Test`'s `static` job
checks all three, apart from the code tests, so those still run when they are
wrong.

## Build artifacts live in the wheel, never in git

`main` is source. Everything the server serves that is not Python — the CAD Viewer
client under `cad_server/_runtime/viewer` and the CAD app page under `_runtime/mcp`
— is gitignored and produced by `scripts/bundle/bundle.sh`. Nothing built is ever
committed: a rebundle used to add a megabyte of history per commit, and a
committed bundle can drift from the source that claims to produce it.

Where the built things live instead:

- **CI** builds the runtime stages needed by each selected test job and tests
  against that build (`bundle.sh --check` now means "the runtime builds and is
  complete", not a diff against a committed copy).
- **The wheel** is the release artifact. `Publish Release` bundles, builds the
  wheel and sdist, asserts the wheel carries `_runtime/`, installs and
  exercises it, keeps the distribution as a workflow artifact, uploads it to
  PyPI (where uv installs it from), and attaches that same
  wheel and sdist to the GitHub Release as the provenance copy of what shipped.
- **The plugin ZIP** (`cad-openai-plugin-<version>.zip`) is the plugin in the
  layout OpenAI's plugin submission portal takes. It is built from the release
  commit and attached to the GitHub Release beside the wheel. See [Submitting
  the plugin to OpenAI](#submitting-the-plugin-to-openai).
- **The install branches** (`latest`, `claude-plugin` for claude.ai's
  directory and `codex-plugin` for Codex's) are the plugin alone, the trees
  installers and stores take. See
  [The install branches](#the-install-branches).
- **A checkout** builds its own: run `scripts/bundle/bundle.sh` once after
  cloning (and after pulling changes to `packages/core`); a missing runtime
  fails with a message that says so.

## Versions a release cannot take

The PyPI project `cad` was transferred to this project on
2026-10-31, and its previous owner published these versions before the transfer: `0.8.0`, `0.8.1`, `0.8.2`, `0.8.3`, `0.8.4`, `0.8.5`, `0.9.0`, `0.9.1`, `0.9.5`, `0.9.6`, `0.9.7`, `0.9.8`, `0.9.9.1`, `0.9.9.3`, `1.0`, `1.0.1`, `1.0.2`, `1.0.3`, `1.0.4`, `1.1.1`, `1.1.2`.
PyPI never accepts a filename again, yanked or deleted or not, so no release of text-to-cad can
carry any of them (`VERSION` is one number for every distribution, which is why the release that
was to be 0.9.0 is 0.10.0). `scripts/release/unavailable-versions.txt` is the
machine-checked source: `check-version.sh` and `bump-version.sh` (which `Prepare Release` runs) refuse a
`VERSION` on it (1.0.0 too, since a trailing `.0` is insignificant to PyPI), and a test keeps
this list identical to the file. Every file of those releases is yanked on PyPI, and must stay so:
uv and cad's own update skip a yanked release, and nothing else keeps a computer from taking the
previous owner's 1.x for a higher major of ours.

## Which number a release bumps

Releases follow [Semantic Versioning](https://semver.org): `VERSION` is `MAJOR.MINOR.PATCH`, and the
part a release bumps says what it asks of the people who update to it. A breaking change bumps the
major from 1.0 and, below 1.0, which the standard leaves to the project, the minor: that part is the
*breaking slot*. Nothing else declares a break, no flag in any config: the number does.

| | Below 1.0 (`0.y.z`) | From 1.0 (`x.y.z`) |
| --- | --- | --- |
| A breaking change | the minor: `0.11.4` to `0.12.0` | the major: `1.4.2` to `2.0.0` |
| An addition, or a deprecation (a rename that keeps the old name working) | the patch: `0.11.4` to `0.11.5` | the minor: `1.4.2` to `1.5.0` |
| A fix | the patch | the patch: `1.4.2` to `1.4.3` |

**A command the skills used keeps working for 30 days.** cad moves to the newest release of its major on
every computer, and a store's copy of the skills can be weeks older. So a `cad` command, an option, a
`--json` key, an exit status, an MCP tool or its arguments that the skills of any release in the last
30 days use keeps working, hidden if need be; CI checks every release against that skill text
(`tests/python/global/test_released_commands_still_parse.py`). Past that window it may change or go
in any release, and that is not a breaking change: it is a hard cutover (law 15, tier 1). A person's
own script that runs `cad` commands may need an edit after an update; the release notes say what
changed.

What breaks is what a person keeps from one release to the next: a Python name a model script imports,
removed or with its contract changed (tier 2); data a release can no longer read (tier 3); a protocol
where two running releases meet, whose newer side stops answering the older (tier 4); and anything on
the list in [What must stay the same](#what-must-stay-the-same). A breaking change always comes with a
migration guide under `docs/migrations/`, which says what to change. A release that does not bump the
breaking slot breaks nothing -- a patch below 1.0, a patch or a minor from 1.0 -- so it adds no new
migration guide: `Test`'s version check refuses one there (`version_breaks_nothing` in
`scripts/release/release-tags.sh`). An existing guide may be corrected or extended in any release. Choose the bump by what the release asks of people,
not by its size; the release to 1.0 bumps the major. When in doubt, it is the breaking slot.

**Which releases install themselves.** cad installs by itself every newer release of the major it is on,
a patch and a minor alike, and never a release of a higher major: a person asks for that with `cad update
--major` ([How a release reaches a computer](#how-a-release-reaches-a-computer)). So below 1.0 a minor that
breaks reaches every computer by itself, with its migration guide: text-to-cad is in beta, and the skills
tell the person when cad is a version ahead of them. The release to 1.0, and every major after it, waits
for the person. The two rules are not one: from 1.0 a minor installs itself and must break nothing, so it
may carry no new guide; below 1.0 a minor installs itself and may break, with its guide
(`version_installs_itself` and `version_breaks_nothing`).

**What breaks, by tier.** [Law 15](../../packages/cad/README.md#the-design-laws) ("Compatibility, by who
pays for a break") sorts what a release can change into four tiers and says what compatibility each
keeps; it is the one statement of them. This table says which slot a change in each tier takes.

| Law 15's tier | Breaks nothing: the patch below 1.0, the minor or patch from 1.0 | Breaking: the breaking slot, with a migration guide |
| --- | --- | --- |
| 1. What an agent reads each session: the skills, the `cad` command's verbs and options, the CAD tools | any change, in any release, once no skill text of the last 30 days uses what it removes | nothing: the 30-day rule keeps what released skills use |
| 2. The library's public imports | an addition; a rename or a move whose earlier spelling stays an alias of the same object, its interface unchanged (a deprecation, which bumps the minor from 1.0) | the alias's removal; a change to a name's contract (what it takes or returns), including a spelling kept by something that is not the same object with the same interface |
| 3. A person's data | a new form, with the previous shipped release's read and migrated on first touch | a release that cannot read what the previous shipped release wrote, or reads it as meaning something else |
| 4. Protocols where two releases meet while both run | an addition within a number; a new number whose newer side keeps answering the previous one | a new number whose newer side stops answering the previous one |

Tier 2 changes in two steps, and only the second breaks. The rename keeps the earlier spelling an
alias of the same object, its interface unchanged, for a release at least, so no script stops working:
it takes the non-breaking slot. Law 15 keeps an alias out of every document but the migration guide,
and asks for no guide when one is made: the rename is announced by its warning, which names the new
spelling at the line that spelled the old, and held by the pinned table (`cad._internal.aliases`), and
it is listed in a migration guide when a breaking release next writes one, at the latest the release
that removes it, where it must be. That removal, a release or more later, is what stops a script that
still spells the old name, so it takes the breaking slot. So does a change to a name's contract, which
no alias keeps, and so does a spelling kept by something other than the same object with the same
interface. In tier 4 the number is the protocol's, not the release's: a new one makes the release a
breaking one only where the newer side stops answering the previous number, which the law decides case
by case; the worker contract keeps no window, so a new worker contract always does.

## How a release reaches a computer

- **cad updates itself, inside its major version**: a global install (`uv tool install cad`), on by
  default, `cad update auto off` to stop it. The server reads the version feed in the background about
  once an hour; when the feed names a release of its own major newer than its own, as it starts, after a
  failed start, or once nothing has run for a minute, a helper stops the server, runs the installer's own
  upgrade bounded to that major (`uv tool install --upgrade "cad>=<installed>,<<next major>"`: PyPI's
  newest of the major; pipx: `pipx upgrade cad --pip-args=...`, the same range) and starts the server
  again (`cad_server/_internal/auto_update.py`). The range is worked out from the installed release
  each time, and uv keeps it, so a person's own `uv tool upgrade cad` stays inside the major too.
  `cad update` does the same now, asking PyPI rather than the feed, and names a higher major where one is
  out.
- **cad's own update crosses a major only when a person asks**: `cad update --major` installs PyPI's
  newest of all (`uv tool install --upgrade "cad>=<installed>"`, the floor alone in place of uv's range;
  pipx: `pipx upgrade cad --pip-args=cad>=<installed>`, which replaces the range pipx 1.18 keeps), and
  the automatic update goes on inside the new major. Bounded to a major, by what cad runs: cad's own
  update, automatic and typed, and cad's own install of itself, by the plugin's server line where a
  computer has no cad and by the bridge's step 4b (`tool_install`: `cad<N>`, never over a `cad` of a
  higher major). Not bounded: the hosted install command, which cad also runs by itself (the plugin's
  catch-up below, and for a computer 0.10.0 to 0.11.11 brought, the bridge's install mode and its last
  step): it installs the plugin from `latest`, the newest of all, and, where uv has no `cad` tool or the
  one there does not start, PyPI's newest `cad` of all (pipx's that does not start: `pipx install
  --force cad`, the same). No higher major exists today; [Before the first release of a higher
  major](#before-the-first-release-of-a-higher-major) is what must change first. cad's own update is
  forward only: it never installs an older release.
- **The plugin follows cad.** Where `cad plugin update auto` is on (the install command turns it
  on wherever cad is there, and keeps its release only where its run ends well) and cad is newer than
  the release the install command last ended well for, cad's server runs `cad plugin update`, the hosted
  install command, once, at its start or a
  quiet tending, however cad got newer: its own update, a typed `cad update`, or `uv tool upgrade cad`
  by hand (`cad_server/_internal/plugin_catch_up.py`). That run is stopped, with all it started,
  after 15 minutes. A failed run is tried again an hour or more later: at most three runs for one
  release. `cad update` itself never runs it.
- **The version feed says when.** It names a release an hour after it is on PyPI, unless the project
  holds it back ([The version feed](#the-version-feed)).
- **A plugin store** (Codex's directory, claude.ai's) updates the copy it installed. Its skills may be
  older than cad, which the 30-day rule covers.
- **Releases 0.10.0 to 0.11.11** are carried over once by their own updater
  ([No version left behind](#no-version-left-behind)).

The reasons are in [docs/contributing/decisions.md](decisions.md).

## What must stay the same

Everything else may change in any release. These may not, because past releases, their skills and
the agents running them reach for them, and nothing shipped later can change what they reach for:

1. **`texttocad.dev/install.sh` and `www.texttocad.dev/install.ps1`, run with no options.** Past
   releases' skills and documents name them, and cad runs them (`cad plugin update`, after an
   automatic update, and the bridge). The Windows line names `www.` because Windows PowerShell 5.1
   does not follow the redirect from `texttocad.dev`.
2. **The version feed's two addresses.** `api.texttocad.dev/v1/versions` and its `latest` field, alone,
   naming the newest release below 0.12.0: every release from 0.7.12 to 0.11.11 reads it to learn of a
   newer one, and 0.11.x installs by itself only a patch of its own minor, so it is frozen and never names
   0.12.0 or later ([decisions](decisions.md), "Old releases are carried through the
   newest 0.11"). `api.texttocad.dev/v1/releases`, its `latest` and its `lines` (the newest release of
   each major): every release from 0.11.12 on reads it.
3. **`uv tool install cad`, with no flags, as the one line that installs cad.** Every skill's Setup
   block runs it, and the docs give it, so the newest `cad` on PyPI must install a working `cad`
   command on any Python from the floor up. No upper bound on `requires-python`: a resolver on a
   newer Python would fall back to an old release without one, which has no `cad` command.
4. **The telemetry address, accepting what older releases send.** They keep sending as long as they
   run ([The version feed](#the-version-feed)).
5. **Every release on PyPI, under all four names.** Codex's plugin line runs `cad@<VERSION>` through
   uvx, and the updaters of 0.10.0 to 0.11.11 ask PyPI for `cad-server` by name: a release removed
   there breaks every copy that names it.
6. **The hidden `cad setup --engine-update`.** The updaters of 0.10.0 to 0.11.11 call it.
7. **The repository's address answering, with its `latest`, `claude-plugin` and `codex-plugin` branches
   and a README that tells an agent how to install.** Installs, apps and stores follow the branches by
   name, and the viewers of 0.7 and 0.8 send agents to the README. GitHub keeps an old address
   answering (web links, and `git clone`, `fetch` and `push`) after a rename or a move to an
   organisation, until a repository is made at the old address again; whether a renamed branch
   redirects is not known, so the three branch names are held fixed.

**Everything else follows one rule: a new release carries the old ones, and an old release never needs
to know a new one.** A name, a place or a layout may change in any release, on the condition that the
release that changes it brings along every computer an earlier one is on, by its own code or by the
install script. Two things that look fixed are instances of the rule:

- **The names `text-to-cad` (the plugin) and `earthtojake` (the catalog).** They are words in our own
  manifests, not GitHub's: moving the repository changes neither. A new name is carried by the install
  script, which removes the copies under the old one, as it does for four older names; a copy the
  script never runs on stays under the old name.
- **Where cad keeps its data** (one folder per user). A later release may move it, carrying the old
  folder along.

## No version left behind

As many past releases as reasonable can reach the latest one:

- **0.10.0 to 0.11.11** update through their own updater, which installs the newest release the old
  way and runs its hidden `cad setup --engine-update`. Where our install command set that computer up
  before, the new cad's server then runs the hosted install command once, which installs cad as a uv
  tool, installs the plugin in the apps and turns `cad plugin update auto` on; elsewhere, or where
  that run installed no cad, the server installs cad with uv itself. Either way it then hands over to
  the global cad's server, which updates itself from then on (`cad_server/cli/setup.py`, kept apart as
  bridge code, to be deleted in one change once those releases are gone). A known gap: the bridge's
  last step (`setup.once`, the install command run once) has no deadline, so a run that hangs lives on,
  and a later catch-up can run beside it.
- **Older releases** reach the latest when a person or an agent runs the install command. The script
  removes what each past layout left in the agent apps (`scripts/install/install.py`, the `cleanup` of
  each row of `APPS` and `remove_loose_skills`).

Check a change to the install script, to cad's update or to the list above against both paths
before it ships.

## Before the first release of a higher major

None of this is done, and no higher major exists today. Before the first one ships:

- **The hosted install command keeps an arriving computer inside its major** unless a person asked for
  more: today it installs PyPI's newest `cad` of all where cad is missing or does not start. It is
  fetched at every run, so it can ask the `cad` that is there for its release and bound its install.
- **The plugin catch-up does not move a plugin across a major**: today the install command installs the
  plugin from `latest`, the newest of all, whatever major the `cad` on the computer is.
- **The newest release below 0.12.0**, the stepping stone through which 0.10.0 to 0.11.11 computers
  arrive (`/v1/versions`), is checked against the same rule: its bridge runs the install command.
- **The previous owner's releases of `cad` on PyPI** (0.8.0 to 1.1.2, every file yanked) stay yanked
  ([Versions a release cannot take](#versions-a-release-cannot-take)): uv and cad skip a yanked
  release, and nothing else keeps them out.

## Shipping a release

Merging a pull request that changes `VERSION` releases it: `Publish Release`
(`release-publish.yml`) runs on that merge. Installers never take `main` as the
plugin: they follow the `latest` branch (see
[The install branches](#the-install-branches)), which `Publish Release` moves
only once PyPI serves the release's wheels. A mention of the release must never reach
anything an installer tracks before PyPI has its wheel. When installers took `main`, anyone
who updated between a release's merge and its upload got a CAD server that would
not start (`uvx … --from cadgen==0.7.14` → "there is no version"), for the 25
minutes the release took to reach PyPI.

A release pull request comes one of two ways. Choose the bump deliberately for
every release, by [Which number a release bumps](#which-number-a-release-bumps); if a
release request does not specify one, confirm it rather than assuming.

A release with significant user-facing features adds its What's new entry before it ships: its
minor version's line in `packages/ui/src/whats-new/notes.js` and its words in all five locale
files, user-facing features only, at most three items, each a bold title and one or two sentences
(the dialog the CAD Viewer and the CAD app's tabs show once after an update; `notes.test.mjs`
holds the shape). A release with nothing a person would notice adds none.

**Its own pull request**, to release what `main` already has: dispatch
`Prepare Release` (`release-prepare.yml`).

```bash
gh workflow run release-prepare.yml --ref main -f bump=patch     # or minor, major; -f set_version=X.Y.Z
```

It runs `bump-version.sh` on a fresh `release/X.Y.Z` branch from `main` and
opens that pull request with `PREPARE_RELEASE_TOKEN`: a pull request the
workflow's own token opens starts no workflows, so no check would ever run on
it. It never merges anything: merge the pull request once its checks pass, and
that merge releases it. `-f dry_run=true` shows the version changes and opens
nothing.

**On the pull request that should carry it**, a feature branch whose merge
should be the release:

```bash
git fetch origin && git merge origin/main      # the bump is relative to main's VERSION
scripts/release/bump-version.sh patch           # or minor, major, or an exact X.Y.Z
```

`bump-version.sh` sets `VERSION`
past `main`'s and stamps the derived metadata and every mention of the release's own
(`sync-version.mjs`: package, plugin and lockfile versions, the four `pyproject.toml`s and the
aliases' `cad==` pins, Codex's server line, `cad@<VERSION>`, and the release each skill's Setup
block names). The install script carries no version.
It works from `main`'s version, not the branch's, so running it twice
changes nothing and running it again after `main` moves moves the bump with it;
it refuses a branch that does not contain `main` yet, whose stamps would conflict.

The pull request's version check (`static`) says what merging it releases, and refuses:

- a bump from a fork — releases come from branches of this repository only, so
  a contributor's pull request can never start one;
- a version that is not past the target branch's and the latest release tag's, or that is on
  the list of [versions a release cannot take](#versions-a-release-cannot-take);
- a release that breaks nothing -- below 1.0 a patch, the target's `X.Y`; from 1.0 a patch or
  minor, the target's `X` -- that adds a migration guide under `docs/migrations/` (a change to one
  already there passes): see
  [Which number a release bumps](#which-number-a-release-bumps);
- a release that changes more than 300 files: GitHub matches a push's paths
  against its first 300 changed files only, so `Publish Release` might never
  start. Release such a change after it merges, from its own pull request;
- stamps out of step with `VERSION` (`check-version.sh`,
  `sync-version.mjs --check`).

A `VERSION` change runs every `Test` job (see [CI](testing.md#ci)), so the release is
tested whole, Windows included, before it can merge. Merge it once everything is
green: that is the release. `Publish Release`, on the merge commit:

1. **Gate.** `check-version.sh` and `sync-version.mjs --check`, and `VERSION`
   must be past the latest release tag (either spelling —
   `scripts/release/release-tags.sh` is the one place that knows `v0.5.0` and
   the bare `0.4.28` before it, and it compares versions, not tag strings).
2. **Tested?** Every `Test` run records the tree it tested
   (`tested-<tree>-<scope>`), and `scripts/github-workflows/tested_tree.py`
   finds the record of a completed, successful `Test` run of this repository
   (never a fork's) that ran every job on exactly this tree: the pull request's
   own, since `main` merges only an up-to-date pull request. Then nothing is
   tested again. Without one, the workflow calls `test.yml` with `full` on the
   release commit and publishes only if every job passes. No untested tree is
   published either way.
3. **Build.** `scripts/release/plugin_zip.py` builds the plugin ZIP from the
   untouched release commit (the skills as `main` has them,
   [The install branches](#the-install-branches)), and checks it
   against the portal's package rules,
   so a package the portal would refuse stops the release before anything
   irreversible; the ZIP is kept as a workflow artifact
   (`cad-openai-plugin-<version>`). `scripts/release/plugin_branch.py --check`
   does the same for the three copies of the plugin the install branches get (`latest`,
   `claude-plugin` and `codex-plugin`). Then
   `bundle.sh --clean` — which is where the server's whole runtime comes into
   existence, Viewer client and CAD app alike, because the release
   commit carries none of it; its `CAD_RELEASE` names the version, so
   the Viewer and the CAD app show `v<VERSION>` where every other build shows
   `v<VERSION>-dev.<commit>` (`@cad/ui/build-id`) — `check-builds.sh`,
   the wheel-contents check, `python -m build` of the release's four projects on
   PyPI into one folder (`cad`, and its empty aliases `cad-server`, `cad-mcp` and `cadgen`, a wheel
   and an sdist each, and nothing else at any other version), and an `unzip -l` assertion
   that the `cad` wheel about to ship really holds `_runtime/viewer` and
   `_runtime/mcp`. The pages' source maps, which the bundle
   builds and the wheel leaves out, are gathered too
   (`scripts/release/sourcemaps.py`): every chunk a crash on the CAD Viewer or
   the CAD app can name, by the debug id its build stamped on it, with its map
   -- a page whose maps PostHog could not use stops the release here.
4. **Install test.** The `cad`, `cad-server` and `cad-mcp` wheels together
   into a fresh venv — `cad --help`, `cad viewer --help`, `cad-mcp --help`,
   `cad doctor` — then
   `scripts/test/test-installed.sh --wheels <the built folder>`; the distributions
   are uploaded as a workflow artifact (`dist-<version>`).
5. **Source maps, then PyPI** (on `main` only). The maps go to PostHog first
   (`posthog-cli sourcemap upload`, pinned), each filed under its chunk's debug
   id, which the chunk's text and its map decide together
   (`@cad/core/chunk-ids`; rolldown's own names the code alone): one id
   names one map in every page and version, so no page's or version's map
   overwrites another's, and a later release that ships the same chunk and map
   uploads it once. Then the `pypi` job uploads the four projects:
   the only job that may mint a PyPI token, in the `release` environment (below,
   "Repository settings"). `cad` goes first, since each alias pins it at its own release, then
   `cad-server` and `cad-mcp` together, in one upload (neither requires the other; the token PyPI
   mints covers every project that trusts this workflow), then `cadgen`, whose index the version
   feed reads (`PROJECTS` in `scripts/release/pypi_release.py`); each step is listed by PyPI's simple
   index, which uv resolves a pin through, before the next goes up (`--wait`: usually seconds).
   It uploads only what PyPI does not hold yet, so a resumed release uploads nothing
   twice, and what PyPI already holds is downloaded and checked against PyPI's
   sha256 for the GitHub Release to attach; a file PyPI holds that the run did not
   build stops the release.
6. **Install branches** (on `main` only), the first step of the tag's job (one runner for both, so a
   busy queue costs the release one wait, not two). `plugin_branch.py` commits the plugin
   alone onto `latest`, `claude-plugin` and `codex-plugin` (the ZIP's files: [The install
   branches](#the-install-branches)), in one atomic push. Only now does
   an installer see the version.
7. **Announce** (on `main` only), after the branches: `Deploy Docs`, whose
   header names the release (it starts once the tag's job ends, and runs where the branches moved
   though the tag failed); and the `v<VERSION>`
   tag and the GitHub Release, with `cad`'s wheel and sdist as PyPI
   serves them (the `pypi` job's artifact, `dist-<version>-released`; the aliases' are empty,
   and PyPI keeps them),
   the plugin ZIP and the source maps (`text-to-cad-sourcemaps-<version>.zip`, to
   upload a version's maps again) attached as release assets (PyPI stays the
   install channel; the release page is the provenance copy), and beside them the
   one-line installer, `install.sh`, `install.ps1` and `install.py`, with their `SHA256SUMS`:
   this release's copies, kept for the record. They install no particular release: run from
   anywhere, `install.sh` and `install.ps1` download the newest `install.py` from
   texttocad.dev (`Deploy Docs` serves it), which installs the newest release.
   Nothing here touches the version feed (`api.texttocad.dev`): it reads PyPI itself and names the
   release once it has been on PyPI for an hour, its edge keeping an answer five minutes
   ([The version feed](#the-version-feed)).

`main` has the new version from the merge on, a few minutes before PyPI has the
wheels. Only an install of `main` itself sees that: a command that names no
branch, and a marketplace added in Cursor, should Cursor fetch the repository in those minutes.

When two pull requests bump at once, the first merged wins. The other then
conflicts on the stamps if it bumped differently (take `main`'s side and run
`bump-version.sh` again) or quietly stops changing `VERSION` if it bumped the
same way — its version check then says it releases nothing; bump again to
release it.

## The install branches

Installers clone a branch and take its tree as the plugin. On `main` that tree
is the monorepo: a Claude Code install copied all of it into its plugin cache
and ran an npm install of the workspace, 1 GB per install, and claude.ai's
directory would hold its workflows, lockfile and binaries for a reviewer. `main`
also names a release from the merge on, before PyPI has the wheel. So
installers follow branches only `Publish Release` writes, once the release is on
PyPI: one commit per release whose tree is only the plugin
(`scripts/release/plugin_branch.py`). A release whose plugin did not change adds
no commit. There are three copies:

- `latest`, the newest release, which every install command names: every app's
  manifest (`.claude-plugin/plugin.json` and `icon.png`, `.cursor-plugin/plugin.json`,
  `.grok-plugin/plugin.json`, `gemini-extension.json`, `.codex-plugin/` and
  `codex.mcp.json`, the one MCP config: browser first, only Codex gets the CAD
  server, `.antigravity-plugin/`, `.kimi-plugin/`, `.devin-plugin/`,
  `.muse-plugin/`), the marketplace catalogs (Claude's, which Codex reads too,
  and Muse's), each listing the plugin at the branch's root, `skills/`,
  `LICENSE` and `README.md`, each README link to a file outside the tree pointed
  at the release commit on GitHub. No root `plugin.json` (the Agent Plugins
  standard's) and no root `mcp.json`: Codex reads a folder with the first as an
  Agent Plugin, whose server comes from the second alone, and never reads
  `codex.mcp.json` ([apps/mcp/README.md](../../apps/mcp/README.md), "Which config Codex
  reads"). It is our own text, as `main` has it, but for the README's install
  section, which installs cad by uv's line in place of the Quickstart's
  one-liners, as `claude-plugin`'s does, so no README of a copy holds a download
  piped to a shell.
- `claude-plugin`, which claude.ai's directory listing tracks: the skills alone.
  `.claude-plugin/plugin.json` (main's less four listing links, naming no MCP
  server and no hooks) and `icon.png`, `skills/`, `LICENSE` and `README.md`, and
  nothing another app reads. The directory flags a download piped to a shell
  (`curl ... | sh`) as an install-time risk, so this copy's README installs cad
  by uv's line in place of the Quickstart's one-liners, and the copy holds no
  pipe-to-shell download anywhere. The directory refuses an MCP
  server that runs on the user's computer, and every file type but Markdown,
  text, JSON, YAML and PNG, JPEG, GIF, WebP or ICO images, from an organization
  it has not verified, so the builder checks each file of this copy against
  that rule and fails `--check`, and with it the release's "Check the plugin
  trees" step, on any other: a program or anything starting with `#!`, text
  that is not UTF-8 or holds a NUL byte, a `hooks.json`, `.mcp.json`,
  `.lsp.json` or `monitors.json`, a package manager's configuration, or
  anything in `.claude-plugin/` but `plugin.json` and images. A `LICENSE` with
  no extension counts as text. No skill is left out to pass: a refused file
  anywhere in `skills/` fails the build, so a skill ships no script, and what
  one would script is a `cad` command (print3d's complete OrcaSlicer presets
  are `cad orcaslicer`, the library's `orcaslicer` integration).
- `codex-plugin`, for Codex's plugin directory: exactly the files of the ZIP a
  person uploads to OpenAI's portal (below), from the one function that builds
  that ZIP (`plugin_zip.build`), so the branch and the ZIP cannot differ.

A store's copy (`claude-plugin`, `codex-plugin` and the ZIP) is delivered and updated by its store.
Every copy holds `main`'s skills byte for byte, so the same Setup block: it installs cad by uv's line,
`uv tool install cad`, and no skill names our install command. No skill pre-approves a tool
(`allowed-tools`), which the directory refuses from an organization it has not verified, and no
manifest of ours declares a hook. No copy names our install script or
pipes a download to a shell anywhere (`plugin_zip.text_errors` and `plugin_branch.PIPE_TO_SHELL`,
which fail the build). No copy names a store in its commands.

**Installs always work from `main`; `latest` is the preferred install.** A
command that names no branch installs `main` as it is, so `main` keeps every
manifest, MCP config and the marketplace catalogs at its root, its catalogs list
the plugin at `./`, and nothing on `main` points an installer at another branch.
Development installs (`scripts/install/dev_install.py`) rely on that too. The
documented commands name `latest` where the app can name a branch, because it is
the plugin alone and never ahead of PyPI; Devin, Antigravity and Factory Droid find no
branch syntax and install `main` (Droid's `#ref` changes the plugin's name). `test_plugin_manifests.py` holds both halves
of the rule. Every copy is built and checked by
`tests/python/global/test_plugin_branch.py` and `test_plugin_zip.py` on every
pull request and again before each release (`plugin_branch.py --check`), the
directory's against claude.ai's file rules
(<https://claude.com/docs/plugins/pre-submission-checklist>).

What each built copy changes from `main`'s text, each change a strict substitution that fails
the build when what it replaces is not there exactly once:

| | `latest` | `codex-plugin` and the OpenAI ZIP | `claude-plugin` |
| --- | --- | --- | --- |
| Skills | as `main` | as `main` | as `main` |
| Codex's server line | as `main`: `uvx ... cad@<VERSION> mcp` in `codex.mcp.json` | the same, in `.mcp.json` | none: no MCP config |
| README's install section | uv's line and one paragraph | no README | the same as `latest` |
| `.claude-plugin/plugin.json` | as `main` | not shipped | without `documentationUrl`, `privacyPolicyUrl`, `supportUrl` and `termsOfServiceUrl`, which the directory's validation does not know; the README links the same pages |

`CAD_INSTALL_CHANNEL` and `CAD_AUTO_UPDATED`, which the configs of 0.11.11 and earlier set, are
no longer written and are ignored where an older copy still sets them.

**Dev note — `plugin` and `claude-plugin`.** `plugin`, which Cursor installs
cloned before `latest` existed, is no longer written; it stays at 0.7.14 until it
is deleted. claude.ai's listing stays on `claude-plugin` while a reviewer has the
plugin, since the portal refuses a tracked-branch change then. Moving it to
`latest` would hand the directory every other app's manifest and MCP config,
which it refuses from an organization it has not verified.

## Submitting the plugin to OpenAI

The plugin directory shared by ChatGPT and Codex takes plugins only through the
web portal at <https://platform.openai.com/plugins>. OpenAI documents no API or
CLI for uploading, submitting or publishing, so CD cannot do it and no secret is
involved. What CD does is build the file to upload: each GitHub Release carries
`cad-openai-plugin-<version>.zip`. It holds the plugin at the archive's root,
each folder with its own entry: `.codex-plugin/` (manifest and icons), `skills/`,
`LICENSE`, and every file the manifest points at. (The portal turned away 0.7.6's
first ZIP, one top-level `cad/` folder with no directory entry of its own, as
holding no plugin.) The portal requires `mcpServers` to resolve to a root
`.mcp.json`, so a server config the checkout keeps under another name is
archived as `.mcp.json`, and the archived manifest points there. That config is
the repository's `codex.mcp.json` as it is: `uvx ... cad@<VERSION> mcp`, Codex's
startup timeout (`startup_timeout_sec`), and no environment.

For each release, a person with the access below:

1. Downloads `cad-openai-plugin-<version>.zip` from the release page.
2. On the Plugins page, opens the text-to-cad plugin, selects **Upload plugin
   to make changes**, and uploads the ZIP. The first submission uses **Upload
   new or existing plugin** instead.
3. Resolves the automated findings, selects **Submit for review**, and completes
   the policy attestations.
4. After approval, selects **Publish plugin**.

OpenAI's directory lists text-to-cad twice: an old listing still at 0.7.10, and the
[current one](https://chatgpt.com/plugins/plugins_6ac32e7e1a74819193e1edd581a99966?open_in_app).
Until OpenAI merges them, upload each release's ZIP to both, so the old listing's users
move to the current release too.

One-time setup, in the OpenAI Platform organization that owns the plugin:
complete individual or business verification under
<https://platform.openai.com/settings/organization/general>. Submitting needs an
organization owner, or a member granted **Apps Management Write**
(`api.apps.write`).

`python3 scripts/release/plugin_zip.py --check` runs the same checks locally;
`--out PATH` also writes the ZIP. `tests/python/global/test_plugin_zip.py` runs
them on every pull request that touches the plugin. The checks are the portal's
documented package rules
([submission errors](https://developers.openai.com/plugins/deploy/submission-errors)),
with the final-submission listing limits, such as 30 characters for the name and
subtitle. A missing `interface.logo` or `interface.composerIcon` is a warning,
not an error, but the portal refuses the upload without them. The portal's own
skill and policy scans still run after upload.

## The version feed

`api.texttocad.dev/v1/releases` (`apps/api/src/versions.mjs`) names `latest`: the newest release on
PyPI that has been there for at least an hour and is not held back; and `lines`, the newest such release
of each major version. Releases 0.7.12 to 0.11.11 read `api.texttocad.dev/v1/versions` instead, which
names `latest` alone and, under the same rules, the newest such release below 0.12.0. It says when: cad's
automatic update begins when the feed names a release of the installed major newer than the one installed
(`cad_server/updates.py` reads it, at most once an hour), and also where the feed names none of the installed
major (no `lines`, or no line for it) while its `latest` is of a higher major, counted by that `latest` and bounded
by its tries; either way the update installs PyPI's newest of the installed major
(`uv tool install --upgrade "cad>=<installed>,<<next major>"`). The install command, `cad update`, the plugin's server
line and the skills' `uv tool install cad` read no feed: they take PyPI's newest (`cad update` and the server line,
of the installed major). So holding a release back
(`CAD_HELD_RELEASES`, an environment variable of the Vercel project, then `gh workflow run
deploy-api.yml --ref main`) stops automatic updates only on computers already on the feed's release;
to pull a release from everyone, yank it on PyPI. The releases 0.10.0 to 0.11.11 install the release
`/v1/versions` names, so the newest 0.11.x carries them over. The feed reads the index of `cadgen`, the last of the four projects a release
uploads, so a release it names is installable under every name. Telemetry passes through the same API to PostHog:
a deploy (`Deploy API`, on every change to `apps/api` on `main`) needs the project's PostHog
settings in Vercel, which `/v1/health` checks (`apps/api/README.md`). A release that sends a new
telemetry schema carries the receiver that reads it, deployed by its merge: until that deploy is
live, the receiver answers the new schema's batches "try later" (503) and the senders keep them, so
check that `Deploy API` succeeded after the merge.

## Resuming and republishing

A run that stopped — say the upload went through and the branches push failed —
is finished by dispatching it:

```bash
gh workflow run release-publish.yml --ref main            # or -f publish=false for a draft
```

That publishes the commit on `main` that last moved `VERSION` — the release
commit, not whatever merged after it — if that version has no tag yet. The
release commit holds the pull request's tested tree, so its record is found and
nothing is tested again (a run that tested a commit itself records it inside
its own run, which does not count, so a resume of one tests again). A dispatch
uses the workflow file on `main`, so a fix to `release-publish.yml` itself
applies to the resume; a fix anywhere else in the tree ships with a new bump,
since the resume builds the release commit as it was. The PyPI upload is
idempotent. A version whose tag exists skips at the gate. A failed docs deploy
is redeployed on its own (see
[Redeploying the docs site](#redeploying-the-docs-site)).

## Rehearsing on `build-test`

`build-test` is a long-lived branch whose only job is to run `Publish Release`
without side effects: there it builds and installs, uploads and pushes nothing,
and prints what it WOULD have uploaded, deployed and tagged
(`publish-github-release.sh --dry-run`). To rehearse a release, reset the
branch, open a bump against it, and merge that:

```bash
git push --force origin main:build-test     # build-test is throwaway; a past rehearsal leaves it ahead
gh workflow run release-prepare.yml --ref main -f bump=patch -f target=build-test
```

Or bump a branch of `build-test` by hand
(`bump-version.sh patch --base origin/build-test`) and open its pull request
against `build-test`. The gate compares the rehearsal's `VERSION` against the
repository's REAL tags, exactly as `main` would: a rehearsal bump passes the
gate and exercises everything. A rehearsal consumes that version number on
`build-test` only; `main` and the tags are untouched, so the real release
re-uses it.

## Redeploying the docs site

`Deploy Docs` (`.github/workflows/deploy-docs.yml`) redeploys without a
release, from a ref that defaults to `main`:

```bash
gh workflow run deploy-docs.yml -f ref=main
gh workflow run deploy-docs.yml -f ref=v0.5.0  # a past release: its tag
```

`Deploy API` (`.github/workflows/deploy-api.yml`) deploys `api.texttocad.dev`
on every change to `apps/api` on `main`, and redeploys `main` on dispatch
(`gh workflow run deploy-api.yml`). It follows no release.

## Local and manual fallbacks

After bundling, `scripts/release/check-wheel-contents.sh` builds from a clean
temporary package copy and verifies that every bundled runtime file is present
with identical bytes, with no obsolete assets left in the wheel. It leaves the
checkout's build scratch untouched. Set `CAD_WHEEL_OUT_DIR` and
`CAD_KEEP_WHEEL=1` to retain that checked wheel for an installed smoke test.

To check a bump locally the way the gate and the version check will:

```bash
git fetch --tags origin
scripts/release/check-version.sh --incremented-from "refs/tags/$(source scripts/release/release-tags.sh && latest_release_tag)"
node scripts/release/sync-version.mjs --check
```

`scripts/release/publish-github-release.sh` is the manual fallback for the tag
and GitHub Release step. Unlike `Publish Release`, the script creates a
draft release unless `--publish` is passed.

## Repository settings

`main` requires a PR with one status check, `CI` ([the gate](testing.md#ci): every `Test`
job that ran passed) — strict (up to date with `main`), squash merges only, a
linear history, no force pushes and no deletions. No other check is required, so
a job is added, renamed, split or sharded in `test.yml` without a
branch-protection change; a job its selection skips passes the gate, so a prose
pull request merges on `static` and `CI`. The other side of one required check:
a pull request that removes a job from `test.yml`, or from `CI`'s `needs`, still
merges green, where a removed required job used to block. Review a change to
`test.yml`, `ci_gate.py` or the selector as a change to what protects `main`
(`test_ci_workspace_selection.py` holds that `CI` needs every job), and require
`CI` from GitHub Actions as its source. Strict up-to-date is what makes a
merged tree the tree its pull request's run tested, so the push run and
`Publish Release` find that run's record and test nothing again; a merge that is
not up to date is still tested, by both.
`PREPARE_RELEASE_TOKEN` is a personal access token, so that the release pull
requests `Prepare Release` opens start their checks. It needs Contents and Pull
requests write on this repository; nothing merges with it, so it need not be an
admin's.
PyPI is published to from one place. The `pypi` job runs in the GitHub environment
`release`, whose deployment branches are `main` alone, and the trusted publisher of each
of the four projects on PyPI (`cad`, `cad-server`, `cad-mcp`, and the deprecated alias `cadgen`) names this repository, `release-publish.yml` and that environment, so no
run on another branch (or a workflow changed on one) can mint a token PyPI takes. A
project PyPI does not have yet takes a pending publisher, the same three names, before
its first release. No other
job asks for `id-token`. `build-test` is protected as `main` is (a pull request to
change it, no force pushes or deletions): a push there runs `Publish Release`, and
its irreversible steps are skipped by the workflow, not by who may push. The
install branches, `latest`, `claude-plugin` and `codex-plugin`, have two rulesets. Install
branches refuses their deletion and any force push, from anyone. Install
branches: release only lets only a deploy key update them, so `Publish Release`
is their only writer: it pushes them with its own write deploy key, whose private
half is the `INSTALL_BRANCHES_KEY` secret, and anyone else's push is refused, an
admin's or an agent's with an admin's credentials included. Its gate stops a
release on `main` that lacks the secret, before the PyPI upload. GitHub allows no
exception for the workflow's own token on a personal account's repository. To
replace the key, add a new write deploy key, set the secret to its private half,
then delete the old key. A deploy key cannot be limited to some branches: its write access is
to the whole repository, and the rulesets are what keep everyone else off the install branches
(the deploy key is their one bypass). A new install branch needs both rulesets extended to it
before its first release, the owner's change once in the repository's settings (for
`codex-plugin`, before the release that first writes it): without it the branch is not protected,
though the release's push still succeeds. The source map upload needs three more secrets, which the
gate checks the same way: `POSTHOG_CLI_API_KEY`, a PostHog personal API key scoped to
the telemetry project with `error_tracking:write` alone (not the receiver's, which
lives in Vercel); `POSTHOG_CLI_PROJECT_ID`; and `POSTHOG_CLI_HOST`
(`https://us.posthog.com` or `https://eu.posthog.com`). Keep
the repository tag ruleset (extend its pattern to cover `v[0-9]*.[0-9]*.[0-9]*`
beside the bare form) and immutable releases.

Dependency updates arrive as Dependabot PRs (`.github/dependabot.yml`: weekly,
one grouped PR per ecosystem for minor + patch bumps, labelled `dependencies`
so they land in the release notes' Maintenance category).

## Source-tree history

Before 0.5.0, `main` held a generated publish tree copied from `develop`.
The source-tree cutover landed on 2026-09-04 in commit `3eb1f9b8a`; the
original granular source history remains at `history/0.5.0-source`.
The old publish transformation and mirror workflow are retired. Use the
current release workflow above for future releases.
