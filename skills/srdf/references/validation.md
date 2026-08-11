# SRDF Validation and Verification

Every created or modified `.srdf` runs this recipe before the task is reported complete.

## Recipe

1. **Bundled validator** (always): `python scripts/validate path/to/robot.srdf`. It collects *all* findings in one pass (severity, code, XML path); fix them and re-run until clean. Use `--strict` to fail on warnings and `--format json` for machine-readable output.
2. **Viewer review** (whenever `$cad-viewer` is available): load the SRDF, confirm the paired URDF resolves and renders, and exercise named group states. Include MoveIt2 controls for IK/path review when the task needs them.
3. **MoveIt smoke test** (when a MoveIt environment is available): load the URDF+SRDF pair in MoveIt Setup Assistant or a project launch; solve IK for the primary group; plan to a named state. Report as skipped when unavailable.

## What the Bundled Validator Checks

Structure and linkage:

- root is `<robot>` with a non-empty name;
- a paired URDF resolves: exactly one `.urdf` in the same folder declares the SRDF's robot name (`no_paired_urdf` / `ambiguous_paired_urdf` errors otherwise); a leftover `<tcad:urdf>`/`<explorer:urdf>` element warns as deprecated and is ignored;
- unique group, end-effector, group-state, and collision-pair identities.

Against the paired URDF:

- every group joint/link/subgroup name exists (joints in the URDF, links in the URDF, subgroups in the SRDF);
- every chain `base_link`/`tip_link` exists **and** the chain is a real parent→child path in the URDF tree;
- subgroup references contain no cycles;
- at least one planning group is defined;
- virtual joints: valid type (`fixed`/`floating`/`planar`), non-empty `parent_frame`, `child_link` exists in the URDF (name collisions with URDF joints warn);
- passive joints exist in the URDF and are never set by group states;
- end effectors: group exists, parent group exists when named, parent link exists, no link overlap between EE group and parent group, parent link in parent group or adjacent to the EE group;
- group states: group exists, each joint exists and belongs to the group, no fixed/mimic/passive joints, values within URDF revolute/prismatic limits; states that omit group joints warn (MoveIt fills them from the current state);
- disabled collisions: both links exist, distinct, non-empty reason, no (reversed) duplicates; pairs claiming reason `Adjacent` that are not actually joined by a URDF joint warn; warns when 25+ pairs are manually reasoned;
- unknown elements under `<robot>` or `<group>` warn — misspelled elements are otherwise silently ignored by MoveIt;
- a paired URDF that is not a single-rooted tree warns (chain/adjacency checks become unreliable).

## What Validation Cannot Prove

- That the planning group matches the user's task intent (right arm vs left arm).
- That the TCP/target link is the physically correct tool point.
- That disabled pairs are safe at every reachable configuration — only sampling (Setup Assistant) approaches that.
- That group-state poses are collision-free or useful.

These are semantic decisions: document them in the ledger and verify interactively in the viewer or MoveIt when confidence matters. Visual rendering review alone cannot prove planning correctness.

## Failure Handling

When validation fails against the URDF, decide which side is wrong before editing: a missing name may mean a typo in the SRDF **or** a rename in the URDF that invalidated existing semantics. Fix the owning file (`$urdf` for structure), then re-run the validator on the pair.
