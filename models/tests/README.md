# Manual validation models

**CI tests must NEVER read, import, build, or depend on anything in `models/`, including this folder.** Automated tests belong under `tests/` (or the package test suites) and must create small, self-contained fixtures in fresh temporary directories with isolated cache stores. Do not use these models as a shortcut for automated test data.

Agents may use these models for manual browser reviews, reproducing edge cases, checking exports, and debugging new features. They are intentionally small and quick to rebuild. Commit useful source scripts and concise reproduction instructions only; generated CAD files, snapshots, logs, and cache data stay untracked.

## Cases

| Folder | Manual checks |
| --- | --- |
| `render_floor/` | Three colored blocks above, across, and below Z=0. Render's default floor stays at the authored origin; aligning to the lowest point is an explicit option. |
| `viewer_concurrency/` | A 32-part drilled-plate assembly. Change `REVISION` and rebuild while the viewer is loading to check update handoffs, progress, and replacement geometry. |
| `unified_annotations/` | An 11-part assembly with named materials, a pose, and embedded animation. Check Materials assignments/reset, motion in both view modes, metadata-only edits, snapshots, and animated GLB exports. The arm's intrinsic green color has alpha 0.6; its blue paint override multiplies opacity by 0.5, yielding 0.3. Assigning a material without `baseColor` restores its intrinsic green. |

## Run manually

From the repository root, using the development environment:

```bash
# Keep manual runs separate from other projects and their active builds.
export CADGEN_CACHE_DIR="$(mktemp -d /tmp/cadgen-manual-store.XXXXXX)"
export CADGEN_DAEMON_STATE_DIR="$(mktemp -d /tmp/cadgen-manual-daemon.XXXXXX)"
.venv/bin/python models/tests/render_floor/source.py
.venv/bin/python models/tests/viewer_concurrency/source.py
.venv/bin/python models/tests/unified_annotations/annotation_fixture.py
(cd models/tests && ../../.venv/bin/cadgen viewer)
```

Artifacts are written next to each case's script and ignored by Git. Use the viewer's file picker to open them. For a CLI check:

```bash
.venv/bin/cadgen step snapshot models/tests/unified_annotations/annotation_fixture.step /tmp/annotations.png --render light --kinematics open --animation demo --time 1
.venv/bin/cadgen glb build models/tests/unified_annotations/annotation_fixture.step /tmp/annotations.glb --animation demo
```

Animation moves the shaft; the `open` pose rotates the arm independently. Material, animation, and literal kinematics edits should refresh the JSON sidecar without rewriting STEP geometry. Computed annotations and geometry changes may require ordinary source execution.
