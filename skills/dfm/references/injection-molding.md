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
then not the size of a molded part.

If a fact family fails, the report carries `"partial": true`, lists the family
in `partial_sections`, and the command exits 2. Do not read a partial report as
"no findings".

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
- `min_wall_draft`: the lowest draft over faces pooled by normal, ignoring the
  sliver tail, with its area and location. `min_facet_draft` is the single
  worst triangle; it moves with the mesh, so quote `min_wall_draft`.
- `drafted_wall_mean_draft_deg`: area-weighted over the drafted walls.

Curved faces are read per facet, so a 1° cone bore reads a little under 1°
because a chord facet tilts less than the analytic surface. Report the measured
value with that caveat rather than rounding it up.

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
reviewing an assembly as a part.

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
