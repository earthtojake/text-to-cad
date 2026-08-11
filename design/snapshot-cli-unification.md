# Snapshot CLI unification: one renderer, one job schema, six front doors

## 0. Execution status

| Phase | Status |
|---|---|
| S0 `--appearance` → `--theme`, hard rename | **DONE** `1e8d59ed` |
| S1 shared CLI shell + kind registry in cadgen | **DONE** `276002fc` |
| S2 CAD / DXF / implicit re-pointed at it | **DONE** `5f008ddc` |
| S3 urdf / srdf / sdf gain snapshot | **DONE** `b8dc2e2f` |
| S4 theme + display pinned to the viewer's | **DONE** `e0f6cfa3` |
| S5 bundles, tests, skill docs | **DONE** |

S4 ran before S3: it is what the drift in §1 was actually about, and it is small.

### What the phases found that the plan did not predict

- **The `"workbench"` theme id was not broken, it was mis-filed.** The browser resolves
  it to light through an explicit back-compat alias, so the theme was always right. The
  damage was that `WORKBENCH_RENDER_THEME_IDS` also decides DEFAULT DIMENSIONS, so
  `--theme workbench` rendered 1600x1200 and `--theme workbench-light` rendered 1200x900
  — same theme, different image, no warning. §1's claim that the id "cannot resolve" was
  wrong; the fix is the same either way.
- **`input_kind()` never recognised `.dxf` at all**, so a drawing handed to the CAD skill
  could not be told where to go. It also read `<name>.dxf.py` as a STEP generator.
- **Moving implicit off its own CLI would have silently dropped three features** —
  `graphics`, `implicitParameters`/`implicitAnimation`, and `animate` mode. They moved
  into the shared schema. Adding `animate` there meant STEP started accepting it, so STEP
  now names its own mode set.
- **The rejection must not name another skill.** Skills install independently, so
  "Use the dxf skill's snapshot for it" asserts something unknowable. A refusal states
  what the running skill accepts and stops.
- **A snapshot should not default to a viewer theme at all.** `snapshot` (render-only,
  absent from the picker) is Workbench Light minus the ground grid and origin axis: helpful
  orientation in a live viewport, geometry-shaped contrast in a still image.
- **Robot snapshot cost three stdlib skills their zero dependencies.** urdf/srdf/sdf were
  pure-Python validators; each now carries a vendored cadgen, a 1.2 MB browser runtime and
  Playwright. They track the runtime like cad/dxf rather than gitignoring it like
  implicit-cad — worth revisiting if repo size matters more than clone-and-run.
- **Non-STEP snapshots were framed loose because they were rendered PERSPECTIVE.**
  `renderJobContext` forced every non-STEP source to a perspective camera regardless of the
  theme ("historical perspective framing"), and `applyTightOrthographicFrame` — the pass
  that fits the canvas to the projected geometry — is orthographic-only, so it silently
  never ran. Measured: STEP `usePerspectiveCamera=false` and the frame tightened
  24.6 → 20.8; STL and URDF `=true` and it was skipped. Projection is now a theme trait for
  every format, matching the viewer's own U1 rule. The robot went from about a quarter of
  the frame to filling it.
- **`--display` is STEP-only.** Its settings are CAD topology settings and every non-STEP
  resolver already rejected all four, so offering it elsewhere advertised an option that
  could only error. `renderJobContext` had always gated `job.display` the same way.
- **`--graphics` is a third option, not part of `--display`.** The viewer has a third tab
  for implicit graphics beside Theme and Display, so the CLI mirrors that rather than
  folding raymarch quality into display settings.

## 1. Where this starts

Three snapshot CLIs exist, and they are three different amounts of the same program.

**CAD** (`skills/cad/scripts/snapshot/__main__.py`, 50 KB) is already the universal one. It
carries a `KIND_RESOLVERS` table keyed by input extension — `step`, `stp`, `glb`, `stl`,
`3mf`, `implicit`, `urdf`, `srdf`, `sdf` — over the shared render core in
`cadgen.snapshot_core` (914 lines: job normalisation, theme/display option loading, asset
URLs, output sizing, the Playwright driver, output writing). Its STEP inputs build through
`ensure_step_topology_artifact`, which holds `artifact_build(STEP_PACKAGE, …)` across the
whole build.

**DXF** (`skills/dxf/scripts/snapshot/cli.py`, 6 KB) is a thin shell over the same core with
its own input resolution, building through `artifact_build(DRAWING_PACKAGE, …)`. It has no
`--display`, no `--job`, and only `view`/`orbit`.

**Implicit** (`packages/implicitjs/scripts/snapshot.mjs`, 978 lines) is a wholly separate
Node program with its own Playwright driver, its own `snapshot-runtime/render.html`, and its
own job schema. It shares nothing with the other two.

The browser side is *already* unified and the Python side has not caught up:
`packages/cadjs/src/common/headlessRenderEntry.js` dispatches on job kind and hands implicit
jobs to `implicitjs/headlessRenderEntry`. Both the CAD and DXF skills bundle that entry to a
byte-identical `snapshot-render.js` (1,296,600 bytes). So one browser bundle can already
render every format in this document; only the drivers disagree.

### Drift this surfaced

`snapshot_core.DEFAULT_RENDER_THEME_ID` is `"workbench"`. The viewer has no such preset —
its ids are `workbench-light` and `workbench-dark` (`packages/cadjs/src/common/themeSettings.js`).

**Corrected during S4:** the id resolves fine, through an explicit back-compat alias in the
browser, so the theme was never wrong. The drift is in the bookkeeping —
`WORKBENCH_RENDER_THEME_IDS` also decides default DIMENSIONS, so the viewer's real preset
names fell through to a different render size. See §0.

