# Loading URDF/SDF Skill Output into PyBullet

How to connect mechanisms produced by the URDF and SDF skills to a
PyBullet session, and the pitfalls that most often invalidate a test
before physics even runs.

## Loading

```python
import pybullet as p

body_id = p.loadURDF("models/mech/mech.urdf", basePosition=[0, 0, 0.0])
body_ids = p.loadSDF("models/mech/world.sdf")   # returns a list
```

- `loadURDF` resolves relative mesh paths against the URDF file's
  directory, then against `p.setAdditionalSearchPath(...)` entries. Run the
  test from a working directory where those relative paths resolve, or pass
  absolute search paths.
- `flags=p.URDF_USE_SELF_COLLISION` enables self-collision when the design
  needs it (gripper fingers, folding linkages); it is off by default and
  off is right for most assemblies.
- `useFixedBase=True` for bench-style mechanisms whose base must not move;
  leave it off for free bodies (vehicles, thrown parts).

## Mesh references

- URDF `<mesh filename="..."/>` entries must resolve at load time. A
  missing mesh does not fail the load loudly in every PyBullet build —
  check the console output of the fixture, and assert
  `p.getNumJoints`/`p.getNumLinks` match the expected structure as a cheap
  structural smoke check.
- Visual and collision meshes are separate in well-formed URDF. Simulation
  uses the collision geometry; a beautiful visual mesh says nothing about
  contact behavior. If collision geometry is missing or a coarse
  placeholder, contact tests are meaningless — flag it in the design note.

## Units and scale

- URDF is SI: meters, radians, kilograms. The CAD skill models in
  millimeters; the URDF skill's generator handles conversion, but a mesh
  exported at millimeter scale and referenced without a `scale` attribute
  loads 1000x too large. When a mechanism behaves absurdly (exploding
  contacts, instant penetration), check mesh scale first.
- PyBullet reports joint positions in radians/meters and velocities in
  rad/s / m/s. Convert to RPM or mm/s only at the assertion boundary.
- STL meshes carry no units; OBJ/GLB conventions vary. Confirm what the
  CAD skill exported before trusting a collision shape.

## Inertials and mass

- Links with missing or near-zero mass produce unstable dynamics under
  motor torque. The URDF skill validates inertials at generation time; if
  you bypass that path, check `p.getDynamicsInfo(body_id, link)` masses
  before blaming the motor model.
- Tiny masses with large motor forces cause solver jitter; scale the
  motor `force` limit to the mechanism's real actuator when the design
  names one.

## Joint semantics

- PyBullet's joint sign convention follows the URDF axis: positive target
  velocity spins around the positive axis. When a mechanism "runs
  backwards", the fix belongs in the generator's axis definition, not in a
  negated test expectation.
- URDF `continuous` joints have no limits; `revolute` limits are enforced
  by most consumers but PyBullet does not hard-stop at them by default —
  assert limit compliance yourself if the design requires it.

## SDF specifics

- `p.loadSDF` returns a list of body ids, one per model in the file; map
  them by order or by `p.getBodyInfo`.
- SDF worlds may include their own gravity and physics tags; PyBullet
  applies its own global settings, so set gravity explicitly in the test
  rather than assuming the SDF values carried over.
