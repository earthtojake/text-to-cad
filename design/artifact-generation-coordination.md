# Render-artifact coordination: investigation + unification plan

Status: design / proposal. Read-only audit of `release/0.4.0` at `56a119c0`; no code changed.

The coordination system audited here is ~1 week old: the `fcntl.flock` lock landed in
`fffe46dd` (2026-07-30, "Make the generation lock real") and the progress sidecar in
`76316513` (2026-07-31). The defects below are rough edges in new code, not long-standing rot.

**Verification status.** Eight defects were confirmed by adversarial review; D1, D2, D4, D7
and the two architectural premises in §0 / §4-Step-0 were additionally re-verified by hand:

- **D1** — `component_package.py` contains no lock reference of any kind (`grep flock|track_generation_run|generation_lock` → no matches).
- **D2** — `useArtifact.js` special-cases only `ready` and `error`; its own comment reads "needs-build (**or a build already running**) -> build".
- **D4** — `render_package_dir()` returns a directory; `validate_step_topology_artifact` gates on `.is_file()`, which is False for every directory, so the fast path cannot fire.
- **D7** — reproduced: 4 threads × 4000 probes of an **unheld** sentinel → **945/16000 (5.91 %)** false `generating` reports; the proposed `LOCK_SH` probe → **0/16000**.
- **§0** — `packages/cadgen/src/cadgen/__init__.py` has **zero** module-scope imports (all deferred via `__getattr__`), and `viewer/requirements.txt` is exactly `--editable ./packages/cadgen`.
- **§4 Step 0** — `scripts/test/test-python.sh` runs only `tests/python/packages/cadgen`, `tests/python/skills/<skill>`, and `tests/python/viewer/moveit2_server`; `viewer/server_py/tests/` is run by nothing.

Items explicitly flagged as *unverified* in §1 and §6 remain so.

---

## 0. The architectural question, settled first

**Can `viewer/server_py` import a shared coordination module directly, or must the hand-mirrored copy in `viewer/server_py/artifact.py` exist?**

**It can import directly. The copy is unnecessary and has never been necessary.** The stated constraint is misstated in the code itself.

The claim, verbatim, in two places:

- `tests/python/global/test_viewer_cadgen_mirror.py:3` — "viewer/server_py must stay importable WITHOUT cadgen/OCP installed"
- `viewer/server_py/source_hash.py:3-5` — same claim, "and cadgen is discovered per-request (see `cadgen_bridge.cadgen_pythonpath`) rather than being on the server's `sys.path`"

Evidence that it is false as applied to the product:

1. **The viewer refuses to start without cadgen.** `viewer/server_py/server.py:376` and `start_viewer.py:90` call `cadgen_bridge.require_cadgen_runtime()`, which raises `RuntimeError` unless a child process can execute `import OCP; import build123d; import cadgen.step_artifact` (`cadgen_bridge.py:28-32`, `106-118`). "Importable without cadgen" is true of the module in isolation and false of every running server.
2. **cadgen is installed into the server's own interpreter.** `viewer/requirements.txt` is one line: `--editable ./packages/cadgen`. Verified in this checkout: `.venv/bin/python -m pip show cadgen` → installed, and `import cadgen` resolves to `packages/cadgen/src/cadgen/__init__.py` with an empty `PYTHONPATH`.
3. **The dev launcher additionally puts cadgen on the server process's own `sys.path`.** `viewer/scripts/start-viewer.mjs:16` builds `baseEnv = cadPythonEnv(repoRoot)`, and `viewer/scripts/cad-python.mjs:82-85` appends `scripts/packages/cadgen/src`, `viewer/packages/cadgen/src`, `packages/cadgen/src` to `PYTHONPATH`. Line 24 spawns `python -m server_py.start_viewer` with that env. `cadgen_bridge.cadgen_pythonpath()` is for *children*; the launcher already covers the parent.
4. **The published skill is the same.** `scripts/bundle/skills/bundle-cad-viewer.sh:361-363` writes `--editable ./packages/cadgen` into the shipped runtime's `requirements.txt`, and line 395 `sync_dir "$VIEWER_DIR/packages" "$target_dir/packages"` rsyncs a **real** (non-symlink) copy of `packages/cadgen` into it. `skills/cad-viewer/requirements.txt` is `--editable ./scripts/viewer/packages/cadgen`.
5. **The import is free and pulls no OCP.** Measured on the repo venv:

   ```
   import cadgen                              0.4 ms
   import cadgen._internal.generation_status  13.3 ms
   import cadgen._internal.progress           20.9 ms
   OCP loaded? False   build123d? False   numpy? False
   ```

   `packages/cadgen/src/cadgen/__init__.py` has **zero** module-scope imports — everything is deferred through `__getattr__` (line 17-44). `generation_status.py` imports only `contextlib/os/threading/pathlib/fcntl`; `progress.py` only `contextlib/json/math/os/time/dataclasses/pathlib`.

**The real constraint is "the long-lived server process must never import OCP/build123d/ezdxf" — not "must never import cadgen."** That is a property of the *module*, and it is enforceable with one CI assertion (`"OCP" not in sys.modules` after import), which is strictly stronger than the current arrangement where the property is protected by a policy comment plus a test that compares path strings.

