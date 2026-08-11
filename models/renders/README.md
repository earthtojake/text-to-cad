# Renders

Large concept renders and related experiments — every model that needs a
**folder of its own** rather than a single flat generator file. Each package
keeps its own internal layout (`STEP/`, `3MF/`, `<name>_parts/`, `render/`,
per-package `README.md`, provenance and research docs) and is self-contained.

Flat single-file `<name>.step.py` generators live in
[`../step/assemblies/`](../step/assemblies/README.md) (multi-part) and
[`../step/parts/`](../step/parts/README.md) (single-body) instead.

## Concept packages

- [f1/](f1/): open-wheel F1 car — modular `f1_parts/` build with a
  parameter sidecar.
- [hypercar/](hypercar/): mid-engine hypercar — modular
  `hypercar_parts/` build, `render/` presentation theme, and a `.step.js`
  sidecar.
- [moonwatch/](moonwatch/README.md): chronograph wristwatch — shared finishing
  vocabulary, per-cluster helpers, eight entry generators (`case`, `dial`,
  `movement_base`, `keyless_works`, `chrono_works`, `movement`, `bracelet`,
  `moonwatch` for the full watch) plus a `finishing_sampler` coupon, and a
  `render/` suite of presentation themes and animation job templates.
- [qdd_actuator/](qdd_actuator): quasi-direct-drive actuator with a parameter
  sidecar.
- [raptor3/](raptor3): Raptor 3 engine concept with a parameter sidecar.
- [starship-mechazilla/](starship-mechazilla): launch mount, tower, ship,
  super heavy booster, and full integrated stack — five entry generators, each
  with its own animation sidecar.

## SpaceX reconstruction packages

> **Educational, non-functional public-source reconstructions. Not suitable
> for manufacture, propulsion, testing, or operational engineering.**

Museum/documentary-style CAD packages reconstructed exclusively from public
sources; proprietary internals are deliberately excluded and hidden internals
appear only as simplified translucent placeholder volumes. Each package's
`PROVENANCE.md`, `DIMENSIONS.md`, and `RESEARCH.md` carry the source,
confidence, and dimension tables.

- [raptor2/](raptor2/README.md): Raptor 2 — exterior, schematic cutaway,
  exploded view, and derived Raptor Vacuum generators, plus a `renders/` suite.
- [starship/](starship/README.md): Starship / Super Heavy full stack (pinned
  V2/Block 2) — booster, ship, stack, cutaway, and exploded generators reusing
  the raptor2 engines as linked instanced subassemblies.
- [merlin1d/](merlin1d/README.md): Merlin 1D — exterior, schematic cutaway,
  and exploded generators (~260–275 named parts each).
- [falcon_heavy/](falcon_heavy/README.md): Falcon Heavy full vehicle — three
  cores with 27 linked Merlin 1D instances, MVac-derivative second stage,
  cutaway and exploded views (~2,150 named parts each).

These packages cross-reference each other by sibling relative path
(`../raptor2/`, `../merlin1d/`), so they must stay siblings in this directory.

## Robot description packages

- [juno/](juno/README.md): Juno humanoid — full biped robot description with
  per-link STEP generators, 3MF meshes, URDF/SRDF, and a parameter sidecar.
- [lyra/](lyra/README.md): Lyra dexterous hand — five-digit robot hand with
  per-link STEP generators, 3MF meshes, URDF/SRDF, and a parameter sidecar.

These two carry URDF/SRDF but live here rather than in `../robots/` because
they are authored concept packages, not the imported robot fixtures that
`../robots/` collects.

## Per-package `render/` folders

Some packages keep a `render/` (or `renders/`) subfolder holding snapshot job
templates and presentation-theme JSON. Those configs are committed; the
generated PNG/GIF output beside them stays gitignored per the repo-wide media
rules in `.gitignore`.
