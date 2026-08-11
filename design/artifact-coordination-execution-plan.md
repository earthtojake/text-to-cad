# Execution plan: unify render-artifact generation coordination

**Audience: an implementing agent.** This is a work order, not a discussion. Each step is
self-contained — you can start a fresh session at any step and only read that step plus §A–§C.

Companion doc (rationale, evidence, measurements): `design/artifact-generation-coordination.md`.
You do **not** need to read it to execute this plan.

Baseline: `release/0.4.0` at `56a119c0`. All line numbers are from that commit — **re-grep
before editing**, do not trust them blindly after step 1 lands.

---

## §A. Ground rules — read before every step

1. **Base branch is `release/0.4.0`, NOT `develop`.** AGENTS.md's usual "branch from `develop`" rule
   does not apply to this work: the entire coordination system exists only on `release/0.4.0`
   (`packages/cadgen/src/cadgen/_internal/generation_status.py` is **absent** on `develop`, which is
   225 commits behind). Branch from and target `release/0.4.0`. Never push `main`, never open a PR
   to `main`. Note that CI does not run on release-branch PRs — run the checks locally.
2. **Do not edit `VERSION`** or any package/plugin/lockfile/`pyproject.toml` version. Ever.
3. **Follow symlinks.** `viewer/packages/cadgen`, `skills/cad/scripts/packages/cadgen`, and
   `skills/dxf/scripts/packages/cadgen` are symlinks to `packages/cadgen` in the dev layout.
   Edit `packages/cadgen/...` — the real source. Never edit through the symlink path.
4. **After ANY change under `packages/cadgen/`**, before committing:
   ```bash
   scripts/bundle/bundle.sh && scripts/bundle/bundle.sh --check
   ```
   Then restore the dev symlink layout if you continue working:
   ```bash
   scripts/dev/setup-symlinks.sh --check || scripts/dev/setup-symlinks.sh
   ```
5. **One step = one commit = one PR.** Do not batch steps. Do not start step N+1 before step N's
   verification passes.
6. **If reality does not match this document — STOP and report.** Do not improvise a different
   fix. The line numbers may drift; the *described behavior* should not. If a "before" snippet
   is not there, say so and stop.
7. **Do not write artifacts outside `models/`.** Scratch files go in `tmp/` or `/tmp`.
8. **Do not relax `scripts/github-workflows/check-builds.sh`'s no-symlink assertion.**

### Environment

This worktree has **no `.venv`**. `scripts/test/common.sh` falls back to bare `python3`, which
has no OCP and will fail every CAD test. Export the main checkout's interpreter first:

```bash
export PYTHON_BIN=/Users/jakefitzgerald/robots/text-to-cad/.venv/bin/python
```

Every `scripts/test/*.sh` invocation below assumes that variable is set.

---

## §B. The problem in one paragraph

Artifact builds coordinate across processes (CLI `cad gen` vs. the CAD Viewer) through a
`fcntl.flock` sentinel plus a JSON progress sidecar beside each model's `__cadgen__` package
directory. The producer half lives in `packages/cadgen/src/cadgen/_internal/{generation_status,progress}.py`;
the reader half is a **hand-written copy** in `viewer/server_py/artifact.py`, kept in sync only by
`tests/python/global/test_viewer_cadgen_mirror.py`. Four independent producers each decide for
themselves whether to lock, one of them doesn't, the freshness gate runs outside the lock on the
viewer's path, the progress record has no run identity, and the reader probes with the wrong lock
mode. Result: builds that are invisible to the other process, duplicate concurrent builds into one
directory, progress bars that show a dead run's position and then jump backwards.

**Seven confirmed defects, referenced throughout as D1–D7:**

| ID | Defect | Fixed in step |
|---|---|---|
| D1 | `build_package_from_compound` rewrites a package holding no lock | 6 |
| D2 | Client POSTs a build when the server said `generating`; server builds after its own timeout | 7, 8 |
| D3 | Queued build blocks untimed inside the process-global worker lock, freezing all other models | 7 |
| D4 | `build_step_artifact`'s "already current" fast path is dead code (`.is_file()` on a directory) | 2 |
| D5 | No post-lock freshness re-check on the viewer's build path | 5 |
| D6 | Progress sidecar has no run identity; a dead run's payload is served as live progress | 4, 5 |
| D7 | Reader probes with `LOCK_EX`, so concurrent probes report a phantom build | 4, 7 |