**Decision: put the shared layer at `packages/cadgen/src/cadgen/coordination/` — a public, stdlib-only subpackage of cadgen.** Not a new `packages/cadcoord`. Rationale: cadgen is *already* the vendored shared-runtime package for every consumer (`viewer/packages/cadgen`, `skills/cad/scripts/packages/cadgen`, `skills/dxf/scripts/packages/cadgen` — symlinks in dev, real copies in the published tree), so AGENTS.md's "shared runtime helpers live under `packages/` and are vendored into each consuming skill runtime" is satisfied with **zero new plumbing**: no new bundle target, no new `pyproject.toml` to version-stamp (AGENTS.md forbids hand-editing those anyway), no `pin-cadgen-requirements.sh` change, no `test_skill_self_containment.py` change. A new package would buy a structural no-OCP guarantee that a one-line test buys just as reliably. If cadgen's import graph ever becomes non-lazy at module scope, split `coordination/` out into `packages/cadcoord` then — AGENTS.md explicitly sanctions that ("Create lightweight shared Python packages under `packages/` when a helper should not inherit heavier package dependencies").

---

## 1. What's broken

Ordered by user impact. **[S1]** = the reported symptom "status/progress not communicated across processes"; **[S2]** = "multiple processes hooking into one generation triggers bugs".

| # | Defect | Where | What the user sees |
|---|---|---|---|
| **D1** | `ensure_step_topology_artifact` rewrites the entire render package holding **no lock** and writing **no progress**. | `packages/cadgen/src/cadgen/step_artifacts.py:130-139` → `_generate_part_outputs` → `component_package.build_package_from_compound` | **[S1][S2]** A cold `cad inspect` / `cad snapshot` build is completely invisible to the viewer: the lock probe finds nothing, so the viewer reports `needs-build`, never `generating`, no bar — and then starts a *second* full OCP build into the same directory. Two unsynchronized writers in one package dir; `assembly.json` is written non-atomically (`component_package.py:715`) and orphan pruning (`:729-731`) can delete components the surviving descriptor references → 404s on `components/<cid>.glb` and a partial render. Self-heals on the next status poll (`viewer/server_py/artifact.py:127-129`). |
| **D2** | The client POSTs a build even when the server just said `generating`; the server's 180 s wait discards its own timeout and builds anyway. | `viewer/src/client/components/workbench/hooks/useArtifact.js:88,92,105` (only `ready`/`error` are special-cased) + `viewer/server_py/backend.py:396-401` (`await_generation_lock`'s bool is dropped at :397) | **[S2]** Open a model while a >180 s `cad gen` runs: the bar climbs on the CLI run, freezes, then **restarts from 0 %** on a duplicate full rebuild. Total wait ≈ 2× the build. Verified by execution: with the flock held by another process and the timeout shortened, `resolve_artifact` spawned a build and returned `state: ready` while the lock was still held. |
| **D3** | The queued build blocks on `fcntl.flock(LOCK_EX)` with **no timeout**, inside the viewer's single process-global worker lock. | `viewer/server_py/worker_client.py:158` (RLock held across an untimed `readline()` at `:141`) + `packages/cadgen/src/cadgen/_internal/generation_status.py:92` | **[S2]** Every *other* model's build and every STEP/DXF export in the viewer freezes for the whole duration, with no progress for the blocked models. Switching away does not release it — `useArtifact.js:123`'s `controller.abort()` only cancels the browser fetch; `server.py` (ThreadingHTTPServer, `:388`) has no disconnect detection, so the orphaned build keeps the sole worker slot. |
| **D4** | `build_step_artifact`'s "already current" fast path is **dead code**: it tests a package **directory** with `.is_file()`. | `packages/cadgen/src/cadgen/step_targets.py:231` reached via `step_artifact.py:192` (`artifact_path=render_package_dir(...)`) | **[S2] and standalone.** *Every* invocation of `cadgen.step_artifact` — the only module the viewer's build POST runs — re-executes `gen_step()`. Measured on a model with a 4.0 s generator: 6.37 s / 4.02 s / 4.01 s across three runs of an unchanged package, `"skipped": true` never emitted. Meshing *is* skipped downstream (`generation.py:1477-1485`), so the waste is the generator run (or, for imported STEP, an uncached `load_step_scene` at `step_artifact.py:349`). Git blame: commit `9cc69340` mechanically rewrote `glb_path=part_glb_path(...)` (a file) → `artifact_path=render_package_dir(...)` (a directory) without adding the descriptor route the `generation.py` call sites got. |
| **D5** | No post-lock freshness re-check on the viewer's build path. The gate runs **before** `track_generation_run` and is never re-evaluated. | `packages/cadgen/src/cadgen/step_artifact.py:319-322` vs `:331` | **[S2]** Reproduced with two real processes 0.3 s apart on a cold package: B blocked ~2.67 s on the flock, woke to a fully current package, and ran `gen_step()` for a further 2.50 s. The CLI path has the fix (`generation.py:1774-1791`, `skip_if_current` re-evaluated under the lock, wired at `:2185`/`:2282`); `build_step_artifact` does not. While B redundantly regenerates it still holds the lock, so every polling client keeps seeing `generating` over an already-ready package. |
| **D6** | The progress sidecar carries **no run identity**; a dead run's payload is served as the live build's progress. | `packages/cadgen/src/cadgen/_internal/progress.py:164-185` (`payload()` has no run id) + `:196-217` (`__init__` emits nothing) + `viewer/server_py/artifact.py:236` (rejects only `phase == "done"`) | **[S1]** A SIGKILLed/segfaulted build leaves `{"phase":"components","done":31,"total":50,"ratio":0.77}` forever (the file is never unlinked by design, `progress.py:36-39`). Any later lock holder that never constructs a reporter — `step_export_target.py:120` and `step_artifacts.py:407` call `run_script_generator` with no `progress=`, holding the *same* per-model lock for the whole generator run — makes the viewer render "Meshing components 31/50 — 77 %" for a run that has meshed nothing, then snap **backwards** to 0 %. Reproduced end-to-end with the real cadgen writer and the real `server_py.artifact` reader. |
| **D7** | The reader probes with `LOCK_EX`, so two concurrent probes report a phantom build. | `viewer/server_py/artifact.py:193` | **[S1]** flock conflicts per open-file-description, so two probes conflict with *each other*: the loser reports `generating` for an idle, fresh model. Measured: 4 threads × 4000 tight-loop probes of an unheld sentinel → 1144/16000 (7.15 %) false positives; hold window median 2.3 µs. At the shipped 400 ms cadence: 0 in 500 probes. Real but narrow; the fix is one constant. |

