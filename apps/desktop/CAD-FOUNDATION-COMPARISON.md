# CAD foundation comparison

Date: 2026-08-24

## Decision

Use **Hardcore/Emdash as the MVP base**, while bringing over OpenDesign's durable artifact manifest,
run status, last-good output behavior, and canceled-run recovery.

The additional VibeCAD and ACP Kit evaluations do not change that decision. VibeCAD has valuable
native-CAD transaction and document-persistence ideas, but its current Apple Silicon release did not
start on the test Mac and its exact release tag is not green. ACP Kit is attractive as a small agent
abstraction, but its real Codex and Claude paths both failed against the currently installed clients.

This is a tentative product decision based on the current spikes, not a claim that Emdash is the
cleaner architecture. OpenDesign required less integration code and ran fewer process families in
the live sample, but Hardcore is more CAD-focused and recovered its visible model workspace more
reliably.

## Matched results

| Dimension | Hardcore/Emdash | OpenDesign spike | Current edge |
| --- | --- | --- | --- |
| CAD engine and providers | Codex and Claude each passed 68 selected Jake tests, viewer launch, real STEP generation, validation, topology, and bounds | Same Jake release; generation, invalid-source detection, repair, revision, and validation passed | Tie |
| Model/conversation mapping | Same-stem STEP/source paths map to one model context; compact model revision history | Enforces one project/conversation/model invariant and retains richer run metadata | OpenDesign |
| CAD workspace | Model browser, Jake viewport, revision history, and prompt; raw tool transcript removed | Jake viewport is integrated, but the full agent transcript is still visually primary | Hardcore |
| Files | Model-scoped artifact browser groups generator, model, drawings, references, validation, and exports; full repository remains an escape hatch | Categorized project files, but STEP appears under `Other` beside Jake cache binaries | Hardcore |
| Refresh/reload | Viewer refresh and full Electron restart restore the exact model, conversation, recovery state, generator, and Jake viewport automatically | Model reopening restarted Jake, but renderer reload stayed blank for more than 25 seconds and required full Electron relaunch plus manual project/model reopening | Hardcore |
| Durable restart state | Model conversation, files, interrupted status, paired model/generator recovery, and one-click restore persist | Project, conversation, files, canceled-run state, and follow-up recovery persist | Tie; OpenDesign retains richer run records |
| Integration change | 46 files, +1,282/−667 lines across the current CAD slice, including removal of generic UI | 35 files, +923/−57 lines from the pinned upstream base | OpenDesign |
| Live dev process sample | About 26 matching processes with Jake and one active agent adapter; many Emdash service workers | About 13 including Jake; Electron plus web and daemon sidecars/dev wrappers | OpenDesign by count; Hardcore by observed recovery |

## Additional fork test results

| Candidate | Version tested | What passed | What failed | Product decision |
| --- | --- | --- | --- | --- |
| VibeCAD | `v26.3.1-RC5-build3` / `6a0ad59668836c4c52947b783d466b7a027e0676` | Published DMG SHA-256 and disk-image verification; 87/88 selected persistence, portability, publication, and restore tests; 3,623 tests in the broad source run | Verified Apple Silicon app froze at `_dyld_start` with a 96 KB footprint and never produced a window; 1 selected timeline-contract failure; broad source run had 137 failures and 7 skips, including both environment-dependent GUI failures and static contract drift | Do not fork as the MVP base. Borrow its exact mutation, embedded-source, rollback, and last-good-state ideas selectively after its packaged runtime is healthy. |
| ACP Kit | `0.6.0` / `c29c49a375f10a09b703039f161229a83204f45a` | Build passed; default suite passed 610 tests with 1 skipped | Official install reported 7 audit findings (2 moderate, 4 high, 1 critical); real providers required deprecated `@zed-industries/*-acp` wrappers; documented smoke defaults used incompatible model IDs; with provider defaults, Codex failed with ACP internal errors and Claude failed processing tool-call updates with `Invalid array length` | Do not replace Emdash's existing agent/runtime layer. Monitor the renamed `@agentclientprotocol/*` adapters and retest later. |
| Hardcore CAD baseline | Current checkout with text-to-CAD `0.4.25` | Jake's selected 68-test suite passed independently for Codex and Claude; both Viewer UI/API launch tests passed; Codex generated a real STEP; Claude validated one occurrence with zero failures and measured 30 × 20 × 6 mm, 7 faces, and 15 edges; snapshot review passed | Root wrapper initially misreported sandboxed localhost bind failures as occupied ports; explicit permitted ports passed | Remains the working baseline. Fix the wrapper's bind-error reporting, but do not treat the sandbox collision as a CAD-runtime failure. |

