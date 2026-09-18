# Tube deformation and morph export

Read this reference for flexible swept bodies in an embedded animation, or for
exporting that deformation into GLB. The [motion reference](kinematics.md)
covers ordinary joints, poses, clip declarations and video rendering.

## Deforming an existing tube

Call `.deformTube()` on an animation handle for a continuous swept STEP body:

```javascript
// Inside update(t, m), with restPath and posedPath defined for this frame:
m.get("tendon").deformTube({
  rest: restPath,
  path: posedPath,
  twistDeg: 0,
  maxSegmentLength: 1,
});
```

Both paths are `{normal, segments}` in assembly coordinates. `normal` is a
required transverse frame seed on each path. Segments must connect tangentially:

| Segment | Fields |
| --- | --- |
| Line | `{kind: "line", start, end}` |
| Arc | `{kind: "arc", center, axis, start, sweepDeg}` |
| Cubic Bezier | `{kind: "bezier", points: [p0, p1, p2, p3]}` |

Positions are vec3 millimetres; angles are degrees. Normalized arc length maps
the rest path to the posed path. Check tendon length, bend radius and collisions
separately: deformation does not solve those constraints. `twistDeg` rotates
authored cross-sections; it does not calculate spool payout.

`maxSegmentLength` controls one-time longitudinal mesh refinement in millimetres
(default `1`, minimum `0.05`). The rest mesh, normals and topology remain
continuous, and shared source buffers remain immutable. Omitting deformation in
a later frame restores the rest shape.

Optional `braid: {pitch: 0.8, depth: 0.02, strands: 8}` adds procedural fiber
color and normal relief over the swept core. Pitch and depth are millimetres;
the strand count must be even. This is a surface finish, not additional CAD or
collision geometry.

## Exporting deformation to GLB

Animated GLB refuses tube deformation by default. Request morph targets explicitly:

```bash
cadgen glb build STEP/hand.step GLB/animated/hand.glb \
  --animation '{"clip": "fist", "fps": 24, "seconds": 6,
                "deform": "morph", "deformTolerance": 1.0}'
```

Each deforming node gets per-vertex position and normal deltas against one base
mesh, plus a weights channel. Interpolation between baked poses can differ from
the procedural deformation. The exporter fits targets per occurrence against
`deformTolerance` (millimetres, default `1.0`, range `0.01`..`10`), checking a
grid four times finer than `fps`, at least 96 Hz. This sampled check is not a
continuous-time error guarantee. The export summary reports `targets`, `bytes`,
`runtimeBytes`, `deviationMm` and `fitGridHz`.

The exporter refuses a bake exceeding 512 MiB of estimated morph playback
memory: 32 bytes per vertex per target, or 16 without normals. To reduce it,
relax `deformTolerance`, shorten `seconds`, increase `--mesh-tolerance`, or
increase the clip's `maxSegmentLength`, as the required fidelity permits.

Limitations:

- Procedural braid shading is not exported. The GLB retains the tube's geometry
  and motion with a smooth surface.
- Changing a tube's `rest` path during the clip is refused because morph targets
  share one base mesh. Use `.rotate()` or `.translate()` for rigid motion.
- A tube held in a constant deformed pose exports in that pose without morph
  targets. `"deform": "rest"` instead explicitly freezes tubes at rest and warns;
  use it only when that is the intended output.

The CAD Viewer plays baked morph animation from GLB, but the original clip's
procedural controls remain in the STEP sidecar. Render a video when the output
needs effects GLB cannot carry; see [motion review](kinematics.md#reviewing-motion).
