# Injection molding

Read this file before modelling or checking a part that is injection molded. What every process
shares (the result in full, a shop's own limits, the review, a redesign) is
[the review reference](manufacturing-review.md).

## Design it

The numbers are recommendations of Protolabs' and Protolabs Network's (Hubs) injection molding guides
and of Xometry's rib guide, named beside each. The few errors are the floors under
[Check it](#check-it).

- **The pull first.** Decide which way the mold opens (`--pull z`: the open side of a box faces +Z)
  and model every feature along it. Extrude the outside up from the parting face with draft, and cut
  the cavity down from the open face with the same draft, so both release:

  ```python
  body = bd.extrude(bd.Rectangle(60, 40), 20, taper=2)                      # 2 degrees, narrowing upward
  cavity = bd.Pos(0, 0, 20) * bd.extrude(bd.Rectangle(56, 36), -18, taper=2)  # from the open face down, narrowing
  body = body - cavity
  ```

  Every wall wants 2 degrees (Hubs, Protolabs) and 0.5 at least on a vertical face (Protolabs): a
  warning under either. A light texture takes 3 and a heavier one 5 or more (Protolabs; not
  checked). A face square to the pull is no wall and takes none; a hole or a boss is drafted as a
  wall is.
- **One wall.** A nominal wall in the resin's recommended range (Protolabs' table: ABS 1.1 to
  3.6 mm, PC 1.0 to 3.8, nylon 0.8 to 2.9; a check's `measurements.rules` has the range of the
  resin it was given) and no section over 1.67 times it (Protolabs): core out thick spots. Change
  thickness over a length of 3 times the step (Hubs).
- **Ribs and bosses.** A rib is at most 60% of the wall it stands on (Xometry), at most 3 walls
  tall (Hubs) and at least 2.5 walls from the next (Xometry), drafted 0.5 degree or more (Xometry),
  with a root fillet of a quarter of its own thickness (Hubs). Run a rib well into the wall it meets
  or stop it clear: a square end a hair off a drafted wall is a crevice whose steel is a knife edge
  (`crevices`, a warning). A boss is a drafted tube whose wall is at most 60% of the wall it stands
  on (Protolabs), its hole along the pull and its root filleted (`molding.boss_root_fillet`). A snap
  arm is a rib with a barb: at least half the wall thick (Hubs), its barb an undercut.
- **Corners.** Inside radius at least half the wall (Hubs), outside radius the inside plus the wall,
  so the thickness stays constant round the corner.
- **Undercuts.** A feature that will not pull straight (a side hole, a snap hook, a lip under a rim)
  takes a side action or a lifter: a warning, and a cost. One nothing frees is an error. Avoid it,
  or plan the action with the person.
- The resin and the process on the part are `part.material = plastics.abs_(process=molded())`
  (`molded` from `bd_materials.processes`): the check then takes `--pull` alone.

## Check it

```bash
cad model dfm "$ID" --process molding --pull z --material abs --cavities 4
cad step dfm cover.step --process molding --candidates
```

- `--pull`: the pull, an axis (`z`, `-y`) or `x,y,z` components; `z` by default, and the result then
  says it measured "the default pull". Draft and undercuts are relative to it, and the part is
  measured along it as it stands: a part modelled tilted is measured tilted. With no confirmed pull,
  rank the pulls with `--candidates` (it judges nothing, whatever its `OK`) and report draft as
  unverified rather than failing every vertical-looking face.
- `--material`: the resin's wall range and clamp factor. With none, or a resin Protolabs' table
  lacks, the range is not evaluated (`resin_unknown` lists the resins it has).
- `--cavities`: the cavities the clamp-force estimate counts.

A warning is a guide's recommendation broken, or a cost: the part is made. An error is what a
general molder sends back, and there are few:

| Error | The floor | Whose |
| --- | --- | --- |
| `molding.undercut_unreleasable` | a feature no slide, lifter or core frees | Hubs |
| `molding.draft_zero` | a broad wall of the shell with too little draft for its depth: none is asked up to 10 mm deep in one mold half, then 0.01 degree for every millimetre past that, 0.25 degree at most | own |
| `molding.wall_too_thin` | a broad wall under half the resin's recommended minimum (no resin of the table named: under 0.51 mm, the least minimum in it) | own |
| `molding.clamp_beyond_press` | a projected area over 6.45 m2 a cavity, which takes over 10 000 US tons even at a ton per square inch: no injection press built clamps it (check the units first) | own |

The floors judge the shell's walls, never a feature. A wall is broad at ten wall thicknesses
across: a boss, a bore, a pin, a gear's teeth, a snap arm, a rib and a window's sides are not, so
their missing draft is the recommendation's warning (`molding.draft_min`). A text stroke, a ridge's
crest, a snap's barb and a living hinge's web are features, whose width is `molding.wall_min`'s
warning at most. Depth is a mold half's: a wall the parting line runs up is split where the parting
plane stands. A wall over twice the resin's recommended maximum (`molding.wall_too_thick`) and an
estimated clamp force over 1 000 US tons (`molding.clamp_large_press`: a press few molders run) are
warnings, own.

Compare a press's and a mold's own limits (projected area, part size, depth from the parting line,
a side action's travel) with `measurements` `projection`, `envelope`, `undercuts` and `clamp`.

## Read it

The result is read as [every process's](manufacturing-review.md#read-the-result). The families of
`measurements`: `draft`, `undercuts`, `thickness`, `transitions`, `ribs`, `bosses`, `corners`,
`projection`, `envelope`, `parting`, `clamp`, `pull_check`; `pulls` with `--candidates`.

- `draft` items carry `draft_deg`; `opens` (`+pull`, `-pull`, `none` for zero draft, `split` where
  the parting crosses the face); and `half_depth_mm` and `broad`, which the draft floor judges.
- `undercuts` items carry the `release` each needs (`side_action` with its `side_actions`
  directions and `stroke_mm`, `lifter`, `collapsible_core`, `bump_off`, `none`) and its `kind`
  (`external`: a slide reaches it from beside the part; `internal`: a lifter's or a core's). Budget
  side actions from `undercuts.side_action_count` and `side_action_directions`, the part's distinct
  slide directions (three slots along +y are one slide), not from its count of features.
  `molding.undercut_bump_off` (a warning) is a lip of 0.1 mm or less (own) stripped off as the part
  ejects: it needs a flexible resin and a rounded lead-in.
- `thickness` (`nominal_mm`; each face's `feature` says whether it is a wall's, a rib's or a
  boss's, and the wall range judges walls alone), `transitions`, `ribs`, `bosses` and `corners` are
  sink and stress signals, not a fill simulation.
- `parting.flat_parting_possible` false is `stepped_parting`, a warning: a costlier mold.
- `clamp` is an estimate (`clamp_estimate`): the part's projected area alone, no runner, at a
  molder's tonnage factor for the resin.
- `pull_better` (a warning): another of the part's own directions does better than the pull
  measured. It leaves fewer features nothing releases or, with as many, is no worse in actions,
  trapped area, wall without draft and parting, and better in one. Its hint is the `--pull` to try.
  Confirm the pull before budgeting side actions or drafting walls; no `pull_better` is not a
  confirmed pull. The pulls compared, and the ones `--candidates` ranks, are `x`, `y`, `z` and the
  part's own: `face0`.. (the directions most of its surface is square to or turns about) and
  `principal0`.. (its principal axes).
- An assembly (`several_bodies`): each part is judged along its own pull, the one given unless one
  of its own directions does better for it (`part_pull`, a warning, names the part and the pull),
  and the areas and the clamp force count every occurrence. Report it as an assembly, not as one
  molded part.
- Three findings say what was not judged, and none is a pass. `crevices` (a warning): two faces
  closer than steel can stand between them, so join them or part them. `undercuts_unsearched` (a
  warning): features found whose release the search's budget did not reach; each is warned as an
  undercut, and where they are most of what is trapped the check is `NOT CHECKED`. Check again with
  `--pull` along the slide expected to free them. `undercuts_unconfirmed` (info): places that read
  trapped on a few points and not on denser ones: look there for a small re-entrant feature.

## Review the part

The check is of conventional thermoplastic injection molding: its limits are not silicone's,
overmolding's or insert molding's. Check by hand what it does not measure:

- Texture draft, the extra draft of a tall wall, a shut-off's draft.
- Stripping undercuts, snap-fit and living-hinge proportions, threads, a boss against its screw.
- A slide's own clearance (its `stroke_mm` is to where its points clear the part), and a feature
  smaller than the spacing of the points the undercut test samples, which it can miss.
- Gate, vents, weld lines, packing, cooling, shrinkage and warpage: the toolmaker's, never a
  validated cycle time. Do not rescale the part for shrinkage without the toolmaker's figures.
