---
name: sync-upstream
description: Rebase current feature branch onto latest upstream/develop. Syncs the fork's develop branch first, then rebases. For the earthtojake/text-to-cad fork workflow where CONTRIBUTING.md designates develop as the PR target.
---

# Sync fork with upstream

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

## How it works

Syncs `origin/develop` → `upstream/develop` (fast-forward), then rebases the
**current feature branch** on top. Three refs touched in order:

1. `git fetch upstream` → get latest upstream/develop
2. `git checkout develop && merge --ff-only upstream/develop && push` → sync fork base
3. `git checkout - && rebase develop` → replay feature commits onto new base

The upstream repo uses `develop` as the PR target per CONTRIBUTING.md.

## Prerequisites

```bash
# Verify before starting:
git remote -v | grep upstream      # upstream must exist
git rev-parse --abbrev-ref HEAD     # should NOT be develop or main
git status --porcelain              # must be empty
```

## Workflow

### Step 1 — Fetch upstream

```bash
git fetch upstream
```

### Step 2 — Fast-forward origin/develop

```bash
git checkout develop && git merge --ff-only upstream/develop && git push origin develop
```

`--ff-only` prevents accidental merge commits. If it fails, someone pushed
directly to your fork's develop — fix manually before continuing.

### Step 3 — Rebase feature branch

```bash
git checkout - && git rebase develop
```

Conflict resolution: `git rebase --continue` after each resolved file,
`git rebase --abort` to cancel entirely.

### Step 4 — Force-push (only if branch was already on origin)

```bash
git push --force-with-lease origin HEAD
```

`--force-with-lease` rejects if someone else pushed to this branch.
If it fails, `git fetch origin HEAD && git log --oneline origin/HEAD..HEAD` to
see what diverged, then coordinate with collaborators.

## Verification

```bash
# develop is identical to upstream
git rev-parse develop upstream/develop    # same hash

# feature branch only has your commits (no duplicates)
git log --oneline develop..HEAD            # your commits, clean
```

## When NOT to use

- **Shared feature branches** — rebase rewrites history others depend on.
  Use `git merge develop` instead.
- **`--ff-only` fails on develop** — origin/develop diverged from upstream/develop.
  Fix before rebasing your feature branch.
