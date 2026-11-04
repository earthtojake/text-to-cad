# Injection molding

The evidence, the rules, the review and how to check a redesign are SKILL.md's
[Can it be made?](../SKILL.md#can-it-be-made), the same for every process; this is what is particular
to injection molding.

## Check it

```bash
cad step dfm cover.step --process molding --pull z --material abs
cad model dfm "$ID" --process molding --pull y --material pc --cavities 4 --rules protolabs
cad step dfm cover.step --process molding --candidates
cad stl dfm cover.stl --process molding --pull z --units mm
```

The options that change the verdicts:

- `--pull`: the confirmed pull, an axis (`z`, `-y`) or `x,y,z` components; `z` by default. Draft and
  undercuts are relative to it. Without a confirmed pull, rank the pulls with `--candidates` (it
  judges nothing) and report draft as unverified rather than failing every vertical-looking face.
- `--material`: the resin's wall range and clamp factor. Without it the wall-range rules are not
  evaluated (`resin_unknown`).
- `--cavities`: the clamp-force estimate.
- `--wall-limit` (45 degrees: a face steeper from the pull is no wall) and `--zero-tol` (0.05
  degrees: under it is zero draft).

Rule sets: `generic`, `protolabs`, `hubs`, `xometry`. A STEP, an xbf or a model is measured exactly
and each item names a face ref; prefer it to a mesh.

## Read it

The families: `draft`, `undercuts`, `thickness`, `ribs`, `bosses`, `corners`, `projection`,
`envelope`, `parting`, `clamp`; `pulls` with `--candidates`.

- `draft` items carry `draft_deg` and `opens` (`+pull`, `-pull`, `none` for zero draft, `split` where
  the parting crosses the face). Faces square to the pull are not walls and appear in no draft figure.
- `undercuts` items carry the `release` each needs: `side_action`, `lifter`, `collapsible_core`, or
  `none`. `molding.undercut` (a warning) is tooling cost; `molding.undercut_unreleasable` (an error)
  is a feature no action tried frees. Distinguish a need for side actions from impossibility.
- `thickness.nominal_mm` and `thick_sections`; `ribs` and `bosses` as ratios to the wall they stand
  on; `corners` as radius over the wall. These are sink and stress signals, not a fill simulation.
- `parting.flat_parting_possible`, and `stepped_parting` where it is not.
- `clamp` is an estimate (`clamp_estimate`): the part's projected area alone, no runner, at a molder's
  factor for the resin.
- Several bodies (`several_bodies`) are an assembly: each body is checked on its own. Say so rather
  than reviewing an assembly as a part.

On a mesh: an STL has no units, so give `--units` and compare `scale.bbox_mm_if_units` with the part
you expect. A curved face's draft reads low by up to its `spread_deg` (`coarse_curved_face`: measure a
finer mesh before citing it); fillets are not seen, so filleted corners and rib roots merge; bosses
are found only along the pull.

## Review the part

Collect resin grade and filler, nominal wall, pull direction, proposed parting line, textured and
cosmetic faces, critical fits, and tooling constraints. Then check by hand what the check does not
measure:

- Texture draft, extra draft on tall features, shut-off draft; core and cavity sides separately.
- Stripping undercuts, snap-fit and living-hinge proportions, threads, a boss against its screw.
- The withdrawal path and the slide's own clearance: a side action's stroke is to where the pull
  clears. The undercut test samples points, so a feature smaller than their spacing can be missed.
- Gate, vent, weld lines, packing, cooling, shrinkage and warpage: tooling questions, never a
  validated cycle time. Do not rescale the part for shrinkage without the toolmaker's assumptions.
- Preserve mating faces and functional dimensions when proposing draft or coring: say which datum
  stays fixed and whether the change adds or removes material.

This workflow reviews conventional thermoplastic injection molding. For silicone, overmolding or
insert molding, obtain applicable guidance rather than reusing thermoplastic limits.

## Worked reasoning example

The following numbers are illustrative inputs, not default process limits.

`molding.draft_min at cover/face 4: wall draft 0 deg is under the 0.5 deg minimum`, along the
confirmed `--pull z`. Report the wall as fail and propose at least the rule's draft, more if the
selected texture needs it, keeping the mating face fixed. Along an unconfirmed pull, report the same
figure as unverified.
