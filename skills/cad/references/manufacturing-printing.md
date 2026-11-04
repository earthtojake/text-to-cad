# 3D printing

The evidence, the rules, the review and how to check a redesign are SKILL.md's
[Can it be made?](../SKILL.md#can-it-be-made), the same for every process; this is what is particular
to additive processes.

Slicing and sending a print to a printer is the print3d skill's ($print3d).

## Check it

```bash
cad stl dfm stand.stl --process printing --technology fdm --material petg
cad model dfm "$ID" --process printing --technology sla --build-volume 145x145x185
cad step dfm housing.step --process printing --technology fdm --layer-height 0.12 --candidates
```

The check measures the part as it stands on the plate: its lowest point, Z up. The options that change
the verdicts:

- `--technology fdm|sls|sla|mjf|pbf` (`fdm` by default; `pbf` is metal powder bed fusion): every limit
  and the self-supporting angle are the technology's. A technology the set has no figure for leaves
  that rule not evaluated. With the process unknown, check each candidate and report per technology.
- `--material`: FDM's warping risk for the materials that warp (`warping_risk`).
- `--build-volume XxYxZ`: the person's printer, else the rule set's machine for the technology.
- `--layer-height` and `--nozzle` (FDM): stair-stepping and fine detail.
- `--angle-limit`: overrides the technology's self-supporting angle, from the person's datasheet.
- `--units` (an STL's: millimetres by default) and `--samples` (rays on a mesh).

Rule sets: `generic`, `hubs`, `protolabs`, `xometry`. `--candidates` ranks the six axis orientations,
plus the largest flat faces laid down, by support, height and finish, and judges nothing: to check
another orientation, turn the part in its model and check again.

## Read it

The families: `solid` (a mesh's `mesh`), `overhangs`, `bridges`, `wall_thickness`, `knife_edges`, `gaps`, `holes`,
`pins`, `details`, `clearances`, `trapped_volumes`, `build_volume`, `bed`, `stair_stepping`,
`support_volume`, `sections`; `orientations` with `--candidates`.

- Report `not_watertight` or `not_sound` first: it blocks slicing for every technology.
- Walls are `supported` (joined to the part on two sides or more) or not, each with its own minimum.
  A mesh cannot say which, so it is judged against the supported minimum (`printing.wall`).
- `printing.knife_edge` is a convex edge under 45 degrees of material, which thins to nothing:
  `thin_depth_mm` says how far in it stays under the minimum wall. Blunt it, chamfer it at 45 degrees
  or more, or move the cut that made it.
- The powder processes (SLS, MJF) need no support: their overhangs are facts, not verdicts, and
  trapped powder and its escape holes (`trapped_volumes`) are the check instead. A sealed cavity in
  SLA traps resin; in FDM it prints as infill (`internal_void`).
- `support_volume` is a column fill to the plate or the part: a coarse upper bound, a cost and finish
  signal, not a failure unless the person set a budget.
- `clearances` measures each pair of parts in an assembly, and walls are per part: attribute a thin
  wall to its part, never to a fit gap between two.
- On a mesh, holes, pins and embossed or engraved detail are not measured (no axes or faces): their
  rules are not evaluated, so check the STEP or the model. When `scale.units_suspect` is true, report
  a units finding and ask before comparing anything.

## Review the part

Collect the technology, material, layer height, and any machine or material datasheet; a datasheet
overrides the rule set: cite whichever is used. Check the exact file that will be sliced, or the
model's document. Then check by hand what the check does not measure:

- Tree supports, support density and the designer's cosmetic faces (the check calls a face cosmetic
  by its size).
- Escape-hole sizes on a mesh, and openings other than round holes, are estimates; cavities smaller
  than the probing ball are found only when sealed.
- Lattices, minimum feature by local curvature, text legibility, tolerance stack-ups and residual
  stress beyond the largest cross-section.
- FDM horizontal holes are judged as bridges, not against a teardrop diameter.

For every fail, give a concrete, plain-language instruction with target numbers from the hint (for
example "thicken the wall at housing/face 8 from 0.3 mm to at least 1 mm"). When the model's source can
be edited, offer to apply it and check the regenerated part again, until no error remains.