### What the extra forks contribute

- VibeCAD is the strongest source of CAD-specific behavior, not the strongest current shell. Its
  exact transactional tools, document-embedded editable source, accepted-state restoration, and
  rollback contracts are worth studying independently of its large workbench and UI surface.
- ACP Kit demonstrates the value of a narrow provider abstraction, but Emdash already has the
  abstraction we need and its installed adapters are working in the real CAD baseline. Replacing
  that layer would add migration risk without improving the primary CAD loop today.
- Neither fork changes the product direction: keep the shell visibly CAD-first, keep Jake as the
  viewing/inspection layer, and import only the persistence and safety invariants that prove useful.

## What to carry forward

1. Keep Hardcore's compact CAD workspace and same-stem model identity.
2. Keep the model-scoped browser as the default: primary STEP, editable generator, drawings,
   references, validation snapshots, and exports. Keep caches and unrelated source hidden.
3. Finish the explicit artifact manifest on top of the durable run state, app-owned Jake validation,
   paired model/generator recovery, and one-click restore now in Hardcore.
4. Keep full-app restart restoration in the regression gate, including project-host readiness.
5. Apply SMUI after the information architecture is stable; it should restyle one CAD product, not
   preserve Emdash/OpenDesign chrome.

## Product decision ledger

### Hardcore / Emdash strengths

- The current interface reads as a CAD product: model navigation, Jake's canvas, compact revision
  history, and one revision composer are the primary hierarchy.
- Same-stem source and STEP files share one logical model context, so a model can reopen its own
  conversation instead of borrowing whichever chat is active.
- Completed agent work is summarized into design history instead of leaving raw commands as the
  default interface.
- Viewer refresh and renderer reload recovered the current model workspace without manual repair.
- A full Electron restart now restores the exact model conversation, recovery state, editable
  generator, and Jake viewport without manual project/model reopening.
- Failed, stopped, and interrupted revisions preserve both sides of the editable CAD package and
  expose one Restore action.
- Agent completion now enters an app-owned Jake validation gate; only checked geometry is labeled
  Validated, with measured size and face count shown in the model workspace.
- The existing agent/session layer already supports Claude and Codex; the CAD product does not need
  a second agent abstraction.
- Emdash contributes mature worktree, file, permission, and provider plumbing that can remain under
  a much smaller visible CAD surface.

### Hardcore / Emdash weaknesses

- Its live process graph is wide: many specialized runtime workers remain even after subtracting
  their UI. This raises packaging, memory, supervision, and debugging questions.
- The CAD integration changed more files and more lines than the OpenDesign spike, partly because it
  had to adapt Emdash's task/conversation UI into a model workflow.
- Model ownership is selected through a context key, but is not yet enforced as strongly at the data
  boundary as OpenDesign's one-project/one-conversation invariant.
- The artifact relationships are still inferred from filename conventions rather than enforced by
  one explicit manifest at the data boundary.
- The automatic gate proves general solid validity and baseline facts, but model-specific dimensions,
  clearances, and interface requirements still need explicit checks tied to the engineering brief.

### OpenDesign strengths

- It needed less integration code because projects, artifacts, files, agents, conversations, and
  run records already exist as first-class concepts.
- The data/API layer enforces one project, one CAD model, and one conversation rather than relying
  only on hidden UI controls.
- It has richer durable run metadata: completed, canceled, and recoverable agent state survives
  process restarts and remains auditable.
