# CAD integration

Hardcore is the thread-first desktop shell for Text-to-CAD. It lives at `apps/desktop` inside
[earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad) and runs on that
repository's canonical resources directly:

- `apps/viewer` — the CAD Viewer's React client; its server is `cadgen.viewer`.
- `packages/cadgen` — the `cadgen` distribution: `@step` recipes, the warm build daemon, the
  content-addressed cache, and the `cadgen` inspection doors.
- `packages/cadgen-js` — the shared render runtime, bundled into the viewer client at build time.
- `skills/` — the agent skills, installed into Codex and Claude Code as the `cad@text-to-cad`
  plugin.

There is no vendored Text-to-CAD copy, no second viewer runtime, and no desktop-owned cache or
daemon. The desktop keeps its existing Electron shell, ACP sessions, Claude/Codex routing, and
design system; the CAD adapter under `src/main/host/cad/` is the only part that knows where the
canonical resources are.

## Locating the canonical tree

`src/main/host/cad/text-to-cad-layout.ts` resolves the tree once per call:

1. `HARDCORE_TEXT_TO_CAD_ROOT`, when set.
2. `Contents/Resources/text-to-cad` beside a packaged app.
3. The nearest ancestor of the app that carries `VERSION`, `packages/cadgen/pyproject.toml`,
   `skills/cad/SKILL.md`, and both plugin manifests — the monorepo root in a checkout.

A checkout uses `apps/viewer/dist` (kind `repository`). A packaged bundle places that build
inside `packages/cadgen/src/cadgen/_runtime/viewer` (kind `bundle`), so installing the bundled
cadgen also installs the viewer. Both launch the installed module with `python -m cadgen.viewer`.

Run the setup and checks from `apps/desktop`:

```bash
pnpm cad:setup    # runtime + viewer client + provider plugins
pnpm cad:check    # report only
pnpm cad:test     # Jake's selected suites, the viewer launch smoke, and a generate/validate smoke
```

`tooling/scripts/setup-cad.mjs` builds `apps/viewer/dist` when it is missing (npm, from
`packages/cadgen-js` and `apps/viewer`), prepares the Python runtime, and registers the plugin.
The Python runtime is, in order: `CAD_DESKTOP_PYTHON`, a checkout's own `.venv` when it imports
cadgen from `packages/cadgen`, or a managed venv under the app's user data installed from
`packages/cadgen` with `tooling/cad-runtime-constraints.txt` as the dependency lock (editable in a
checkout). At runtime `HARDCORE_CAD_PYTHON` overrides the same choice.

Provider plugins are installed from a filtered, symlink-free staging copy under the runtime root
(`plugins/text-to-cad`): manifests, `skills/`, `LICENSE`, and `VERSION`. The desktop replaces
`cad-viewer` with its own `cad-desktop` skill. No viewer runtime is copied into the plugin.

## Product model

The thread is the entry point. A user opens a project folder and can run many independent threads in
parallel. A thread may create or edit any relevant STEP, drawing, assembly, analysis, document, or
supporting file in that folder. The primary layout is:

```text
projects and threads | active conversation | artifacts and viewer
```

First launch opens the welcome screen directly. The inherited EmDash database import wizard
and import services are removed; existing Hardcore data still uses the normal schema migrations.

Artifact tabs belong to the selected thread. Opening an existing CAD file opens its canonical STEP
directly in the artifact area, served by the CAD Viewer for that thread's workspace. Advanced file
browsing remains the desktop's ordinary project-file UI.

## Canonical artifact lifecycle (cadgen 0.5)

The accepted on-disk STEP and its recorded SHA-256 are canonical model state. A Python recipe with a parameterless `@step` function and an explicit main call is the
optional source that can rebuild it. Filenames, including `.step.py`, do not decide whether a
program is current; cadgen validates the declarations when it runs.

Every geometry-changing turn follows the same lifecycle:

1. Hash and back up the accepted STEP, its optional `.step.json` sidecar, and the linked recipe.
2. Let the selected agent edit files, or apply the user's explicit recipe edit in the source editor.
3. Run `python <recipe>.py --json`. The recipe must call its parameterless decorated function
   from `if __name__ == "__main__":`. Cadgen owns caching and concurrency; the desktop does not
   pass `--force` or the retired `--lock-timeout` flag.
4. Read the build result's `document` path and independently inspect and validate those bytes
   with `cadgen step inspect refs` and `cadgen step inspect validate`.
5. At turn completion, accept and reload only the validated on-disk artifact.
6. Restore the previous STEP, sidecar, and recipe after failure, interruption, or invalid geometry.
   Never delete store entries on rollback: a render tree is keyed by the document bytes.

