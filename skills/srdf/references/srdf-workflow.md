# SRDF Workflow

Use this reference when creating or editing MoveIt planning semantics for an existing URDF.

## Step 0: Extract the URDF Table

Do this before writing any SRDF XML. Parse the paired URDF (read it, or run a three-line ElementTree script for large robots) and write down:

- robot `name` (the SRDF must match it exactly);
- every link name;
- every joint: name, type, parent link, child link, lower/upper limits, and whether it has `<mimic>`;
- the root link and the main serial chains (walk parent→child).

Every name that appears in the SRDF is **copied from this table**. If a name you want is not in the table, the URDF is wrong or your assumption is — resolve that first with `$urdf`. This single habit eliminates the most common SRDF failure class: plausible near-miss names and chains that do not exist in the tree.

## Edit Loop

1. Confirm the URDF is valid (`$urdf` validator) and extract the URDF table.
2. Read or create the planning ledger (`references/planning-ledger.md`); keep the compact form as a comment block in the `.srdf`.
3. Author or edit the SRDF XML directly per `references/authoring-contract.md`, in element order: virtual joints, groups, group states, end effectors, passive joints, disabled collisions. Save it next to the URDF with the same robot name — colocation plus name match is how every consumer pairs the files.
4. Derive — do not invent — disabled collisions (`references/disabled-collisions.md`) and group-state values (URDF-native units, within limits).
5. Validate with `python scripts/validate <file.srdf>`; fix findings until clean.
6. Hand the file to `$cad-viewer`; include MoveIt2 controls when interactive IK/planning review is needed.
7. Run MoveIt smoke tests when a MoveIt environment is available; otherwise report them skipped.
8. Report assumptions: inferred TCP links, manual collision pairs, unverified planner behavior.

## Group Design

- **Serial manipulator** → one chain group, `base_link` at the mount, `tip_link` at the flange/TCP link. The validator rejects chains that are not a real parent→child path.
- **Gripper / hand** → joint-member group listing its actuated joints; it becomes the end-effector group.
- **Dual-arm / whole-body** → subgroup unions. Check for duplicate semantics (a joint reachable through two subgroups) and cycles.
- **Mobile base** → typically a planar/floating virtual joint plus a group for the base; do not model wheel joints as planning DOF unless the planner consumes them.

Fixed and mimic joints are never planning variables: they do not belong in group states, and chain-derived groups exclude them automatically.

## When the URDF Changes

Renamed links or joints, changed limits, or restructured chains invalidate the SRDF silently. After any URDF edit, re-run the SRDF validator on the paired `.srdf`, and re-check group states against the new limits. Treat URDF+SRDF as a pair in every task that touches either.
