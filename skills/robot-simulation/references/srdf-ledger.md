# SRDF planning ledger

Read this before writing a `.srdf`. Its ledger is a comment block that opens the file, as a URDF's
does ([urdf-ledger.md](urdf-ledger.md)), for what the SRDF's XML cannot say: what the semantics are
for, and where each choice came from.

```xml
<?xml version="1.0"?>
<!--
  srdf: example_arm | urdf: example_arm.urdf | task: arm IK and gripper control
  groups: arm (chain base_link -> tool0, the IK group), gripper (finger_joint)
  tcp: tool0, on the flange face
  states: arm/home, the rest pose (radians, within the URDF's limits)
  disabled collisions: URDF-adjacent pairs only (reason Adjacent)
  assumptions: tool0 is the TCP; no sampled collision matrix yet
-->
```

What each line answers for:

- **task**: what is planned (arm IK, a plan to a pose, a gripper, a mobile base, two arms), the
  primary group, the solver or planner expected, and whether IK constrains orientation or position
  alone.
- **groups**: what each is for, and why its base and tip or its members. Also why each virtual and
  passive joint is there.
- **tcp**: the link a pose target means ([srdf-end-effectors.md](srdf-end-effectors.md)).
- **states**: what each named pose is for.
- **disabled collisions**: where the pairs came from
  ([srdf-disabled-collisions.md](srdf-disabled-collisions.md)).
- **assumptions**: one line for every choice that was inferred: a group's member, a chain's end, the
  TCP, a virtual joint's frame, a joint taken as passive, a state's values, a pair disabled by hand,
  a solver setting, a MoveIt check that was not run.
