# SDF examples

These examples illustrate the intended authoring style: explicit `relative_to` frames, a ledger comment block, computed inertials with their formula named, and structured assumptions.

## Minimal model

```xml
<?xml version="1.0"?>
<!--
  model: calibration_box | consumer: Gazebo Harmonic (SDF 1.12)
  units: meters, kilograms, radians
  inertials: uniform-density solid-box formula, m=1.0 kg
  assumptions: uniform density; box is rigid
-->
<sdf version="1.12">
  <model name="calibration_box">
    <link name="body">
      <inertial>
        <mass>1.0</mass>
        <!-- solid box 0.1^3: ixx=iyy=izz=m(a^2+a^2)/12 -->
        <inertia>
          <ixx>0.0016666667</ixx>
          <ixy>0</ixy>
          <ixz>0</ixz>
          <iyy>0.0016666667</iyy>
          <iyz>0</iyz>
          <izz>0.0016666667</izz>
        </inertia>
      </inertial>
      <visual name="body_visual">
        <geometry>
          <box><size>0.1 0.1 0.1</size></box>
        </geometry>
      </visual>
      <collision name="body_collision">
        <geometry>
          <box><size>0.1 0.1 0.1</size></box>
        </geometry>
      </collision>
    </link>
  </model>
</sdf>
```

## Minimal world

```xml
<?xml version="1.0"?>
<!--
  world: empty_lit_world | consumer: Gazebo Harmonic (SDF 1.12)
  world intentionally contains no inline model
-->
<sdf version="1.12">
  <world name="empty_lit_world">
    <light name="sun" type="directional">
      <pose relative_to="world">0 0 10 0 0 0</pose>
      <cast_shadows>true</cast_shadows>
    </light>
  </world>
</sdf>
```

## Two-link model with an explicit joint frame

Note the explicit `relative_to` on every nontrivial pose, and the joint axis with explicit `expressed_in`:

```xml
<?xml version="1.0"?>
<!--
  model: two_link_demo | consumer: Gazebo Harmonic (SDF 1.12)
  frames: base_link at model origin; arm_link placed by shoulder_pan joint
  inertials: solid-box formulas at stated masses (base 2.0 kg, arm 0.5 kg)
  assumptions: positive shoulder_pan rotates arm counterclockwise viewed from +Z
-->
<sdf version="1.12">
  <model name="two_link_demo">
    <link name="base_link">
      <inertial>
        <mass>2.0</mass>
        <!-- solid box 0.4 x 0.3 x 0.1 -->
        <inertia>
          <ixx>0.0166667</ixx><ixy>0</ixy><ixz>0</ixz>
          <iyy>0.0283333</iyy><iyz>0</iyz>
          <izz>0.0416667</izz>
        </inertia>
      </inertial>
      <visual name="base_visual">
        <geometry><box><size>0.4 0.3 0.1</size></box></geometry>
      </visual>
      <collision name="base_collision">
        <geometry><box><size>0.4 0.3 0.1</size></box></geometry>
      </collision>
    </link>
    <link name="arm_link">
      <pose relative_to="shoulder_pan">0 0 0 0 0 0</pose>
      <inertial>
        <mass>0.5</mass>
        <!-- solid box 0.3 x 0.05 x 0.05 -->
        <inertia>
          <ixx>0.000208333</ixx><ixy>0</ixy><ixz>0</ixz>
          <iyy>0.00385417</iyy><iyz>0</iyz>
          <izz>0.00385417</izz>
        </inertia>
      </inertial>
      <visual name="arm_visual">
        <geometry><box><size>0.3 0.05 0.05</size></box></geometry>
      </visual>
      <collision name="arm_collision">
        <geometry><box><size>0.3 0.05 0.05</size></box></geometry>
      </collision>
    </link>
    <joint name="shoulder_pan" type="revolute">
      <pose relative_to="base_link">0 0 0.05 0 0 0</pose>
      <parent>base_link</parent>
      <child>arm_link</child>
      <axis>
        <xyz expressed_in="base_link">0 0 1</xyz>
        <limit>
          <lower>-1.5708</lower>
          <upper>1.5708</upper>
        </limit>
      </axis>
    </joint>
  </model>
</sdf>
```

This uses the SDF 1.8+ frame-graph pattern: the joint pose is expressed relative to the parent link, and the child link's pose is `relative_to` the joint frame. That mirrors URDF semantics and makes URDF-derived SDF mechanical to audit.

## Plugin block from documentation

When a plugin block is copied from target simulator documentation, preserve its explicit parameters and cite the source in a comment:

```xml
<!-- Source: gz-sim diff_drive tutorial (Harmonic docs). Unverified in target env. -->
<plugin name="example_control" filename="libexample_control.so">
  <namespace>robot1</namespace>
</plugin>
```

Do not invent plugin fields. If the documentation source is not available, mark the plugin as unverified in the ledger and the final report.
