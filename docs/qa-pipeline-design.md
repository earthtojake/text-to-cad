# QA Pipeline Design: mesh-qa and sim-test skills

Status: proposed
Date: 2026-07-25

## Scope and goal

Add an autonomous print/physics QA loop to the text-to-cad skill library:

1. Two new agent skills, `mesh-qa` (static/geometric printability validation)
   and `sim-test` (physics simulation of moving mechanisms), written as pure
   tool/API guides — no mandatory rules, no fixed thresholds, no scripts.
2. An orchestration section in `AGENTS.md` and `CLAUDE.md` that steers future
   part-generation tasks through the same
   clarify → design note → generate → test → iterate → review loop used for
   this task itself.

The agent running a future part task decides which checks are meaningful for
which part. The skills only document what trimesh, PyBullet, and the existing
`gcode` skill offer, plus reference (non-binding) FDM tolerance ranges.

## Tool choices and rationale

- **trimesh** (Python) — primary library for mesh-qa. Mature, pip-installable,
  covers watertightness, volume, bounding boxes, winding consistency,
  connected-component splitting, and ray-casting for local wall-thickness
  estimation. numpy and rtree as supporting dependencies.
- **PyBullet** — primary physics engine for sim-test. Chosen over MuJoCo for
  easy pip install, headless `p.DIRECT` mode, and native URDF loading, which
  matches the repo's existing `urdf` skill output. Contact-physics precision
  is sufficient for a QA loop. MuJoCo is documented as an optional
  alternative reference for cases where the agent decides contact fidelity
  matters (`references/mujoco-alternative.md`).
- **Existing `gcode` skill** — mesh-qa documents how to read its slicer
  dry-run/validate output (support requirements, overhang warnings,
  out-of-bounds motion) and turn it into pytest assertions. The `gcode` skill
  itself is not modified.
- **pytest** — the format for agent-generated part tests, matching the repo's
  existing Python test conventions.

## Approach: documentation-only skills

Both skills contain only `SKILL.md`, `references/*.md`, and
`requirements.txt`. No `scripts/` helpers: any bundled CLI would inevitably
embed default thresholds or behavior, which conflicts with the core principle
that the skills are tool guides, not rulebooks. Reference files include
copyable code snippets so the agent does not rewrite boilerplate.

## Skill boundaries

### skills/mesh-qa

Does:

- Teach programmatic printability and geometry-health checks for a generated
  mesh/STEP/STL before printing.
- Document the trimesh API surface: `is_watertight`, `volume`,
  `bounding_box.extents`, `is_winding_consistent`, self-intersection checks,
  `split()` for connected components, ray-casting wall-thickness estimation.
- Document how to interpret the `gcode` skill's dry-run/validate output and
  convert it into assertions.
- Provide a generic pytest skeleton (mesh-loading fixture, example
  assertions) the agent adapts per part under
  `tests/generated/<part-name>/test_geometry.py`.
- `references/trimesh-api.md`: longer API notes and code examples.
- `references/printability-heuristics.md`: typical FDM reference ranges
  (wall thickness, overhang angle, etc.), explicitly marked as
  reference-only, non-binding values.
- `requirements.txt`: trimesh, numpy, rtree.

Does not:

- Decide which checks apply to which part.
- Enforce any threshold.
- Modify the `cad` or `gcode` skills.

### skills/sim-test

Does:

- Teach how to run a URDF/SDF mechanism definition in PyBullet and validate
  motion, collision, and friction behavior.
- Document the PyBullet API surface: `p.connect(p.DIRECT)`,
  `p.loadURDF(...)`, `p.setJointMotorControl2(...)`, `p.stepSimulation()`,
  `p.getContactPoints(...)`, `p.changeDynamics(..., lateralFriction=...)`,
  `p.getLinkState(...)` / `p.getBaseVelocity(...)`.
- Describe example test patterns (non-binding): motor within expected RPM,
  no unexpected contact points, joint staying within limits, slip behavior
  under changed friction.
- Recommend a short/low-resolution simulation first, refining only when
  needed, with a stated upper bound on step count and wall-clock time.
- `references/pybullet-api.md`: longer API notes.
- `references/urdf-sdf-integration.md`: connecting `urdf`/`sdf` skill outputs
  to PyBullet (file paths, mesh references, unit/scale pitfalls).
- `references/mujoco-alternative.md`: optional switch notes when contact
  fidelity matters.
- `requirements.txt`: pybullet, numpy.

Does not:

- Replace visual review via `cad-viewer`.
- Run CFD or FEA.
- Enforce scenario choices or pass/fail criteria.

## Registration and docs

- Registration is directory-based: adding `skills/<name>/SKILL.md`,
  `skills/<name>/agents/openai.yaml`, and `skills/<name>/LICENSE` makes the
  skill discoverable by `scripts/utils/list-skills.sh` and bundled into
  `plugins/cad/skills/` by `scripts/bundle/bundle.sh`. The marketplace
  manifests in `.claude-plugin/` and `.codex-plugin/` reference the plugin
  directory, not individual skills, so no manifest edit is needed.
- Add `mesh-qa` and `sim-test` rows to the README skill table in the
  existing format.
- Add an orchestration section to `AGENTS.md` (see below). Root `CLAUDE.md`
  is a one-line `@AGENTS.md` import pointer, so it needs no separate edit.

## Orchestration loop (AGENTS.md / CLAUDE.md addition)

A new section instructing future part-generation tasks to:

1. **Clarify** — ask a short clarifying question only when the request is
   ambiguous on fit-critical/safety-critical points; otherwise proceed with
   stated assumptions.
2. **Mini design note** — for complex or moving parts, write a short design
   note (purpose, critical tolerances, which QA skills are relevant) before
   CAD generation; skippable for simple static parts.
