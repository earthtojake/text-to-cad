# Restore the implicit raymarch render path in the CAD Viewer

Execution plan. The viewer goes back to FOUR internal render types — GLB, STL, 3MF, and
implicit (GPU raymarch) — reversing the viewer-side half of the render consolidation for
implicits only. Decision context: after per-vertex colours, resolution 144→256, crease
normals, and Hermite feature snapping, mesh extraction still cannot match the raymarcher's
quality on mechanical models (planetary-gear A/B, 2026-08-07); display and exchange are
therefore split — raymarch for pixels, mesh packages for export.

## 0. Scope fence — read before touching anything

**Restore (viewer display only):**
- Implicit models render in the viewer by GPU raymarch of their GLSL, loaded directly from
  the `.implicit.js` module — no package required to display.
- The implicit settings/controls removed in phase 3: params sidebar, animations, raymarch
  graphics settings (`ImplicitFileSheet`, `ImplicitGraphicsSection`, graphics settings
  store).

**Do NOT touch:**
- **DXF stays on its baked `preview.glb`** (phases 3a + 4 remain).
- **STEP path** — untouched.
- **The implicit EXPORT pipeline** (`implicit_export`: GLB/STL/3MF on demand, coordination
  via generator_busy): keep — it becomes the only mesh consumer, at high-quality defaults
  (§2.1). The render PACKAGE (`implicit_artifact`'s model.glb) is retired instead — see
  §2.3/R6.
- **implicitjs core work from this branch**: the GLSL→JS compiler, equality harness,
  mesher fixes (edge refinement, thin-axis floor, feature snap), writeGlb COLOR_0/sRGB.
  These serve export quality and are independent of how the viewer displays.
- Coordination/loading-bar work — generic, keep.

## 0.1 Execution status

| Step | Title | Status |
|---|---|---|
| R1 | Restore deleted files from release/0.4.0 | **DONE** `cfc60a19` |
| R2 | Re-wire CadWorkspace's implicit arm | **DONE** `cfc60a19` + `8c476e8b` |
| R3 | Restore file-sheet tabs + settings | **DONE** `8c476e8b` |
| R4 | Raymarch builtin gaps (ES-1.00) | **NOT NEEDED — premise was stale** |
| R5 | Gates + full-corpus visual sweep | **DONE** (see below) |
| R6 | Retire the implicit render package | **partial** — export default done; package removal outstanding |

### R4: unnecessary, and why

The recorded follow-up said nine ES-3.00 builtins were missing and that
`catenoid-ring-bridge` could not GPU-render because of `cosh`. It does render, correctly and
un-clipped, and the opt-in GPU gate (`IMPLICIT_GPU_SHADER_CHECK=1`) compiles **44/44** shaders
in a real GL context. Only two ES-3.00 builtins are used by the corpus at all (`cosh`,
`round`) and both work. No polyfills were added — the note was stale, and adding dead GLSL
would have been worse than nothing.

### R5 results

- **42/43 implicits render** through the restored raymarch path. The one failure,
  `menger-sponge`, is a pre-existing MODEL defect, not a regression: its field is ≥ 2.77
  everywhere inside its own declared bounds (0 negative samples of 15,625), so there is no
  solid to draw. Same conclusion the mesh path reached.
- Other formats verified by screenshot: **STL** and **3MF** render fully (3MF with per-part
  colours). **STEP** was mid-build at 92% (no package in this worktree) with its Tree/Reference
  /Display sheet intact. **DXF** correctly shows "No mesh data is available — rebuild the CAD
  assets", which is the designed alert for an unbuilt package, not a break.
- METHOD WARNING for whoever repeats this: sampling the WebGL canvas via `drawImage` reports
  EVERY format blank, because the drawing buffer is not preserved. It briefly looked like the
  whole mesh path had regressed. Use `page.screenshot()`, which composites the real
  framebuffer.

### R6 remaining

Done: the export default is 192 (decision 1). Outstanding, and genuinely cross-cutting —
`cad gen` still writes an implicit render package nothing displays: remove the
`IMPLICIT_PACKAGE` ArtifactKind, the `implicit_artifact` package writer, and the viewer/server
artifact handling for `.implicit.js`; verify what the implicit-cad skill's snapshot consumes
and move it to the raymarcher; keep `implicit_export` as the only mesh consumer, still
coordinated by `generator_busy()`.

## 1. The exact inventory (verified against git)

Phase 3 is commit `93cfda9b` ("six render paths become two"). Its viewer/cadjs deletions,
ALL present on `release/0.4.0` (merge-base `56a119c00`):

```
packages/cadjs/src/implicit/exportModel.js
packages/cadjs/src/implicit/graphicsSettings.js
packages/cadjs/src/implicit/loader.js
packages/cadjs/src/implicit/render.js
viewer/src/client/components/ImplicitCadViewer.js
viewer/src/client/components/workbench/ImplicitFileSheet.js
viewer/src/client/components/workbench/ImplicitGraphicsSection.js
viewer/src/client/workbench/implicitExport.js
viewer/src/client/workbench/implicitGraphicsSettings.js
viewer/src/client/workbench/implicitGraphicsSettings.test.js
```

### R1 — restore them

```bash
git checkout release/0.4.0 -- <each path above>
```

Then reconcile imports, which is where the real work is:

- `packages/cadjs/package.json` — phase 3 removed the `./implicit/*` subpath export
  entries (recorded at the time as "two dead cadjs/implicit re-export subpaths"). Restore
  whatever entries the four restored `packages/cadjs/src/implicit/*.js` files need; they
  are thin `export * from "implicitjs/..."` re-exports, so check each target still exists
  in implicitjs (it does — snapshot/export kept them alive).
- `ImplicitCadViewer.js` imports from `cadjs/implicit/*` — must resolve after the above.
- `implicitExport.js` was the client-side export flow; the CLI now owns export
  (`implicit_export.py`). Restore it only if `ImplicitFileSheet` imports it; if its export
  buttons now conflict with the CLI flow, keep the UI but point it at the server route —
  decide by reading what release/0.4.0's sheet actually did, do not guess.

### R2 — CadWorkspace re-wire (the diffs live in `93cfda9b` and this thread)

All in `viewer/src/client/components/CadWorkspace.js`, mirror-reverse of phase 3:

1. `ARTIFACT_MANAGED_SOURCE_FORMATS` (~line 273): remove `RENDER_FORMAT.IMPLICIT` — the
   viewer must not POST artifact builds to display an implicit. `useArtifact` then treats
   implicit entries as direct-render "ready" automatically (`enabled: false` path).
2. `STATUS_ONLY_FILE_SHEET_KINDS` (~line 285): remove `"implicit"` — implicits get their
   real file sheet back.
3. Restore the implicit arm of the render switch (the `<ImplicitCadViewer …>` branch) and
   the implicit arm of `viewerLoading` (`implicitViewerLoading`, was deleted with the
   comment "DXF and implicit have no arm of their own any more" ~line 2444).
4. Loading label arm for implicit already exists ("Loading implicit CAD..." ~line 2479) —
   verify it binds to the restored loading state.
5. entry icon/status: `entryIconStatus.js` and `stepArtifactStatus.js` gate on artifact
   generation for managed formats; with implicit out of the managed list, implicit entries
   must not show "generating" states. The vestigial STEP-only gating recorded in the
   follow-ups is adjacent — do not expand this step into that cleanup.

### R3 — file sheet + settings

The dual-wiring footgun (documented in repo memory and `viewer/docs/settings-ui.md`): a
tab needs BOTH a `{id,title,content}` descriptor in `themeTabs` AND its id in
`renderedFileSheetSectionIds` (plus that list's test), or it silently won't stay open.
Phase 3 removed the implicit tabs from both places; restore both, and restore
`implicitGraphicsSettings.test.js` to the viewer test run. Settings panels follow
`viewer/docs/settings-ui.md` (FileSheet primitives, switches on one right axis) — the
restored release/0.4.0 components already comply; do not restyle.

### R4 — raymarch builtin gaps (now display-blocking)

The raymarcher assembles GLSL **ES 1.00** shaders; nine ES-3.00-only builtins are missing
(`sinh cosh tanh asinh acosh atanh trunc round roundEven` — recorded follow-up ES-1.00).
`catenoid-ring-bridge` does not GPU-render because of `cosh`. Now that raymarch is THE
display path this is a bug, not a footnote: add polyfill functions to
`IMPLICIT_CAD_GLSL_LIBRARY` in `packages/implicitjs/src/lib/implicitCad/render.js`
(`sinh(x) = (exp(x)-exp(-x))*0.5`, etc.), injected only when the source references them if
the library is size-sensitive. The opt-in GPU compile test tier
(`IMPLICIT_GPU_SHADER_CHECK=1`, "every model's fragment shader compiles in a real GL
context") is the gate — run it; all 43 must compile.

### R5 — gates

- `npm --prefix viewer run test` and `run build`; `npm --prefix packages/cadjs test`;
  `npm --prefix packages/implicitjs test` (the SDF equality harness must stay green —
  nothing here touches the evaluator).
- Any viewer tests phase 3 *modified* (not deleted) around implicit rendering: restore
  their release/0.4.0 assertions rather than writing new ones — `git show 93cfda9b`
  lists them.
- **Full-corpus visual sweep**: load all 43 implicits through the viewer with playwright
  (`--use-angle=metal`; SwiftShader renders differently — repo memory), assert non-blank
  viewport, screenshot planetary-gear + catenoid-ring-bridge + gosper-curve-tube for the
  user. A blank-but-no-error viewport is the known GLSL-compile-failure signature.
- STEP, DXF, GLB, STL, 3MF each loaded once to prove the other arms didn't move.
- `scripts/bundle/bundle.sh` + `--check`, dev symlinks restored, **no `git add -A`**
  (see prior plans' process notes).

## 2. Decisions (answered by the user, 2026-08-07)

1. **Export quality over speed.** Exports are explicit actions (like STL/3MF), so their
   defaults must match the viewer's render quality: raise the export-path default
   resolution to 192 (clamp stays 256). Minutes-long export is acceptable; a mismatched
   cheap export is not. The mesher improvements from this branch (compiler, edge
   refinement, crease normals, feature snap, COLOR_0) are exactly what make the exported
   mesh worth keeping.
2. **Staleness indicators for implicits VANISH.** The render is recomputed dynamically;
   there is no artifact to be stale. Implicit entries carry no generating/stale states
   anywhere (icon, sheet, status items).
3. **Retire the implicit render package (R6).** With display raymarched and snapshot
   aligned to the same render logic, `model.glb`/`implicit.json` has no consumer:
   - `cad gen` for implicits stops producing a render package; the viewer's artifact route
     reports implicits as direct-render.
   - VERIFY what the implicit-cad skill's snapshot actually consumes today; if any of its
     modes read the package, move them to the raymarcher so snapshot and viewer share one
     render path. (The skill's raymarch machinery exists — `snapshot.mjs` with headless
     chromium; note SwiftShader-vs-Metal differences when validating.)
   - `implicit_export.py` (GLB/STL/3MF) meshes ON DEMAND at export time with the
     high-quality defaults from (1) — keep, this becomes the only mesh consumer.
   - Unwind the IMPLICIT_PACKAGE plumbing with the package: the ArtifactKind entry, the
     `implicit_artifact` package writer, and viewer/server artifact handling for
     `.implicit.js` — read `design/unified-glb-render-artifacts.md` phase 2 for what was
     added, and remove in reverse. Coordination still guards EXPORT via generator_busy(),
     as STEP exports do.
   - Existing `__cadgen__/models/*.implicit.js/` package directories on disk: `cad gen`
     should stop regenerating them; leave cleanup of stale directories to a normal
     `git clean`-style sweep, do not write a migration.
