# URDF: CAD Viewer nonlinear four-bar coupling

Standard URDF `<mimic>` is affine and cannot close a nonlinear four-bar linkage. When exact CAD Viewer motion is required, keep the URDF link graph as a tree, expose the physical output joint as the only independent coordinate, and place this namespaced extension on the derived input joint:

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

Lengths use metres. `input_zero` and `output_zero` are the two moving-link angles, in radians from the ground link direction, when both URDF joint values are zero. The input and driver joints must share one ground link, use coplanar pivots separated by `ground_length`, and use parallel, same-direction axes. The server selects that assembly branch and derives the input angle from `driver` over the driver's whole operating range — its `<limit>`, or one full turn for a continuous driver — when it resolves the description for the CAD Viewer or `cad urdf snapshot`; the Viewer shows no slider or handle for the dependent joint (its driver's moves it) and a snapshot's `--pose` refuses it by name. The complete driver range must remain reachable on that branch, and the dependent joint limits must contain the entire derived input range (a continuous dependent joint has none). A joint cannot declare both `<mimic>` and `<tcad:four_bar>`.

`urdf check` checks the element itself: one per joint, every length positive, both zero angles, a revolute or continuous joint, and a `driver` that is a revolute or continuous joint on the same ground link, with no mimic cycle through it. It treats the derived joint as a mimic joint, so an SRDF group state cannot set it. The linkage's geometry (coplanar pivots `ground_length` apart, parallel axes, closure at the zero pose on the branch `input_zero` names and over the driver's range, the derived range within the joint's limits) is checked when the server resolves the robot: the Viewer and `cad urdf snapshot` refuse it then, naming the file, the joint, the driver angle and what to change.

A URDF generated from a CAD model never writes it: the extension derives one rocker's angle and places no coupler link, and a generated loop's coupler is a link of its own. The generated URDF leaves the loop's closing joint out (the export says so) and the MJCF closes the loop; write `<tcad:four_bar>` by hand only on a hand-written URDF whose CAD Viewer motion must be exact.

This is a Text-to-CAD vendor extension, not standard URDF behavior. Other consumers ignore the namespaced element; a robot state publisher or hardware driver must publish the same derived joint value to preserve loop closure outside the Viewer.
