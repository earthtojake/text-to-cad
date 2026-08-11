# Robot descriptions as a first-class render type

Companion to `design/viewer-format-unification.md`, which folded STEP, DXF, the mesh
formats and implicit into one capability-driven shell (93 → 34 identity checks). URDF, SRDF
and SDF were carried along by that work but never audited on their own terms. This is that
audit, and the plan it produces.

Written 2026-08-09 against `claude/viewer-format-unification-u2-u5`.

## 0. The short version

The robot family is **structurally** in the shared stack — same `CadViewer`, same stage,
same theme, same camera, one registry row, its own `fileSessionState` slice — and
**functionally** the thinnest render type in the viewer. It is the only one with:

- no headless render path at all (the snapshot CLI rejects robot inputs outright),
- no export route,
- no structure panel (a URDF is a link tree, but see R1: selection has no payload),
- no display modes, no clip plane, no exploded view,
- a load that takes ~20× longer than a mesh of comparable size, all-or-nothing.

None of that is a bug in the sense of something broken. It is what "carried along" looks
like: every feature added since robots landed was added where someone was looking, and
nobody was looking at robots. The unification effort's own gate had **no robot fixture
until this branch** — six formats swept, and the seventh was the one nobody checked.

## 1. What the audit found

Measured on `models/robots/so101/so101.urdf` (13 link meshes, 16 MB of STL) against a
viewer serving the repo `models/` root, unless stated otherwise.

### 1.1 No headless render path

`skills/cad/scripts/snapshot/__main__.py` says it plainly: *"direct DXF/G-code/robot-
description inputs are unsupported"*. `resolveHeadlessJobKind` knows exactly two backends,
`implicit` and `mesh`. So there is no way to snapshot a robot, no way to produce an orbit
GIF of one, and no way for a skill or CI job to render a robot at all.

This is the largest gap and the one with the clearest shape: a robot resolves to mesh data
in the viewer already (`selectedUrdfPreview.meshData`), so the headless mesh backend could
render it if something assembled the robot first. The work is a resolver arm plus a
headless-side URDF assembly step, not a new render stack.

### 1.2 No export

`exportFormats: []`, and `viewer/server_py/backend.py` implements `generate_export`
(STEP family), `generate_dxf_export` and `generate_implicit_export` — nothing for robots.
An assembled robot is a mesh scene; STL/GLB/3MF export is the same operation it is for an
implicit. Users can export the *parts* of a robot only by opening each link mesh
individually.

### 1.3 No structure panel, though a URDF is a tree

A URDF is a link/joint tree — the direct analogue of a STEP assembly tree, and the reason
`parts`/`topology` exist as capabilities. The robot row declares `parts: false,
topology: false`, so the robot sheet has Joints, Motion and (for SDF) an SDF tab, but no
Tree: you cannot select a link, isolate it, hide it, or zoom to fit it. The DXF sheet grew
a Layers tab explicitly described in `fileSheetSections.js` as *"the drawing's own
STRUCTURE, the DXF analogue of STEP's Tree"*. The robot never got the same treatment,
despite having the most literal tree of the three.

Consequence, now visible: since this branch gave every format the Select tool, a robot
shows a Select button that can never select anything — not because select is inert for
robots in principle, but because no link is pickable.

### 1.4 No display modes, no clip, no exploded view

`displayModes: false, clip: false, exploded: false`. The robot sheet has no Display tab
(`fileSheetSections.js` gives `THEME_DISPLAY` to `step` only). A robot cannot be shown
wireframe or transparent, cannot be sectioned, and cannot be exploded — three things that
are natural on an assembly of rigid links and are implemented once, on mesh data the robot
already produces.

### 1.5 The load is all-or-nothing, and slow

`useCadAssets` fetches every link mesh through `loadRenderRobotMeshes` and only then sets
`ASSET_STATUS.READY`. Nothing renders until the last mesh lands. Measured, cold, on
localhost:

| | model visible | toolbar usable |
|---|---|---|
| STL (6.3 MB, one mesh) | ~0.2 s | **0.8 s** |
| URDF (16 MB, 13 meshes) | ~15.7 s | **15.7 s** |

For ~2.5× the bytes, ~20× the wait, with a static "Loading URDF robot…" card for the whole
of it. The loader *does* track progress — it sets `loading meshes 7/13` — but that stage
string only reaches the file-list status chip, never the viewport card the user is looking
at. Two fixes are available and independent: surface the stage the loader already reports,
and render links as they arrive instead of waiting for the set.

(This also forced the standing sweep's robot fixture to a 26 s window, against 9 s for
every other format.)

### 1.6 Framing

The robot fixture sweeps at 0.10 non-background coverage against 0.16–0.31 for every other
format — it is framed small. Not diagnosed; recorded because the DXF equivalent turned out
to be a real bug (a HATCH seed point inflating the bounds 35×) rather than a camera
problem, so the same suspicion applies to the robot's bounds rather than its fit.

### 1.7 What robots already share, and should not be "fixed"

Worth stating so the plan is not read as "robots are broken":

