# MuJoCo as a Contact-Fidelity Alternative

PyBullet is the primary engine for this skill. Switch to MuJoCo only when
you decide the test hinges on contact fidelity that PyBullet's rigid
contact model cannot deliver. This reference exists so that switch is a
deliberate, documented choice — not a default.

## When the switch is worth it

- Gear meshing, cam profiles, or threaded interfaces where tooth-level
  contact forces drive the conclusion.
- Stacked or wedged contacts (drawer slides under load, jamming analysis)
  where PyBullet's contact softness hides or invents binding.
- Grasping and high-count simultaneous contacts where solver quality
  changes the outcome.
- **Platform availability**: PyBullet publishes Linux wheels only (as of
  3.2.7). On Windows or macOS you must build it from source (MSVC/Xcode
  toolchain) or run under WSL2; MuJoCo ships prebuilt wheels for all three
  platforms, so it is the pragmatic engine off Linux even when contact
  fidelity is not the driver.

For limit checks, speed bands, slip-vs-hold friction tests, and
gross-collision checks, PyBullet is sufficient and much simpler — on
platforms where it installs cleanly.

## Practical differences

- **Model format**: MuJoCo's native format is MJCF (XML). It can import
  URDF via its compiler, but SDF is not supported — SDF-defined mechanisms
  would need a URDF or MJCF conversion first.
- **Install**: `pip install mujoco` ships prebuilt wheels; headless works
  out of the box. The API is `mujoco.MjModel`/`MjData` plus
  `mujoco.mj_step`, lower-level than PyBullet's convenience calls.
- **Units**: same SI conventions as URDF, so the unit/scale pitfalls in
  `references/urdf-sdf-integration.md` apply unchanged.
- **Contact model**: soft contacts with configurable solver parameters
  (`solref`, `solimp`); expect to tune per-mechanism rather than relying
  on defaults.

## Minimal sketch

```python
import mujoco

model = mujoco.MjModel.from_xml_path("models/mech/mech.urdf")
data = mujoco.MjData(model)

for _ in range(2000):
    data.ctrl[0] = TARGET_TORQUE_OR_POSITION
    mujoco.mj_step(model, data)

rotor_velocity = data.qvel[0]
```

## Cost of switching

- A second engine to install, learn, and keep in requirements; the
  mechanism definition may need MJCF-specific adjustments (compiler
  settings, contact pairs, excludes).
- Test results are not portable between engines: a speed band that passes
  in PyBullet can shift under MuJoCo's contact model. Record which engine
  a test ran on in the iteration log.

If you switch for a specific part, say so in the design note and the
iteration log, with the contact-fidelity reason.