---

## §C. Target design (reference — steps 4+ implement this)

### On-disk protocol

Three hidden siblings of the artifact's output directory, under gitignored `__cadgen__`.
For package dir `<folder>/__cadgen__/models/<name>.step`:

| File | Purpose |
|---|---|
| `.<name>.step.generation.lock` | **Writer** sentinel. `LOCK_EX` held while mutating the output dir. **Path and name unchanged from today** — a mixed-version pair (old bundled skill + new viewer) must still mutually exclude. Now carries the holder's `runId` as its payload. |
| `.<name>.step.generator.lock` | **New.** Held by anything running the model's generator *without* writing its package (exports, on-demand topology extraction). A writer holds **both**, writer first. |
| `.<name>.step.generation.progress.json` | The status record. Never unlinked (its terminal record carries `stageMs` to weight the next build's bar). |

> **Deviation from the original design, applied in step 3.** The record was going to be
> renamed to `.generation.status.json`. It is **not** renamed: the v2 schema is a strict
> superset of v1, so keeping the filename means a reader that predates this work goes on
> working unchanged while producers migrate. Renaming would have opened a window — between
> the producer cutover (step 4) and the reader cutover (step 6) — in which the viewer showed
> `generating` with no progress bar, which matters because each step is meant to be
> independently shippable. The filename buys nothing functionally; `runId` is what fixes D6.

### Status record, schema v2

```json
{ "schemaVersion": 2,
  "runId": "3f9c...",        // uuid4 hex, minted at lock acquire
  "pid": 13679, "host": "...",
  "kind": "step-package",     // ArtifactKind.name
  "intent": "write",          // "write" | "generate"
  "startedAt": 1785940824670,
  "outcome": null,            // null=running | "done" | "failed" | "skipped"
  "phase": "components", "label": "Meshing components", "detail": "",
  "done": 31, "total": 50, "determinate": true,
  "ratio": 0.77, "ratioFloor": 0.62, "ratioCeiling": 0.94,
  "phaseStartedAt": 0, "phaseExpectedMs": 0, "updatedAt": 0,
  "stageMs": null }           // populated ONLY when outcome == "done"
```

Three invariants — these are the whole point, do not compromise them:

1. **A `starting` record is written synchronously inside acquire**, before any work and before
   yielding. The sidecar can therefore never describe an older run while the lock is held.
2. **A reader attributes a record only when `record.runId == sentinel runId`.** This is
   *attribution*, never *liveness* — the kernel stays the sole authority on "a run is in flight".
3. **`stageMs` is written only on `outcome == "done"`.** A failed run must not teach the next
   build's bar from partial stage times.

A reader seeing `schemaVersion != 2` reports **no progress** but still reports `generating` from
the lock.

### API

```python
from cadgen.coordination import artifact_build, generator_busy, snapshot, Contended

# PRODUCER — owns lock + progress + the post-lock freshness re-check
with artifact_build(STEP_PACKAGE, package_dir,
                    is_current=lambda: _package_is_current(spec),
                    force=force) as run:
    if run.skipped:              # is_current() re-evaluated UNDER the lock
        return existing_payload()
    run.phase(PHASE_GENERATE)
    ...
    run.advance()

# PRODUCER — generator busy, writes no package
with generator_busy(STEP_PACKAGE, package_dir):
    ...

# READER — one non-blocking snapshot, never creates files
snap = snapshot(package_dir)
# snap.state:    "idle" | "writing" | "busy"
# snap.run_id:   str | None
# snap.progress: dict | None   (only when record.runId == sentinel runId)
# snap.degraded: bool          (no fcntl, or flock unsupported on this filesystem)
```

`artifact_build(kind, output_dir, *, is_current, force=False, deadline_ms=None)` does, in order:
acquire `LOCK_EX` (blocking by default; bounded and raising `Contended` when `deadline_ms` is
given) → mint `runId`, write it to the sentinel, emit the `starting` record → call `is_current()`
**under the lock**, set `run.skipped` → yield → write the terminal record → release.
`force=True` skips only the `is_current()` call, **never** the lock.

Probing is `LOCK_SH | LOCK_NB` on each sentinel, opened **read-only**. `LOCK_SH` cannot conflict
reader-with-reader (that is D7's fix), and read-only `open` means a status GET never materialises
a sentinel for a never-built model.

### Server state machine

| snapshot | freshness | reported state |
|---|---|---|
| `writing` | *not evaluated* | `generating` + progress + `runId` |
| `busy` | fresh | `ready` (annotated `busy: true`) |
| `busy` | stale | `needs-build` + `blocked: true` — client waits, does **not** POST |
| `idle` | fresh | `ready` |
| `idle` | stale, buildable code | `needs-build` |
| `idle` | stale, other code | `error` |

Two protocol rules:
- **`GET /__cad/artifact` never enqueues work.**
- **`POST /__cad/artifact` never blocks on a peer.** If the snapshot says `writing`, return
  `{"ok": true, "state": "generating", "runId": ...}` immediately.

---

# The steps

## Step 1 — Wire the viewer's Python tests into CI

**Nothing below this line is protected until this lands.** `viewer/server_py/tests/` contains **79
passing tests** including `test_artifact.py`, the only real lock coverage in the repo, and **no CI
job runs them**. `scripts/test/test-python.sh` runs only `tests/python/packages/cadgen`, the
per-skill dirs, and `tests/python/viewer/moveit2_server`.

The suite is already green — this step only wires it up. Verified before writing this plan:

```bash
PYTHONPATH="$PWD:$PWD/viewer" /Users/jakefitzgerald/robots/text-to-cad/.venv/bin/python \
  -m unittest discover -s viewer/server_py/tests -t viewer
# Ran 79 tests ... OK
```

**File:** `scripts/test/test-python.sh`

Add one line after the MoveIt2 line:

```bash
run_python_unittest "MoveIt2 server Python tests" "tests/python/viewer/moveit2_server" "viewer/moveit2_server"
run_python_unittest "CAD Viewer server Python tests" "viewer/server_py/tests" "viewer"
```

**Verify:**
```bash
PYTHON_BIN=/Users/jakefitzgerald/robots/text-to-cad/.venv/bin/python scripts/test/test-python.sh
```

**Done when:** the run reports the viewer server suite and it passes. If the suite needs a
different `PYTHONPATH` root than `viewer`, adjust that argument only — do not modify the tests.

**Do NOT:** change any test file in this step.

---

## Step 2 — Fix D4: the dead "already current" fast path

**This is not a concurrency change and it ships alone.** It removes a full `gen_step()` run from
*every* viewer-triggered build. Ship and measure before doing anything else.

**The bug.** `packages/cadgen/src/cadgen/step_artifact.py:188` `_current_artifact_for_spec` calls
`validate_step_topology_artifact(..., artifact_path=render_package_dir(spec.entry_path))`.
`render_package_dir()` returns a **directory** (`catalog.py:266-275`). `validate_step_topology_artifact`
(`step_targets.py:229-231`) gates on `resolved_artifact_path.is_file()`, which is False for every
directory → raises `missing_glb` → caught → returns `None`. The fast path can never fire.

The check *above* it — `_existing_topology_artifact_matches_spec_without_scene` — already handles
packages correctly via `_package_descriptor_matches_spec` (`generation.py:1219`). Its sibling
`step_artifacts.py` avoids the bug only because it guards with `is_assembly_package()` at
`step_artifacts.py:96` and routes assemblies elsewhere. `step_artifact.py` has no such guard.

**File:** `packages/cadgen/src/cadgen/step_artifact.py`

Replace `_current_artifact_for_spec` (currently at :188-203) with:

```python
def _current_artifact_for_spec(spec: EntrySpec) -> StepTopologyArtifact | None:
    if not _existing_topology_artifact_matches_spec_without_scene(spec):
        return None
    # A component-GLB package is a DIRECTORY, and validate_step_topology_artifact() gates on
    # `.is_file()` -- routing a package through it always raised missing_glb, so this whole
    # fast path was dead and every build re-ran gen_step(). The descriptor comparison above
    # (_package_descriptor_matches_spec) IS the package's freshness gate; there is nothing
    # further to validate here.
    from cadgen._internal.component_package import is_assembly_package, read_package_descriptor

    package_dir = render_package_dir(spec.entry_path)
    if is_assembly_package(package_dir):
        manifest = read_package_descriptor(package_dir)
        if not isinstance(manifest, dict):
            return None
        return StepTopologyArtifact(
            cad_path=spec.cad_ref,
            kind=spec.kind,
            source_path=spec.source_path,
            step_path=spec.step_path,
            artifact_path=package_dir,
            manifest=manifest,
        )
    try:
        return validate_step_topology_artifact(
            ResolvedStepTarget(
                cad_path=spec.cad_ref,
                kind=spec.kind,
                source_path=spec.source_path,
                step_path=spec.step_path,
            ),
            artifact_path=package_dir,
            require_selector=True,
        )
    except StepTopologyArtifactError:
        return None
```

All names used are already imported at the top of the file (`StepTopologyArtifact`,
`render_package_dir`, `ResolvedStepTarget`, `validate_step_topology_artifact`,
`StepTopologyArtifactError`). The `component_package` import is function-local to avoid a cycle —
that is the same pattern `generation.py:1233` uses.

**Add test** `tests/python/packages/cadgen/test_step_artifact_skip.py`:
`test_second_build_of_a_current_package_is_skipped` — build a small generated model twice via
`build_step_artifact`; assert the second call returns `skipped: True` and that `gen_step()` ran
**exactly once** across both (count by having the fixture generator append a line to a file).

**Verify:**
```bash
PYTHON_BIN=/Users/jakefitzgerald/robots/text-to-cad/.venv/bin/python scripts/test/test-python.sh
scripts/bundle/bundle.sh && scripts/bundle/bundle.sh --check
```

**Done when:** the new test passes, the full Python suite is green, and a manual second run of
`cadgen.step_artifact` on an unchanged model emits `"skipped": true`.

**Do NOT:** touch `step_targets.validate_step_topology_artifact` itself — other callers pass real
file paths to it and depend on the `.is_file()` gate.

---

## Step 3 — Create `cadgen.coordination`, move the primitives

**Architectural note you can rely on:** `viewer/server_py` **can** import cadgen directly. The
mirrored copy in `viewer/server_py/artifact.py` was never necessary. Evidence:
`packages/cadgen/src/cadgen/__init__.py` has **zero** module-scope imports (everything is deferred
through `__getattr__`); `viewer/requirements.txt` is exactly `--editable ./packages/cadgen`; and
`server.py:376` already hard-requires cadgen via `cadgen_bridge.require_cadgen_runtime()`. The real
constraint is *"the long-lived server process must never import OCP/build123d/ezdxf"* — a property
of the module, enforced by one CI assert (added below).

**New files** — stdlib only, no third-party imports, no cadgen imports outside `coordination/`:

```
packages/cadgen/src/cadgen/coordination/
  __init__.py    # the entire public API (re-exports from the modules below)
  paths.py       # lock / generator-lock / status paths derived from an output dir
  lock.py        # flock acquire + probe + degradation policy
  record.py      # schema v2: atomic write, typed read, runId attribution
  phases.py      # phase sets, weights, stage-time learning
  kinds.py       # ArtifactKind registry
```

**Move, do not copy**, the bodies of `_internal/generation_status.py` and `_internal/progress.py`.
Leave both old module paths as thin re-export shims for one release, so
`step_artifact.py:16-17`, `generation.py:39`, and the mirror test keep importing unchanged.

Implement per §C: `runId`, the `starting` emit inside acquire, `stageMs`-only-on-success, the
`LOCK_SH` read-only reader probe, `.generator.lock`, and `deadline_ms`/`Contended`.

**Also fix the degradation hole while you are here.** In today's `generation_status.py:83-92`,
the `try/except OSError` covers only `mkdir` and `open` — the `fcntl.flock` call itself sits
*outside* it. On a filesystem returning `ENOLCK`/`EOPNOTSUPP` (NFS, SMB, some Docker bind mounts)
that turns advisory coordination into a hard build failure. `lock.py` must catch `OSError` from
`flock` too and degrade to no-coordination, which is the policy the existing comment at `:87`
already claims.

**Add test** `tests/python/packages/cadgen/test_coordination_is_stdlib_only.py`: in a **fresh
subprocess**, `import cadgen.coordination`, then assert `"OCP" not in sys.modules`,
`"build123d" not in sys.modules`, `"ezdxf" not in sys.modules`, and that the import costs < 100 ms.

**Add test** `tests/python/packages/cadgen/test_coordination_probe.py`:
`test_concurrent_probes_do_not_report_a_phantom_build` — N threads × M probes of an **unheld**
sentinel, assert **zero** `writing` results. (Against today's `LOCK_EX` probe this fails at ~6 %.)

**Verify:**
```bash
PYTHON_BIN=/Users/jakefitzgerald/robots/text-to-cad/.venv/bin/python scripts/test/test-python.sh
scripts/bundle/bundle.sh && scripts/bundle/bundle.sh --check
```

**Done when:** the whole existing suite is green **without any call-site changes** (the shims make
this a pure refactor), plus the two new tests pass.

**Do NOT:** change `.generation.lock`'s path or filename. Rollout skew depends on it.

---

## Step 4 — Producer cutover

Rewrite each producer onto `artifact_build` / `generator_busy`. This fixes **D5** and the
lock-without-progress half of **D6**.

| File | Current | Change to |
|---|---|---|
| `packages/cadgen/src/cadgen/step_artifact.py:319-360` | pre-lock `if not force:` gate at :319, lock at :331, no re-check | one `with artifact_build(..., is_current=...)`; delete the pre-lock gate; return the existing payload when `run.skipped` |
| `packages/cadgen/src/cadgen/_internal/generation.py:1774-1791` | `_run_with_spec_generation_status` with its own `skip_if_current` | delegate to `artifact_build`; `skip_if_current` becomes `is_current` |
| `packages/cadgen/src/cadgen/dxf_artifact.py:94-110` | currency gate at :95 outside the lock; `load_drawing_descriptor` (:101) and `export_drawing_dxf` (:106) run **after** the lock is released; never reports progress | wrap the **whole body** in one `artifact_build` |
| `packages/cadgen/src/cadgen/step_export_target.py:120` | takes the model's **writer** lock while writing no package | `generator_busy(...)` |
| `packages/cadgen/src/cadgen/step_artifacts.py:407` | same | `generator_busy(...)` |
| `packages/cadgen/src/cadgen/interference.py:221` | same | `generator_busy(...)` |

The two producers must end up sharing one `is_current` predicate so they cannot diverge again.

**Add tests:**
- `test_queued_producer_finds_the_package_current_and_skips` — two **real subprocesses** ~0.3 s
  apart on a cold package; assert `gen_step()` ran exactly **once** across both and the loser
  returns `skipped`. (Today: two full generator runs.)
- `test_export_does_not_report_a_build` — hold `generator_busy`, assert a fresh model still
  reports `ready`, not `generating`.
- `test_dxf_build_reports_progress` — assert `snapshot()` returns a non-`None` progress record
  during a drawing build. (Today no DXF path writes a sidecar at all.)
- `test_failed_build_does_not_poison_stage_weights` — raise inside `artifact_build`, assert
  `stageMs` is absent from the terminal record.

**Warning about existing coverage:** `tests/python/packages/cadgen/test_generation_status.py:200`
("skip_if_current is evaluated under the lock") passes `generator_name="unknown-generator"`, which
makes `_track_spec_generation` return `track_generation_run(None)` — a `nullcontext`. It asserts
call ordering with **no lock in play**. Fix it to use a real generator name.

**Verify:** full Python suite + bundle check, as in step 3.

---

## Step 5 — Close D1: move the lock to the mutation boundary

`packages/cadgen/src/cadgen/_internal/component_package.py` contains **zero** lock references,
despite its own comment at `:724-726` claiming "Writers are serialized by the generation lock."
`step_artifacts.ensure_step_topology_artifact:130-139` reaches it unlocked, so a cold
`cad inspect` / `cad snapshot` build is invisible to the viewer and races a viewer-started build
in the same directory.

1. `build_package_from_compound` (`component_package.py:414`) begins with
   `require_write_lock(package_dir)` — **raises** under test/CI (`CADGEN_STRICT_LOCKS=1`), **warns**
   in production. This is the guard that stops a future producer from being added without a lock.
2. `step_artifacts.ensure_step_topology_artifact:130-139` wraps `_scene_for_regeneration` +
   `_generate_part_outputs` in one `artifact_build`.
3. Make the descriptor write atomic: `component_package.py:715` `write_text` → tmp + `os.replace`,
   matching every other write in that module. A reader can currently observe a truncated
   `assembly.json`.
4. Gate the orphan prune (`component_package.py:729-731`) behind a grace period — readers are
   lock-free by design, and the prune currently deletes `<cid>.glb` files a browser's in-flight
   descriptor still references.

**Add tests:**
- `test_package_write_requires_the_write_lock` — monkeypatch `build_package_from_compound` to probe
  the sentinel from a second fd; drive `ensure_step_topology_artifact` on a **cold** package (no
  `assembly.json` — that is the only branch that reaches it) and assert the lock is held.
- `test_cold_cli_inspect_reports_generating_to_a_reader` — run inspect in a subprocess, poll
  `snapshot()` from the parent, assert it observes `writing` at least once.

---

## Step 6 — Consumer cutover (delete the mirror)

**File:** `viewer/server_py/artifact.py` — delete `_GENERATION_LOCK_SUFFIX`,
`_GENERATION_PROGRESS_SUFFIX`, `_PROGRESS_PHASE_DONE` (`:49-54`), `generation_lock_path`,
`generation_lock_active`, `generation_progress_path`, `read_generation_progress`,
`await_generation_lock`, `_as_int`, `_as_float` (`:167-275`). Replace with
`from cadgen.coordination import snapshot`. This fixes **D7**.

**File:** `viewer/server_py/backend.py`
- `artifact_status:297-323` → the §C state table.
- `resolve_artifact:385-403` → return `generating` immediately when the snapshot says `writing`.
  **Delete** the `await_generation_lock` call at `:397` and the "timeout expired, build anyway"
  fallthrough at `:396-401`. This fixes **D2**'s server half and removes **D3**'s trigger.

Net: roughly 110 lines deleted, 35 added.

**Add test** `viewer/server_py/tests/test_backend_concurrency.py` (new; needs step 1):
- `test_post_does_not_build_while_a_peer_holds_the_lock` — subprocess holds the write lock; call
  `backend.resolve_artifact`; assert **zero** builds spawned and `state == "generating"`.
- `test_a_blocked_build_does_not_stall_other_models` — hold model A's lock from a subprocess, POST
  a build for A, then POST for model B; assert B completes within a bound.

---

## Step 7 — Client

**File:** `viewer/src/client/components/workbench/hooks/useArtifact.js:87-105`

Today it special-cases only `ready` and `error`; its own comment reads *"needs-build (or a build
already running) -> build"*. That is the D2 trigger.

- Add a third branch: `generating` → **attach**. Poll until the state leaves `generating`, then
  re-evaluate. **Never POST.**
- Only `needs-build` POSTs.
- The poll (`:63-79`) must read `state` and `runId`, not just `progress`.
- **Reset the bar when `runId` changes.** This is what stops the backwards jump at run handoff (D6's
  visible symptom).

While here, delete confirmed-dead surface in `viewer/src/client/workbench/stepArtifactStatus.js`:
`runStepArtifactGenerationWithRetries`, `validateGeneratedStepArtifactPayload`, and
`STEP_ARTIFACT_GENERATION_FAILURE_DISPLAY_THRESHOLD` have no production caller. Confirm with a
repo-wide grep before deleting.

**Add test** `viewer/src/client/components/workbench/hooks/useArtifact.test.js` — **no test file
for `useArtifact` exists anywhere in the repo**. Assert `generating` polls and never POSTs.

**Verify:**
```bash
npm --prefix viewer run test && npm --prefix viewer run build
```
Node 22 is required for the viewer build (the default v18 fails with a PostCSS "native binding"
error).

---

## Step 8 — Consolidate freshness (retires the last mirror)

Move the descriptor + closure validator into `coordination/freshness.py` (it is already stdlib on
both sides). Delete `viewer/server_py/source_hash.py` and `artifact._validate_render_package:102-164`.
Point `scanner.render_package_dir:68-72` at `coordination.paths` instead of re-deriving the path,
and point cadgen's `_package_descriptor_matches_spec` at the same function.

**Settle the symlink divergence here.** `cadgen.catalog.render_package_dir:274` calls `.resolve()`;
`viewer/server_py/scanner.render_package_dir:68-72` does a plain `dirname`/`basename` join. For a
symlinked **entry file** the two sides derive different package dirs, different sentinels, and
different packages — a permanent rebuild loop that never shows `generating`. The mirror test hides
this by calling `.resolve()` on the viewer's result before comparing (`:56`).
**Recommendation: `.resolve()` on both sides, plus an explicit test.** If you find evidence that
symlinked entry files are an unsupported layout, say so and stop — that is a product call, not
yours.

### Retire `tests/python/global/test_viewer_cadgen_mirror.py`

- After **step 6**: delete `test_generation_lock_paths_match` (`:82`),
  `test_generation_progress_paths_match` (`:92`),
  `test_generation_progress_round_trips_across_the_mirror` (`:101`) — both sides now call one function.
- After **step 8**: delete `test_render_package_dir_shapes_match` (`:53`) and the descriptor-constant
  tests (`:64`, `:74`). **Move** the closure-hash corpus (`:174-283`) — it is genuinely valuable — to
  `tests/python/packages/cadgen/test_coordination_freshness.py`.
- **Delete the file.** Its one irreplaceable job ("the viewer must not drag OCP into the server
  process") is now `test_coordination_is_stdlib_only.py` from step 3, which tests the actual
  invariant rather than a proxy for it.

---

## Step 9 — Generalize

Register `ArtifactKind` entries for `export` and `snapshot`:

```python
@dataclass(frozen=True)
class ArtifactKind:
    name: str                            # "step-package" | "drawing-package" | "export" | "snapshot"
    output_dir: Callable[[Path], Path]   # entry path -> the coordinated directory
    is_current: Callable[[Path], bool]   # THE one freshness predicate
    phases: tuple[str, ...]              # phase order for the bar
```

Replace the viewer's parallel per-format dict (`backend.py:274-285`) with a lookup into this
registry. Add `snapshot_many(dirs)` so `scanner.scan_cad_directory` can stamp in-flight state on
**every** catalog entry — today `scanner.py` is entirely lock-blind, so the file list cannot show
that a build is running.

---

## Out of scope — do not build these

- A job queue, build daemon, or cross-process scheduler. Two processes still race; they just race
  correctly.
- Any liveness inference: no pid checks, no heartbeats, no age windows. `runId` is for record
  *attribution* only. The current design gets this right and it must survive — the heartbeat
  approach was already tried and removed (see `generation_status.py:8-22`).
- Cancelling a running build. A *queued* waiter becomes bounded and abandonable; an OCP mesh
  already in flight is not interruptible.
- Cross-machine locking. `flock` is local-filesystem advisory locking.
- Changing the package layout, `assembly.json`'s schema, the content-addressed cid scheme
  (`component_package.py:123-133`), or the warm-worker architecture.
- Making the warm worker per-model. `worker_client.py:55/158` is one process-global `RLock` around
  every cadgen call; "POST never blocks" removes D3's trigger, but a genuinely long build still
  occupies the only worker. That is a real follow-up, deliberately **not** folded in here.

---

## Open questions — raise, do not decide alone

1. **Orphan prune vs. a live browser session.** How long may a stale tab keep fetching components
   from a descriptor it already loaded? Step 5 needs a number, a package generation id, or a
   two-phase prune.
2. **What replaces the 180 s wait, in UX terms.** Attaching to a peer's build is strictly better
   than forcing a duplicate, but it is unbounded — a hung generator leaves the user watching a
   frozen bar. The server side supports a force escape hatch (`force=true` bypasses `is_current`,
   never the lock); the UI affordance is undesigned.
3. **Symlinked entry files** (step 8) — supported layout or not?
4. **Degraded-coordination signalling.** Without `fcntl`, or on a filesystem where `flock` fails,
   or with an unwritable sentinel, both sides silently no-op today (reproduced: with a `0444`
   sentinel, two processes both entered the critical section). Proposal: keep degrading — a build
   must never fail because a lock is unavailable — but surface it via `snapshot().degraded`, one
   startup warning line, and a viewer banner. Confirm before building the banner.
