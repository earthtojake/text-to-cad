# Injection molding

## Sources

Where the user supplies no shop specification, start from these two, and read
the shared rule-selection rules in `SKILL.md` before citing either:

- [Injection molding design guide](https://www.hubs.com/guides/injection-molding/) (Protolabs Network) for the design rules: wall thickness and hollowing thick sections, draft, ribs, bosses, undercuts and side actions, snap fits and living hinges, common defects (sink, warp), and the straight-pull cost tips.
- [Plastic injection molding guidelines](https://www.protolabs.com/services/injection-molding/plastic-injection-molding/design-guidelines/) (Protolabs) for that supplier's size limits, resin-specific wall thickness table, draft, undercut and radii guidance.

Texture, wall depth, resin grade, fillers, and tooling can change the
applicable limits. Verify the current guidance before citing numerical
thresholds.

## Measurement: `scripts/mold_tool.py`

```bash
python scripts/mold_tool.py measure part.stl --pull z [--units mm]
python scripts/mold_tool.py pulls part.stl
```

Input is a mesh (`.stl`, `.obj`, `.ply`, `.3mf`). For a STEP, export an STL
sidecar with `$cad` first — around 50,000 to 200,000 triangles is the useful
range: enough that a 1 mm feature has facets of its own, few enough that the
run stays under a minute. The tool splits faces further where it needs to.

Mesh files carry no units, so `--units mm|cm|m|in|ft` states the file's, and
the report repeats it as `scale.declared_units`. Without it everything is read
as millimetres, and `scale.units_suspect` flags a part whose bounding box is
then not the size of a molded part. That flag catches only the extremes: a
4 × 3 × 2 part is plausible in millimetres, centimetres AND inches, so
`scale.bbox_mm_if_units` gives the envelope under each one. Check it against
the part you expect rather than treating a clear flag as confirmation.

If a fact family fails, the report carries `"partial": true`, lists the family
in `partial_sections`, and the command exits 2. Do not read a partial report as
"no findings". A family that fails inside `pulls` counts: every candidate axis
carries its own `error`. Exit 1 is a failure with no report to read — a bad
argument, an unloadable mesh, or a measurement that was not a finite number.

### `draft`

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
face. On a face whose draft should be uniform that spread is the export's
tessellation, and it BOUNDS the error: the reading is low by no more than the
spread it declares. A spread over a degree means re-export finer before citing
the figure against a limit, and `reading_note` says so. Note that `area_mm2` for
a curved face is the whole face's area, not the area at that one draft.

Read `min_wall_draft` against `zero_draft_wall_area_mm2` in the same report. If
there is zero-draft wall area and the minimum is not zero, the two disagree and
the report is wrong; say so rather than quoting one of them.

### `undercuts`

A straight two-half pull occlusion test. From each face a ray is cast along the
direction its mold half withdraws; faces the part itself blocks are candidates.
Zero-draft walls count only when both directions are blocked. Faces are split
to a small maximum edge before casting, so the counted area follows the feature
rather than the tessellation.

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

`probe_resolution_note` appears when the face budget stopped the split short.
A mesh already over budget is cast unsplit, so undercut area follows the
tessellation; re-export nearer the edge the note names before quoting the area.

### `projection`

Silhouette area along the pull, rasterised, with `raster_resolution_mm` sized
to the part and reported. Plus depth along the pull and volume. The figure is a
count of covered cells, accurate to about one cell ring.

### `pulls`

Repeats the draft and undercut summaries for x, y, z AND the mesh's own
principal axes. A part modelled off-axis has no good pull among the three
world axes, and reading a 2° draft as 12° under `--pull z` looks like a
measurement rather than a mismatch; `principal0/1/2` are where its draft was
built. Choose a pull from measured area, not by eye.

### Not measured here

**Wall thickness.** Use `$dfam-check`'s `measure`, and ignore its `max_mm`: it
casts one ray along the face normal, which reads a plate's LENGTH rather than
its thickness. The thin end — `min_mm` and the thin samples — is what it gets
right, and the thin end is what fill depends on. Neither tool sees a sealed
void. State the method with any thickness finding.

## Review

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

If a side wall has measured 0.5 degree draft (from `scripts/mold_tool.py
measure --pull <axis>`) relative to the confirmed pull and the selected
texture/tooling specification requires 2 degrees, report the shortfall for that
wall. Without a confirmed pull direction, report draft as unverified rather
than failing every vertical-looking face.
