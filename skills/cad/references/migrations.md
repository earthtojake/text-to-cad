# Migrations

A project written for cadgen 0.7 does not run on 0.8, and nothing it prints points here:
0.8 has no compatibility layer, so a retired name fails as an unknown one does. The full
migration is the guide, followed top to bottom:

- [Migrating a CAD project from cadgen 0.7 to 0.8](https://github.com/earthtojake/text-to-cad/blob/main/docs/migrations/migrating-0.7-to-0.8.md)
  (in a text-to-cad checkout, `docs/migrations/migrating-0.7-to-0.8.md`)

## A 0.7 project

Any one of these says the project was written for 0.7:

- `from cadgen import build123d as bd`, or `from cadgen.build123d import ...`
- `@step(out=..., kinematics=..., materials=..., animation=...)`; `revolute(...)`,
  `fastened(...)`, `couple(...)` or `srgb(...)` from cadgen; `read_scene`
- an `animation=` string of JavaScript (`export const clips = ...`)
- `<name>.step.json` sidecars or `.params.js` files beside its STEP files
- project notes (a README, agent instructions) that run
  `uvx ... --from cadgen==0.7.x python ...`, `--force`, `cadgen store why` or
  `cadgen step snapshot`, or open `?file=` links
- under 0.8, its first run stops at
  `ImportError: cannot import name 'build123d' from 'cadgen'`

## First

1. Run the project's scripts with this skill's `python` and `cadgen`, never the 0.7 command
   its docs pin (that keeps building on 0.7), with the project's `PYTHONPATH` set.
2. Keep a STEP the project's 0.7 build wrote, to compare placements part by part at the
   end: a stage that moves parts inside a sub-assembly can build on 0.8 with some parts a few
   millimetres off and nothing said.
3. Follow the guide's checklist in order, rerunning the root script after each step: each
   error names the next thing 0.8 wants. Tell the person before deleting 0.7 files.

## Open CASCADE 8 and build123d 0.13

cadgen 0.8.1 replaces cadgen materials with native `bd_materials` objects and rebuilds
earlier XBF documents from source. Models importing OCP directly may also need renamed
collections, downcasts and bounding-box reads. See [the Open CASCADE 8 migration guide](https://github.com/earthtojake/text-to-cad/blob/main/docs/migrations/migrating-to-opencascade-8.md).
