# Injection molding

The evidence and the rules are SKILL.md's [Can it be made?](../SKILL.md#can-it-be-made), and the result
in full, the review and how to check a redesign are [the review reference](manufacturing-review.md),
the same for every process; this is what is particular to injection molding.

## Design it

What a molded part has from its first line (the rules' numbers, general practice from Protolabs' and
Protolabs Network's guides; a molder's own figures move them):

- **The pull first.** Decide which way the mold opens (`--pull z`: the open side of a box faces +Z) and
  model every feature along it. Build the outside by extruding the outline up from the parting face
  with draft, and cut the cavity by extruding the inner outline down from the open face with the same
  draft, so both release:

  ```python
  body = bd.extrude(bd.Rectangle(60, 40), 20, taper=2)                      # 2 degrees, narrowing upward
  cavity = bd.Pos(0, 0, 20) * bd.extrude(bd.Rectangle(56, 36), -17, taper=2)  # from the open face down, narrowing
  body = body - cavity
  ```

  Every wall wants 2 degrees (Hubs' and Protolabs' recommendation; 0.5 at least on a vertical face,
  Protolabs: a warning under either; a light texture takes 3, a heavier one 5 or more) to eject cleanly,
  and a wall or a rib deeper than 10 mm with no draft at all is an error; a face square to the pull is
  not a wall and takes none. A hole or a boss is drafted the same way.
- **One wall.** A nominal wall in the resin's range (ABS 1.1 to 3.6 mm, PC 1.0 to 3.8, nylon 0.8 to 2.9;
  the material table has the rest) and no section thicker than 1.7 times it: core out thick spots. A
  wall under half the range's minimum or over twice its maximum is an error.
  Change thickness over a length of three times the step, never a sharp step.
- **Ribs and bosses.** A rib is 50 to 60% of the wall it stands on, at most three walls tall, at least
  2.5 walls from the next, drafted 0.5 degree or more, with a fillet of a quarter of the rib's own
  thickness at its root. Run a rib well into the wall it meets or stop it clear: a square end a hair off
  a drafted wall is a crevice no steel fills (`crevices`). A boss is a drafted tube whose wall is 60% of the base wall at most, its hole
  along the pull, a fillet at the root (a sharp root is `molding.boss_root_fillet`, a warning) and
  gussets to the wall rather than a thick foot. A snap arm is a rib with a barb: the check reads it as a
  snap (`kind: snap`, at least half the wall thick, Hubs) and its barb as the undercut it is.
- **Corners.** Inside radius at least half the wall, outside radius the inside plus the wall, so the
  thickness stays constant around the corner. Fillet the cavity's vertical edges and its floor edges.
- **Undercuts.** A feature that will not pull straight -- a side hole, a snap hook, a lip under a rim --
  takes a side action or a lifter (a warning, a cost) and one nothing frees is an error: avoid it, or
  plan the action with the person.
- The resin and the process on the part: `part.material = plastics.abs_(process=molded())`
  (`bd_materials.processes`); `cad model dfm "$ID" --pull z` then needs no `--process` or `--material`.

## Check it

```bash
cad step dfm cover.step --process molding --pull z --material abs
cad model dfm "$ID" --process molding --pull y --material pc --cavities 4
cad step dfm cover.step --process molding --candidates
```

Molding is judged on exact geometry alone: a mesh (STL, 3MF, GLB) is refused -- check the STEP or the
model it came from.

The options that change the verdicts:

- `--pull`: the confirmed pull, an axis (`z`, `-y`) or `x,y,z` components; `z` by default, and the
  result then says it measured "the default pull". Draft and undercuts are relative to it, and the part
  is measured along it as it stands: a part modelled tilted against the pull is measured tilted. Every
  check of one part asks whether another pull does better and warns, naming it (`pull_better`, its hint
  the `--pull` to try). Without a confirmed pull, rank the pulls with `--candidates` (it judges
  nothing) and report draft as unverified rather than failing every vertical-looking face.
- `--material`: the resin's wall range and clamp factor. Without it the resin's recommended range is not
  evaluated (`resin_unknown`), and a wall fails only outside every resin's range (under 0.5 mm, over
  25.4 mm).
- `--cavities`: the clamp-force estimate.
- `--wall-limit` (45 degrees: a face steeper from the pull is no wall) and `--zero-tol` (0.05
  degrees: under it is zero draft).

**What fails a part.** A warning is a published guide's recommendation broken: the part is made, at a
cost or a risk. An error is a floor -- it cannot be molded as drawn, or a general shop sends it back:

| error | the floor | whose |
|---|---|---|
| `molding.undercut_unreleasable` | a feature no slide, lifter or core frees | geometry |
| `molding.draft_zero` | no draft at all (under `--zero-tol`) on a wall or a rib deeper than 10 mm | text-to-cad's own |
| `molding.wall_too_thin` | a wall under half the resin's recommended minimum (no resin named: under 0.5 mm) | text-to-cad's own |
| `molding.wall_too_thick` | a wall over twice the resin's recommended maximum (no resin named: over 25.4 mm) | text-to-cad's own |

The guides only recommend (0.5 to 2 degrees, a wall range by resin), so the last three cite text-to-cad,
never a publisher: say so when you report one, and do not quote it as Protolabs' or Hubs' limit.

