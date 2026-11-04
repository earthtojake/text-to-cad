# CNC machining

The evidence, the rules, the review and how to check a redesign are SKILL.md's
[Can it be made?](../SKILL.md#can-it-be-made), the same for every process; this is what is particular
to milling and turning.

## Design it

What a part built for milling has from its first line, so its first check passes or nearly (the
`generic` set's numbers, from Protolabs Network's guide; a shop's set or `--tools` moves them):

- **Stock and setups.** Start from the blank (`--stock`, else the part's box) and put the features on
  as few sides as can be: each side a tool must face is a setup, four at most.
- **Pockets, slots and windows.** Vertical walls on a flat floor (or none: a window). Every vertical
  internal corner gets a radius -- at least half the smallest end mill (1.25 mm with no `--tools`),
  and a third of the cavity's depth where the design allows -- never a sharp corner, which no round
  tool cuts: `part = part.fillet(r, part.edges().filter_by(bd.Axis.Z).filter_by(inside_the_pocket))`
  after the cut. Depth at most four times the width (a tool reaches three to four diameters). The
  floor-to-wall root may stay sharp. A hex or an odd-angle socket cannot be milled sharp: give its
  corners a radius or call out a broach.
- **Holes.** Standard drill diameters (6.8 mm for M8, 4.2 for M5, 6.6 for an M6 clearance; `cnc.drill_size`
  names the nearest), depth at most four diameters, and a thread as its tap-drill hole with a callout,
  not modelled.
- **Walls and gaps.** Walls 0.8 mm or more in metal, 1.5 mm in plastic (0.5 / 1.0 are the floor);
  gaps 2.5 mm or wider (or the smallest tool).
- **Reach.** Every face seen straight from one of the six axis directions (3 axes); no undercut, no
  T-slot or dovetail unless the person planned the cutter; no closed void.
- **Turning.** One axis of revolution, diameters stepping down toward the free end, outside grooves
  at least 1.2 mm wide, cross holes radial; a flat, a keyway or an off-axis hole is live tooling.
- The material on the part: `part.material = metals.aluminum()`; the check reads it.

## Check it

```bash
cad model dfm "$ID" --process cnc --material aluminum
cad step dfm plate.step --process cnc --material aluminum --axes 5 --tools 3,6,10 --rules protolabs
cad step dfm shaft.step --process cnc --turning --material stainless
```

The options that change the verdicts:

- `--material`: metal or plastic wall limits, hardness, a shop's envelope. Without it walls are
  judged as metal (`cnc.material_assumed`).
- `--axes 3|4|5` (3 by default): the directions that reach a face, the setups it takes, a shop's
  envelope.
- `--turning`: the part is turned on a lathe. Its axis, diameters, bores, grooves and the off-axis
  features that need live tooling are measured instead of pockets and corners.
- `--tools 3,6,10`: the shop's end mill diameters. Corner radius and gap limits then follow the
  smallest; a corner no tool fits leaves its reach unmeasured.
- `--stock 100x60x25`: the blank, else the part's box.

Rule sets: `generic`, `hubs`, `protolabs`, `xometry`. A mesh is refused: check the STEP or the model.

## Read it

The families: `holes`, `threads`, `pockets`, `internal_corners`, `sharp_edges`, `walls`, `gaps`,
`access`, `setups`, `voids`, `stock`, `small_features`; with `--turning`, `turning`,
`turned_diameters`, `bores`, `grooves` and `live_tooling`.

- `internal_corners` are a pocket's in-plane corners: `radius_mm`, `depth_mm`, and `reach_ratio`, the
  depth over the largest tool that fits. A floor-to-wall root is never a corner: a flat end mill
  makes it sharp, and a root fillet is optional (it takes a corner-radius or ball tool).
- `cnc.sharp_internal_edge` is a concave edge no rotating tool makes. The fix is a radius or a relief
  where acceptable; another setup, a special cutter or EDM are proposals, not a verified plan.
- `access` is line of sight for a tool of no diameter: `undercut` faces five axes would reach,
  `no_line_of_sight` faces nothing straight reaches.
- `setups.setup_count` estimates clampings from the reachable directions.
- `holes` carry `standard_drill` and `tap_candidate` as facts: a diameter that matches a drill or a
  tap drill, not a callout.

## Review the part

Collect material, stock form, milling or turning, the axes, critical fits and tolerances, and the
shop's tools. With the process unspecified, discuss candidate setups without claiming a machining
plan. Then check by hand what the check does not measure:

- Tool holder and spindle collisions. A cutter that fits a corner or a pocket does not prove holder
  access; reach limits are material-specific.
- Fixturing, workholding, stock allowance and setup changes. Treat setup counts as estimates; no
  cycle time or quote without that evidence.
- Thread callouts on the drawing, engagement, drill-tip clearance: the check sees modelled threads
  and tap-drill diameters only. Follow the shop's thread representation.
- Tolerances and surface finish; a T-slot or dovetail cutter's entry path; pockets whose floor is not
  planar (reported through `access` and `walls`); engraved text (seen only as fine faces and narrow
  gaps).
- Turning: parting and chucking allowances, ID groove depth beyond the bore, a cone's point angle.
  Rotational symmetry alone does not prove tool access.

Separate geometry constraints from cost suggestions. Preserve functional interfaces; suggest relaxed
tolerances only where function permits them.

## Worked reasoning example

The following numbers are illustrative inputs, not default process limits.

`cnc.internal_corner_radius at plate/face 7: internal corner radius 0.5 mm is under the 1.5 mm
minimum`, from a check with `--tools 3,6,10`. `cad model inspect "$ID" 'plate/face 7'` shows a cylinder
of radius 0.5 mm 8 mm deep. Report the corner as fail against the 3 mm tool, and propose a radius of
at least 1.5 mm, or a smaller tool if the shop has one; reach and holder clearance remain checks of
their own.
