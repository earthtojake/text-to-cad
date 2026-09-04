# Demo Models

Curated model fixtures and generator assets for text-to-cad workflows.

This tree is intended to be committed with Git LFS for large CAD, mesh, and
robot artifacts. Source generators and concise documentation remain normal
text files.

## Layout

One flat level: each directory is a self-contained project. Twelve are
cad-projects; four are imported robot-description fixtures.

```text
models/
├── examples/         the demo corpus: parts, assemblies AND 2D drawings
├── thang010146/      imported, annotated mechanism assemblies
├── f1/ f14d/ hypercar/ moonwatch/ motorbike/ qdd_actuator/
├── falcon_heavy/     SpaceX public-source reconstruction
├── juno/ lyra/       authored robot description packages (URDF/SRDF)
```

**Each cad-project has the same shape**, the one the `$cad-project` skill
defines: authored code in `src/` (one `@step` or `@dxf` model per file, shared
modules in `src/lib/`), `.step.js` render modules beside the documents they animate (authored, committed),
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

**Where does a new model go?** If it is one self-contained model script, it
belongs in the `examples/` cad-project: the script in `examples/src/`, its
artifact declared into a format folder with `out=`. If it needs a folder of its
own — helper modules, per-link generators, research/provenance docs, a
`render/` config — it gets a directory of its own here. Robot fixtures imported
from elsewhere get a directory of their own too.

Generated output (`.step`/`.dxf`/`.stl`/`.3mf`/`.glb` exports and their
`.step.json` sidecars) is gitignored — never commit it; a fresh clone
regenerates by running the scripts.

## Directory Map

### The demo corpus

- [examples/](examples/src/README.md): every part, assembly and 2D drawing that
  is a single self-contained model script, as one cad-project. `@step` and
  `@dxf` scripts sit directly under `examples/src/` (shared helpers in
  `src/lib/`, `.step.js` render modules beside the documents they animate), and
  every artifact lands in a root-level format folder. Two models
  (`planetary_gear_assembly`, `mars_rover_concept`) carry typed mates and
  animation clips; a handful declare STL/3MF/GLB exports so the mesh doors have
  fixtures. Two paths hold committed SOURCES rather than outputs:
  `examples/imported/import-smoke.step` (the viewer launch smoke's fixture) and
  `examples/DXF/imported/` (permissively licensed `.dxf` files for tooling
  robustness tests).

### Concept packages

Models that need a **folder of their own** rather than a single loose script.

- [thang010146/](thang010146/README.md): mechanism assemblies from the
  [thang010146](https://www.youtube.com/@thang010146/videos) YouTube channel.
  Its content is `STEP/imported/` — annotated mechanism STEPs, each a
  `cadgen.read_step` of the vendor document re-exported with kinematics
  (`.step.json` sidecar) and its authored `.step.js` render module beside it.
- [f1/](f1/src/README.md): open-wheel F1 car — a modular `lib/` build over one
  shared surface vocabulary, plus `f1_stage.appearance.json`, the authored
  presentation stage. Its DRS four-bar and rack-and-track-rod steering are
  CLOSED loops, so both solves live in `f1.step.js` rather than in typed mates.
- [f14d/](f14d/src/README.md): Grumman F-14D Super Tomcat — one lofted airframe
  skin with ten systems grouped on top of it, a staged teardown in
  `f14d.step.js`, and a `render/` suite of presentation configs and review
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
  teardown in `qdd_actuator.step.js`.

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

These two are cad-projects that happen to carry URDF/SRDF — authored concept
packages, not imported fixtures. Their `3MF/` meshes are GENERATED and no longer
committed: build the link models before loading either URDF.

### Robot fixtures (imported)

Robot descriptions imported from elsewhere, with their supporting meshes. These
are NOT cad-projects — there is no `src/`, nothing regenerates them, and each
keeps its own mix of URDF/SRDF, mesh, and other file types side by side.


The larger `mechbench/` and `mechbench2/` external datasets are intentionally
not included in this committed fixture tree.

## Kinematics, animation, and per-package `render/` folders

A project's articulation is split three ways (see the `$cad` skill's
`kinematics.md`): geometry parameters are the model function's signature,
typed mates are pure data under the `@step` decorator's `kinematics=`, and
choreography is a `.js` module named by `animation=`. The retired `.params.js`
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
