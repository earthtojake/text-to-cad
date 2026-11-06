# Injection molding

The evidence, the rules, the review and how to check a redesign are SKILL.md's
[Can it be made?](../SKILL.md#can-it-be-made), the same for every process; this is what is particular
to injection molding.

## Sources

Where the person supplies no shop specification, start from these two:

- [Injection molding design guide](https://www.hubs.com/guides/injection-molding/) (Protolabs Network) for the design rules: wall thickness and hollowing thick sections, draft, ribs, bosses, undercuts and side actions, snap fits and living hinges, common defects (sink, warp), and the straight-pull cost tips.
- [Plastic injection molding guidelines](https://www.protolabs.com/services/injection-molding/plastic-injection-molding/design-guidelines/) (Protolabs) for that supplier's size limits, resin-specific wall thickness table, draft, undercut and radii guidance.

Texture, wall depth, resin grade, fillers, and tooling can change the
applicable limits. Verify the current guidance before citing numerical
thresholds.

## Measure it

`cad <type> dfm --process molding` measures draft, undercuts and projected area along a pull:

```bash
cad step dfm part.step --process molding --pull z
cad model dfm "$ID" --process molding --pull y --json
cad stl dfm part.stl --process molding --units mm
cad step dfm part.step --process molding --candidates
```

```text
warning: zero_draft_walls at 0, -10, 0: 1250.84 mm2 of wall has no draft along the pull (under 0.05 deg), 66 triangles; the largest face is 300 mm2
OK part.step: molding along 0,0,1: walls 1250.84 mm2, zero-draft 1250.84 mm2, min wall draft 0 deg, undercut candidates 0 mm2, projected 550 mm2, depth 10 mm
```

The source is an `.stl`, `.3mf`, `.glb`, `.step` or `.xbf`, or a model's id, and `<type>` is its document
type: `stl`, `threemf` (`cad threemf dfm part.3mf`), `glb`, `step`, `xbf` or `model`. A STEP or an xbf is
tessellated by the engine, so there is nothing to export first. `--pull` is an axis (`z`, `-y`) or
`x,y,z` components, `z` by default; `--wall-limit` (45 degrees) is where a face stops being a wall and
`--zero-tol` (0.05 degrees) is zero draft. A mesh already held in a program (an `.obj`, a `.ply`) is
measured with `cad.trimesh.molding(mesh, pull="z")` in a check script.

The check is facts only: it never compares a figure with a resin's or a tool's limit, so its `OK` is
not a moldable verdict. Its findings say what the figures show (warnings `zero_draft_walls`,
`undercut_candidates`, `units_suspect`, `several_bodies`, `coarse_curved_face`; info
`probe_resolution`), each at the place it was measured. It exits 1 when something was not measured: a
`measurement_failed` error names the family and the rest are still reported, so never read that run
as "no findings"; `mesh_unreadable`, `not_finite` and `invalid_target` carry no measurements at all.

`--json` prints one line, `ok`, `findings`, `summary` and `measurements`, the report the families
below describe.

### Units: `measurements.mesh` and `measurements.scale`

An STL carries no units, so `--units mm|cm|m|in|ft` states the file's (the other types declare their
own), and the report repeats it as `scale.declared_units`. Without it an STL is read as millimetres,
and `scale.units_suspect` flags a part whose bounding box is then not the size of a molded part. That
flag catches only the extremes: a 4 × 3 × 2 part is plausible in millimetres, centimetres AND inches,
so `scale.bbox_mm_if_units` gives the envelope under each one. Check it against the part you expect
rather than treating a clear flag as confirmation.

### `measurements.draft`

- `wall_area_mm2`: faces within `--wall-limit` (default 45°) of the pull. Tops,
  bottoms and steep chamfers are not walls and appear in no draft figure.
- `wall_draft_histogram_mm2`: wall area by draft band.
- `wall_area_by_opening_mm2`: wall area by the direction its half withdraws
  (`+pull`, `-pull`, `none`). Walls opening both ways along one pull is the
  normal two-half case; which faces belong to which half is a parting-line
  decision, not this.
- `zero_draft_wall_area_mm2`: FLAT wall area parallel to the pull, pooled by
  normal in `largest_zero_draft_faces`.
- `zero_draft_tangent_area_mm2`: facets on a CURVED face that merely runs
  parallel to the pull. A sphere is tangent to the pull along a line, not over
  an area, so this figure scales with the tessellation — one sphere read
  261 mm² coarse and 67 mm² fine. Report it as a tangency, never as a wall.
  A wall that a fillet joins tangentially is NOT this: a flange rim with a
  radius top and bottom stays zero-draft wall. The whole connected zero-draft
  region is measured, not one triangle of it, so a flat wall the exporter split
  into rows is not mistaken for one step of a sweep.
- `min_wall_draft`: the lowest draft over the part's faces, above an absolute
  area floor (0.1% of surface area), with its area and location. Tangent bands
  are excluded. `min_facet_draft` is the single worst triangle; it moves with
  the mesh, so quote `min_wall_draft`.
- `drafted_wall_mean_draft_deg`: area-weighted over the drafted walls.

Every reported face carries `"surface"`: `"flat"` or `"curved"`, and the two are
pooled differently because they have to be. A flat face is pooled by normal and
read exactly — every facet of a planar wall carries the surface's own normal. A
curved face is pooled by the SURFACE it lies on, because a facet of one is a
chord: pooled by normal instead, a 3° cone came back as 318 separate "faces" of
10 to 60 mm² and the lowest chord among them was reported as the part's minimum,
giving 0.46°, 0.68° and 1.91° for the same wall at three tessellations.

A curved face is read at the **5th percentile of its own area**, not its mean
(which would bury a real low-draft band on a sphere) and not its minimum (the
chord outlier again). It also carries `spread_deg`, the scatter across the same
face. On a face whose draft should be uniform that spread is the tessellation,
and it BOUNDS the error: the reading is low by no more than the spread it
declares. A spread over a degree means measure a finer mesh before citing the
figure against a limit, and `reading_note` (the `coarse_curved_face` finding)
says so. Note that `area_mm2` for a curved face is the whole face's area, not
the area at that one draft.

Read `min_wall_draft` against `zero_draft_wall_area_mm2` in the same report. If
there is zero-draft wall area and the minimum is not zero, the two disagree and
the report is wrong; say so rather than quoting one of them.

### `measurements.undercuts`

A straight two-half pull occlusion test. From each face a ray is cast along the
direction its mold half withdraws; faces the part itself blocks are candidates
(`candidate_area_mm2`, `candidate_area_pct_of_surface`, `largest_candidate_faces`
with their centroids). Zero-draft walls count only when both directions are
blocked (`trapped_zero_draft_area_mm2`). Faces are split to a small maximum edge
before casting, so the counted area follows the feature rather than the
tessellation.

`opens_toward` is the lean of a face's outward normal along the pull, not its
mold-half assignment. The test assumes a straight two-half tool with the
parting at the silhouette; a candidate may be resolved by a side action, a
lifter, or another parting line, and that judgement, plus the full withdrawal
path and shutoffs, is made in the review, not here.

A file with several bodies is an assembly, not one molded part: each body is
tested against itself, `body_count` and `per_body` appear, and nothing treats
one body as an obstruction for another. Say so in the report rather than
reviewing an assembly as a part. A sealed internal void is NOT a second body —
coring a thick section is the standard molding fix, so it is counted in
`internal_void_count` and the part stays one body. Nothing here measures a
sealed void's own walls or reaches inside one.

`probe_resolution_note` (the `probe_resolution` finding) appears when the face
budget stopped the split short. A mesh already over budget is cast unsplit, so
undercut area follows the tessellation; measure a finer mesh near the edge the
note names before quoting the area.

### `measurements.projection`

Silhouette area along the pull (`projected_area_mm2`), rasterised, with
`raster_resolution_mm` sized to the part and reported. Plus depth along the pull
(`depth_along_pull_mm`) and volume. The figure is a count of covered cells,
accurate to about one cell ring.

### `--candidates`: `measurements.pulls.candidates`

In place of one pull's `draft`, `undercuts` and `projection` (it takes no `--pull`),
repeats the draft and undercut summaries for x, y, z AND the mesh's own
principal axes, each row a `pull` with its `undercut_candidate_area_mm2`,
`wall_area_mm2`, `zero_draft_wall_area_mm2`, `wall_area_below_1deg_mm2` and
`min_wall_draft_deg`. A part modelled off-axis has no good pull among the three
world axes, and reading a 2° draft as 12° under `--pull z` looks like a
measurement rather than a mismatch; `principal0/1/2` are where its draft was
built. Draft magnitude is the same for a +axis and a -axis pull. Choose a pull
from measured area, not by eye.

### Not measured here

**Wall thickness.** Measure it on the CAD model, or on the mesh with a tool
that casts rays (`cad <type> dfm --process printing` reports
`measurements.wall_thickness`), and trust only the thin end of a ray cast: one
ray along the face normal reads a plate's LENGTH rather than its thickness. The
thin end — the minimum and the thin samples — is what it gets right, and the
thin end is what fill depends on. No ray cast sees a sealed void. State the
method with any thickness finding.

## Review the part

Collect resin grade/filler, nominal wall, pull direction, proposed parting line,
texture/cosmetic faces, critical fits, and tooling constraints. Treat unknown
resin or pull direction as missing context, not permission to guess a verdict.

- Review local wall thickness and transitions, including rib and boss junctions.
  Sampling must state its coverage. Thick intersections can matter even when
  nominal walls are consistent. Compare with resin-specific guidance.
- Evaluate draft relative to the stated pull direction, separating core/cavity
  sides and textured faces. Zero draft means a wall parallel to the pull direction;
  top/bottom faces perpendicular to it should not be flagged as zero-draft walls.
- Identify candidate undercuts and trapping features relative to the proposed
  parting and pull. A normal-angle check alone is not a complete undercut test;
  visibility/occlusion and the full withdrawal path matter. Distinguish a need
  for side actions or inserts from impossibility of molding.
- Review ribs, bosses, corner transitions, shutoffs, and likely ejection access.
  Flag sink/warpage risks qualitatively unless a relevant analysis was run.
- Discuss gate, vent, weld-line, packing, cooling, and shrinkage implications as
  tooling questions; geometry review does not simulate filling or predict a
  validated cycle time. Do not rescale the finished part for shrinkage without
  the toolmaker's resin/process assumptions.
- Preserve mating faces and functional dimensions when proposing draft or
  coring. Identify which datum stays fixed and whether the proposed change
  adds or removes material.

This workflow reviews conventional thermoplastic injection molding. For silicone,
overmolding, or insert molding, identify the additional process requirements
and obtain applicable guidance rather than reusing thermoplastic limits blindly.

## Worked reasoning example

The following numbers are illustrative inputs, not default process limits.

If a side wall has measured 0.5 degree draft (`measurements.draft.min_wall_draft`
from `cad step dfm part.step --process molding --pull <axis>`) relative to the
confirmed pull and the selected texture/tooling specification requires 2 degrees,
report the shortfall for that wall. Without a confirmed pull direction, report
draft as unverified rather than failing every vertical-looking face.
