# 3D printing

Read this file before modelling or checking a part that is 3D printed: FDM, SLA, SLS, MJF or metal
powder bed (PBF). What every process shares (the result in full, a shop's own limits, the review, a
redesign) is [the review reference](manufacturing-review.md).

## Design it

The numbers are FDM's unless another technology is named: for each figure, the first of Protolabs
Network's (Hubs), Protolabs' and Xometry's design guides that gives one. Those marked *own* are
text-to-cad's where no guide states one, and a finding's `source` says which. A machine's datasheet
moves them.

- **Model it as it prints.** Z up, standing on its largest flat face: the check measures the part
  as it stands. For another orientation, turn the part in its model and check again.
- **Overhangs.** A down-facing slope at least 45 degrees from horizontal prints without support
  (FDM, PBF; SLA 19): chamfer an overhang at 45 rather than leaving it flat. On FDM a flat ceiling
  bridges at most 5 mm, and a horizontal round hole prints unsupported up to 10 mm (own; wider, a
  teardrop, or turn the part so the hole is vertical). SLS and MJF need no support: there trapped
  powder is the question.
- **Walls.** A standing wall of 0.8 mm or more on FDM: two beads of a 0.4 mm nozzle, and of the
  `--nozzle` given (own). Elsewhere, a wall joined on two sides or more and a free one: SLA 0.5 and
  1.0, SLS 0.8 and 1.0, MJF 0.7 and 1.0, PBF 0.4 and 0.8. On FDM a skin lying in the layer plane (a
  tray's floor, a living hinge) is laid layer on layer and needs two layers (own; under one it is
  not printed at all).
- **Holes, pins and detail.** Holes 1 mm or wider (SLS and PBF 1.5, SLA 0.8), vertical where they
  can be. Pins 1 mm (Xometry; SLS 0.8, PBF 0.6, SLA and MJF 0.5) and never thinner than the free
  wall: a pin is a wall joined on one side. Embossed text 1 mm high (FDM, SLS) and engraving 0.4 mm
  deep (SLA; SLS 1): raised or sunk detail alone, since a step that runs across a face is the
  part's shape.
- **No knife edges.** A convex edge with under 45 degrees of material thins to nothing over its
  last millimetres: blunt it to the wall minimum, or open it to 45 degrees or more
  (`printing.knife_edge`, a warning, own: the tip prints rounded). Two surfaces that meet at a
  glancing angle (a sphere emerging from a cone) leave such a feather along their edge.
- **Hollow parts.** SLS, MJF and PBF need an escape hole of 3.5 mm or more for each cavity (Hubs's
  SLS figure, applied to the other two); SLA a drain hole and walls of 2 mm; FDM prints a sealed
  cavity as infill. A cavity is any air wider than its way out: a flat pocket behind a small vent
  traps powder as a hollow ball does.
