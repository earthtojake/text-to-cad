# Tube deformation

Read this reference for flexible swept bodies in an animation clip, and for how
that motion reaches the CAD Viewer, snapshots and an animated GLB. The
[motion reference](kinematics.md) covers ordinary joints, poses, clip
declarations and video rendering.

## Deforming an existing tube

Call `.deform_tube()` on a clip's handle for a continuous swept STEP body:

```python
# Inside a clip's update(t, m), with rest_path and posed_path built for this t:
m.get("#tendon").deform_tube(
    rest=rest_path,
    path=posed_path,
    twist_deg=0,
    max_segment_length=1,
)
```

Both paths are `{"normal": [x, y, z], "segments": [...]}` dicts in assembly
coordinates. `normal` is a required transverse frame seed on each path.
Segments must connect tangentially:

| Segment | Fields |
| --- | --- |
| Line | `{"kind": "line", "start": ..., "end": ...}` |
| Arc | `{"kind": "arc", "center": ..., "axis": ..., "start": ..., "sweepDeg": ...}` |
| Cubic Bezier | `{"kind": "bezier", "points": [p0, p1, p2, p3]}` |

Positions are `[x, y, z]` millimetres; angles are degrees. Normalized arc length
maps the rest path to the posed path. Check tendon length, bend radius and
collisions separately: deformation does not solve those constraints.
`twist_deg` rotates authored cross-sections; it does not calculate spool payout.

Only `path` and `twist_deg` move during a clip: `rest`, `max_segment_length`
and `braid` stay the same in every sample that deforms the tube, and the build
refuses a clip that changes them. Use `.rotate()` or `.translate()` for rigid
motion. A sample that does not call `.deform_tube()` shows the tube at rest.

Every view draws the tube as a glTF skin. Joints stand along the rest centerline
at most `max_segment_length` apart; each keyframe places them on that keyframe's
path, turned by its twist, and the tube's mesh is bound to the two joints either
side of each vertex. Between keyframes the joints blend, so the build keeps
keyframes until that blend follows the clip to well under a tenth of a degree. A
path no tube could follow — a kink, a cusp — fails the build with the clip, the
part and the time it happens.

A path that is its rest under one affine map is stored as that map, twelve
numbers a keyframe, rather than as a copy of the whole centerline. A coil spring
built from lines and Beziers whose turns all close up alike as it compresses
gets this automatically. Arcs never map, and a spring whose end turns hold still
while its middle closes stores whole paths, many times larger.

`max_segment_length` controls the joint spacing and the longitudinal mesh
refinement, in millimetres (default `1`, minimum `0.05`): a straight STEP surface
may have rings only at its ends, so cadgen splits it into bands this long before
binding it, and a bend draws an arc rather than a chord. Its edges are split and
bound the same way, so they bend with the surface.

Optional `braid={"pitch": 0.8, "depth": 0.02, "strands": 8}` adds procedural
fiber color and normal relief over the swept core. Pitch and depth are
millimetres; the strand count must be even. This is a surface finish, not
additional CAD or collision geometry.

## Exporting deformation to GLB

An animated GLB carries a bending tube as a glTF skin — the same joints and
keyframes every CAD view plays — with no option to set:

```bash
cadgen glb build STEP/hand.step GLB/animated/hand.glb --animation fist
```

Each tube's node names its skin; its mesh carries `JOINTS_0` and `WEIGHTS_0`;
its joints are nodes keyed `LINEAR`, under the pivot that also moves the tube's
parts when a rigid track carries them. Tubes one track bends must move together:
a track that bends parts a rigid track moves apart is refused, because a skin's
joints move as one.

Limitations:

- Procedural braid shading is not exported. The GLB retains the tube's geometry
  and motion with a smooth surface, and the export warns.
- Render a video when the output needs effects GLB cannot carry; see
  [motion review](kinematics.md#reviewing-motion).
