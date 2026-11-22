# URDF: a nonlinear four-bar coupling in the viewer

Read this when a hand-written URDF holds a four-bar whose motion the viewer must show exactly.
`<mimic>` is affine and cannot close one. Keep the links a tree, leave the output joint the one
independent coordinate, and put this namespaced element on the input joint, which it derives:

```xml
<robot name="example" xmlns:tcad="https://text-to-cad.dev/urdf">
  <!-- links and the independent output joint omitted -->
  <joint name="input_crank_joint" type="revolute">
    <parent link="ground_link" />
    <child link="input_crank_link" />
    <origin xyz="0 0 0" rpy="0 0 0" />
    <axis xyz="0 0 1" />
    <limit lower="-0.6" upper="0.7" />
    <tcad:four_bar
      driver="output_joint"
      input_length="0.026"
      ground_length="0.220"
      output_length="0.026"
      coupler_length="0.220"
      input_zero="-1.570796326795"
      output_zero="1.806068683023" />
  </joint>
</robot>
```

- **The numbers.** Lengths are metres. `input_zero` and `output_zero` are the directions of the
  input and the output link when both joints are at zero: angles in radians about the joints' axis,
  from the line that runs from this joint's pivot to the driver's. A four-bar closes two ways for
  one driver angle, and `input_zero` says which: it must be an angle the lengths close at.
- **The joints.** Both are revolute or continuous, on one parent link (the ground), with parallel
  axes that point the same way and pivots in one plane across the axis, `ground_length` apart. The
  input joint carries no `<mimic>`. Its limits must hold everything the driver's range derives (a
  continuous one has none), and the linkage must close over the driver's whole range: its `<limit>`,
  or one turn for a continuous driver.
- **What moves it.** The viewer and `cad urdf snapshot` place the input joint from the driver's
  value. The person cannot pose it in the viewer, a snapshot's `--pose` refuses it by name, and an SRDF group
  state cannot set it, as with a mimic joint.
- **What checks it.** `cad urdf validate` checks the element alone: at most one on a joint, every
  length positive, both zero angles numbers, the joint and its driver revolute or continuous on one
  parent, no cycle of drivers and mimics. The linkage's geometry (the two points above) is checked
  when the viewer opens the file: its page refuses the robot, naming the joint, what it found
  and what to change. `cad urdf snapshot` checks none of it: it draws what the numbers give, and
  refuses only a pose the coupler cannot reach. So a clean validation and a picture do not show that
  the linkage closes.
- **Not in a generated URDF.** The extension derives one joint's angle and places no coupler link,
  and a loop generated from a CAD model has its coupler as a link. The generated URDF leaves the
  loop's closing joint out and says so, and the MJCF closes it ([from-cad.md](from-cad.md)).
- **Only `cad` reads it.** Any other consumer ignores the namespaced element: a robot state
  publisher or a hardware driver must publish the same derived value to keep the loop closed.
