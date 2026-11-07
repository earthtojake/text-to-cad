# SDF frame and pose semantics

Use this reference before editing any SDF `<pose>`, `<frame>`, `<joint>`, `<axis>`, `<visual>`, `<collision>`, sensor, or plugin placement.

## Core pose rules

A typical SDF pose is:

```xml
<pose relative_to="some_frame">x y z roll pitch yaw</pose>
```

or, when using quaternion rotation:

```xml
<pose rotation_format="quat_xyzw" relative_to="some_frame">x y z qx qy qz qw</pose>
```

Rules to keep in mind:

- The first three values are position.
- With the default `rotation_format="euler_rpy"`, the pose has six values: `x y z roll pitch yaw`.
- With `rotation_format="quat_xyzw"`, the pose has seven values: `x y z qx qy qz qw`.
- Euler angles are radians by default. `degrees="true"` is valid SDF but should be avoided unless the target explicitly requires it.
- `relative_to` names the frame in which the pose is expressed.
- If `relative_to` is omitted, SDF applies element-specific defaults, commonly the frame of the parent XML element. This may be valid but is easy to misread. Prefer explicit `relative_to` for every nontrivial pose.
- Nested scopes may use `::`, for example `outer_model::inner_model::sensor_frame`.

## Joint pose and axes

For SDF joints:

- `<parent>` names the parent frame or `world`.
- `<child>` names the child frame; `world` is not valid as the child.
- Joint pose defaults are easy to misinterpret. Use explicit `<pose relative_to="...">` when the joint frame is not obviously the child-link frame.
- `<axis><xyz>...</xyz></axis>` is the unit axis vector.
- An axis is expressed in the joint frame unless the axis `expressed_in` attribute specifies another frame.
- `axis2` is used for multi-axis joints such as `revolute2` and `universal`.
- Axis vectors should be finite, nonzero, and normalized.

Record the expected positive motion in the design ledger. Example: “positive shoulder_pan rotates the arm counterclockwise when viewed from +Z.”

## Visual and collision poses

A `<visual>` or `<collision>` pose places that geometry owner relative to its parent frame unless `relative_to` says otherwise. In ordinary model-level use, that parent is the link frame.

Do not use visual offsets to hide a wrong link or joint frame. If a mesh needs an offset because the mesh asset origin is not the link frame, record that fact in the geometry table.

## Named frames

Use `<frame>` when a reusable transform is meaningful:

```xml
<frame name="camera_optical_frame" attached_to="camera_link">
  <pose relative_to="camera_link">0 0 0 -1.57079632679 0 -1.57079632679</pose>
</frame>
```

Frames are useful for sensors, plugins, tool frames, nested models, and repeated placement logic. They also make SDF more auditable.

`attached_to` and `relative_to` are different:

- `attached_to` says what the frame moves with.
- `relative_to` says how the frame's pose numbers are represented.

The `attached_to` chain should not cycle and should eventually resolve to a link, model, world, joint, or another valid frame target.

## LLM guardrails

Do not infer any of the following from prose alone:

- sign of a joint axis;
- frame in which an axis is expressed;
- RPY order or units;
- mesh origin convention;
- `relative_to` frame;
- nested-scope reference;
- sensor optical-frame transform;
- plugin frame/topic semantics.

When data is missing, either ask for the source data or write an explicitly labeled assumption.

## Useful official references

- SDFormat pose semantics: `https://sdformat.org/tutorials?tut=pose_frame_semantics`
- SDFormat pose fields: `https://sdformat.org/spec/1.12/world/`
- SDFormat joint element: `https://sdformat.org/spec/1.12/joint/`
