# URDF Validation

Use this reference when validating generated URDF files.

## Structural Checks

Validate that:

- the root element is `<robot>`
- the robot has a non-empty name
- every link has a unique non-empty name
- every joint has a unique non-empty name
- every joint has valid parent and child links
- parent/child links exist
- each child link has at most one parent
- the graph has exactly one root link
- the graph is connected and acyclic
- the tree has exactly `links - 1` joints unless the design intentionally uses a different structure and the validator supports it

## Joint Checks

Supported joint types are:

- `fixed`
- `continuous`
- `revolute`

For revolute joints, validate lower and upper limits. Confirm axes and origins match the intended kinematic behavior.

## Mesh Checks

Validate that visual mesh references:

- are non-empty
- point to supported mesh formats
- resolve from the generated URDF location or package URI convention
- refer to files that exist

If mesh references changed, confirm the corresponding CAD/STL outputs were regenerated separately.

## Tooling

`scripts/gen_urdf --summary` prints a compact robot/link/joint summary after regeneration.

The URDF source reader also validates XML structure with `yourdfpy`, which must be installed in the active Python environment.
