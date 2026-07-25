# PyBullet API for Sim Test

Long-form notes and copyable snippets for headless mechanism validation
with PyBullet. This is an API guide, not a scenario list: pick what serves
the mechanism you are validating.

## Connecting and loading

```python
import pybullet as p
import pybullet_data

p.connect(p.DIRECT)                      # headless, no GUI
p.setAdditionalSearchPath(pybullet_data.getDataPath())
p.setGravity(0, 0, -9.81)
p.setTimeStep(1.0 / 240.0)               # default; go finer only when needed

plane_id = p.loadURDF("plane.urdf")      # optional ground
body_id = p.loadURDF("models/mech/mech.urdf", basePosition=[0, 0, 0.01])
```

- `p.DIRECT` runs without a display and is the right mode for tests.
- `loadURDF` returns a body unique id used by every later call. `useFixedBase=True`
  anchors the base link for rig-style mechanisms.
- SDF files load via `p.loadSDF("world.sdf")`, which returns a list of body
  ids.

## Inspecting the model

```python
p.getNumJoints(body_id)
info = p.getJointInfo(body_id, j)
# info[1]  joint name (bytes)
# info[2]  joint type: p.JOINT_REVOLUTE / JOINT_PRISMATIC / JOINT_FIXED / ...
# info[8], info[9]  lower and upper limits
```

Build a name-to-index map once; joint indices are stable for the session:

```python
joint_ix = {
    p.getJointInfo(body_id, j)[1].decode(): j
    for j in range(p.getNumJoints(body_id))
}
```

## Driving joints

```python
p.setJointMotorControl2(
    body_id, joint_ix["rotor"],
    controlMode=p.VELOCITY_CONTROL,
    targetVelocity=10.0,      # rad/s for revolute, m/s for prismatic
    force=5.0,                # max motor force/torque
)
```

- Control modes: `POSITION_CONTROL`, `VELOCITY_CONTROL`, `TORQUE_CONTROL`.
- In `VELOCITY_CONTROL`, `force` caps the motor authority; an unrealistically
  large value hides binding and friction problems. Size it like the real
  actuator when the design names one.
- `POSITION_CONTROL` accepts `positionGain`/`velocityGain` when servo
  stiffness matters.

## Stepping and reading state

```python
for _ in range(240):          # one simulated second at 1/240 s
    p.stepSimulation()

pos, vel, reaction_forces, motor_torque = p.getJointState(body_id, joint_ix["rotor"])
link_state = p.getLinkState(body_id, link_index)   # world pose of a link
linear_vel, angular_vel = p.getBaseVelocity(body_id)
```

- Let driven mechanisms settle before asserting: read the value after a
  fixed settle window, and prefer asserting a band (`min <= v <= max`) over
  an exact number.
- `p.getJointState` velocity units are rad/s (revolute) or m/s (prismatic).
  RPM = rad/s * 60 / (2*pi).

## Contacts

```python
contacts = p.getContactPoints(bodyA=body_id, bodyB=other_id)
for c in contacts:
    link_a, link_b = c[3], c[4]
    position_on_b, normal_on_b = c[6], c[7]
    penetration_depth = c[8]   # negative means penetration
```

- Filter by `bodyA`/`bodyB`, or by `linkIndexA`/`linkIndexB` for
  link-pair checks (gear teeth vs. housing).
- Assert both directions as the design requires: contact that must happen
  (mesh, cam follower) and contact that must never happen (rotor tip vs.
  wall, lid vs. frame at closed position).
- A persistently negative `contactDistance` beyond a small tolerance flags
  interpenetrating geometry — usually a URDF collision-mesh problem.

## Friction and dynamics

```python
p.changeDynamics(body_id, link_index, lateralFriction=0.8)
p.changeDynamics(body_id, -1, mass=0.5)          # -1 addresses the base
```

- Defaults are low (`lateralFriction` around 0.5). Set values that match
  the intended material pair when slip behavior is under test.
- Spinning friction and rolling friction (`spinningFriction`,
  `rollingFriction`) matter for wheels and balls, rarely for hinges.

## Putting it together: test skeleton

Guard engine imports with `pytest.importorskip` so a part's test suite
still collects on platforms where the chosen engine has no wheel
(PyBullet ships Linux wheels only):

```python
import pytest

p = pytest.importorskip("pybullet")


@pytest.fixture(scope="module")
def sim():
    p.connect(p.DIRECT)
    p.setGravity(0, 0, -9.81)
    body = p.loadURDF("models/<part-name>/<mech>.urdf", useFixedBase=True)
    yield body
    p.disconnect()


def test_motor_reaches_speed_band(sim):
    p.setJointMotorControl2(sim, 0, p.VELOCITY_CONTROL,
                            targetVelocity=TARGET_RAD_S, force=MAX_TORQUE)
    for _ in range(480):
        p.stepSimulation()
    velocity = p.getJointState(sim, 0)[1]
    assert LOW_RAD_S <= velocity <= HIGH_RAD_S
```

## Performance guidance

- Most behavior questions resolve within 240-1200 steps. Treat runs beyond
  a few simulated seconds as exceptional and justify them.
- Keep timestep at the default unless contact jitter or tunneling appears;
  halving the timestep doubles cost.
- One `p.connect` per test module (fixture, `scope="module"`), one
  `p.disconnect` at teardown. Reconnecting per test doubles runtime and
  leaks physics server instances on failure paths.
- `p.resetSimulation()` inside a module fixture lets several tests share a
  connection while starting clean.
