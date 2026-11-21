skill: robot-simulation
fixtures: arm.py -> src/arm.py

## Request

src/arm.py is a CAD model of a two-joint arm (base, upper arm, forearm). I need it in ROS and in MuJoCo: a URDF and an MJCF. All three parts are 6061 aluminium. The base should be the base link ROS expects. Both joints are driven by servos rated 2.9 N*m stall torque and 4.7 rad/s no-load speed. I have weighed the forearm at 85 g including its servo, which is not in the CAD. I also need a tool frame at the tip of the forearm. Validate what you generate and tell me what you checked.

## Expect

Materials on all three parts, `link(base, "base_link")`, `limits(..., effort=2.9, velocity=4.7)` on both joints, `mass(forearm, 85)`, a frame at the forearm's tip (`bd.Pos(0, 0, 100)` in its own frame). `cad urdf validate` and `cad mujoco check` both OK; total mass 0.3673 kg; neither file edited by hand.
