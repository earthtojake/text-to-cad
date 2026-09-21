# Demo Models

Curated model fixtures and generator assets for text-to-cad workflows.

This tree is intended to be committed with Git LFS for large CAD, mesh, and
robot artifacts. Source generators and concise documentation remain normal
text files.

## Layout

One flat level: each directory is a self-contained project.

```text
models/
├── tests/            small manual validation models; NEVER used by CI
├── examples/         standalone demo PARTS, one script each
├── assemblies/       demo ASSEMBLIES, one src/<assembly>/ group each
├── drawings/         2D `@dxf` drawings, one script each
├── thang010146/      imported, annotated mechanism assemblies
├── f1/ f14d/ hypercar/ moonwatch/ motorbike/ qdd_actuator/ w16/
├── tendon_hand/      tendon-driven research hand (source-only)
├── falcon_heavy/     SpaceX public-source reconstruction
├── juno/ lyra/       authored robot description packages (URDF/SRDF)
```

The demo corpus is split three ways on purpose — a part is one script, an
assembly owns a folder, a drawing is a `@dxf` — and each of the three has its
own `src/README.md` catalog.

**Each cad-project has the same shape**, the one the `$cad` skill's `project-layout.md` reference
defines: authored code in `src/` (one `@step` or `@dxf` model per file, shared
modules in `src/lib/`, and animation source embedded in owning `@step` declarations),
raw artifacts in format folders (`STEP/`, `DXF/`, `3MF/`, `GLB/`, `STL/`),
committed inputs no script regenerates in `<FORMAT>/imported/`, scratch in
`tmp/`, and a `.gitignore` that keeps the artifacts out of the repo. A fresh
clone has no `STEP/` at all; regenerate a project by running its scripts:

```bash
cd models/<project>
ls src/*.py | xargs -n1 -P4 python     # unchanged models no-op
```

Each project's `src/README.md` is its model catalog — which script builds which
artifact — so start there rather than reading every file.

**Where does a new model go?** A standalone part that is one self-contained
script belongs in the `examples/` cad-project: the script in `examples/src/`,
its artifact declared into a format folder with `out=`. An assembly gets a
group in `assemblies/` (`src/<assembly>/`, outputs in `STEP/<assembly>/`); a
2D drawing gets a script in `drawings/src/`. If it needs a project of its own
— helper modules, per-link generators, research/provenance docs, a `render/`
config — it gets a directory of its own here.

Generated output (`.step`/`.dxf`/`.stl`/`.3mf`/`.glb` exports and their
`.step.json` sidecars) is gitignored — never commit it; a fresh clone
regenerates by running the scripts.

For manual edge-case checks and debugging, use [tests/](tests/README.md). Automated tests must never depend on any model in this tree; they must create their own isolated fixtures.

## Directory Map

### The demo corpus

- [examples/](examples/src/README.md): standalone demo PARTS as one
  cad-project. Every script directly under `examples/src/` is one runnable
  `@step` model (shared helpers in `src/lib/`), and its artifact lands in a
  root-level format folder. A handful declare STL/3MF/GLB exports so the mesh
  doors have fixtures.
- [assemblies/](assemblies/src/README.md): demo ASSEMBLIES as one cad-project,
  one group per assembly: `src/<assembly>/` holds the root model plus every
  part model and helper that assembly owns, with artifacts in
  `STEP/<assembly>/` (meshes in `STL|3MF|GLB/<assembly>/`). Several carry typed
  mates and animation source embedded in their owning `@step` declarations
  (`planetary_gear_assembly`, `mars_rover_concept`).
- [drawings/](drawings/src/README.md): 2D `@dxf` drawings as one cad-project,
  one script each, artifacts in `DXF/`. `drawings/DXF/imported/` holds
  committed SOURCES rather than outputs: permissively licensed `.dxf` files
  for tooling robustness tests.

Automated suites own their own fixtures and never read this tree — the viewer
launch and browser gates, for instance, generate or commit their STEP fixture
with the tests.

### Concept packages

Models that need a **folder of their own** rather than a single loose script.