**Related, evidenced but not independently verified** (flagged as such; they drive the generalization section): a STEP/STL/3MF export takes the model's *build* lock (`step_export_target.py:120` → `generation.py:968` → `_track_spec_generation`, `:1761-1766`) while writing no package and reporting no progress, so an export makes a fully-current model report `generating` with an empty bar; and `build_dxf_artifact` (`dxf_artifact.py:94-110`) never calls `report_build_progress` at all, so **no DXF drawing can ever show progress**, while its descriptor read (`:101`) and DXF export (`:106`) run *after* the lock has been released.

**Mapping to the two reported symptoms.** S1 ("status not communicated") is D1 (a whole producer the protocol doesn't know about), D6 (a progress channel with no identity), D7 (phantom state), plus the export/DXF gaps. S2 ("multiple processes hooking into one generation") is D2+D3+D5 (the queued-contender path: POST → discard timeout → build → block untimed → rebuild in full → stall the whole backend), amplified everywhere by D4 (no build can ever short-circuit).

---

## 2. Root causes

**RC1 — The lock is placed at call sites, not at the mutation boundary.** Four independent producers each decide for themselves whether to lock: `build_step_artifact` (locks the whole build, `step_artifact.py:331`), `_run_with_spec_generation_status` (locks + re-checks, `generation.py:1789`), `run_script_generator` (locks only the generator run, `generation.py:968`), and `ensure_step_topology_artifact` (locks nothing, `step_artifacts.py:130`). `component_package.build_package_from_compound` — the function that actually writes the descriptor, unlinks `topology.glb` and prunes orphans — takes no lock and asserts nothing, while its own comment (`component_package.py:724-726`) says "Writers are serialized by the generation lock." D1 is exactly what that arrangement permits: a producer added without one.

**RC2 — Freshness is six near-duplicate predicates, and the gate runs outside the lock.** `step_artifact._current_artifact_for_spec` (dead, D4), `step_artifacts._current_artifact_for_spec`, `_existing_topology_artifact_matches_spec_without_scene`, `_existing_topology_artifact_matches_options`, `_assembly_is_current` + `_assembly_glb_package_current`, and the viewer's `_validate_render_package`. The pre-lock and post-lock gates on the same path are *literally different functions*, so "check before or after acquiring?" has no single answer. D4 and D5 both fall out of this.

**RC3 — Two hand-mirrored halves implementing two *different* protocols from one primitive.** The producer takes a blocking exclusive lock around the build; the consumer takes a momentary exclusive lock to *ask a question* and then decides outside it. That mismatch is D7 (wrong lock mode on a read), D2 (`await_generation_lock` has no producer counterpart, so its timeout policy is unreviewed and its return value unread), and the whole TOCTOU family. The drift guard (`test_viewer_cadgen_mirror.py:82-99`) pins path *strings* and one round-trip; it normalizes both sides before comparing paths, and pins no lock mode, no schema version, no descriptor keys, and no concurrency at all.

**RC4 — The lock means three different things, and progress is an uncorrelated second channel.** "I am rewriting this package" (build paths), "I am running this model's generator but writing nothing" (`step_export_target.py:120`, `step_artifacts.py:407`), and "please show a spinner" (`backend.py:309`). Meanwhile the progress sidecar has no run identity and no relationship to the lock holder, so lock-without-progress and progress-from-a-corpse are both reachable. D6 and the export/DXF phantoms are this cause.

**RC5 — No bounded, cancellable wait, and the one blocking wait happens inside a process-global serialization point.** `generation_status.py:92` is `LOCK_EX` with no `LOCK_NB`, no timeout, no deadline; `worker_client.py:158` holds one RLock across the entire round-trip. So "wait for a peer" escalates into "freeze the whole CAD backend" (D3), and the only bound anywhere — `artifact.py:270`'s 180 s — is a client-side illusion whose expiry licenses a duplicate build (D2).

---

## 3. The unified design

### 3.1 Where it lives

```
packages/cadgen/src/cadgen/coordination/
  __init__.py      # the entire public API; stdlib only
  paths.py         # lock/status/generator sentinel paths from an output dir
  lock.py          # flock acquire/probe, degradation policy
  record.py        # status record schema v2, atomic write, typed read
  phases.py        # phase sets, weights, stage-time learning (from _internal/progress.py)
  kinds.py         # ArtifactKind registry
  freshness.py     # THE descriptor+closure validator (arrives in migration step 7)
```

**Consumption, without violating repo rules.** `cadgen` produces: `from cadgen.coordination import artifact_build`. `viewer/server_py` consumes: `from cadgen.coordination import snapshot` — legal today (§0), no `sys.path` manipulation, no new PYTHONPATH entry, no new dependency. Skills consume it through the cadgen they already vendor (`skills/cad/scripts/packages/cadgen`, `skills/dxf/scripts/packages/cadgen`) — no new vendor target, and `check-builds.sh:63-76`'s no-symlink assertion is untouched because the bundle already rsyncs real copies. AGENTS.md's "shared runtime helpers must live under `packages/` and be vendored/generated from there" is satisfied by construction. **`scripts/bundle/bundle.sh` must still run after any change under `packages/cadgen`**, exactly as today.

Guard rail (replaces the mirror test's real purpose): `tests/python/packages/cadgen/test_coordination_is_stdlib_only.py` asserts `"OCP" not in sys.modules and "build123d" not in sys.modules and "ezdxf" not in sys.modules` in a fresh interpreter after `import cadgen.coordination`, and that the import costs < 100 ms.

### 3.2 On-disk protocol

All three files are hidden siblings of the artifact's output directory, under gitignored `__cadgen__` — the shape both sides already derive (`generation_status.py:48-56`, `progress.py:94-103`, `artifact.py:172-176`, `artifact.py:210-216`):

| File | Purpose |
|---|---|
| `.<dir>.generation.lock` | **Writer** sentinel. `LOCK_EX` held by whoever is mutating the output dir. **Name and path unchanged** so a mixed-version pair (old skill cadgen + new viewer, or vice versa) still mutually excludes during rollout. Now carries a payload: the holder's `runId` as fixed-width hex, written under the lock immediately after acquire (today it is deliberately zero-byte, `generation_status.py:5-6`). |
| `.<dir>.generator.lock` | **New.** Generator-busy sentinel. `LOCK_EX` held by anything occupying the model's generator without writing its package — exports (`step_export_target.py:120`), `_scene_for_regeneration` (`step_artifacts.py:407`), `interference.py:221`. A writer holds **both**, in the order writer→generator. |
| `.<dir>.generation.status.json` | Replaces `.generation.progress.json`. Superset of today's payload plus identity. Written tmp+`os.replace` (as `progress.py:390` already does). Never unlinked — the terminal record still carries `stageMs` for the next build's bar weighting. |

**Record schema (v2):**

```json
{ "schemaVersion": 2,
  "runId": "3f9c…",              // uuid4 hex, minted at acquire
  "pid": 13679, "host": "…",
  "kind": "step-package",         // ArtifactKind.name
  "intent": "write",              // "write" | "generate"
  "startedAt": 1785940824670,
  "outcome": null,                // null=running | "done" | "failed" | "skipped"
  "phase": "components", "label": "Meshing components", "detail": "",
  "done": 31, "total": 50, "determinate": true,
  "ratio": 0.77, "ratioFloor": 0.62, "ratioCeiling": 0.94,
  "phaseStartedAt": …, "phaseExpectedMs": …, "updatedAt": …,
  "stageMs": null }               // populated ONLY on outcome=="done"
```

Three rules close D6:

1. **A `starting` record is emitted synchronously inside acquire, before any work and before yielding.** The sidecar can therefore never describe an older run while the lock is held. (Today `ProgressReporter.__init__` emits nothing, `progress.py:196-217`.)
2. **A reader accepts a record only when `record.runId == sentinel.runId`.** Attribution, never liveness — the kernel remains the sole authority on "a run is in flight."
3. **`stageMs` is written only on `outcome=="done"`.** A failed run no longer teaches the next build's bar from partial stage times (`progress.py:440-443` currently calls `finish()` from a `finally`).

Version handling: a reader that sees `schemaVersion != 2` returns *no progress* but still reports `generating` from the lock — the same safe degradation as an unreadable file today (`artifact.py:231-232`).

### 3.3 API surface

**Producer — one context manager that owns lock + progress + post-lock re-check:**

```python
from cadgen.coordination import artifact_build, generator_busy, Contended

with artifact_build(STEP_PACKAGE, package_dir,
                    is_current=lambda: package_is_current(spec),
                    force=force) as run:
    if run.skipped:                       # is_current() re-evaluated UNDER the lock
        return existing_payload()
    run.phase(PHASE_GENERATE)
    scene = run_script_generator(spec, "gen_step", progress=run)
    run.phase(PHASE_COMPONENTS, total=len(work))
    for item in work:
        ...
        run.advance()
```

`artifact_build(kind, output_dir, *, is_current, force=False, deadline_ms=None)` does, in order: acquire `LOCK_EX` (blocking by default; bounded and raising `Contended` when `deadline_ms` is given) → mint `runId`, write it to the sentinel, emit the `starting` record → call `is_current()` **under the lock** and set `run.skipped` → yield → write the terminal record (`done` with `stageMs`, or `failed` without) → release. `force=True` skips only the `is_current()` call, never the lock.

`generator_busy(kind, output_dir)` is the shared-mode sibling: takes only `.generator.lock`, writes an `intent:"generate"` record, writes no package. This is the single change that stops an export from claiming a build is in flight.

**Reader — one non-blocking snapshot:**

```python
from cadgen.coordination import snapshot
snap = snapshot(package_dir)
# snap.state:    "idle" | "writing" | "busy"
# snap.run_id:   str | None
# snap.progress: dict | None   (only when record.runId == sentinel runId)
# snap.degraded: bool          (no fcntl, or flock unsupported on this FS)
```

Probing is `LOCK_SH | LOCK_NB` on each sentinel, which **cannot conflict reader-with-reader** — that is D7's fix, and it is why two sentinels rather than one mode flag: `LOCK_SH` on the writer sentinel fails iff an exclusive writer holds it, and `LOCK_SH` on the generator sentinel fails iff a generator run holds it. `snapshot()` opens **read-only** and treats `ENOENT` as `idle`, so a status GET never creates files (today `artifact.py:189` opens `"a+b"` and materialises a sentinel for a never-built model under the server's uid).

**State machine (server side, one function):**

| snapshot | freshness | reported state |
|---|---|---|
| `writing` | *not evaluated* | `generating` + progress + `runId` |
| `busy` | fresh | `ready` (annotated `busy: true`) — an export no longer hides a renderable model |
| `busy` | stale | `needs-build` + `blocked: true` — client waits, does **not** POST |
| `idle` | fresh | `ready` |
| `idle` | stale, buildable code | `needs-build` |
| `idle` | stale, other code | `error` |

**Two protocol rules that delete D2 and D3's trigger:**

- **`GET /__cad/artifact` never enqueues work.** (Already true; now explicit.)
- **`POST /__cad/artifact` never blocks on a peer.** If the snapshot says `writing`, it returns `{"ok": true, "state": "generating", "runId": …}` immediately. `await_generation_lock` (`artifact.py:270-275`) is **deleted**, not merely unused, and with it the "180 s expired, so build anyway" fallthrough at `backend.py:396-401`.

**Client:** `useArtifact.js:87-105` gains a third branch. `generating` → **attach**: poll until the state leaves `generating`, then re-evaluate; never POST. Only `needs-build` POSTs. The poll (`useArtifact.js:63-79`) starts reading `state` and `runId`, not just `progress`, and **resets the bar when `runId` changes** — which is what stops the backwards jump when one run hands off to another.

### 3.4 How it generalizes

An artifact kind supplies four things and gets coordination, progress, cross-process status, and the post-lock re-check for free:

```python
@dataclass(frozen=True)
class ArtifactKind:
    name: str                                   # "step-package" | "drawing-package" | "export" | "snapshot"
    output_dir: Callable[[Path], Path]          # entry path -> the coordinated directory
    is_current: Callable[[Path], bool]          # THE one freshness predicate (RC2)
    phases: tuple[str, ...]                     # phase order for the bar
```

Registered in `coordination/kinds.py`. The viewer's per-format table (`backend.py:280-300`) becomes a lookup into that same registry instead of a parallel dict.

**Worked example — DXF drawing package.** `ArtifactKind(name="drawing-package", output_dir=render_package_dir, is_current=drawing_package_current, phases=(PHASE_GENERATE, PHASE_FINALIZE))`. `build_dxf_artifact` (`dxf_artifact.py:94-110`) wraps its **whole body** — the currency gate, `run_script_generator`, the descriptor load at `:101`, and `export_drawing_dxf` at `:106` — in one `artifact_build(...)`. Three defects vanish at once: the descriptor read and DXF export stop happening outside the lock; the pre-lock gate becomes a post-lock gate; and the drawing gets a real progress bar, which it can never have today because no DXF code path writes a sidecar at all.

**Worked example — STEP/STL/3MF/GLB export.** Two coordinated resources, correctly separated for the first time. `step_export_target.export_model_to_path` (`step_export_target.py:120`) wraps its `run_script_generator` in `generator_busy(STEP_PACKAGE, render_package_dir(entry_path))` instead of inheriting the writer lock — so a 60 s export of an already-built model leaves it `ready` in the viewer rather than showing a phantom build, while a real concurrent build still excludes it. The export's *own output file* becomes a first-class kind: `ArtifactKind(name="export", output_dir=lambda out: out.parent, is_current=…)` keyed on the destination filename, so two exports to the same default path serialize instead of interleaving, and the write becomes tmp+`os.replace`.

**Third kind, same shape — snapshots/renders.** `skills/cad/scripts/snapshot` and the cadjs snapshot paths have no lock and no progress anywhere today. `ArtifactKind(name="snapshot", output_dir=<gif/png parent>, is_current=<input content hash>, phases=("scene","frames","encode"))` gets the identical treatment. This is the point of the exercise: adding a coordinated artifact format should be a registry entry, not a fifth hand-placed lock.

### 3.5 Scope boundaries — what this deliberately does not do

- **Not a job queue or build daemon.** No cross-process scheduler, no persistent build server, no work stealing. Two processes still race; they just race correctly.
- **Not a cache and not a freshness authority.** Coordination *calls* `is_current`; it never decides what current means. (Consolidating the six predicates is migration step 7, a separate concern that happens to use the same home.)
- **No liveness inference. Ever.** No pid checks, no heartbeats, no age windows. `runId` is for record *attribution* only. This is the one property the current design gets right (`generation_status.py:8-22` documents why the old heartbeat failed) and it must survive.
- **Not cross-machine.** `flock` is local-filesystem advisory locking. NFS/SMB/some bind mounts degrade (see §6).
- **Does not cancel a running build.** A *queued* waiter becomes bounded and abandonable; an OCP mesh already in flight is not interruptible.
- **Does not change** the package layout, `assembly.json`'s schema, the content-addressed cid scheme (`component_package.py:123-133`), or the warm-worker architecture.

---

## 4. Migration plan

Each step is independently reviewable, independently testable, and independently shippable.

**Step 0 — wire the viewer's Python tests into CI.** `viewer/server_py/tests/` (37 tests, incl. `test_artifact.py`) is **run by nothing**: `scripts/test/test-python.sh` runs `tests/python/packages/cadgen`, per-skill `tests/python/skills/<skill>`, and `tests/python/viewer/moveit2_server` only; `viewer/scripts/run-tests.mjs:8-10` collects `*.test.[cm]js` under `src/` and `scripts/` and never touches Python. Nothing below is protected until this lands. *Files:* `scripts/test/test-python.sh` (add one `run_python_unittest` line).

**Step 1 — fix D4 standalone.** Route `step_artifact._current_artifact_for_spec` (`step_artifact.py:188-203`) through the package-aware descriptor predicate (`generation.py:1219-1270`'s `_package_descriptor_matches_spec`, whose own docstring documents this exact class of bug) instead of `validate_step_topology_artifact` (`step_targets.py:231`). Not a concurrency change; it removes a full generator run from *every* build. Ship first, alone, so the coordination work is measured against a sane baseline.

**Step 2 — create the package, move the primitives.** New `packages/cadgen/src/cadgen/coordination/{__init__,paths,lock,record,phases}.py`. **Move** (not copy) the bodies of `_internal/generation_status.py` and `_internal/progress.py`; leave both old module paths as thin re-export shims for one release so `step_artifact.py:16`, `generation.py`, and the mirror test keep importing. Add schema v2 with `runId`, the `starting` emit inside acquire, `stageMs`-only-on-success, the `LOCK_SH` reader probe, `.generator.lock`, and `deadline_ms`/`Contended`. Also fix the degradation hole: `generation_status.py:92`'s `fcntl.flock` sits *outside* the `try/except OSError` at `:83-89`, so an `ENOLCK`/`EOPNOTSUPP` filesystem turns advisory coordination into a hard build failure — the new `lock.py` catches it and degrades, matching the policy the comment at `:87` already states.

**Step 3 — producer cutover.** Rewrite `step_artifact.build_step_artifact:319-360` to `with artifact_build(..., is_current=…)` (fixes **D5**). Rewrite `generation._run_with_spec_generation_status:1774-1791` to delegate to the same primitive (its `skip_if_current` becomes `is_current`, so the two producers cannot diverge again). Rewrite `dxf_artifact.build_dxf_artifact:94-110` to wrap its whole body. Convert `step_export_target.py:120`, `step_artifacts.py:407`, and `interference.py:221` to `generator_busy`.

**Step 4 — close D1 by moving the lock to the mutation boundary.** `component_package.build_package_from_compound` (`:414`) begins with `require_write_lock(package_dir)` — raising under test/CI, warning in production — so no future producer can write a package unlocked. `step_artifacts.ensure_step_topology_artifact:130-139` wraps `_scene_for_regeneration` + `_generate_part_outputs` in `artifact_build`. Make the descriptor write atomic (`component_package.py:715` `write_text` → tmp+`os.replace`, matching every other write in the module) and gate the orphan prune (`:729-731`) behind a grace period, since readers are lock-free by design.

**Step 5 — consumer cutover.** Delete from `viewer/server_py/artifact.py`: `_GENERATION_LOCK_SUFFIX`, `_GENERATION_PROGRESS_SUFFIX`, `_PROGRESS_PHASE_DONE` (`:49-54`), `generation_lock_path`, `generation_lock_active`, `generation_progress_path`, `read_generation_progress`, `await_generation_lock`, `_as_int`, `_as_float` (`:167-275`) — replaced by `from cadgen.coordination import snapshot` (fixes **D7**). Rewrite `backend.artifact_status:297-323` onto the §3.3 state table and `backend.resolve_artifact:385-403` to return `generating` immediately instead of awaiting (fixes **D2**'s server half and removes **D3**'s trigger). ~110 lines deleted, ~35 added.

**Step 6 — client.** `useArtifact.js:87-105`: add the `generating` → attach branch; poll `state` + `runId`, not just `progress`; reset the bar on `runId` change (fixes **D2**'s client half and **D6**'s visible symptom). While here, delete the orphaned surface the audit found: `runStepArtifactGenerationWithRetries`, `validateGeneratedStepArtifactPayload`, and `STEP_ARTIFACT_GENERATION_FAILURE_DISPLAY_THRESHOLD` in `stepArtifactStatus.js` have no production caller.

**Step 7 — consolidate freshness (retires the last mirror).** Move the descriptor+closure validator into `coordination/freshness.py` (stdlib only — it is already stdlib on both sides). Delete `viewer/server_py/source_hash.py` and `artifact._validate_render_package:102-164`; have `scanner.render_package_dir:68-72` import `coordination.paths` instead of re-deriving it (which also settles the symlinked-entry divergence in §6); point cadgen's `_package_descriptor_matches_spec` at the same function.

**Step 8 — generalize.** Register the `export` and `snapshot` kinds. Add a batch `snapshot_many(dirs)` so `scanner.scan_cad_directory` can stamp in-flight state on **every** catalog entry, not just the selected one — today the file list cannot show that a build is running (`scanner.py` is entirely lock-blind).

### The mirror test: it shrinks, then dies

`tests/python/global/test_viewer_cadgen_mirror.py` exists to pin two hand-copies together. Once there is one copy it is asserting a module against itself.

- After **Step 5**: delete `test_generation_lock_paths_match` (`:82`), `test_generation_progress_paths_match` (`:92`), `test_generation_progress_round_trips_across_the_mirror` (`:101`) — both sides now call the same function.
- After **Step 7**: delete `test_render_package_dir_shapes_match` (`:53`, which today hides a real divergence by calling `.resolve()` on the viewer's output before comparing), the descriptor-constant tests (`:64`, `:74`), and move the closure-hash corpus (`:174-283`) — genuinely valuable — to `tests/python/packages/cadgen/test_coordination_freshness.py` as a direct test of the one implementation.
- **The file is deleted.** Its one irreplaceable job — "the viewer must not drag OCP into the server process" — is replaced by `test_coordination_is_stdlib_only.py` (§3.1), which tests the actual invariant rather than a proxy for it.

### Bundling implications

No new package ⇒ no new vendor target, no `pyproject.toml` to stamp, no `scripts/release/pin-cadgen-requirements.sh` change, no `tests/python/global/test_skill_self_containment.py` change. But every step touching `packages/cadgen` still requires `scripts/bundle/bundle.sh` + `scripts/bundle/bundle.sh --check` before commit, because `viewer/packages/cadgen`, `skills/cad/scripts/packages/cadgen`, and `skills/dxf/scripts/packages/cadgen` are symlinks in the dev layout (`scripts/dev/setup-symlinks.sh`) and real rsync'd copies in the published tree (`bundle-cad.sh:216`, `bundle-cad-viewer.sh:282`, `bundle-dxf.sh:4`). `check-builds.sh:63-76`'s no-symlink assertion is unaffected and must not be relaxed.

---

## 5. Test plan

Everything below lands under `tests/python/packages/cadgen/test_coordination_*.py` unless noted. **All cross-process tests spawn real subprocesses and use real `fcntl`** — the existing `test_generation_status.py:200` "skip_if_current is evaluated under the lock" test is a cautionary example: it passes `generator_name="unknown-generator"`, which makes `_track_spec_generation` return `track_generation_run(None)`, i.e. a `nullcontext` — it asserts call ordering with **no lock in play**.

| Defect | Test that would have caught it |
|---|---|
| **D1** | `test_package_write_requires_the_write_lock` — monkeypatch `build_package_from_compound` to probe the sentinel from a second fd with `LOCK_EX\|LOCK_NB`; drive `ensure_step_topology_artifact` on a **cold** package (no `assembly.json`, which is the only branch that reaches it — verified: warm and warm-`force` do not) and assert the lock is held. Plus `test_cold_cli_inspect_reports_generating_to_a_reader`: run inspect in a subprocess, poll `snapshot()` from the parent, assert it observes `writing` at least once. |
| **D2** | `test_post_does_not_build_while_a_peer_holds_the_lock` — subprocess holds the write lock; call `backend.resolve_artifact` with a **shortened** deadline; assert zero builds spawned and `state == "generating"`. (Today, with the timeout shortened, this provably spawns a build and returns `ready`.) Client: `viewer/src/client/components/workbench/hooks/useArtifact.test.js` — **no test file for `useArtifact` exists anywhere in the repo**; add one asserting `generating` polls and never POSTs. |
| **D3** | `test_a_blocked_build_does_not_stall_other_models` — hold model A's lock from a subprocess, POST a build for A, then POST for model B; assert B completes within a bound. Belongs in `viewer/server_py/tests/test_backend_concurrency.py` (new), which requires Step 0. |
| **D4** | `test_second_build_of_a_current_package_is_skipped` — two sequential `build_step_artifact` calls on an unchanged model; assert the second returns `skipped: True` and that `gen_step()` ran **once** (count invocations via a file the generator appends to). The DXF twin already has this (`tests/python/skills/dxf/test_dxf_artifact.py:41-44`); the STEP path has none. |
| **D5** | `test_queued_producer_finds_the_package_current_and_skips` — two processes 0.3 s apart on a cold package; assert `gen_step()` ran exactly **once** across both, and the loser returns `skipped`. Today: two generator runs. |
| **D6** | `test_stale_record_is_not_attributed_to_the_new_run` — write a non-terminal record with `runId=A`, acquire the lock as run B, assert `snapshot()` returns `state=="writing"` with `progress is None` until B's first phase. **Kill-mid-build:** `test_sigkill_leaves_no_renderable_progress` — SIGKILL a real build mid-`components`, assert lock clears (already covered for the lock at `viewer/server_py/tests/test_artifact.py:122`) **and** that the leftover record is rejected on the next acquire. Plus `test_failed_build_does_not_poison_stage_weights` — raise inside `artifact_build`, assert `stageMs` is absent from the terminal record. |
| **D7** | `test_concurrent_probes_do_not_report_a_phantom_build` — N threads × M probes of an **unheld** sentinel; assert zero `writing` results. Today this fails at ~7 % with 4 threads. |
| Export/DXF (unverified) | `test_export_does_not_report_a_build` — hold `generator_busy`, assert a fresh model still reports `ready`. `test_dxf_build_reports_progress` — assert `snapshot()` returns a non-None progress record during a drawing build. |

**Where existing coverage is and what it misses.** `viewer/server_py/tests/test_artifact.py:105-172` is the only real lock coverage and is genuinely good on the primitive (it drives a separate process and SIGKILLs it) — but it is **single-threaded**, tests no probe concurrency, and never exercises `artifact_status`/`resolve_artifact` at all; `:166` pins that `await_generation_lock` returns `False` on timeout, which is exactly the value `backend.py:397` discards. `tests/python/packages/cadgen/test_generation_status.py` never touches `step_artifacts.py` or `build_step_artifact`. `tests/python/skills/cad/cadgen/test_step_artifacts.py` has no lock coverage, and the two tests that mock a current artifact (`:146`, `:193`) patch `step_artifacts._current_artifact_for_spec`, a *different function in a different module* from the dead one in `step_artifact.py`. And none of `viewer/server_py/tests/` runs in CI (Step 0).

---

## 6. Risks and open questions

**Non-POSIX / `fcntl`-absent degradation.** Today both sides silently no-op: `generation_status.py:66` (`if lock_path is None or fcntl is None: return nullcontext()`) and `artifact.py:186` (`return False`) — a Windows or `fcntl`-less environment gets *zero* coordination with no signal, and so does an unwritable or wrong-uid sentinel (`generation_status.py:83-89` swallows the `open()` failure; reproduced with a `0444` sentinel: two processes both entered the critical section). **Proposal:** keep degrading — a build must never fail because a lock is unavailable — but surface it: `snapshot().degraded == True`, one warning line at server startup, and a viewer banner saying builds are uncoordinated on this filesystem. Separately, `lock.py` must catch `OSError` from `flock` **itself** (the current `try/except` at `:83-89` covers only `mkdir` + `open`), so an `ENOLCK`/`EOPNOTSUPP` filesystem — NFS, SMB, some Docker bind mounts — degrades instead of hard-failing the build.

**Symlinked entry *files* — unresolved.** `cadgen.catalog.render_package_dir:274` calls `.resolve()`; `viewer/server_py/scanner.render_package_dir:68-72` does a plain `dirname`/`basename` join. For a symlinked directory both open the same inode and it does not matter; for a symlinked `.step.py` **entry file** the two sides derive different package dirs, different sentinels, and different packages — a permanent rebuild loop with no `generating` ever shown. The mirror test hides this by calling `.resolve()` on the viewer's result before comparing (`:56`). Step 7 forces one answer; **I recommend `.resolve()` on both sides plus an explicit test**, but whether a symlinked entry is a supported layout at all is a product question the audit could not settle (AGENTS.md notes the `develop` layout is symlink-heavy).

**Orphan pruning vs. a live browser session — not settled.** `component_package.py:721-731` deletes every `<cid>.glb` the new descriptor does not reference, on the argument that "readers re-resolve components from the descriptor they load." A browser holding descriptor v1 does not re-resolve. A grace period, a monotonic package generation id in the descriptor, or a two-phase prune all work; picking one needs a decision about how long a stale tab may keep fetching.

**What replaces the 180 s wait, in UX terms.** Deleting `await_generation_lock` means a user who clicks a model a peer is building now *attaches* — sees the peer's live bar — instead of eventually forcing a duplicate build. That is strictly better, but it is unbounded: a hung generator leaves the user watching a frozen bar with no escape hatch. Needs a cancel/force affordance in the UI, which this plan specifies the server side for (`force=true` still bypasses `is_current`, never the lock) but not the design.

**The warm worker remains a single global serialization point.** `worker_client.py:55/158` is one process-global `RLock` around every cadgen call. "POST never blocks" removes the *trigger* for D3, but a genuinely long build still occupies the only worker, so a second model's build queues behind it with no progress. Keying the worker per model, or running N workers, is a larger change than this plan requires — flagged as follow-up, not folded in.

**Rollout skew.** During a release where a bundled skill carries old cadgen and the viewer carries new (or the reverse), mutual exclusion must not break. Mitigated by keeping `.generation.lock`'s path and name byte-identical and making the status record purely additive under a version gate; the new `.generator.lock` is simply not taken by old producers, which is a loss of the new `busy` distinction, not a correctness regression.

**Items carried into §3 from unverified findings** — that exports take the render-package lock while writing nothing (`step_export_target.py:120`) and that DXF builds never write a progress sidecar (`dxf_artifact.py:94-110`) — are strongly evidenced by code reading but were not reproduced end-to-end. They shape the `generator_busy` split and the DXF worked example; if either is wrong, those two pieces shrink but the rest of the design is unaffected.