The rules are general, no shop's: a press's and a mold's own limits -- projected area, part size,
depth from the parting line, shot volume, a side action's travel -- are compared with the measurements
(`projection`, `envelope`, `undercuts`) and the clamp estimate. A STEP, an xbf or a model is measured
exactly and each item names a face ref; prefer it to a mesh.

## Read it

The families: `draft`, `undercuts`, `thickness`, `transitions`, `ribs`, `bosses`, `corners`, `projection`,
`envelope`, `parting`, `clamp`, `pull_check`; `pulls` with `--candidates`.

- `draft` items carry `draft_deg` and `opens` (`+pull`, `-pull`, `none` for zero draft, `split` where
  the parting crosses the face). Faces square to the pull are not walls and appear in no draft figure.
- `undercuts` items carry the `release` each needs: `side_action` (its `side_actions`: the slide's
  direction, the feature's own axis where it has one, `angled` where it leaves the parting plane, and
  its `stroke_mm`), `lifter`, `collapsible_core`, `bump_off`, or `none`; its `kind` (`external`: a slide
  reaches it from beside the part; `internal`: a lifter's or a core's); and how deep it is (`depth_mm`
  against the straight pull; `slide_depth_mm` against the best slide where nothing frees it). Budget
  side actions from `undercuts.side_action_count` and `side_action_directions`: the part's distinct
  slide directions (three slots along +y are one slide), not its count of features.
  `molding.undercut` (a warning) is tooling cost and says what releases the feature;
  `molding.undercut_bump_off` (a warning) is a lip of 0.1 mm or less (text-to-cad's own figure) stripped
  off as the part ejects -- it needs a flexible resin and a rounded lead-in; `molding.undercut_unreleasable`
  (an error) is a feature no action tried frees, its lip deeper than that. Distinguish a need for side
  actions from impossibility.
- `thickness.nominal_mm` and `thick_sections` (a face's `feature` says whether it is a wall's, a rib's or
  a boss's: the wall range judges walls alone); `transitions` (a step between two walls read on its
  stepped side, `basis: step`: its run over its change, `min_mm`, `max_mm`, the two points in `at_xyz`,
  judged by `molding.wall_transition`; a free-form face's from the rolling ball, `basis: ball`); `ribs`
  (`kind` rib or snap) and `bosses` as ratios to the wall they stand on; `corners` as radius over the
  wall. These are sink and stress signals, not a fill simulation. Walls drafted with `extrude(taper=...)`
  are B-splines that the check reads as the planes and cylinders they are.
- `parting.flat_parting_possible`, and `stepped_parting` where it is not.
- `clamp` is an estimate (`clamp_estimate`): the part's projected area alone, no runner, at a molder's
  factor for the resin.
- Several bodies (`several_bodies`) are an assembly: each body is checked on its own. Say so rather
  than reviewing an assembly as a part. A part of several solids gets the same warning: a component
  model whose contacts sit inside its housing reads its pins as walls and ribs and its slots as
  undercuts, so check the housing alone (one fused solid gives no such signal: say so).

`pull_better` (a warning) says another pull does better than the one measured -- it traps no more,
needs no more actions, leaves no more wall without draft and steps the parting no more, and is better
in one of them -- and names it with its axis: confirm the pull (`--pull` with that axis, or the
mold's own) before budgeting side actions or drafting walls. `pull_check.chosen` is the measured
pull's own figures and `pull_check.candidates` what each other pull was read to. No `pull_better` is not
a confirmed pull: the check compares x, y, z and the part's principal axes, no others.

Three more findings say what was not judged; none is a pass. `crevices` (info): two faces closer than
steel can stand between them (a rib's end a hair off a wall), no undercut -- join them or part them.
`undercuts_unsearched` (a warning): undercuts whose release the search did not reach; whether a slide
frees them is not known. `occurrences_measured_once` (a warning): a part that occurs several times in an
assembly is measured where its first occurrence stands; check the part on its own.

## Review the part

Collect resin grade and filler, nominal wall, pull direction, proposed parting line, textured and
cosmetic faces, critical fits, and tooling constraints. Then check by hand what the check does not
measure:

- Texture draft, extra draft on tall features, shut-off draft; core and cavity sides separately.
- Stripping undercuts, snap-fit and living-hinge proportions, threads, a boss against its screw.
- The withdrawal path and the slide's own clearance: a side action's stroke is to where its points
  clear the part along the pull. The undercut test samples points, so a feature smaller than their
  spacing can be missed.
- Gate, vent, weld lines, packing, cooling, shrinkage and warpage: tooling questions, never a
  validated cycle time. Do not rescale the part for shrinkage without the toolmaker's assumptions.
- Preserve mating faces and functional dimensions when proposing draft or coring: say which datum
  stays fixed and whether the change adds or removes material.

This workflow reviews conventional thermoplastic injection molding. For silicone, overmolding or
insert molding, obtain applicable guidance rather than reusing thermoplastic limits.

## Worked reasoning example

The following numbers are illustrative inputs, not default process limits.

`molding.draft_min at cover/face 4: wall draft 0 deg is under the 0.5 deg recommended minimum`, along
the confirmed `--pull z`, on a wall 6 mm deep. A recommendation, not a limit: report the wall as at risk
of sticking and scuffing and propose at least the rule's draft, more if the selected texture needs it,
keeping the mating face fixed. The same wall 25 mm deep is `molding.draft_zero`, an error: the part goes
back for draft, and the report says the 10 mm floor is text-to-cad's own, no guide's. Along an
unconfirmed pull, report either figure as unverified.
