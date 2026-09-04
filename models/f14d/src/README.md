# f14d models

| Script   | Artifact         | Description                                        |
|----------|------------------|----------------------------------------------------|
| f14d.py  | STEP/f14d.step   | Grumman F-14D Super Tomcat, whole aircraft, clean: the ten system models below, linked in occurrence order |
| airframe.py | STEP/airframe.step | `o1.1` the one-piece blended skin, cut and detailed |
| cockpit.py | STEP/cockpit.step | `o1.2` tub, panels, seats, HUD, canopy, windscreen |
| wings.py | STEP/wings.step | `o1.3` panels, slats, flaps, spoilers, tip lights |
| inlets.py | STEP/inlets.step | `o1.4` ramps, splitters, bleed slots, ducts |
| nozzles.py | STEP/nozzles.step | `o1.5` C-D nozzles, petals, seals, actuator rings |
| empennage.py | STEP/empennage.step | `o1.6` fins, rudders, stabilators, ventral fins |
| aft.py | STEP/aft.step | `o1.7` speed brakes, beavertail, tailhook, dump mast |
| nose_gear.py | STEP/nose_gear.step | `o1.8` leg, wheels, launch bar, doors, bay |
| main_gear.py | STEP/main_gear.step | `o1.9` legs, wheels, brakes, doors, bays |
| details.py | STEP/details.step | `o1.10` antennas, probes, lights, wicks, vents, panels |

Build: `python src/f14d.py` builds the aircraft and every stale system beneath
it (in parallel, one worker each) and links their results; unchanged models
are no-op. `python src/<system>.py` builds one system alone — the aircraft does
not pick it up until `f14d.py` is rerun. It is a long build cold (the
airframe skin's structural cuts dominate, ~6 minutes on their own), so let it
run; every other system is done long before the airframe is.

`f14d.anim.js` is not a model — it is the choreography module `f14d.py`
declares with `animation=`, and the CAD Viewer's Animation tab is its only
consumer (clips: `teardown`, `explodedHold`). It sits beside its script.

`lib/` is the shared part library: one module per aircraft system, each
exporting `build()`, wrapped by the model of the same stem under `src/`.
Nothing in `lib/` is runnable. The SYSTEMS list in `f14d.py` IS the occurrence
order (`o1.1` airframe through `o1.10` details); read its docstring before
adding or removing a system: a new group renumbers every occurrence after it
and `f14d.anim.js` must be renumbered in the same commit. Which skin cutters
the airframe applies (and which were dropped as too costly) is decided in
`src/airframe.py`.

Project tooling lives outside `src/` because it is not model code:

- `../validate.py` — bilateral-symmetry check plus `inspect validate` and
  `inspect interfere`.
- `../render/` — review-render helpers (`shot.py`, `gauntlet.py`, `part.py`,
  `ab.py`, `subrefs.py`) and the committed presentation theme/display JSON.
  `subrefs.py` regenerates the act-2 occurrence-id lists in `f14d.anim.js`.
  All of them write to `../tmp/`.
