# AGENTS.md

text-to-cad is a set of CAD skills for AI agents and the `cad` program they drive. Installing it
rather than developing it? Follow the Quickstart in [README.md](README.md).

This file is the index: what is where, the rules that hold everywhere, and which one document to read
before a change. Keep it that short. Detail belongs in the document a row below points at.

## What is where

| Path | What it is |
|---|---|
| `skills/` | The product: eight agent skills, each a `SKILL.md` and its references. They ship in the plugin as they are |
| `packages/cad/` | The one Python distribution, `cad`: the library (`src/cad`), the server and the `cad` command (`src/cad_server`), and the stdio transport agent apps start (`src/cad_mcp`) |
| `packages/core/`, `packages/ui/` | Shared JavaScript: `@cad/core` (no React) and `@cad/ui` (the viewer's components) |
| `apps/web/` | The CAD Viewer's React client, which the server serves |
| `apps/mcp/` | The CAD app the Codex app shows as tabs |
| `apps/docs/`, `apps/api/` | The docs site, and `api.texttocad.dev` (the version feed and analytics) |
| `models/` | Sample models, built by hand; no test reads them |
| `scripts/` | Durable repo commands, by purpose: `test/`, `bundle/`, `release/`, `install/`, `bench/` |
| `tests/` | Every test suite, grouped by what it tests; `tests/python/global/` holds the policy tests |
| `.claude-plugin/` and the other `.*-plugin/` folders, `codex.mcp.json`, `gemini-extension.json` | Plugin manifests: the repository root is the plugin |
| `VERSION` | The one release version; everything else is stamped from it |

## Read before you change

Read the one document for what you are changing, then the link it gives you. Not the tree.

| Changing | Read first |
|---|---|
| A skill | [Writing a skill](docs/contributing/writing-a-skill.md) |
| The library, the server or the `cad` command | [The design laws](packages/cad/README.md#the-design-laws), then the mechanism: the [engine](packages/cad/src/cad_server/engine/README.md), the [server](packages/cad/src/cad_server/README.md) or the [transport](packages/cad/src/cad_mcp/README.md) |
| A document type or an integration | [Adding a document type](docs/contributing/adding-a-document-type.md), [adding an integration](docs/contributing/adding-an-integration.md) |
| An environment variable | Law 31: declare it in `cad._internal.environment` first, and prefer not to add one |
| The CAD Viewer or shared JS | [apps/web](apps/web/README.md), [packages/ui](packages/ui/README.md) (its `docs/settings-ui.md` binds every settings control), [packages/core](packages/core/README.md) |
| The CAD app | [apps/mcp](apps/mcp/README.md) |
| The docs site or the API | [apps/docs](apps/docs/README.md), [apps/api](apps/api/README.md) |
| A test or a CI job | [Testing](docs/contributing/testing.md) |
| Install, update or plugin distribution | [Decisions](docs/contributing/decisions.md), [docs/install.md](docs/install.md) |
| A release, a version, the install branches | [Releases](docs/contributing/releases.md) |
| A script | [scripts/README.md](scripts/README.md) |
| A sample model | [models/README.md](models/README.md) |
| The trust boundary | [SECURITY.md](SECURITY.md) |
| Your checkout: setup, worktrees, testing in agent apps | [CONTRIBUTING.md](CONTRIBUTING.md) |

## Rules that hold everywhere

**Branches and releases**

- Branch from `main` and open pull requests against it; never push `main`. Never commit to `latest`,
  `claude-plugin` or `codex-plugin`: a release writes them.
- A pull request that changes `VERSION` is a release, and merging it ships it to every computer. Never
  bump it during other work, never pick the bump yourself (ask: patch, minor or major), and merge a
  release only on the user's explicit word. Never hand-edit a stamped version.
- A `cad` command, option or tool the skills used keeps working for 30 days after they stop using it,
  hidden if need be. A breaking change comes with a migration guide.

**Skills**

- A skill teaches a tool and how to check work done with it. Its `SKILL.md` has a size budget, and a
  line is added only for something an agent got wrong without it, with the evidence in the pull
  request. A change to what a skill tells agents to do is tested A/B before it ships.
- A skill runs plain `cad` commands with no version, installs nothing, ships no scripts and imports no
  other skill.
- Claude Code, Codex and Cursor are first-class: a change to the skills, the plugin, the server or the
  CAD app keeps all three working.

**Code**

- No superficial wrappers (law 29): add a helper or a command only where something is missing without
  it. What a tool already does is used as the tool's own.
- cad knows no app and no skill: knowledge of agent apps lives in the plugin and
  `scripts/install/install.py`.
- Markdown inside `packages/cad` refers to nothing outside that package (law 14).
- `packages/core` has no React; apps never import each other, and shared packages never import apps.
- The Python floor is `requires-python` in `packages/cad/pyproject.toml` and nowhere else.
- Where a law or a guide does not fit what you are adding, do not force it: say which and why in the
  change, and amend it there.

**Tests**

- Every test runs in CI; one that no job runs is wired in or deleted. No manual-only gates.
- A test makes its own fixtures in a temporary folder with its own server. It never reads `models/`.
- Test a contract once, at the cheapest level that exercises the real path. Await the condition,
  never a fixed sleep. A flaky test is fixed or deleted, never retried.
- Benchmarks under `scripts/bench/` are run by hand, and their output is never committed.

**The tree**

- Git holds source only: no CAD or mesh files, no built runtime (`_runtime/` is built by
  `scripts/bundle/bundle.sh`), no symlinks, no Git LFS, no file over 5 MiB.
- Installs work from `main`: every manifest and MCP config stays at the repository root, and nothing
  on `main` points an installer at another branch
  ([the install branches](docs/contributing/releases.md#the-install-branches)).
- `scripts/` is for durable commands; one-off helpers go in `tmp/`.
- The README and the docs site's homepage share their structure and copy: change them together.
- Keep documents current in the change that makes them stale, and keep them short.

## Working here

```bash
uv sync                      # the Python environment, from uv.lock
npm ci                       # the JavaScript workspaces
scripts/bundle/bundle.sh     # the viewer and CAD app pages the server serves (needed to open a model's page)
```

Run a server of your own, never one you did not start, with these set in every command:

```bash
export CAD_ENGINE_DIR=$PWD/tmp/cad/engine CAD_STATE_DIR=$PWD/tmp/cad/state \
       CAD_CACHE_DIR=$PWD/tmp/cad/cache CAD_UPDATE_CHECK=0
```

In a worktree, use the skills under that worktree's `skills/`, not ones installed from another checkout.

## Checks

Run the smallest check that covers the change, then the broader one before hand-off.

| Changed | Run |
|---|---|
| Anything, before the first push | `scripts/test/test-global.sh` (policy tests, under a minute) |
| Python | `scripts/test/test-python.sh <test files>`; `--select cadgen\|viewer\|skills\|all` for a suite |
| Shared JS or the viewer | `npm run build:packages`, then `scripts/test/test-js.sh --select core\|ui\|web\|mcp\|all` |
| What the bundlers consume | `scripts/bundle/bundle.sh --check` |
| The docs site, the API | `npm --prefix apps/docs run check`, `npm --prefix apps/api test` |
| A skill's behaviour | `scripts/bench/skill_ab.py` ([Writing a skill](docs/contributing/writing-a-skill.md#test-a-change-ab)) |
| Everything | `scripts/test/test.sh` |

CI runs one job per concern, only where a change reaches it; `main` requires the single check `CI`.