- Its explicit CAD artifact manifest and last-good-output behavior are strong foundations for safe
  generation and repair.
- The project file manager is already scoped to project data and categorized, which is closer to a
  product file system than a raw repository tree.
- Its live dev sample used fewer matching processes than Emdash despite adding web and daemon
  sidecars.
- Both Claude and Codex completed the controlled generation, failure, repair, and revision workflow
  inside the same durable project conversation.

### OpenDesign weaknesses

- The full agent transcript and shell still dominate the experience, so the app can feel like
  OpenDesign with a CAD viewer embedded rather than one CAD tool.
- Generic creation types, design modes, home vocabulary, feedback controls, and transcript details
  remain visible or structurally nearby even when CAD does not need them.
- The file taxonomy is not CAD-aware: STEP is `Other`, while Jake's internal `.glb` and `.bin`
  packages appear beside user-owned outputs.
- A renderer reload stayed blank in the live spike. Full Electron relaunch recovered persisted data,
  but returned to Home and required manual project and model reopening.
- Electron depends on both the Next web sidecar and daemon. Restarting one layer can tear down the
  agent or viewer owned by another, increasing the severity of coupled failures.
- The spike encountered CAD-irrelevant HyperFrames preflight, Node/SQLite ABI requirements, Next
  cache disk exhaustion, and a web-to-daemon restart that canceled an active run.
- It still needs automatic last-open-model restore, CAD-specific file classification, transcript
  compression, and a reliable reload path before it is an equal MVP candidate.

### Shared strengths

- Both shells use Jake rather than recreating CAD selection, camera, tree, reference, measure,
  display, export, and STEP rendering behavior.
- Both can connect Claude and Codex to the same editable generator and generated CAD files.
- The common CAD layer passed upstream tests, real STEP generation, deterministic validation,
  topology, dimensions, and cross-provider handoff.
- Both can keep one conversation associated with the logical model rather than creating an
  unrelated chat for every revision.

### Shared weaknesses and non-negotiable safeguards

- Jake's warm generator cache can return stale geometry after source edits. Source constants and
  measured geometry must agree before a revision is considered complete.
- A failed generator can leave the last-good STEP and render package on disk. Validate the generator
  itself before trusting STEP inspection or the visible model.
- STEP byte hashes are not stable because OCCT writes timestamps; compare Jake's geometry hash and
  measured facts instead.
- Both depend on localhost viewer lifecycle and an installed provider-native CAD package. Setup,
  version pinning, health checks, and recovery must be owned by the product.
- Neither current file manager expresses the user-facing relationship among model, generator,
  drawings, references, validation evidence, and exports.

## How this should inform upcoming decisions

- Prefer the option that shortens the primary loop: describe → generate → inspect → revise → export.
- Borrow infrastructure independently of visible UI. OpenDesign's persistence can move into
  Hardcore without importing OpenDesign's product chrome.
- Treat model identity, last-good output, validation status, and restart recovery as data invariants,
  not visual affordances.
- Do not use process count or implementation diff size alone as a proxy for product simplicity.
- Re-run the same generation, invalid-geometry repair, revision, renderer reload, full restart, and
  file-persistence gates after every major foundation change.
- Delay broad SMUI migration until the model workspace and CAD file taxonomy are settled.

## Evidence

- `artifacts/screenshots/hardcore-cad-baseline-20260824_20260824T190758Z.png`
- `artifacts/screenshots/hardcore-live-comparison-20260824.jpg`
- `artifacts/screenshots/hardcore-reload-persistence-20260824.jpg`
- `artifacts/screenshots/hardcore-recovery-cold-start-20260824.jpeg`
- `artifacts/screenshots/hardcore-app-validation-20260824.jpeg`
- `artifacts/screenshots/hardcore-project-onboarding-20260824.jpeg`
- OpenDesign report: `../hardcore-opendesign-spike/CAD-SPIKE-REPORT.md`
- OpenDesign restart proof: `../hardcore-opendesign-spike/artifacts/screenshots/opendesign-restart-recovery-20260824.jpg`
