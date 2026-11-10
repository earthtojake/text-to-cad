# CNC machining

The evidence and the rules are SKILL.md's [Can it be made?](../SKILL.md#can-it-be-made), and the result
in full, the review and how to check a redesign are [the review reference](manufacturing-review.md),
the same for every process; this is what is particular to milling and turning.

## Design it

What a part built for milling has from its first line, so its first check passes or nearly (the
rules' numbers: general practice from Protolabs Network's guide where it states one, text-to-cad's own
floor where it does not, each finding saying which; `--tools` moves the tool's):

- **Stock and setups.** Start from the blank (`--stock`, else the part's box) and put the features on
  as few sides as can be: each side a tool must face is a setup, five at most (text-to-cad's reading
  of the guide's "rotated up to three or four times"). The check machines each part in its own frame, the one its faces and holes
  square, whatever its pose in the model (`machine.frames`). A pocket or a hole along none of that
  frame's six directions (`cnc.inclined_feature`) is a setup of its own on an angled fixture, or more
  axes: align it with the part's faces where the design allows.
- **Pockets, slots and windows.** Walls on a flat floor (or none: a window), square to it or drafted
  back up to 25 degrees: a drafted, lofted or tapered pocket is judged as its straight twin, its width
  and its corners' radius read at the floor, where they are least. Every vertical
  internal corner gets a radius -- at least half the smallest end mill (with no `--tools`, 1.25 mm or
  more is recommended), and a third of the cavity's depth where the design allows -- never a sharp
  corner, which no round tool cuts (the error): `part = part.fillet(r, part.edges().filter_by(bd.Axis.Z).filter_by(inside_the_pocket))`
  after the cut. Depth at most four times the width (a tool reaches three to four diameters); past 30
  widths no tool reaches the floor (an error), and a corner or a slot that takes a tool under 1 mm is
  made 25 to 30 of that tool's diameters deep at most (25 at 0.5 mm and under, rising evenly to 30 at
  1 mm; an error past it: a 0.1 mm corner radius 6 mm down is EDM's). A straight slit open at both
  ends is a slitting saw's past that (`cnc.slitting_saw`, a warning), to 60 of its widths. An annular
  cavity -- an O-ring's face groove, a round pocket about a boss -- is a pocket, its width the radial
  gap. Lettering (at most 1 mm deep, under 2.5 mm wide) is an engraving tool's: its corners are no
  error (`cnc.engraving` says it once; its strokes still warn as gaps under 2.5 mm). The floor-to-wall root may stay sharp. A hex or an odd-angle socket cannot be milled
  sharp: give its corners a radius or call out a broach.
- **Holes.** Standard drill diameters (6.8 mm for M8, 4.2 for M5, 6.6 for an M6 clearance; `cnc.drill_size`
  names the nearest), 1 mm or more (under it a hole is micro-drilled, a warning, and reaches 25 to 40
  diameters as a slot that narrow does; under 0.05 mm an error), depth at most four diameters -- a counterbore's and a stepped bore's larger step too, each
  over its own diameter -- and a thread as its tap-drill hole with a callout, not modelled.
- **Walls and gaps.** Walls 0.8 mm or more in metal, 1.5 mm in plastic (0.5 / 1.0 are the floor);
  gaps 2.5 mm or wider (or the smallest tool). A wall, rib, pin or boss standing more than four
  times its thickness, whatever its thickness, chatters as it is cut (`cnc.tall_feature`, a warning):
  shorten it, thicken it or tie it to a neighbour.
- **Reach.** Every face seen straight from one of the part's six axis directions (3 axes; its own
  frame, not the world's); no undercut, and a
  T-slot or dovetail, through or blind (a closed one with an entry hole the cutter drops into), or a
  groove inside a bore (a keyseat cutter's), only where the
  person planned the cutter (`cnc.special_cutter` or `cnc.undercut`, a warning) -- and only as deep
  past its opening as half the opening is wide, the most a disc that passes the opening reaches: a
  chamber wider than twice its bore, a cavity behind a vent, a passage that turns a corner inside the
  part is a face no tool gets to (`cnc.no_line_of_sight`, an error, rounded edges or not). No closed
  void.
- **Size.** A part over 2000 mm long is past what a general shop's mill takes (a lathe's 431 mm
  across and 990 mm long), and over 4000 mm (a lathe's 1000 mm across) a specialist's machine: both
  warnings -- long-bed mills and vertical lathes exist -- so size alone fails no part. Give `--stock`
  to have the part held to a blank (an error where it does not fit).
- **Turning.** One axis of revolution, diameters stepping down toward the free end, outside grooves
  as wide as the shop's grooving tool and no deeper than five widths, an internal groove no deeper
  than a quarter of the bore its tool enters by (a warning; past half of it an error), no section
  longer than ten of its own diameters without a steady rest (a warning, judged a section: a thin
  stem on a wide flange is as slender as the stem alone), cross holes square to the axis (through it or beside
  it); a flat, a keyway or an off-axis hole is live tooling.
- **One solid a part.** A part that holds several separate solids is judged solid by solid, each its
  own stock and setups (`several_solids` says so): fuse what is one piece, export the rest
  as an assembly's parts.
- The material and the process on the part: `part.material = metals.aluminum(process=machined())`
  (`bd_materials.processes`); `cad model dfm "$ID"` then needs no `--process` or `--material`.

## Check it

```bash
cad model dfm "$ID" --process cnc --material aluminum
cad step dfm plate.step --process cnc --material aluminum --axes 5 --tools 3,6,10
cad step dfm shaft.step --process cnc --turning --material stainless
```

The options that change the verdicts:

- `--material`: metal or plastic wall limits. Without it walls are judged as metal
  (`cnc.material_assumed`).
- `--axes 3|4|5` (3 by default): the directions that reach a face, the setups it takes.
- `--turning`: the part is turned on a lathe. Its axis, diameters, bores, grooves and the off-axis
  features that need live tooling are measured instead of pockets and corners, and judged: the
  grooves, the part's slenderness and size, its walls, holes and voids, and every face no tool
  reaches. What turning does not judge -- setups and chucking, a sharp concave edge or a narrow gap
  off the grooves -- it says (`cnc.turning_not_judged`): check the part without `--turning` for its
  milled features.
- `--tools 3,6,10`: the shop's end mill diameters. Corner radius and gap limits then follow the
  smallest; a corner no tool fits leaves its reach unmeasured.
- `--stock 100x60x25`: the blank, else the part's box. A face of the stock's own (where the blank is
  as long as the part) is no setup's to cut, typed or not; a bare block takes none.

The rules are general, no shop's: a shop's own machine sizes, lathe capacity and feature limits (its
narrowest engraved line, its turned diameters and grooves) are compared with the measurements
(`stock`, `turning`, `turned_diameters`, `grooves`, `holes`). An error means no general shop makes
the part as drawn; a warning that it is made, dearer or less true. A finding names its
`source`: the guide's, or `text-to-cad` for a floor of its own (its reason in the rule's note,
`measurements.rules`). A part of over 4000 faces is not measured, and says so (the bound on a
check's time: check it in smaller pieces). An assembly's every occurrence is judged and counted,
however its instances are turned. A mesh is refused: check the STEP or the model.

## Read it

The last line is the check's state and its exit status -- `OK` 0, `FAILED` 1 (a finding is an error; with
`--strict` a warning fails too), `NOT CHECKED` 3 (something was not judged: never a pass), and 2 for a
command refused -- and a rule's finding is data to edit from (`value`, `limit`, `unit`, `op`, `source`,
`refs`): [Read the result](../SKILL.md#read-the-result).

The families: `holes`, `threads`, `pockets`, `internal_corners`, `sharp_edges`, `walls`, `gaps`,
`access`, `setups`, `voids`, `stock`, `small_features`; with `--turning`, `turning`,
`turned_diameters`, `bores`, `grooves` and `live_tooling`.

- `internal_corners` are a pocket's in-plane corners: `radius_mm` (a drafted corner's at the floor),
  `depth_mm`, and `reach_ratio`, the depth over the largest tool that fits. Each corner is its own
  finding at its own face -- `refs[0]` is the fillet to edit, the cavity's floor after it (`pocket`) --
  as a sharp one is at its edge. A floor-to-wall root is never a corner: a flat end mill
  makes it sharp, and a root fillet is optional (it takes a corner-radius or ball tool).
- `cnc.sharp_internal_edge` is a concave edge no tool of the machine makes; its item's `reason` says
  why (`acute`, `vertical_corner`, `blocked`, `no_square_face`, or `other_axes`: a direction the
  machine lacks would make it, a warning) and the hint follows it. A square corner a square end mill
  forms from some side -- its end on one face, its flank on the other, seen from outside (a plate's
  notch, however it is turned) -- is made, that side one more setup (`setups`); so is a V a chamfer
  mill cuts along its bisector. An obtuse root between two flats each faced from its own side is made
  too, and adds no setup of its own: it is made in the setups that make its faces; side-milled, it keeps
  the tool's radius, a warning saying how many more setups make it sharp (one where a face is square to a
  counted setup). A chamfer mill's V, shoulder or tip, and an end mill's corner over a chamfer below a wall,
  are formed as drawn: nothing said (a slot's 45-degree floor chamfers need no slot cutter). A tool makes an edge only where it reaches its whole length: a window or a low lip that
  opens part of a corner leaves the rest unmade, and the finding says how much and where. A gear's
  curved tooth root or a closed pocket's corner no tool forms from any side: an error. The fix is a radius or a relief
  where acceptable; another setup, a special cutter or EDM are proposals, not a verified plan. Where the
  recommended radius does not fit the cavity's width, the hint names the process instead (a keyway: broached
  or slotted; another corner: EDM). A
  crease a ball end mill rounds stays in the record (`made_by`, `deviation_mm`; `cnc.ball_creases`).
  A corner of 150 degrees or more along the tool's axis (a many-sided pocket's, a faceted arc's) is the
  end mill's flank's: made, the radius it leaves said (`end_mill_flank`, `deviation_mm`; `cnc.flank_corners`),
  a warning past 0.05 mm (`cnc.flank_corner_residue`, text-to-cad's own figure).
- `access` is line of sight for a tool of no diameter: `undercut` faces five axes would reach,
  `no_line_of_sight` faces nothing straight reaches -- one item a recess, its faces listed, with
  `disc_reach` (a disc cutter on a straight shank gets to them through an opening that holds the disc:
  a warning, `cnc.undercut`) and `no_tool_fraction` (the share no such cutter reaches either: an
  error, `cnc.no_line_of_sight`) --, `special_cutter` edges only a T-slot, dovetail or
  keyseat cutter makes -- only where its shank finds a way out beside the whole edge, its disc
  clears the part and the disc can get there (a keyseat's down a bore no narrower than it; a T-slot's
  through an opening as wide as it or from a side the slot opens to): a chamber behind a small bore or
  port is `no_way_in`, an error. A V or dovetail of no standard angle (the 66 degree O-ring dovetail, a
  75 degree V) is a special cutter ground to it, named with its angle; a wall a few degrees past square
  (an 87 degree dovetail) is asked squared, which an end mill makes. A slot cutter's neck narrower than
  the recess is tall (`narrow_opening`) and a profile's obtuse root, which side-milling rounds
  (`obtuse_root`), are warnings.
- `setups.setup_count` estimates clampings from the reachable directions and the sides square corners
  are side-milled from (a direction's `sharp_edges`); a hole is one setup along its axis, from the
  end that reaches all of it.
- `walls` carry `standing` and `height_to_thickness` for a feature that rises from a root (a
  fin, a rib, a pin, a wall beside a pocket); `grooves` (turning) `depth_to_width` and, internal,
  `entry_diameter_mm` and `depth_to_entry`; `turned_diameters` each section's slender run
  (`run_mm`, `run_to_diameter`).
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
- Tolerances and surface finish; a T-slot or dovetail cutter's travel from its way in; pockets whose
  floor is not planar (reported through `access` and `walls`); engraved text deeper than 1 mm or
  wider than 2.5 mm (judged as pockets), and the stroke width the shop's engraving tool cuts.
- Turning: parting and chucking allowances, a cone's point angle, a boring bar's reach down a deep
  bore (judged as a drilled hole's depth). Rotational symmetry alone does not prove tool access.
- A disc cutter's travel from where it gets in to where it cuts, and a recess fed from an open side
  that no straight line reaches into.

Separate geometry constraints from cost suggestions. Preserve functional interfaces; suggest relaxed
tolerances only where function permits them.

## Worked reasoning example

The following numbers are illustrative inputs, not default process limits.

`cnc.internal_corner_radius at plate/face 9: internal corner radius 0.5 mm is under the 1.5 mm
minimum (...) (8 mm tall, a corner of the cavity at plate/face 7)`, from a check with
`--tools 3,6,10`, and three more like it at `plate/face 11`, `13` and `15`. `plate/face 9` is the
corner's own fillet (`refs[0]`), `plate/face 7` the pocket's floor; `cad model inspect "$ID"
'plate/face 9'` shows a cylinder of radius 0.5 mm 8 mm deep. Report the pocket's four corners as fail
against the 3 mm tool, and propose a radius of at least 1.5 mm on each, or a smaller tool if the shop
has one; reach and holder clearance remain checks of their own.
