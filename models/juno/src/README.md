# juno models

`juno.py` is the full robot; the other 28 scripts each build ONE URDF link in
its own part-local frame, exporting both a STEP part and the millimetre 3MF
mesh that `../juno.urdf` references. The robot composes those same models by
CALLING them — a stale link builds on its own worker, a current one loads,
and the robot links its tree — so the assembly and the URDF meshes can never
disagree, and rebuilding a link alone leaves the robot to be rerun.

| Script | Artifact | Description |
|---|---|---|
| juno.py | STEP/juno.step | Full 28-occurrence humanoid assembly, 27 revolute mates + 5 pose presets, `juno.anim.js` choreography |
| pelvis.py | STEP/pelvis.step + 3MF/pelvis.3mf | Pelvis link (waist-yaw center at the origin) |
| torso.py | STEP/torso.step + 3MF/torso.3mf | Torso link |
| neck_collar.py | STEP/neck_collar.step + 3MF/neck_collar.3mf | Neck collar link |
| head.py | STEP/head.step + 3MF/head.3mf | Head link |
| hip_bracket_{left,right}.py | STEP/… + 3MF/… | Hip yaw-to-roll bracket |
| hip_carrier_{left,right}.py | STEP/… + 3MF/… | Hip roll-to-pitch carrier |
| thigh_{left,right}.py | STEP/… + 3MF/… | Thigh segment |
| shin_{left,right}.py | STEP/… + 3MF/… | Shin segment |
| ankle_link_{left,right}.py | STEP/… + 3MF/… | Ankle pitch-to-roll link |
| foot_{left,right}.py | STEP/… + 3MF/… | Foot |
| shoulder_pod_{left,right}.py | STEP/… + 3MF/… | Shoulder pitch-to-roll pod |
| yaw_housing_{left,right}.py | STEP/… + 3MF/… | Shoulder roll-to-yaw housing |
| bicep_{left,right}.py | STEP/… + 3MF/… | Upper arm |
| forearm_{left,right}.py | STEP/… + 3MF/… | Forearm |
| wrist_carrier_{left,right}.py | STEP/… + 3MF/… | Wrist roll-to-pitch carrier |
| hand_{left,right}.py | STEP/… + 3MF/… | Five-digit hand |

Build one: `python src/<script>.py`; unchanged models are no-ops.
Build the lot: `ls src/*.py | xargs -n1 -P4 python`.

`src/lib/` holds the shared part builders (`chain.py` is the kinematic
chain/pose/limit spec mirrored by `../juno.urdf` and `../juno.srdf`;
`juno_lib.py` is the shared style/geometry vocabulary). Nothing in `lib/` is
a model — it carries no `@step`.

`juno.anim.js` sits beside `juno.py` and is copied verbatim into
`STEP/juno.step.json` at build time.
