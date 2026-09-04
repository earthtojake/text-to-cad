# f1 models

| Script  | Artifact       | Description                                       |
|---------|----------------|---------------------------------------------------|
| f1.py   | STEP/f1.step   | F1 concept car — the 28 part models below, linked in the frozen occurrence order |
| front_wing.py | STEP/front_wing.step | `#o1.1` front wing |
| nose.py | STEP/nose.step | `#o1.2` nose |
| monocoque.py | STEP/monocoque.step | `#o1.3` monocoque (survival cell) |
| halo.py | STEP/halo.step | `#o1.4` halo |
| cockpit.py | STEP/cockpit.step | `#o1.5` cockpit furniture |
| sidepod_left.py | STEP/sidepod_left.step | `#o1.6` left sidepod |
| sidepod_right.py | STEP/sidepod_right.step | `#o1.7` right sidepod (the left one's mirror image, from the same factory) |
| engine_cover.py | STEP/engine_cover.step | `#o1.8` engine cover |
| airbox.py | STEP/airbox.step | `#o1.9` airbox |
| floor.py | STEP/floor.step | `#o1.10` floor |
| diffuser.py | STEP/diffuser.step | `#o1.11` diffuser |
| cooling.py | STEP/cooling.step | `#o1.12` cooling (radiators, ducts) |
| power_unit.py | STEP/power_unit.step | `#o1.13` power unit |
| drivetrain.py | STEP/drivetrain.step | `#o1.14` drivetrain |
| rear_wing.py | STEP/rear_wing.step | `#o1.15` rear wing mainplane + endplates |
| drs_flap.py | STEP/drs_flap.step | `#o1.16` DRS flap (rotates in `f1.anim.js`) |
| drs_actuator.py | STEP/drs_actuator.step | `#o1.17` DRS actuator four-bar |
| beam_wing.py | STEP/beam_wing.step | `#o1.18` beam wing |
| suspension_front.py | STEP/suspension_front.step | `#o1.19` front suspension |
| suspension_rear.py | STEP/suspension_rear.step | `#o1.20` rear suspension |
| corner_fl.py | STEP/corner_fl.step | `#o1.21` front-left corner: wheel, brake, upright |
| corner_fr.py | STEP/corner_fr.step | `#o1.22` front-right corner |
| track_rod_left.py | STEP/track_rod_left.step | `#o1.23` left track rod |
| track_rod_right.py | STEP/track_rod_right.step | `#o1.24` right track rod |
| corner_rl.py | STEP/corner_rl.step | `#o1.25` rear-left corner |
| corner_rr.py | STEP/corner_rr.step | `#o1.26` rear-right corner |
| steering_rack.py | STEP/steering_rack.step | `#o1.27` steering rack |
| details.py | STEP/details.step | `#o1.28` details |

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

OCCURRENCE ORDER IS FROZEN — `f1.anim.js` addresses children as `#o1.N` in the
order `assemble()` adds them — one sibling model per row. The table lives in `f1.py`'s docstring; do not
reorder, insert or remove a child without updating both in the same change.

No `kinematics=`: both of this car's mechanisms are CLOSED LOOPS (the DRS is a
planar four-bar, the steering solves each wheel against a fixed-length track
rod), and typed mates evaluate pure forward kinematics on a TREE. Both solves
live in `f1.anim.js`, which is where the teardown belongs anyway. Clips:
`showcase` (the loop-closed timeline: car opens, engine stands alone, engine
opens, both reassemble), `drs`, `steering`, `teardown`, `engine`.

`../f1_stage.appearance.json` is the presentation stage (authored config, not
an artifact) — a cool key from high front-left, a hot rim from behind-right,
and a dark specular floor. Its `_comment` records why the materials are satin
rather than piano-black; read it before retuning.
