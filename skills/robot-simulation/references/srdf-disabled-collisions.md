# SRDF disabled collisions

Read this when writing or changing `<disable_collisions>`. A planner never checks a disabled pair,
so a wrong one hides a real collision: each pair comes from evidence, never from how the robot
looks.

```xml
<disable_collisions link1="base_link" link2="shoulder_link" reason="Adjacent" />
```

## Where a pair comes from

- **Adjacency**: two links one URDF joint joins, listed from the URDF's joints (a few lines of
  script on a large robot).
- **Sampling**: MoveIt Setup Assistant's self-collision matrix, or collision sampling in a known
  MoveIt configuration, dense enough to cover the poses the task reaches.
- **A matrix the person gives.**
- **A pair reviewed by hand**, with what was reviewed written in its reason.

A matrix goes stale when geometry, limits or group membership change: derive it again.

## What the validator reads in a reason

`cad srdf validate` requires a `reason` on every pair, and refuses a pair of one link with itself
and a pair given twice, in either order. Then it reads the reason's words:

- One that contains `adjacent` is held to the URDF: a warning where no joint joins the two links.
- One that contains none of `adjacent`, `never`, `always`, `default`, `sample`, `setup`, `assistant`
  or `assum` counts as reasoned by hand (`User`, `Manual: fixture is outside the workspace`). 25 or
  more of those warn: regenerate the matrix by sampling instead.

So write the reason that is true: Setup Assistant's own word where it made the pair (`Adjacent`,
`Never`, `Always`, `Default`), and `assumed` only where the person asked for a provisional SRDF and
the report says so.
