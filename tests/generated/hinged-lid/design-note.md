# Design Note: hinged-lid (QA pipeline end-to-end validation part)

Purpose: end-to-end validation part for the mesh-qa / sim-test QA pipeline.
A small open-top box with a hinged lid — a moving part that exercises both
geometric printability checks and physics simulation.

## Requirements

- Base: open-top box, 60 x 40 x 20 mm, 2.0 mm walls and floor.
- Lid: 60 x 40 mm plate, nominal thickness 2.0 mm, hinged at the back top
  edge through knuckles with a 4.2 mm pin bore.
- Hinge: revolute, 0 to 110 degrees of travel; closed = lid resting on the
  base rim.
- Printability: lid plate must be at least 1.0 mm thick (basis: FDM
  handling wall, see printability-heuristics reference ranges; nominal
  design value 2.0 mm).

## Relevant QA skills

- mesh-qa: watertightness, single-body, bounding-box dimensions, lid plate
  thickness.
- sim-test: hinge settles closed under gravity from an opened position,
  stays within joint limits, no interpenetration with the base.

## Environment note

Sim tests run with MuJoCo in this environment because PyBullet publishes no
Windows wheels; the sim-test skill documents MuJoCo as the deliberate
contact-fidelity alternative.