- One `CadViewer`, one stage, one theme, one camera kit, one zoom/fit stack.
- One registry row; `content: robot` and `assetKind: robot` are honoured everywhere.
- The shared alert builder (`buildViewerMeshAlert`) — including, as of this branch, the
  correct "confirm the file exists" resolution rather than a rebuild command.
- The shared `fileSessionState` `urdf` slice for per-file persistence.
- Orbit, screenshot, pan, draw and the viewport context menu, all as of this branch.
- `sceneScale: "urdf"` is a genuine capability, not a divergence: robots are authored in
  metres and CAD in millimetres, and the scale profile is one registry field.

### 1.8 The one capability robots have and nothing else does

`posePicker`. It is correctly a capability and correctly robot-only today. Note it will
interact with §2.1: if links become pickable, pose-picking and link-selection are two
things a click could mean, and the toolbar already has a mode concept (`tabToolMode`) to
disambiguate them.

## 2. Plan — status

R2 (display modes) and R5 (export) were dropped by the owner: robots do not need
display modes, and URDF/SRDF/SDF are end of the line — they IMPORT 3D formats rather than
producing them, so there is nothing to export. Everything else is done.

| Phase | Status |
|---|---|
| R0 robot in the standing sweep | **DONE** `4456420f` |
| R1 links are parts | built, then **REMOVED** — selection had no payload |
| R2 display modes / clip / exploded | **dropped** (not wanted) |
| R3 progressive loading | **DONE** `b2052a75` |
| R4 robots in the headless renderer | **DONE** `e849884f` |
| R5 export | **dropped** (robots are end of the line) |
| R6 framing | **ANSWERED by R3**, no bug — see below |

### R1 — links are parts: BUILT, THEN REMOVED

Shipped and reverted in the same branch, which is worth recording so it is not rebuilt.

`buildRobotAssemblyRoot` turned urdfData plus the preview's parts into the node shape
`buildStepTreeRoot` returns, and a robot's links became selectable, hideable, isolatable
and zoom-to-fit-able. It worked. It was also **useless**: selecting a link gives you
nothing to do with it. A STEP face or occurrence has a copyable reference — `#o1.2` — that
a user pastes into a generator or a snapshot job. A URDF link has no such currency, so the
whole affordance was a highlight and no payload.

Removed at the owner's call, and `parts` is back to false for robots. On every non-STEP
format the select TOOL stays visible and inert: it is the default mode, and in it the left
button orbits and the right button pans — which is all a robot needs. Verified on URDF,
STL and implicit: a click selects nothing, left-drag orbits, right-drag pans; STEP still
selects.

This also retires **R1b** (the shared Tree panel, 556 lines inside `StepFileSheet` reading
20 props and 33 derived locals). With no selection there is nothing for a robot Tree tab to
drive. Do not extract it for robots' sake.

The lesson generalises: `parts` is not "does this format have sub-objects" but "can a user
DO something with one". A format earns it by having a reference worth carrying away.

### R3 — progressive loading (done)

    before   15.7 s to first pixel, 15.7 s to toolbar
    after     1.8 s to first pixel,  1.8 s to toolbar, complete by ~8 s

The loader hands each mesh over as it lands and the robot republishes on every arrival.
`urdfViewerLoading` had to become "is there nothing to draw yet?" rather than "is the fetch
still running?" — the renderer clears the model outright while loading, so the status-based
gate would have held the blank card up until the last link and thrown the benefit away.

### R4 — robots in the headless renderer (done)

`packages/cadjs/src/lib/urdf/loadRobot.js` is the assembly step with no UI attached;
`loadSource` grows a robot branch so a robot reaches the shared mesh backend as ordinary
mesh data. The CLI takes `.urdf`/`.srdf`/`.sdf` and poses with `jointValues`. Verified:
still, posed still (visibly different), 72-frame orbit GIF, and list mode reporting link
visuals as part refs.

Found on the way: `sceneScale` was accepted, validated, then overwritten with `"cad"`
unconditionally, so a robot was framed for a workpiece a thousand times its size. Now
honoured, and defaulted for robot jobs.

### R6 — framing (answered, not fixed)

The 0.10 sweep coverage was measured at 16 s — the instant an all-or-nothing robot
appeared. With links streaming the same fixture sweeps in line with the mesh formats, and
the settled framing is correct by screenshot. No bounds outlier; the DXF suspicion did not
carry over. The sweep's robot coverage NUMBER varies run to run (0.15–0.57) because the
sample lands at different points in the settle; the assertion is only "not blank".

## 3. Non-goals

- No second render stack. Everything above routes robots through the mesh path that
  already draws them.
- No BREP topology for robots. There is none to have.
- No change to the URDF/SRDF/SDF *authoring* skills or their validators — this is viewer
  parity only.
- No move of `posePicker`, joints or motion planning out of the robot sheet. Those are
  format-specific CONTENT, which the registry gates but does not absorb.

## 4. Standing verification

`viewer/scripts/e2e-format-sweep.mjs` with the robot fixture (R0), plus
`viewer/scripts/e2e-theme-conformance.mjs` if any phase touches shading. Each phase also
states its own gate above. The identity-check ratchet in
`tests/python/global/test_viewer_format_capability_policy.py` must not rise: R1 and R2 are
capability flips, and a phase that needs a robot identity check has found a missing
capability.
