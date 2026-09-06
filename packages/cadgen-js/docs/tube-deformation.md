# Flexible tube animation

`m.get(target).deformTube({rest, path, twistDeg=0, maxSegmentLength=1, braid?})`
animates a continuous tube or hollow sheath already present as a swept STEP
body. It deforms the original surface and its edge overlays in the same shared
pass used by CAD Viewer and snapshots. It does not create a replacement rope or
change the STEP artifact. Subsequent rigid occurrence transforms act on the
deformed result. The paths use assembly coordinates before those transforms.

```js
const rest = {
  normal: [0, 0, 1],
  segments: [{kind: 'line', start: [0, 0, 0], end: [10, 0, 0]}]
};
const bent = {
  normal: [0, 0, 1],
  segments: [{
    kind: 'arc', center: [0, 5, 0], axis: [0, 0, 1],
    start: [0, 0, 0], sweepDeg: 90
  }]
};
// Inside a render module clip update(t, m):
m.get('tendon').deformTube({rest, path: bent, twistDeg: 360 * t});
```

Each path is `{normal?, segments}`. `normal` is a transverse seed for the
first frame, projected perpendicular to its tangent; later frames use parallel
transport. Give matching explicit seeds to rest and posed paths when their
first tangents change. Every segment must meet the next at the same position
and tangent. Discontinuities and corners throw a teaching error.

The closed segment vocabulary is:

- `{kind:'line', start:[x,y,z], end:[x,y,z]}`
- `{kind:'arc', center:[x,y,z], axis:[x,y,z], start:[x,y,z], sweepDeg}`.
  Axis is a nonzero normal. Sweep is signed, nonzero, and at most 360 degrees.
  Start lies in the circle plane and determines its radius.
- `{kind:'bezier', points:[p0,p1,p2,p3]}`. This is a cubic Bézier with four
  finite vec3 control points. It uses adaptive five-point quadrature for length
  and numerical parallel transport; stationary tangents and cusps are errors.

The runtime projects each original mesh vertex onto the analytic rest
centerline and retains its longitudinal coordinate and transverse offsets.
Normalized arc length maps to the posed path; length changes therefore stretch
or contract the visible tube. This is a display mapping, **not a tendon tension,
spool payout, friction, collision, or constant-length solver**. An author must
solve those mechanics and pass the resulting centerline. Tube thickness remains
unchanged. `twistDeg` rotates each cross-section in its transported frame; it can
show phase travel in an authored helical braid without moving the centerline.
It does not itself simulate material payout.

The source STEP tessellation is immutable. Each occurrence retains a rest
mesh and one reusable displayed mesh; unchanged component buffers remain shared.
Straight STEP surfaces may contain only
end rings, so the runtime first splits their existing triangles into bands of
at most `maxSegmentLength` mm in rest arc length. This preserves the exact rest
surface, interpolates attributes, preserves CAD face picking, and prevents an
animated bend becoming a single end-to-end chord. The default is 1 mm; values
below 0.05 mm are rejected. A per-occurrence 700,000-triangle ceiling throws
instead of exhausting memory. Refinement is cached until the rest path or band
length changes. Original smooth normals are transformed by the deformation's
local inverse-transpose; silhouettes and technical edges follow the surface.

Every evaluation starts from rest. Omitting `deformTube` on a later frame or
clearing animation restores the rest shape. Shared component meshes are never
mutated. A changed centerline can be independently inspected without a renderer:
`evaluateAnimationClip` returns `deformations`, keyed by occurrence ID, with
compiled rest/posed paths and their lengths. `compileTubePath`,
`sampleTubePath`, and `projectTubePath` are exported from
`common/tubeDeformation.js`. Line and circle lengths/curvature are analytic;
`minRadius` for a Bézier is a sampled diagnostic and must not substitute for an
independent curvature gate. As with any CAD tessellation, a finite surface mesh
approximates the analytic posed centerline between its vertices.

For a smooth CAD core, `braid:{pitch:0.8, depth:0.02, strands:8}` adds a
procedural braided surface finish. Pitch and normal-relief depth are millimetres;
strands is an even carrier count from 2 to 64. Crossing helices, fine fiber
lines and lighting relief use rest material coordinates and follow
`twistDeg` as the tube deforms. This is a GPU normal/color finish, **not added
CAD fiber bodies or collision geometry**; it remains inside the nominal core's
rendered envelope. No image texture is fetched and no helical solids are
created. The finish is scoped to that occurrence's material and disabled when
the effect is omitted. The original material's source color and shader hooks
remain in force.
