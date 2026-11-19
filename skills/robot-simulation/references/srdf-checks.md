# SRDF checks

Read this when a `.srdf` or the URDF beside it changed, or a check's result has to be read.
[Check each change](../SKILL.md#check-each-change) has the commands; this is what
`cad srdf validate` covers and what a clean result leaves open.

## The validator

```bash
cad srdf validate path/to/robot.srdf --strict
```

```text
OK robot.srdf: robot 'example_arm', urdf example_arm.urdf, 2 groups, 1 end effectors, 1 group states, 1 disabled collision pairs, 1 virtual joints
```

- **Two phases.** The SRDF alone first (its XML, names, duplicates, numeric state values, a reason
  on every pair), then every name, chain, state and pair against the URDF. An error in the first
  stops the second, so a short first report is not a short list of problems: fix and run again.
- **The URDF** is the one beside it with the same robot name, or the one `--urdf` names
  ([pairing](srdf-authoring.md#urdf-pairing)). A URDF with an error of its own is
  `invalid_paired_urdf`, with the first of its errors: run `cad urdf validate` for the rest.
- **A URDF that is not one rooted tree** is only a warning, `paired_urdf_not_a_tree`, and every
  check against it is skipped: the SRDF passes on its own structure. Fix the URDF and run again
  before trusting that result.
- **Errors against the URDF**: a name it does not hold, a chain that is not a parent-to-child path,
  a cycle of subgroups, no group or an empty one, an end effector that breaks its rules
  ([srdf-authoring.md](srdf-authoring.md#end-effectors)), and a state that sets a fixed, mimic or passive
  joint, a joint outside its group, or a value past the URDF's limits.
- **Warnings**, which pass unless `--strict`: a state that leaves out joints of its group, which
  MoveIt fills from wherever the robot is; a pair whose reason is not borne out
  ([srdf-authoring.md](srdf-authoring.md#disabled-collisions)); a virtual joint that takes a URDF
  joint's name; and an unknown element under `<robot>` or `<group>`, a misspelled tag that MoveIt
  ignores silently.
- **A group or a state that names a virtual joint** is reported as a missing name, since group
  joints are looked up in the URDF alone. MoveIt reads a virtual joint as a joint of the robot, and a
  mobile base's group lists one: report it as the check's limit, not the file's fault.

## What a clean result leaves open

- **Whether the group suits the task**: the right arm and not the left, the right tip.
- **Whether the TCP link is the tool point.**
- **Whether a disabled pair is safe** in every pose the robot can reach. Only sampling approaches
  that.
- **Whether a state is collision-free or useful.** A value typed in degrees is caught only where it
  passes a limit.
- **That a picture means a valid file.** `cad srdf snapshot` runs no validation and draws SRDFs the
  validator fails (a chain that is no path, a state past a limit). The viewer does not: its page
  refuses one, with the validator's errors.
- **That MoveIt plans with it.** Where MoveIt is at hand, load the pair (Setup Assistant, or the
  project's launch), solve IK for the primary group, plan to a pose and to a named state, and run a
  collision check. Where it is not, report that as skipped.

When a name is missing, decide which file is wrong before editing: a typo in the SRDF, or a rename
in the URDF that the SRDF never followed.
