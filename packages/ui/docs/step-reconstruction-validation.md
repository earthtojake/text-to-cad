# STEP reconstruction experiment: validation and rollback

Validated on macOS ARM64, 2026-09-10. This is an **opt-in experiment**, not a general inverse-CAD engine. A verified sequence is a newly constructed sequence matching the final solid; it is not the original modeling history. Inference uses STEP-derived numeric geometry, without AI or model source files.

## Try it

After installing the repository's normal development dependencies and building packages, start the desktop with `CADGEN_RECONSTRUCTION_EXPERIMENT=1` in its environment. Open a STEP through the existing file explorer, then **Model → Features**. Recognition and verification begin on load; verified components expose **Play build sequence → Export → Animated GIF / Video**. Video uses the browser's supported MP4/WebM encoder. The managed viewer must be restarted when changing the flag.

Unset the flag (or set it to `0`) and restart to disable the whole experiment: no Features subtab, recognition workers, or verification requests. Geometry inspection and the regular viewer remain available.

## Additional real STEP files

Eleven additional files were read through `cadgen step compile`, parsed from their resulting SURF data, and checked for numeric reconstruction candidates. Every proposed complete recipe went through the real, independent BREP verifier. These files were already on the test machine; private/local CAD bytes are not bundled with this report.

| STEP file | Faces | Solids | Complete playback | App check |
| --- | ---: | ---: | --- | --- |
| `locked-in-base.step` | 35 | 1 | Not supported; partial inspection | Passed |
| `state_0003.step` | 10 | 1 | Verified, 2 frames | Passed |
| `iphone17pro_case.step` | 74 | 1 | Not supported; partial inspection | Passed |
| `locked-in-lid.step` | 38 | 1 | Not supported; partial inspection | Passed |
| `cad_part.step` | 13 | 1 | Not supported; partial inspection | Passed |
| `4335T32_Low-Pressure Socket-Connect Unthreaded Pipe Fitting.STEP` | 67 | 1 | Not supported; partial inspection | Passed |
| `9bcfe8ec.step` | 0 | 0 | Empty geometry | Passed |
| `5564K61_Automatic-Winding Hose Reel.STEP` | 2360 | 59 | Not supported; partial inspection | Loading exceeded 60 s, also with experiment OFF |
| `2885e933.step` | 26 | 1 | Not supported; partial inspection | Passed |
| `91253A029_Black-Oxide Alloy Steel Hex-Drive Flat Head Screw.STEP` | 43 | 1 | Not supported; partial inspection | Passed |
| `pythonocc-11752.step` | 1018 | 1 | Not supported; partial inspection | Passed |

Only **one of these eleven files** has complete playback. Ten passed live app inspection/fallback checks with zero renderer errors; the hose reel is a known loading failure, not a pass. Its ordinary viewer load also exceeded 60 seconds with the feature flag off and no reconstruction requests. This needs a separate viewer investigation. It imports as one component containing 59 solids; the current replay verifier deliberately accepts only one solid per component.

The new supported part replayed and verified in 1.70 s; a new-process disk-cache read took 0.015 s with kernel execution explicitly forbidden. Client inference across the new files ranged from 0.1 ms to 445 ms, excluding file loading and worker startup. STEP compile times ranged from 0.76 s to 36.3 s. These are local observations, not performance guarantees.

## Regression models

- Ferrari: all 35 unique components verified again (91 placed occurrences). Playback is per component, not a whole-assembly construction animation.
- PythonOCC `as1`: all 5 components containing solids verified again; 5 empty entries are excluded. Timelines have 2–14 frames.
- PythonOCC feature sample: the one solid verified again, 10 frames; one empty entry.
- iPhone 15 case: cached proof and all 34 frames restored with kernel execution forbidden.
- FreeCAD Schenkel: remains partial; no complete recipe is claimed.
- The Ferrari `import_demo` copy was also verified, but is not counted as independent shape coverage.

## Automated checks

The shared UI, core, web, viewer backend, package boundaries, desktop typecheck/lint, bundle freshness, inspector/toolbar integration, and experiment-off/on integration are the handoff gates. Tests cover rejected dimensions/geometry, operation dependencies, stale/foreign components, bounded inputs, cache invalidation/corruption, sequential background work, tab disposal, occurrence-scoped selection, export cancellation, and real GIF download.

Run the focused app checks after the normal package and desktop builds:

```sh
CADGEN_DAEMON=0 npm --workspace hardcore run e2e -- tests/e2e/model-inspector.spec.mjs tests/e2e/toolbar.spec.mjs tests/e2e/reconstruction.spec.mjs
```

Use the repository's Python runtime (`CAD_DESKTOP_PYTHON` if needed). The tracked `models/examples/imported/import-smoke.step` fixture must be hydrated, and the tests skip if no CAD runtime is available. The reconstruction spec tests both flag states itself. Hidden Electron tests choose a download path through `will-download` instead of waiting for a native save dialog.

## Removal

The commit **Keep STEP inspection independent of model source** is the baseline: source-link removal and geometry-only inspection. The following **Add opt-in STEP reconstruction and playback exports** commit contains the experiment, backend worker/cache, dependency, tests, and documentation. Revert that second commit to remove the experiment without restoring source-code coupling. Reinstall dependencies and rebuild/relaunch afterward; disposable mesh-cache entries need no migration.

The experiment writes neither STEP files nor model scripts. Proof/playback cache entries use the existing disposable store. Recognition limits and unsupported surfaces still apply: drafted/blended parts, freeform surfaces, and flattened multi-solid components commonly get only partial inspection.
