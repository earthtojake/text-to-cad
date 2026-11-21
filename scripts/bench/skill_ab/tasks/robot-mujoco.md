skill: robot-simulation
fixtures: arm.py -> src/arm.py

## Request

src/arm.py is a CAD model of a two-joint arm (base, upper arm, forearm), all 6061 aluminium. I want to try a controller on it in MuJoCo. Make me a scene: the arm fixed to a floor, a position actuator on each joint (the servos give 2.9 N*m), simple collision shapes rather than the meshes, and a 50 mm wooden cube resting on the floor 250 mm from the base along X. Check the model, then simulate 2 seconds holding the shoulder at 45 degrees and the elbow at 60 degrees, and tell me where the forearm's tip ends up, whether the joints reached their targets, and what the cube did.

## Expect

The robot generated from the CAD model and composed into a scene in code (the skill's MuJoCo function and `MjSpec`), run with `cad run`, not an MJCF typed by hand. `cad mujoco check` on the written scene reports no error. Two position actuators limited to 2.9 N*m. The simulation's own numbers in the reply: both joints within about 2 degrees of 45 and 60, the tip near x = 0.181 m (either sign), z = 0.079 m, and the cube still at rest where it was put (centre 0.025 m above the floor).
