# PROTOTYPE — CoW worktree materialization benchmark (throwaway, do not ship)

Answers ticket
[01 — validate and benchmark the CoW materialization recipe](../../../../../.scratch/workspace-activation-speed/issues/01-cow-recipe-prototype.md):
does the clone → read-tree → refresh → reset → clean recipe work, and how fast is it
against plain `git worktree add`?

Run it (from the repo root):

```bash
pnpm --dir apps/emdash-desktop exec tsx tooling/prototypes/cow-worktree/run.ts
```

Flags: `--repo <path>`, `--synthetic <nFiles>`, `--keep`.

## Measured results (this repo, 2026-08-06, APFS, M-series Mac, ~208k entries incl. node_modules)

| Scenario | Total | Notes |
|---|---|---|
| Baseline `git worktree add` | 0.6–1.6s | no node_modules — deps need a full install (minutes) |
| Full snapshot, `cp -cR` engine | **58s** | userspace per-file clone is the bottleneck |
| Full snapshot, `clonefile(2)` engine | **8.1s** | kernel-recursive dir clone; git plumbing ≈ 1s of it |
| Full snapshot, clonefile + copied-index/`checkStat=minimal` | 9.6s | refresh drops 638ms → 36ms but reset pays it back; not worth it |
| Hybrid: `worktree add` + clonefile of node_modules only | **4.3s** | no index tricks, no clean step; simplest semantics |

Verification (all CoW scenarios): `git status --porcelain` empty afterwards despite a
dirty source checkout; node_modules survived and `tsx --version` runs from the cloned
tree; ignored artifacts kept by `git clean -fd`.

## What the numbers established

1. **The recipe is correct.** Dirty tracked files are reset, untracked strays cleaned,
   ignored artifacts kept, index healthy (steady-state `git status` ≈ 50ms).
2. **The clone engine decides everything.** `cp -cR` (per-file userspace clonefile) is
   ~12x slower than a kernel-recursive `clonefile(2)` on the directory. Node/libuv can
   do neither on macOS — a real implementation needs a tiny native helper (or shells
   out; the prototype's per-entry `python3` spawn adds ~2s of pure overhead to the
   clone step, so a native call would land near the raw 4.3s node_modules figure).
3. **The `checkStat=minimal` copied-index optimization is not worth it**: it moves cost
   from `update-index --refresh` (638ms → 36ms) into `reset --hard` (40ms → 832ms) for
   zero net win. The plain refresh recipe stands.
4. **The hybrid (checkout tracked via git, clone only ignored artifact dirs) is the
   fastest AND simplest**: no read-tree/refresh/clean, no dirty-source correction
   needed, ~4.3s of which 3.3s is the node_modules clone. Its open question is how to
   decide *which* ignored dirs to clone (fixed list? top-level ignored dirs from
   `git status --ignored`? setting?).
5. `clonefile(2)`'s man page discourages directory cloning (non-atomic vs concurrent
   writes) — same tearing risk we already accepted for level (c); tracked files are
   self-healing via the reset either way.
