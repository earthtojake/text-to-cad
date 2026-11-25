# CNC machining

Read this file before modelling or checking a part that is milled or turned. What every process
shares (the result in full, a shop's own limits, the review, a redesign) is
[the review reference](manufacturing-review.md).

## Design it

The numbers are Protolabs Network's (Hubs) CNC design guide's, and those marked *own* are
text-to-cad's where the guide states none (a partial hole is Fictiv's guide's). `--tools` puts the shop's end mills in place of the tool
sizes here.

- **Setups.** Put the features on as few sides as can be: each side a tool must face is a setup,
  and a sixth warns (own, from the guide's "rotated up to three or four times"). Each part is
  machined in its own frame, the one its faces and holes square, whatever its pose in the model
  (`measurements.machine.frames`). A pocket or a hole along none of that frame's six directions is a
  setup of its own on an angled fixture, or more axes (`cnc.inclined_feature`, a warning).
- **Pockets, slots and windows.** Walls rise from a flat floor (a window has none), square to it or
  drafted back by up to 25 degrees (own); a drafted pocket's width and corner radii are read at its
  floor, where they are least. An annular cavity (an O-ring's face groove, a round pocket about a
  boss) is a pocket as wide as its radial gap.
- **Corners.** With `--tools`, every corner along the tool's axis takes a radius of at least half
  the smallest end mill (an error under it); with none, 1.25 mm, a 2.5 mm end mill's, is
  recommended. A sharp corner is an error either way: no round tool cuts it. A third of the
  cavity's depth is recommended too. The floor-to-wall root may stay sharp.
- **Depth.** A cavity at most 4 times as deep as it is wide (a warning past it: a tool reaches 3 to
  4 diameters); past 30 no tool reaches the floor (an error). A tool under 1 mm reaches 25 of its
  diameters at 0.5 mm and under, rising evenly to 30 at 1 mm (own). A straight slit open at both
  ends is a slitting saw's past that (`cnc.slitting_saw`, a warning), to 60 of its widths (own).
- **Lettering.** At most 1 mm deep (own) and under 2.5 mm wide it is an engraving tool's: its
  corners are no error (`cnc.engraving` says so once), and its strokes still warn as gaps under
  2.5 mm.
- **Holes.** A standard drill's diameter (`cnc.drill_size` warns over 0.005 mm from a metric,
  fractional, number or letter drill; own tolerance), 1 mm or more (smaller is micro-drilled, a
  warning; under 0.05 mm an error) and at most 4 diameters deep (a warning; 40 is the error, and a
  micro drill's 25 to 40, own). A counterbore, and a stepped bore's larger step, is judged over its
  own diameter. Model a thread as its tap-drill hole with a callout, not as a thread. Keep a drilled
  hole's mouth a whole circle on one face: one that straddles a pocket's wall, a step, a rib or the
  part's side is a partial hole (`cnc.partial_hole`, a warning: the drill wanders, and the wall keeps
  the hole's scallop). Move it back by the finding's `value`, its reach past the wall, or widen the
  pocket to take it whole. A slot that runs into a hole (a clamp's slit, a keyway) is not one.
- **Walls and gaps.** Walls 0.8 mm or more in metal and 1.5 mm in plastic (0.5 and 1.0 are the
  errors); gaps 2.5 mm or wider, and never narrower than the smallest tool. A wall, rib, pin or
  boss standing over 4 times its thickness chatters as it is cut (`cnc.tall_feature`, a warning,
  own): shorten it, thicken it or tie it to a neighbour.
- **Reach.** On 3 axes every face is seen straight from one of the part's six directions. A T-slot,
  a dovetail or a groove inside a bore takes a special cutter (`cnc.special_cutter`, `cnc.undercut`:
  warnings): keep one for where the person planned the cutter, and no deeper past its opening than
  half the opening is wide, the most a disc that passes the opening reaches. A face no tool gets to
  (a chamber wider than twice its bore, a passage that turns a corner inside the part) is an error
  (`cnc.no_line_of_sight`, own, by geometry), as a closed void is (`cnc.enclosed_void`).
- **Size.** A part over 2000 mm long, or turned over 431 mm across or 990 mm long, is past a
  general shop's machine (the guide's service page), and over 4000 mm, or turned over 1000 mm
  across, a specialist's (own). Both are warnings: size alone fails no part.
- **Turning.** One axis of revolution. An outside groove no deeper than 5 of its widths; an internal
  groove no deeper than a quarter of the bore its tool enters by (past half, an error); no section
  longer than 10 of its own diameters without a steady rest (all own; warnings but that error). A
  flat, a keyway or an off-axis hole is live tooling.

## Check it

```bash
cad model dfm "$ID" --process cnc --material aluminum --axes 5 --tools 3,6,10
cad step dfm shaft.step --process cnc --turning --material stainless
```

- `--material`: a metal's or a plastic's wall limits; with none, a metal's (`cnc.material_assumed`).
- `--axes 3|4|5` (default 3): the directions that reach a face, and so the setups.
- `--tools 3,6,10`: the shop's end mill diameters. Corner radius and gap limits follow the smallest;
  a corner no tool given fits has no reach to judge.
- `--stock 100x60x25`: the blank, else the part's box. A part that does not fit it is an error
  (`cnc.stock_too_small`). With no `--stock` the faces on the part's box are the blank's own and
  take no setup; a larger blank has them cut.
- `--turning`: the part is turned on a lathe. Its axis, diameters, bores and grooves are measured
  and judged with its walls, holes, voids and reach. Setups, sharp concave edges and gaps are not,
  which `cnc.turning_not_judged` says: check the part again without `--turning` for its milled
  features.

A part of over 4000 faces is not measured (`NOT CHECKED`): check it in smaller pieces. Compare a
shop's own machine sizes and feature limits with `measurements` `stock`, `turning`,
`turned_diameters`, `grooves` and `holes`.

## Read it

The result is read as [every process's](manufacturing-review.md#read-the-result). The families of
`measurements`: `holes`, `counterbores`, `threads`, `pockets`, `internal_corners`, `sharp_edges`,
`knife_edges`, `walls`, `gaps`, `access`, `setups`, `voids`, `stock`, `small_features`; with
`--turning`, `turning`, `turned_diameters`, `bores`, `grooves` and `live_tooling`.

- `holes` carry `mouth` (`whole`, `slotted`, `stepped` or `open`), `past_wall_mm` and `cut_by`: what
  a wall across a hole's mouth makes of it. `cnc.partial_hole` judges the drilled ones.
- `internal_corners` are a pocket's corners along the tool's axis; `reach_ratio` is the depth over
  the largest tool that fits. A round corner's finding is at its own face (`refs[0]`, the fillet to
  edit), the cavity's floor after it (`pocket`); a sharp one's is at its edge.
- `cnc.sharp_internal_edge` is any other concave edge no tool of the machine makes. Its item's
  `reason` says why, and the hint follows it: `acute`, `vertical_corner`, `blocked`,
  `no_square_face` and `no_way_in` are errors; `other_axes` (more axes make it), `narrow_opening`
  and `obtuse_root` are warnings. An edge a tool forms from some side is no finding: a square corner
  a square end mill side-mills (that side one more setup), a V a chamfer mill cuts. The fix is a
  radius or a relief; another setup, a special cutter or EDM is a proposal, not a verified plan.
- A crease a ball end mill rounds, and a corner of 150 degrees or more that the end mill's flank
  makes, are made: `deviation_mm` is how far from the drawn edge (`cnc.ball_creases`,
  `cnc.flank_corners`; past 0.05 mm, own, the warning `cnc.flank_corner_residue`).
- `access` is line of sight for a tool of no diameter. `kind` `undercut`: five axes would reach the
  face. `no_line_of_sight`: nothing straight does; `disc_reach` says a disc cutter through its
  opening gets there (`cnc.undercut`, a warning), and `no_tool_fraction` is the share nothing
  reaches (`cnc.no_line_of_sight`). `special_cutter`: edges only a T-slot, dovetail or keyseat
  cutter makes, the finding naming the cutter.
- `setups.setup_count` is an estimate of clampings: the directions that reach the faces, and the
  sides corners are side-milled from.

## Review the part

Check by hand what the check does not measure:

- Tool holder and spindle collisions: a cutter that fits a corner or a pocket does not prove the
  holder gets there.
- Fixturing, workholding and stock allowance; tolerances and surface finish. A setup count gives no
  cycle time or quote.
- Thread callouts, engagement and drill-tip clearance: the check sees modelled threads and
  tap-drill diameters only (a hole's `tap_candidate` is a diameter that matches, not a callout).
- A disc cutter's travel from where it gets in to where it cuts, and a recess fed from an open side
  that no straight line reaches into.
- Pockets whose floor is not planar (reported through `access` and `walls`); engraving deeper than
  1 mm or wider than 2.5 mm (judged as pockets), and the stroke the shop's engraving tool cuts.
- Turning: parting and chucking allowances, a cone's point angle, a boring bar's reach down a deep
  bore (judged as a drilled hole's depth).