## 2. Decisions

Taken with the repo owner, and load-bearing for everything below.

**Each skill owns its own formats, and only its own.**

| Skill | Accepts |
|---|---|
| `cad` | `.step.py`, `.step`, `.stp`, `.3mf`, `.glb`, `.stl` |
| `implicit-cad` | `.implicit.js` |
| `dxf` | `.dxf.py`, `.dxf` |
| `urdf` / `srdf` / `sdf` | its own description format |

CAD loses `.implicit.js` and the robot formats it accepts today. Robot rendering does not
disappear — it moves to the three robot skills, which have never had a snapshot.

**The lock is per FORMAT, not per tool.** "Same lock system" means: when a snapshot has to
generate the artifact required to render an asset, it goes through the same locked build every
other surface of that format uses — the CLI, the viewer, `scripts/artifact`. It is shared
across a format's surfaces, never across formats. STEP already does this
(`artifact_build(STEP_PACKAGE)`), and so does DXF (`artifact_build(DRAWING_PACKAGE)`).
Implicit and robots require **no** artifact to render, so there is nothing to coordinate and
no lock is taken — an honest answer, not a gap.

**Implicit always raymarches.** The viewer renders implicit two ways: the baked `model.glb`
from its package when idle, and a live raymarch while animating or dragging a parameter. The
snapshot takes the raymarch path unconditionally and must never depend on a GLB export. This
is deliberate and not configurable — there is no `--raymarch` flag, because there is no other
mode to choose between.

**`--appearance` becomes `--theme`, hard.** No alias, no deprecation window. The viewer calls
this Theme, `themeSettings.js` calls it theme, and the CLI was the only thing still calling it
appearance. The job-schema field renames with it, so the CLI flag, the JSON job, and the
browser all use one word.

**Everything under the viewer's Display tab lives under one `--display`; everything under
Theme lives under one `--theme`.** Neither grows per-setting flags.

## 3. Target shape

```
packages/cadgen/src/cadgen/
  snapshot_core.py     render/driver core (exists)
  snapshot_cli.py      the CLI shell + every kind resolver                    NEW

skills/<skill>/scripts/snapshot/__main__.py   ~30 lines: KINDS + runtime dir
```

A skill's snapshot becomes a declaration, not a program:

```python
run_snapshot_cli(
    argv,
    kinds=("step", "stp", "3mf", "glb", "stl"),
    runtime_dir=Path(__file__).resolve().parent / "runtime",
    prog="scripts/snapshot",
)
```

Every resolver lives in cadgen, not in a skill. A skill may not import another skill's code
(AGENTS.md), and the robot resolver is needed by three skills at once, so the registry has to
sit under `packages/`. A skill selects rows; it does not own them.

An input kind the running skill does not list is rejected by name, stating what this skill
accepts. It does NOT name the skill that owns the format: skills install independently, so
pointing at one asserts something unknowable.

### Why one bundle, copied six times

Each skill ships its own `runtime/snapshot-render.js`, so this goes from two copies to six
(~7.8 MB of generated output). That is forced: agent installers disagree about symlinks and
one drops them silently, so a skill must be self-contained. Building a smaller per-skill
bundle (dropping the implicit backend from the robot skills, say) would need separate
entrypoints — and separate entrypoints are exactly how the picture starts drifting between
skills. One entry, one bundle, copied.

## 4. Phases

**S0 — `--appearance` → `--theme`.** ~211 occurrences across cadjs, implicitjs, cadgen,
viewer, skills and tests (docs: none). Mechanical, and done first so every later phase is
written in the final vocabulary.

**S1 — the shell moves.** `parse_snapshot_args`, `SnapshotOptions`, `help_text`, the option
overrides, `load_job_from_options`, `input_kind`, `KIND_RESOLVERS`, `resolve_render_job*`,
`run_render_cli` leave the CAD skill for cadgen, parameterized by allowed kinds and runtime
dir. The three kind resolvers (`resolve_step_render_job`, `resolve_implicit_render_job`,
`resolve_robot_render_job`, `resolve_drawing_render_job`) go with them. They landed in
`snapshot_cli.py` rather than a separate `snapshot_kinds.py`: resolution and the argument
surface are one concern, and splitting them bought nothing but an import.

**S2 — the three existing skills re-point.** CAD and DXF become declarations. The implicit
skill drops `snapshot.mjs`, its `snapshot-runtime/`, and the `.mjs` shim, and gains a Python
snapshot on the shared core. DXF gains `--display`, `--job`, and the full mode set for free.

**S3 — robots gain snapshot.** `urdf`, `srdf`, `sdf` each get `scripts/snapshot` and the
bundled runtime.

**S4 — theme and display pinned to the viewer.** Fix the `workbench` → `workbench-light`
default. `--display` accepts exactly `DEFAULT_DISPLAY_SETTINGS`' shape (`mode`, `clip`,
`exploded`, `edges`) and `--theme` exactly the Theme tab's, with a test that fails when the
viewer grows a setting the CLI cannot express.

**S5 — bundles, tests, docs.** Bundle wiring for three new skill runtimes, `bundle.sh --check`
clean, each affected `SKILL.md` updated, Python and JS suites extended.

## 5. What this does not do

Robot and implicit inputs still reject STEP-only options (selectors, `stepParameters`,
exploded, non-solid display modes) — those rejections move with the resolvers rather than
being relaxed. The warm daemon (`--socket` / `--no-daemon`) stays CAD-only; it warms
OCP for STEP builds and no other format has anything to warm.