- **Fits.** Parts printed together, in place, fuse under a clearance of 0.76 mm (Xometry; SLA 0.5,
  SLS 0.3, MJF 0.9, PBF 0.64). A part printed on its own is checked by its own id, and a fit made
  after printing is not judged (about 0.3 mm on FDM is common practice, no rule's). Walls are
  judged per part, clearances per pair.
- The material and the process on the part are
  `part.material = plastics.petg(process=fdm(layer_height_mm=0.2))`, with `sls()`, `mjf()`, `slm()`
  (metal powder bed) or `vat()` (resin) for the others, from `bd_materials.processes`: the check
  then needs no `--process`, `--technology` or `--layer-height`.

## Check it

```bash
cad model dfm "$ID" --process printing --technology sla --build-volume 145x145x185
cad stl dfm stand.stl --technology fdm --material petg --candidates
```

- `--technology fdm|sls|sla|mjf|pbf` (default `fdm`): every limit and the self-supporting angle are
  the technology's, and a rule it has no figure for is not evaluated. With the process unknown,
  check each candidate and report by technology.
- `--material`: on FDM, the warping risk of the materials that warp (`warping_risk`). A metal with
  a plastic technology, or a plastic with `pbf`, is refused.
- `--build-volume XxYxZ`: the person's printer, an error to pass. With none, a typical machine of
  the technology's is assumed (a warning names it), and the error is a part that fits the largest
  machine the guide lists lying no way (900 x 600 x 900 mm for FDM). The fit is of the part lying
  its best way, across the bed's corners too, so it does not change with how the model is turned.
- `--printer FILE` (FDM): the build volume and the nozzle read from a 3MF that OrcaSlicer or Bambu
  Studio saved (a project or a sliced `.gcode.3mf`), or from a complete machine preset JSON;
  `--build-volume` and `--nozzle` given win. The volume is the bed's rectangular bounding box and the
  printable height, so a part that fits it can still cross a round bed's edge or an excluded zone. A
  preset that holds only its differences from a parent (`inherits`) has no volume: give a 3MF the
  slicer saved. Ask the person for the file rather than copying the printer's numbers.
- `--layer-height`: stair-stepping and, on FDM, a lying skin's layers. `--nozzle` (FDM): the wall
  minimum, two beads of it (0.4 mm assumed, and said, where none is given).
- `--angle-limit`: the printer's own self-supporting angle, from its datasheet, in place of the
  technology's.
- `--units` (an STL's: millimetres by default) and `--samples` (the rays cast for a mesh's walls,
  2000).

`--candidates` ranks the six axis orientations, and the largest flat faces laid down, by support,
height and finish, each with the rotation that turns the part to it. It judges nothing.

## Read it

The result is read as [every process's](manufacturing-review.md#read-the-result). The families of
`measurements`: `solid` (a mesh's `mesh`), `overhangs`, `bridges`, `wall_thickness`, `knife_edges`,
`gaps`, `holes`, `pins`, `details`, `clearances`, `trapped_volumes`, `build_volume`, `bed`,
`stair_stepping`, `support_volume`, `sections`; `orientations` with `--candidates`.

- **Walls.** A wall is `supported` (joined to the part on two sides or more: a tray's floor, a web
  between two posts) or not (a fin on its base, a pin on its foot), each with its own minimum
  (`printing.wall_supported`, `printing.wall_unsupported`). One whose support could not be read is
  `printing.wall`: judged as supported, and warned of between the two minima. FDM judges a `lying`
  skin by its layers (`printing.skin_layer`, `printing.skin_layers`).
- **A mesh's walls are sampled**, by `--samples` rays from random points. A place smaller than
  their spacing can be missed, and a thin `min_mm` beside a thick `p05_mm` is one small thin place:
  find it from its item's `xyz`, and confirm it on the STEP or the model before the design changes.
  A wall under its limit by no more than the mesh's chords may stray from the surface (`chord_mm`)
  is a warning, at the limit within the mesh's accuracy: only the exact model says which side it
  falls.
- `mesh_at_limit` (info, a mesh alone): curved surface or edges within the mesh's own angular
  accuracy of a limit (3 degrees at most) were not judged. The STEP or the model has the angle.
- **A mesh's `OK`** is of what a mesh can be judged by. Its last line says what it left ("not judged
  on a mesh: ...", `families_not_measured`): holes over 3 mm across as holes (their crowns are
  judged as overhangs or bridges), pins' own minima (a pin is judged as a wall) and embossed and
  engraved detail. A mesh with no inside is `NOT CHECKED` in one finding (`mesh_empty`,
  `mesh_unreadable`, `inconsistent_normals`, `mesh_no_volume`; over 2 million triangles,
  `mesh_too_large`). `mesh_repaired` (a warning) says what was put right before measuring: a slicer
  reads the file as it is, so export it again.
- `knife_edges` items: `angle_deg` is the edge's least, `length_mm` the stretch under 45 degrees,
  `thin_depth_mm` how far in the material stays under the minimum wall.
- `trapped_volumes`: on SLS and MJF overhangs are facts, and trapped powder and its escape holes are
  the verdict. `min_escape_hole_mm` is a round hole's diameter, or the narrowest throat of any other
  opening. A sealed cavity prints as infill on FDM (`internal_void`).
- `gaps` are slots within one part. `clearances` are between the parts of an assembly, the solids
  of one part or the bodies of one mesh, measured as printed together.
- `support_volume` is a column fill to the plate or the part: a coarse upper bound, a cost and
  finish signal, not a failure.
- A B-rep is searched for self-intersections up to 1000 faces in all: the parts past that are
  `NOT CHECKED` (`measurement_failed`), so check them one at a time.

## Review the part

Check by hand what the check does not measure:

- Tree supports, support density, and which faces are cosmetic (the check calls a face cosmetic by
  its size).
- A cavity under about five voxels across (`trapped_volumes.pitch_mm`), which is found only where
  it is sealed, and an opening under a voxel wide, which is known only to be that narrow.
- Lattices, text legibility, tolerance stack-ups and residual stress.
- A horizontal round hole on a mesh, which has no axes: its crown reads as a bridge of its span
  (`printing.bridge_length`), where exact geometry judges its diameter (`printing.horizontal_hole`).