3. **Generate** — produce the part with the `cad` skill.
4. **Write tests** — the agent decides which of mesh-qa / sim-test / gcode
   apply and writes pytest files under `tests/generated/<part-name>/`.
5. **Run and iterate** — on failure, read the error output, fix the CAD
   source, retry. Maximum **3 attempts**; when the budget is exhausted the
   agent stops, reports current state and remaining failures, and asks the
   user for direction.
6. **Review** — after all tests pass, briefly review the part and tests
   against the design note (missed requirements, superficial tests) and
   present a short review summary to the user.
7. **Log** — keep `tests/generated/<part-name>/iteration-log.md` updated per
   iteration: what passed/failed, what changed, review outcome.

This loop is complementary to `cad-viewer`: visual verification and
automated test verification are separate layers.

## Iteration budget, limits, regression policy

- **Iteration budget: 3 attempts** per part (initial run + 2 fix-retry
  cycles). Budget exhaustion → stop, report, ask user.
- **Simulation limits**: sim-test documentation recommends starting with a
  short, low-step simulation and refining only on demand; an upper notation
  for step count and wall-clock time is included as guidance, not a rule.
- **CI**: local agent sessions only. `tests/generated/` tests are committed
  but not wired into GitHub Actions; existing `test.yml` is untouched.
- **Regression policy**: agent-generated test files and iteration logs under
  `tests/generated/<part-name>/` are committed to the repo and kept as
  durable regression artifacts. They stay separate from the repo's own CI
  suites under `tests/python`.
- **Tolerance philosophy**: values in `printability-heuristics.md` are
  reference-only. No skill file contains binding thresholds or
  mandatory-test rules.

## Out of scope / risks

- CFD (OpenFOAM etc.) and FEA — explicitly out of scope for this phase.
- No modifications to existing skills (`cad`, `gcode`, `urdf`, `sdf`, ...);
  they are referenced only.
- CI integration of generated tests — deferred; local-only for now.
- Risk: PyBullet's soft contact model may miss subtle gear-mesh issues;
  mitigated by the MuJoCo alternative reference.
- Platform note (added after Phase 5): PyBullet publishes Linux wheels
  only, so `skills/sim-test/requirements.txt` gates it behind
  `sys_platform == "linux"` and the skill documents OS availability as a
  deliberate engine-selection criterion; MuJoCo (wheels for all OSes) is
  the documented alternative. Engine-dependent tests skip via
  `pytest.importorskip`.
- Risk: an agent may still write superficial tests; mitigated by the review
  step in the orchestration loop, which explicitly asks the agent to check
  test meaningfulness.

## Acceptance criteria

This task is complete when all of the following exist and hold:

1. `skills/mesh-qa/` with `SKILL.md`, `references/trimesh-api.md`,
   `references/printability-heuristics.md`, `requirements.txt`.
2. `skills/sim-test/` with `SKILL.md`, `references/pybullet-api.md`,
   `references/urdf-sdf-integration.md`, `references/mujoco-alternative.md`,
   `requirements.txt`.
3. Both skills discoverable through the repo's directory-based registration
   (`scripts/utils/list-skills.sh` lists them; `plugins/cad/skills/` exposes
   them via the develop symlink layout, with real copies produced by the
   bundle on release). No manifest edits required.
4. Orchestration section present in `AGENTS.md` and `CLAUDE.md`, covering
   clarify → design note → generate → test → iterate (≤3) → review → log.
5. README skill table includes both new skills.
6. No existing skill files or CI workflows are modified.
7. No skill file contains binding thresholds or mandatory per-part test
   rules (spot-checked in the Phase 4 self-review).
8. End-to-end validation (Phase 5): a moving test part (e.g. two gears or a
   hinged lid) is generated; both skills trigger; the agent writes a
   sensible test file; at least one fail-fix-retry cycle is deliberately
   exercised (e.g. an intentionally thin wall); the review summary step
   runs; results are reported against these criteria.

## Appendix: convention note (Phase 2 findings)

Conventions extracted from existing skills; all new files follow them:

- **Frontmatter**: exactly two unquoted fields, `name` (= directory name)
  and `description` (one long single line: capability sentence + "Use
  when..." trigger sentence, ~50-80 words).
- **Provenance block**: verbatim, immediately after the H1:
  `Provenance: maintained in [earthtojake/text-to-cad](...)` plus the
  "installed local skill files as the runtime source of truth" sentence.
- **Structure**: short SKILL.md (~60-140 lines) with `## Core Rules` /
  `## Workflow` / `## References` sections; depth lives in
  `references/*.md`. References use lowercase kebab-case names and are
  listed as a `## References` bullet list with backtick-quoted relative
  paths, plus inline links where load-time relevance matters.
- **Per-skill files**: every skill has `LICENSE` (copy of root MIT) and
  `agents/openai.yaml` (3-key `interface` block: `display_name`,
  `short_description`, `default_prompt`). `requirements.txt` only when real
  third-party deps exist; mirrored in the comment list of root
  `requirements-dev.txt`.
- **Registration**: directory discovery via `scripts/utils/list-skills.sh`;
  bundle into `plugins/cad/skills/` with `scripts/bundle/bundle.sh`. No
  manifest enumeration.
- **Root docs**: `CLAUDE.md` is a one-line `@AGENTS.md` import; root-level
  agent guidance lives only in `AGENTS.md`.
- **Tests**: repo-owned tests live in `tests/python/skills/<skill>/` and run
  with `unittest`; cross-cutting policy in
  `tests/python/global/test_skill_self_containment.py` scans every skill
  dir, so new skill files must keep skills self-contained (no cross-skill
  imports). Agent-generated part tests go under `tests/generated/`
  (new directory, separate from `tests/python`).
