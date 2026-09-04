# hypercar models

| Script          | Artifact           | Description                                    |
|-----------------|--------------------|------------------------------------------------|
| hypercar.py     | STEP/hypercar.step | Mid-engine hypercar, full assembly: the 13 system models below, linked in occurrence order |
| body.py | STEP/body.step | `o1.1` painted panels, pillars, aero skins |
| glazing.py | STEP/glazing.step | `o1.2` DLO glass + lamp lenses |
| lighting.py | STEP/lighting.step | `o1.3` lamp internals + light signature |
| chassis.py | STEP/chassis.step | `o1.4` monocoque tub, subframes, crash structures |
| suspension_front.py | STEP/suspension_front.step | `o1.5` wishbones, uprights, pushrods, rockers, coilovers |
| suspension_rear.py | STEP/suspension_rear.step | `o1.6` the same, rear |
| wheels.py | STEP/wheels.step | `o1.7` rims, tyres |
| brakes.py | STEP/brakes.step | `o1.8` discs, calipers, hubs |
| powertrain.py | STEP/powertrain.step | `o1.9` engine, intake, exhaust, transaxle, driveshafts |
| interior.py | STEP/interior.step | `o1.10` seats, wheel, dash, console, pedals, door cards |
| aero.py | STEP/aero.step | `o1.11` splitter, diffuser, wing |
| hinge.py | STEP/hinge.step | `o1.12` dihedral synchro-helix door mechanism |
| details.py | STEP/details.step | `o1.13` mirrors, badges, filler, vents, fasteners |

Build: `python src/hypercar.py` builds the car and every stale system beneath
it (in parallel, one worker each) and links their results; `python
src/<system>.py` builds one system alone — the car does not pick it up until
`hypercar.py` is rerun. Unchanged models are no-ops.

## Layout

- `lib/` — the part builders, one module per system (each `build()` returns
  the system's labelled group; the model file of the same stem under `src/`
  wraps it), plus `surfaces.py` (the one master body surface every panel is
  cut from), `palette.py` (colours, authored as sRGB hex) and `context.py`
  (the shared `group`/`style` helpers). Plain modules: no `@step` lives here.
- `../STEP/hypercar.step.js` — the render module beside the document:
  choreography (the showcase tour, the door loop, the explode loop). Authored
  and committed; the viewer loads it by name and no build reads it.
- `../render/` — authored presentation config for beauty renders, kept at the
  project root because it is neither code nor an artifact:

  ```bash
  cadgen step snapshot STEP/hypercar.step tmp/beauty.png \
    --theme render/presentation_theme.json \
    --display render/presentation_display.json
  ```

## Assembly order

The order of `SYSTEMS` in `hypercar.py` IS the occurrence order, and
`hypercar.step.js` targets those ids — do not reorder without updating it.

    o1.1 body   o1.2 glazing   o1.3 lighting   o1.4 chassis
    o1.5 suspension_front   o1.6 suspension_rear   o1.7 wheels   o1.8 brakes
    o1.9 powertrain   o1.10 interior   o1.11 aero   o1.12 hinge   o1.13 details

## Kinematics

The dihedral synchro-helix doors are typed mates on the decorator: one
`cylindrical` per door (62 deg of rotation coupled to 310 mm of travel about
the same tower axis) plus a `fastened` mate for each part that rides the door,
all geared by the `doors` coupling. Poses: `shut` (0) and `open` (1).

```bash
cadgen step snapshot STEP/hypercar.step tmp/open.png --kinematics open
```
