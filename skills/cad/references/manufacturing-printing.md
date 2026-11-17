# 3D printing

The evidence and the rules are SKILL.md's [Can it be made?](../SKILL.md#can-it-be-made), and the result
in full, the review and how to check a redesign are [the review reference](manufacturing-review.md),
the same for every process; this is what is particular to additive processes.

Slicing and sending a print to a printer is the print3d skill's ($print3d).

## Design it

What a printed part has from its first line (the rules' FDM numbers, general practice, unless another
technology is named; a machine datasheet moves them):

- **Model it as it prints.** Z up, the face it stands on at the bottom: the check measures the part as
  it stands, so build the model in its print orientation, or turn it in the model and check again
  (`--candidates` ranks the orientations and judges nothing). The largest flat face down.
- **Overhangs.** A down-facing slope at least 45 degrees from horizontal (FDM, metal PBF; SLA 19) prints
  without support: chamfer an overhang at 45 rather than leaving it flat; a flat ceiling spans at most
  5 mm as a bridge (FDM), and a horizontal round hole up to 10 mm prints unsupported (wider: a teardrop,
  or turn the part so the hole is vertical). Powder processes (SLS, MJF) need no support: there, trapped powder is the
  question.
- **Walls, pins and holes.** Standing walls 0.8 mm or more (two beads of a 0.4 mm nozzle: with `--nozzle`
  given, two of its; SLA 0.5 supported / 1.0 free,
  SLS 0.8 / 1.0, MJF 0.7 / 1.0, PBF 0.4 / 0.8); on FDM a skin lying in the layer plane (a tray's floor, a
  living hinge) is laid layer on layer and needs two layers (0.4 mm at 0.2 mm layers; under one layer it is
  not printed at all); holes 1 mm or wider (SLS 1.5), vertical where they
  can be; pins 1 mm (FDM, Xometry's recommendation) or 0.8 mm (SLS, a recommendation; SLA 0.5), and never
  thinner than the free-wall minimum: a pin is a wall joined on one side; embossed text 1 mm high (FDM) and engraving 0.4 mm deep (SLA's rule) -- raised or
  sunk detail alone: a step running across a face is the part's shape, not text.
- **No knife edges.** A chamfer or a draft that meets a face under 45 degrees thins to nothing over
  its last millimetres: blunt it to the wall minimum (`printing.knife_edge`, a warning: the tip prints
  rounded). Two surfaces meeting at a glancing angle (a sphere emerging from a cone) leave a feather of
  material along their edge, a knife over the stretch where their angle falls under 45 degrees (read along
  the edge, not at its middle): blend them, or cut the feather back. A tip at 45 degrees or more is
  neither a knife nor a thin wall.
- **Hollow parts.** SLS, MJF and PBF need an escape hole of 3.5 mm or more per cavity for the powder;
  SLA a drain hole and walls of 2 mm; FDM prints a sealed cavity as infill. A cavity is any air wider
  than its way out, whatever its shape: a flat pocket behind a small vent traps powder as a hollow ball does.
- **Fits.** Mating parts 0.3 mm apart for FDM in practice (the general rule warns under 0.76), SLS 0.3,
  SLA 0.5; walls are judged per part, clearances per pair.
- Within the printer: `--build-volume 256x256x256` for the person's machine (without it the fit is
  judged against a typical machine of the technology's, assumed: a warning naming it -- and an error only
  where the part fits the largest machine the guide lists lying no way, 900 x 600 x 900 mm for FDM). The fit
  is of the part lying its best way -- on any side, turned any way on the bed, across its corners -- so it
  does not change with how the model is turned. The material and the
  process on the part, `part.material = plastics.petg(process=fdm(layer_height_mm=0.2))` (`sls()`,
  `mjf()`, `slm()` for metal powder bed, `vat()` for resin): `cad model dfm "$ID"` then needs no
  `--process`, `--technology` or `--layer-height`.

## Check it

```bash
cad stl dfm stand.stl --process printing --technology fdm --material petg
cad model dfm "$ID" --process printing --technology sla --build-volume 145x145x185
cad step dfm housing.step --process printing --technology fdm --layer-height 0.12 --candidates
```

The check measures the part as it stands on the plate: its lowest point, Z up. The options that change
the verdicts:

- `--technology fdm|sls|sla|mjf|pbf` (`fdm` by default; `pbf` is metal powder bed fusion): every limit
  and the self-supporting angle are the technology's. A technology the rules have no figure for leaves
  that rule not evaluated. With the process unknown, check each candidate and report per technology.
- `--material`: FDM's warping risk for the materials that warp (`warping_risk`). A metal with a plastic
  technology, or a plastic with `pbf`, is refused.
- `--build-volume XxYxZ`: the person's printer, else a typical machine of the technology's, assumed.
- `--layer-height` and `--nozzle` (FDM): stair-stepping and fine detail; the nozzle sets FDM's minimum
  wall, two of its beads (0.8 mm for the common 0.4 mm nozzle, assumed and said where none is given).
- `--angle-limit`: the person's printer's self-supporting angle, from its datasheet: the overhangs are
  counted and `printing.overhang_angle` judges each against it in place of the technology's figure.
- `--units` (an STL's: millimetres by default) and `--samples` (rays on a mesh).

The rules are general, no printer's or shop's: a machine's own limits come in as options or from its
datasheet. `--candidates` ranks the six axis orientations,
plus the largest flat faces laid down, by support, height and finish, and judges nothing: to check
another orientation, turn the part in its model and check again.

## Read it

The last line is the check's state and its exit status -- `OK` 0, `FAILED` 1 (a finding is an error; with
`--strict` a warning fails too), `NOT CHECKED` 3 (something was not judged: never a pass), and 2 for a
command refused -- and a rule's finding is data to edit from (`value`, `limit`, `unit`, `op`, `source`,
`refs`): [Read the result](../SKILL.md#read-the-result).

The families: `solid` (a mesh's `mesh`), `overhangs`, `bridges`, `wall_thickness`, `knife_edges`, `gaps`, `holes`,
`pins`, `details`, `clearances`, `trapped_volumes`, `build_volume`, `bed`, `stair_stepping`,
`support_volume`, `sections`; `orientations` with `--candidates`.

- Report `not_watertight` or `not_sound` first: it blocks slicing for every technology. A mesh with no
  inside is refused in one finding and measured not at all: `mesh_empty`, `mesh_unreadable`,
  `mesh_too_large` (over 2 million triangles: decimate it), `inconsistent_normals`, `mesh_no_volume`.
  `mesh_repaired` (a warning) says what was put right before measuring -- doubled triangles, triangles
  wound against their neighbours, a shell inside out: export the file again, a slicer reads it as it is.
  `bodies_intersect`: bodies that pass through each other; the volume given is their sum (a body wholly
  inside another is counted once). `several_solids` (a warning): a part of several solids, or a mesh of
  several bodies -- what lies between two of them is a clearance, not a gap. A B-rep of more faces than the
  self-intersection check's budget (1000 in all) is `NOT CHECKED` for the parts past it: check them one at a
  time.
- Walls are `supported` (joined to the part on two sides or more) or not, each with its own minimum
  (`printing.wall_supported`, `printing.wall_unsupported`), read off the wall itself on a STEP and on a
  mesh alike from the outline of its thin region: a fin on its base and a pin on its foot are joined on one
  side; a skin over a cavity, a tray's floor and the land a countersink leaves round a hole are joined all
  round. A wall whose support could not be read is `printing.wall`: judged as supported, and warned of
  between the two minima. FDM judges a skin lying in the layer plane (`lying`) by its layers
  (`printing.skin_layer`, `printing.skin_layers`), not by two beads. On a mesh
  the field is `--samples` rays (2000) from random points over the surface (plus one from every
  triangle on a mesh of 5000 triangles or fewer), each straight in to the face it leaves through, a
  knife edge's own sliver left to the knife family: a thin `min_mm` beside a thick `p05_mm` is a small
  thin place (a web between two cuts, a feather where two surfaces meet at a glancing angle); name it
  from its item's `xyz` and judge it there. A mesh's walls are an item per face and the face across (one
  fin, one item). Every reading is sampled (`sampled`); the thinnest walls are then refined (`refined`):
  on the B-rep to the exact least distance, on a mesh to the least wall about the thinnest sample. On a
  mesh a place smaller than the rays' spacing can still be missed, so a mesh's thin reading is confirmed
  on the STEP or the model before the design changes. A mesh's wall under its limit by no more than its
  chords may stray from the curved surface (`chord_mm`) is a warning, at the limit within the mesh's
  accuracy (a 0.5 mm tube's STL reads 0.498): only the exact model can say which side it falls.
- `printing.knife_edge` is a convex edge under 45 degrees of material somewhere along it, which thins
  to nothing: `angle_deg` is its least, `length_mm` the stretch under 45, `thin_depth_mm` how far in it
  stays under the minimum wall. A warning (text-to-cad's own rule;
  no guide defines a knife edge, and the tip prints rounded): blunt it, chamfer it at 45 degrees or
  more, or move the cut that made it.
- `mesh_at_limit` (info, a mesh alone): curved surface or edges that read within the mesh's own angular
  accuracy of a limit (3 degrees at most) -- a 45 degree cone's triangles read 44.3 to 45.4 -- and were not
  judged. The STEP or the model has the angle; a finer mesh narrows the band. A flat face reads its own
  angle exactly: a 30 degree flat overhang is an overhang on a mesh as on a STEP.
- The powder processes (SLS, MJF) need no support: their overhangs are facts, not verdicts, and
  trapped powder and its escape holes (`trapped_volumes`) are the check instead. A sealed cavity in
  SLA traps resin; in FDM it prints as infill (`internal_void`). Each opening's `min_escape_hole_mm` is the
  hole's own diameter on a STEP and the throat measured on the triangles on a mesh or for an opening that is
  no round hole (within `escape_hole_uncertainty_mm`); MJF's and metal's escape-hole verdicts say they
  apply the SLS guide's figure.
- `support_volume` is a column fill to the plate or the part: a coarse upper bound, a cost and finish
  signal, not a failure unless the person set a budget.
- `clearances` measures each pair of parts in an assembly (and of solids in one part, of bodies in a
  mesh), and walls are per part: attribute a thin wall to its part, never to a fit gap between two. A gap
  is a slot whose walls face each other (within 45 degrees): a thread's V is no slot.
- On a mesh, a round hole up to 3 mm across is read as a hole and judged as on a STEP, and a pin as a
  wall. Pins' own recommended diameters and embossed or engraved detail are not measured (no axes or
  faces): their rules are not evaluated, and the result's line says so ("not judged on a mesh: ...",
  `families_not_measured`) -- so an `OK` of a mesh is of what a mesh can be judged by: check the STEP or
  the model for the rest. A family that ran out of its budget on a very large mesh (`measurement_failed`,
  `clearance_bounded`) makes the result `NOT CHECKED`, never `OK`. When `scale.units_suspect` is true, report
  a units finding and ask before comparing anything.

## Review the part

Collect the technology, material, layer height, and any machine or material datasheet; a datasheet
overrides the rules: cite whichever is used. Check the exact file that will be sliced, or the
model's document. Then check by hand what the check does not measure:

- Tree supports, support density and the designer's cosmetic faces (the check calls a face cosmetic
  by its size).
- A cavity under about five voxels across (`trapped_volumes.pitch_mm`) is found only where it is sealed,
  and an opening under a voxel wide is known only to be that narrow.
- Lattices, minimum feature by local curvature, text legibility, tolerance stack-ups and residual
  stress beyond the largest cross-section.
- A horizontal round hole is judged by its diameter (`printing.horizontal_hole`: over 10 mm on FDM its
  crown sags; a teardrop or a turn of the part fixes it), not as a bridge; smaller ones print unsupported.
  A mesh has no axes: there its crown reads as a bridge of its span (`printing.bridge_length`).

For every fail, give a concrete, plain-language instruction with target numbers from the hint (for
example "thicken the wall at housing/face 8 from 0.3 mm to at least 1 mm"). When the model's source can
be edited, offer to apply it and check the regenerated part again, until no error remains.
