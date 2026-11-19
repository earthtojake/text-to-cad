# SRDF end effectors

Read this when writing or changing an `<end_effector>`.

```xml
<end_effector name="gripper_eef" parent_link="tool0" group="gripper" parent_group="arm" />
```

`cad srdf validate` holds each one to this:

- `group` is a group of this SRDF, as is `parent_group` where one is given, and `parent_link` is a
  link of the URDF.
- The two groups share no link. A group's links are the ones it lists and the child link of each of
  its joints, so a chain holds its tip and not its base.
- `parent_link` is a link of `parent_group`, where one is given, and is in the end-effector group or
  joined to one of its links by a joint.

An `<end_effector>` says where the tool attaches, not where it acts, and no check knows the tool
point. Record the TCP link in the ledger ([srdf-ledger.md](srdf-ledger.md)), and name it when
handing the SRDF on wherever it is not the tip a consumer would take from the group.