- [thang010146/](thang010146/README.md): mechanism assemblies from the
  [thang010146](https://www.youtube.com/@thang010146/videos) YouTube channel.
  Its content is `STEP/imported/` — annotated mechanism STEPs, each a
  `cadgen.read_step` of the vendor document re-exported with kinematics
  (`.step.json` sidecar) with animation embedded by its owning Python model.
- [f1/](f1/src/README.md): open-wheel F1 car — a modular `lib/` build over one
  shared surface vocabulary, plus `f1_stage.appearance.json`, the authored
  presentation stage. Its DRS four-bar and rack-and-track-rod steering are
  CLOSED loops, so both solves live in `f1.py`'s embedded `ANIMATION_JS` rather than in typed mates.
- [f14d/](f14d/src/README.md): Grumman F-14D Super Tomcat — one lofted airframe
  skin with ten systems grouped on top of it, a staged teardown embedded in
  `f14d.py`, and a `render/` suite of presentation configs and review
  tooling.
- [hypercar/](hypercar/src/README.md): mid-engine hypercar — modular `lib/`
  build with a `render/` presentation theme.
- [moonwatch/](moonwatch/README.md): chronograph wristwatch — shared finishing
  vocabulary, per-cluster helpers, eight entry models (`case`, `dial`,
  `movement_base`, `keyless_works`, `chrono_works`, `movement`, `bracelet`,
  `moonwatch` for the full watch) plus a `finishing_sampler` coupon, and a
  `render/` suite of presentation themes and job templates.
- [motorbike/](motorbike/README.md): retro step-through scooter — `lib/spec.py`
  is the hardpoint/palette source of truth and `lib/lib.py` the shared geometry
  vocabulary; 19 part models plus a 46-occurrence `motorbike` assembly with
  typed mates for steering, wheel spin, engine swing and the stand pivot.
- [qdd_actuator/](qdd_actuator/src/README.md): quasi-direct-drive actuator —
  one virtual `drive` DOF gears the rotor, carrier, both ball cages and the
  three planets through the 4.5:1 planetary reduction, with the exploded
  teardown embedded in `qdd_actuator.py`.
- [w16/](w16/src/README.md): quad-turbo 8.0 L W16, sectioned museum cutaway —
  thirteen system models linked by `src/w16.py`, with `crank` and `explode`
  clips from its embedded `ANIMATION_JS`. Its hand-off notes (`REPORT.md`,
  `TODO.md`, `GAUNTLET.md`, `BUILDING.md`) sit beside the source.
- [tendon_hand/](tendon_hand/README.md): tendon-driven research right hand —
  24 joint DOF and 48 antagonistic tendon actuators, SOURCE ONLY (every STEP,
  GLB, video and validation output is generated and ignored). Two models solve
  their choreography rather than authoring it, so their `animation=` string is
  read at build time from a generated, ignored `src/<model>_animation.js`
  sibling; regenerate that sibling first — a missing one is a build error
  naming its generator. `validation/` and `website/` carry its validation
  programs and standalone HTML presentation.

### SpaceX reconstruction package

> **Educational, non-functional public-source reconstruction. Not suitable
> for manufacture, propulsion, testing, or operational engineering.**

A museum/documentary-style CAD package reconstructed exclusively from public
sources; proprietary internals are deliberately excluded and hidden internals
appear only as simplified translucent placeholder volumes. Its
`PROVENANCE.md`, `DIMENSIONS.md`, and `RESEARCH.md` carry the source,
confidence, and dimension tables.

- [falcon_heavy/](falcon_heavy/README.md): Falcon Heavy full vehicle — three
  cores with 27 linked Merlin 1D instances, MVac-derivative second stage,
  cutaway and exploded views (~2,150 named parts each). The Merlin 1D library
  is VENDORED into `src/lib/merlin_common.py`; the standalone Merlin 1D
  package it came from no longer lives in this repo, so the vendored copy is
  the source of truth.

### Robot description packages (authored)

- [juno/](juno/README.md): Juno humanoid — a 27-DOF biped: one model per link
  emitting both a STEP part and the 3MF mesh the URDF references, plus the
  authored `juno.urdf` / `juno.srdf`.
- [lyra/](lyra/README.md): Lyra dexterous hand — a 16-DOF five-digit hand, the
  same shape: per-link models with 3MF exports, authored `lyra.urdf` /
  `lyra.srdf`, and named poses shared between the SRDF group states and the
  STEP's kinematics presets.

These two are cad-projects that happen to carry URDF/SRDF. Their `3MF/` meshes
are GENERATED and no longer committed: build the link models before loading
either URDF.

There are no IMPORTED robot-description fixtures in this tree any more — every
URDF/SRDF here is authored by the cad-project beside it — and the larger
`mechbench/` and `mechbench2/` external datasets are intentionally not included
either.

## Kinematics, animation, and per-package `render/` folders

A project's articulation is split three ways (see the `$cad` skill's
`kinematics.md`): geometry parameters are the model function's signature,
typed mates are pure data under the `@step` decorator's `kinematics=`, and
choreography is JavaScript source embedded in Python and passed to `animation=`. The retired `.params.js`
sidecars are gone from every package here.

Some packages keep a `render/` subfolder holding presentation-theme JSON,
snapshot job templates, and review tooling. Those configs are authored and
committed; anything they generate goes to the project's `tmp/`.

## Git LFS Fetching

Repository LFS config excludes `models/**` from default LFS fetches so ordinary
checkout and publish jobs can avoid downloading every model blob. Fetch the
model artifacts explicitly when you need local bytes:

```bash
git lfs pull --include="models/**" --exclude=""
```

## Cleanup Policy

- Keep canonical sources (`*.py`, `*.urdf`, `*.srdf`, and docs)
  readable in normal Git.
- Keep durable generated fixtures (`*.step`, `*.stl`, `*.3mf`, `*.glb`, and
  `*.dxf`) in Git LFS.
- Do not commit supplementary media or sidecar metadata such as `*.png`,
  `*.mp4`, `*.gif`, or `*.json` unless a future workflow defines them as a
  required model artifact — a package's `render/` job/theme JSON configs
  (e.g. `moonwatch/render/`) are the established exception.
- Do not commit local runtime debris such as `.DS_Store`, `__pycache__/`,
  `.cache/`, logs, or one-off timestamped review snapshots.
- Put temporary scratch artifacts under ignored local paths, not in this tree.
