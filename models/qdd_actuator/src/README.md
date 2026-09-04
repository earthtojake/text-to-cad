# qdd_actuator models

| Script            | Artifact                  | Description                                                     |
|-------------------|---------------------------|-----------------------------------------------------------------|
| qdd_actuator.py   | STEP/qdd_actuator.step    | Quasi-direct-drive actuator, 4.5:1 planetary, 153 occurrences   |

Build: `python src/qdd_actuator.py`; unchanged models are no-ops.

Kinematics: one virtual DOF, `drive`, in INPUT REVOLUTIONS of the rotor
(0..4.5; 4.5 input turns = one carrier revolution). The coupling gears the
rotor, carrier, both ball cages, the cross-roller cage, and the three planets
off it; each planet's mate parent is the carrier, so its declared angle is the
mesh-relative spin and the orbit rides for free. Poses: `rest`,
`quarter_output`, `full_output`.

Animation (`qdd_actuator.step.js`): `drive` (gear train running), `inspect`
(the same cycle while the stack separates and returns), `teardown` (static
full explosion).