Opening, previewing, and restart recovery never run the source program. A source edit alone never
overwrites the accepted STEP; only an explicit rebuild does.

The desktop's Source action first uses the persisted model-catalog association. Otherwise it reads
cadgen's optional code-side provenance (`index/output` → `index/model`), verifies that the script
exists inside the workspace and its declared output is this STEP, and offers that source. This is
authoring context, never render identity or a validation prerequisite. A missing or evicted record
leaves the document viewable. A same-stem `.py` beside an imported STEP is never assumed to own it.
Old `.step.py` siblings remain discoverable, but must use current declarations to rebuild.
The `.step.json` sidecar carries kinematics;
choreography lives in the document's `.step.js` render module.

## Live build previews

While a local task is visible and an agent is working, the desktop scans for new artifacts
about every two seconds, using asynchronous filesystem reads. It waits for recent writes to
settle and validates new STEP files before opening a temporary preview tab. This tab follows
the newest completed model, preferring STEP, so finished leaf parts can appear during the
first build and the assembled artifact replaces them when ready. Pinning, closing, or selecting
another tab stops following; an existing CAD tab is never taken over. Other new files receive
an Open action. A final scan also covers turns
that finished while another task was visible. Failed scans stay pending for retry.

The embedded viewer already polls its artifact catalog and follows revisions at the same path.
Intermediate builds are previews; they do not advance an existing model's accepted revision or
replace its rollback backup. Final validation and rollback remain owned by the desktop's run
lifecycle. Previewing never executes a recipe. Agents should publish completed, valid builds at
meaningful milestones; the viewport cannot show geometry that has not been built yet.

Parts are shown individually in their own artifact coordinates, not progressively placed in an
unfinished assembly. Cadgen's daemon
already exposes child job states and declared output paths, but that feed carries no parent
occurrence transforms. Pending placements live inside the build process; the completed artifact
tree publishes them. The viewer must not infer placements from source or model records, or treat
an older assembly's layout as the current build's layout. Progressive component loading from an
already published tree can be implemented in the viewer independently. Keep cadgen's build
process unchanged for preview work; changes there are limited to separately demonstrated bugs.

## Viewer ownership

Jake's viewer owns the viewport, topology tree, measurement, references, display controls, pose
controls, and per-file rendering. The desktop starts one server per workspace directory with
`python -m cadgen.viewer --host 127.0.0.1 --json --dist <built client>` from that directory, reads the launcher's
`{url, port, action}` line, and embeds `http://127.0.0.1:<port>/?file=<workspace-relative path>`.
The launcher owns ports and reuse: `action: "reused"` means another launch already serves that
directory at the same code, and the desktop tracks that port without owning a process to stop.
Health is `GET /__cad/server` with `rootPath` equal to the workspace.

The desktop does not script the viewer: there is no injected CSS or DOM, no reading of React
internals, and no polling of viewer state. Selections reach the chat through the viewer's own Copy
Reference and Copy Link actions; screenshots use Electron's webContents capture. When the accepted
STEP changes, the desktop reloads the page.

## Future visual editing

Hardcore previously injected a source-backed feature tree and parameter sliders into the viewer's
DOM. That bridge was removed with the move into this repository; the last version is
`amywork777/hardcore@cb70246a40` (`src/core/features/cad/browser/cad-viewer-integration.ts`,
`cad-history-panel.tsx`, `cad-agent-panel.tsx`). The unused descriptor, fixture and Python source
parser were also removed from this import; their last version is available at
`8654e450:apps/desktop/apps/emdash-desktop/src/core/features/cad/api/`.

Current 0.5.0 laws make the viewer a source-blind artifact reviewer. Future visual editing should
keep source updates, rebuild, validation, rollback and acceptance in the desktop, with viewport
interactions exposed through explicit shared interfaces. Recipes currently use the desktop's
Source view and the rebuild lifecycle above.

## Acceptance gate

Before shipping a desktop build, verify the installed application rather than only a checkout:

1. Start Claude and Codex sessions and confirm the bundled skills are available automatically.
2. Open an existing STEP without regeneration and confirm its hash.
3. Generate a STEP from a plain `@step` recipe and open the accepted artifact.
4. Change a numeric dimension in the source editor, rebuild, validate, and reload it.
5. Produce an invalid edit and an interrupted run and confirm the last accepted artifact is restored.
6. Restart the app and confirm the same STEP hash and viewport artifact return without regeneration.
7. Run at least two CAD threads concurrently and confirm independent status, processes, and viewers.
8. Package the app and run the packaged CAD smoke (`scripts/release/verify-packaged-cad.ts`), which
   provisions the bundled runtime, builds two models in two roots, validates them, and serves each
   from its own viewer.
