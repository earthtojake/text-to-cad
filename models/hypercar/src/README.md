# hypercar models

| Script          | Artifact           | Description                                    |
|-----------------|--------------------|------------------------------------------------|
| hypercar.py     | STEP/hypercar.step | Mid-engine hypercar, full assembly: the 13 system models below, linked in occurrence order |
| body.py | STEP/body.step | painted panels, pillars, aero skins |
| glazing.py | STEP/glazing.step | DLO glass + lamp lenses |
| lighting.py | STEP/lighting.step | lamp internals + light signature |
| chassis.py | STEP/chassis.step | monocoque tub, subframes, crash structures |
| suspension_front.py | STEP/suspension_front.step | wishbones, uprights, pushrods, rockers, coilovers |
| suspension_rear.py | STEP/suspension_rear.step | the same, rear |
| wheels.py | STEP/wheels.step | rims, tyres |
| brakes.py | STEP/brakes.step | discs, calipers, hubs |
| powertrain.py | STEP/powertrain.step | engine, intake, exhaust, transaxle, driveshafts |
| interior.py | STEP/interior.step | seats, wheel, dash, console, pedals, door cards |
| aero.py | STEP/aero.step | splitter, diffuser, wing |
| hinge.py | STEP/hinge.step | dihedral synchro-helix door mechanism |
| details.py | STEP/details.step | mirrors, badges, filler, vents, fasteners |

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
- `ANIMATION` in `hypercar.py` — clips for the showcase tour, door loop, and
  explode loop, baked to keyframes in the car's sidecar at build time.
- `../render/` — authored presentation config for beauty renders, kept at the
  project root because it is neither code nor an artifact:

  ```bash
  cadgen step snapshot STEP/hypercar.step tmp/beauty.png \
    --theme render/presentation_theme.json \
    --display render/presentation_display.json
  ```

## Assembly order

The order of `SYSTEMS` in `hypercar.py` is the occurrence order; the animation
clips address systems and parts by name, so the order carries nothing else.

    body   glazing   lighting   chassis
    suspension_front   suspension_rear   wheels   brakes
    powertrain   interior   aero   hinge   details

## Kinematics

The dihedral synchro-helix doors are typed mates on the decorator: one
`cylindrical` per door (62 deg of rotation coupled to 310 mm of travel about
the same tower axis) plus a `fastened` mate for each part that rides the door,
all geared by the `doors` coupling. Poses: `shut` (0) and `open` (1).

```bash
cadgen step snapshot STEP/hypercar.step tmp/open.png --kinematics open
```
