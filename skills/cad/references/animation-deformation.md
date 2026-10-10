# Tube deformation

Read this reference for flexible swept bodies in an animation clip. The
[motion reference](kinematics.md) covers joints, poses, clip declarations and
video rendering.

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
coordinates; `normal` is a required transverse frame seed. Segments must connect
tangentially:

| Segment | Fields |
| --- | --- |
| Line | `{"kind": "line", "start": ..., "end": ...}` |
| Arc | `{"kind": "arc", "center": ..., "axis": ..., "start": ..., "sweepDeg": ...}` |
| Cubic Bezier | `{"kind": "bezier", "points": [p0, p1, p2, p3]}` |

Positions are millimetres and angles degrees; normalized arc length maps the rest
path to the posed path. Deformation does not solve tendon length, bend radius or
collisions, and `twist_deg` rotates the cross-sections without computing spool
payout.

- Only `path` and `twist_deg` may change during a clip; the build refuses a clip
  that changes `rest`, `max_segment_length` or `braid`. A sample that does not
  call `.deform_tube()` shows the tube at rest; `.rotate()`/`.translate()` move
  it rigidly.
- A path no tube could follow (a kink, a cusp) fails the build, naming the clip,
  the part and the time.
- `max_segment_length` (mm, default `1`, minimum `0.05`) spaces the skin's joints
  and splits the tube's surfaces into bands, so a bend draws an arc rather than a
  chord.
- A path that is its rest under one affine map (a coil of lines and Béziers whose
  turns close up alike) is stored as twelve numbers per keyframe; arcs and
  non-uniform motion store whole paths, many times larger.
- Optional `braid={"pitch": 0.8, "depth": 0.02, "strands": 8}` adds procedural
  fibre colour and relief (pitch and depth in mm, an even strand count). It is a
  surface finish, not CAD geometry.

## Exporting deformation to GLB

An animated GLB carries each bending tube as a glTF skin, the same joints and
keyframes every view plays:

```bash
cadgen glb build STEP/hand.step GLB/animated/hand.glb --animation fist
```

Tubes that one track bends must move together: a track that bends parts a rigid
track moves apart is refused, because a skin's joints move as one. Braid shading
is not exported (the export warns); a [clip video](kinematics.md#rendering-the-whole-clip)
carries it.
