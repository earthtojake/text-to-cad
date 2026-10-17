# f1 models

| Script  | Artifact       | Description                                       |
|---------|----------------|---------------------------------------------------|
| f1.py   | STEP/f1.step   | F1 concept car — the 28 part models below, linked and addressed by name |
| front_wing.py | STEP/front_wing.step | `#front_wing` front wing |
| nose.py | STEP/nose.step | `#nose` nose |
| monocoque.py | STEP/monocoque.step | `#monocoque` monocoque (survival cell) |
| halo.py | STEP/halo.step | `#halo` halo |
| cockpit.py | STEP/cockpit.step | `#cockpit` cockpit furniture |
| sidepod_left.py | STEP/sidepod_left.step | `#sidepod_left` left sidepod |
| sidepod_right.py | STEP/sidepod_right.step | `#sidepod_right` right sidepod (the left one's mirror image, from the same factory) |
| engine_cover.py | STEP/engine_cover.step | `#engine_cover` engine cover: the parts around the shell, linking the model below |
| cover_panel.py | STEP/cover_panel.step | carbon cover shell (linked by `engine_cover.py`; its own model because it is nine tenths of the cover's build time) |
| airbox.py | STEP/airbox.step | `#airbox` airbox |
| floor.py | STEP/floor.step | `#floor` floor |
| diffuser.py | STEP/diffuser.step | `#diffuser` diffuser |
| cooling.py | STEP/cooling.step | `#cooling` cooling (radiators, ducts) |
| power_unit.py | STEP/power_unit.step | `#power_unit` power unit |
| drivetrain.py | STEP/drivetrain.step | `#drivetrain` drivetrain: the running gear, linking the three models below |
| gearbox_casing.py | STEP/gearbox_casing.step | ribbed gearbox casing (linked by `drivetrain.py`; its own model because it is two thirds of the drivetrain's build time) |
| drivetrain_ancillaries.py | STEP/drivetrain_ancillaries.step | hardware bolted to the casing (linked by `drivetrain.py`) |
| rear_structure.py | STEP/rear_structure.step | rear impact structure, pickup carriers, pylon pad, rear light (linked by `drivetrain.py`) |
| rear_wing.py | STEP/rear_wing.step | `#rear_wing` rear wing mainplane + endplates |
| drs_flap.py | STEP/drs_flap.step | `#drs_flap` DRS flap (rotates through the `ANIMATION` clips in `f1.py`) |
| drs_actuator.py | STEP/drs_actuator.step | `#drs_actuator` DRS actuator four-bar |
| beam_wing.py | STEP/beam_wing.step | `#beam_wing` beam wing |
| suspension_front.py | STEP/suspension_front.step | `#suspension_front` front suspension |
| suspension_rear.py | STEP/suspension_rear.step | `#suspension_rear` rear suspension |
| corner_fl.py | STEP/corner_fl.step | `#corner_fl` front-left corner: wheel, brake, upright |
| corner_fr.py | STEP/corner_fr.step | `#corner_fr` front-right corner |
| track_rod_left.py | STEP/track_rod_left.step | `#track_rod_left` left track rod |
| track_rod_right.py | STEP/track_rod_right.step | `#track_rod_right` right track rod |
| corner_rl.py | STEP/corner_rl.step | `#corner_rl` rear-left corner |
| corner_rr.py | STEP/corner_rr.step | `#corner_rr` rear-right corner |
| steering_rack.py | STEP/steering_rack.step | `#steering_rack` steering rack |
| details.py | STEP/details.step | `#details` details |

Build: `python src/f1.py` builds the car and every stale part beneath it (in
parallel) and links their results; `python src/<part>.py` builds one part
alone — the car does not pick it up until `f1.py` is rerun. Unchanged models
are no-ops. The mirrored pairs (sidepods, track rods, the four corners) are
separate models from one `lib/` factory, because STEP cannot express a
reflection.

`lib/` holds the part builders each `src/<part>.py` model wraps. Read the two contracts first: `lib/spec.py` is
the coordinate system, package dimensions, suspension hardpoints, the DRS
four-bar and the material palette; `lib/surfaces.py` is the shared surface
vocabulary (airfoil family, blade family, body lofts) every part module builds
from, so the car has ONE surface language.

CHILDREN ARE ADDRESSED BY NAME — the `ANIMATION` clips in `f1.py` address each child by its model's
name (`#drs_flap`), the name `assemble()` links it under; order carries nothing. The table lives in
`f1.py`'s docstring; adding or removing a child means updating both in the same change.

No `kinematics=`: both of this car's mechanisms are CLOSED LOOPS (the DRS is a
planar four-bar, the steering solves each wheel against a fixed-length track
rod), and typed mates evaluate pure forward kinematics on a TREE. Both solves
live in `f1.py`'s `ANIMATION` clips, which also own the teardown; they read
their hardpoints from `lib/spec.py` and are baked to keyframes in the car's
sidecar when it builds. Clips: `showcase` (the loop-closed timeline: car opens,
engine stands alone, engine opens, both reassemble), `drs`, `steering`,
`teardown`, `engine`.

`../f1_stage.appearance.json` is the presentation stage (authored config, not
an artifact) — a cool key from high front-left, a hot rim from behind-right,
and a dark specular floor. Its `_comment` records why the materials are satin
rather than piano-black; read it before retuning.
